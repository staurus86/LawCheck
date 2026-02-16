#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API для проверки текста на соответствие закону №168-ФЗ
УЛУЧШЕННАЯ ВЕРСИЯ с максимальным функционалом
"""

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
import os
from datetime import datetime
from checker import RussianLanguageChecker
import requests
from bs4 import BeautifulSoup
import io
import json
import uuid
import base64
import time
from collections import defaultdict

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max request size
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.getenv('SECRET_KEY', 'change-this-secret-key'))
OCR_TIMEOUT = int(os.getenv('OCR_TIMEOUT', '30'))
OPENAI_OCR_BASE_URL = os.getenv('OPENAI_OCR_BASE_URL', 'https://api.openai.com/v1').strip()
GOOGLE_VISION_BASE_URL = os.getenv('GOOGLE_VISION_BASE_URL', 'https://vision.googleapis.com/v1').strip()
OCRSPACE_BASE_URL = os.getenv('OCRSPACE_BASE_URL', 'https://api.ocr.space').strip()
# CORS - разрешаем все домены
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Lazy initialization - checker будет создан при первом запросе
checker = None

def get_checker():
    """Get or create checker instance with lazy initialization"""
    global checker
    if checker is None:
        import time
        print("[INFO] Initializing RussianLanguageChecker...")
        start_time = time.time()
        checker = RussianLanguageChecker()
        elapsed = time.time() - start_time
        print(f"[OK] Checker initialized in {elapsed:.2f}s")
    return checker

# Хранилище истории проверок (в продакшене используйте Redis/Database)
check_history = []
statistics = {
    'total_checks': 0,
    'total_violations': 0,
    'most_common_violations': defaultdict(int)
}

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/about')
def about():
    """Страница о законе"""
    return render_template('about.html')

@app.route('/api-docs')
def api_docs():
    """API документация"""
    return render_template('api_docs.html')

@app.route('/examples')
def examples():
    """Примеры использования"""
    return render_template('examples.html')
    
@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - используем data URI в HTML

def _mask_token(token):
    if not token:
        return ''
    if len(token) <= 8:
        return '*' * len(token)
    return f"{token[:4]}...{token[-4:]}"


def _extract_data_url_payload(image_data_url):
    if not image_data_url or ';base64,' not in image_data_url:
        raise ValueError('Invalid image data URL')
    return image_data_url.split(';base64,', 1)[1]


def _extract_openai_text(response_json):
    if isinstance(response_json.get('output_text'), str) and response_json.get('output_text').strip():
        return response_json['output_text'].strip()
    chunks = []
    for output_item in response_json.get('output', []):
        for content_item in output_item.get('content', []):
            if content_item.get('type') in ('output_text', 'text'):
                text_value = content_item.get('text', '')
                if text_value:
                    chunks.append(text_value)
    return '\n'.join(chunks).strip()


def _ocr_openai(api_key, model, image_url=None, image_data_url=None):
    input_image = image_url or image_data_url
    if not input_image:
        raise ValueError('Pass image_url or image_data_url')
    payload = {
        'model': model or 'gpt-4.1-mini',
        'input': [{
            'role': 'user',
            'content': [
                {'type': 'input_text', 'text': 'Extract all text from this image and return plain raw OCR text only. Do not edit, normalize, translate, summarize, censor, or correct anything. Preserve original wording, casing, punctuation, numbers, and line breaks exactly as recognized.'},
                {'type': 'input_image', 'image_url': input_image}
            ]
        }]
    }
    response = requests.post(
        f"{OPENAI_OCR_BASE_URL.rstrip('/')}/responses",
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload,
        timeout=OCR_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    return _extract_openai_text(data), data


def _ocr_google(api_key, model, image_url=None, image_data_url=None):
    feature_type = model or 'DOCUMENT_TEXT_DETECTION'
    image_block = {}
    if image_data_url:
        image_block['content'] = _extract_data_url_payload(image_data_url)
    elif image_url:
        image_block['source'] = {'imageUri': image_url}
    else:
        raise ValueError('Pass image_url or image_data_url')
    payload = {'requests': [{'image': image_block, 'features': [{'type': feature_type}]}]}
    response = requests.post(
        f"{GOOGLE_VISION_BASE_URL.rstrip('/')}/images:annotate?key={api_key}",
        headers={'Content-Type': 'application/json'},
        json=payload,
        timeout=OCR_TIMEOUT
    )
    response.raise_for_status()
    data = response.json()
    first = (data.get('responses') or [{}])[0]
    text = (
        (first.get('fullTextAnnotation') or {}).get('text')
        or ((first.get('textAnnotations') or [{}])[0].get('description') if first.get('textAnnotations') else '')
        or ''
    )
    return text.strip(), data


def _ocr_ocrspace(api_key, model, image_url=None, image_data_url=None):
    data = {'language': model or 'rus', 'isOverlayRequired': 'false', 'OCREngine': '2'}
    files = None
    if image_data_url:
        file_bytes = base64.b64decode(_extract_data_url_payload(image_data_url))
        files = {'file': ('image.png', file_bytes)}
    elif image_url:
        data['url'] = image_url
    else:
        raise ValueError('Pass image_url or image_data_url')
    response = requests.post(
        f"{OCRSPACE_BASE_URL.rstrip('/')}/parse/image",
        headers={'apikey': api_key},
        data=data,
        files=files,
        timeout=OCR_TIMEOUT
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('IsErroredOnProcessing'):
        raise ValueError('; '.join(payload.get('ErrorMessage') or ['OCR.Space error']))
    parsed = payload.get('ParsedResults') or []
    text_parts = [item.get('ParsedText', '') for item in parsed if item.get('ParsedText')]
    return '\n'.join(text_parts).strip(), payload


def _extract_ocr_usage(provider, raw_response):
    if not isinstance(raw_response, dict):
        return {}
    if provider == 'openai':
        usage = raw_response.get('usage') or {}
        return {
            'input_tokens': usage.get('input_tokens'),
            'output_tokens': usage.get('output_tokens'),
            'total_tokens': usage.get('total_tokens')
        }
    if provider == 'google':
        first = (raw_response.get('responses') or [{}])[0]
        pages = ((first.get('fullTextAnnotation') or {}).get('pages') or [])
        text_annotations = first.get('textAnnotations') or []
        return {'pages_detected': len(pages), 'text_annotations': len(text_annotations)}
    if provider == 'ocrspace':
        parsed = raw_response.get('ParsedResults') or []
        processing_ms = None
        if parsed:
            value = parsed[0].get('ProcessingTimeInMilliseconds')
            try:
                processing_ms = int(float(value))
            except (TypeError, ValueError):
                processing_ms = None
        return {'parsed_results': len(parsed), 'processing_ms': processing_ms}
    return {}

# ==================== API ENDPOINTS ====================

@app.route('/api/check', methods=['POST'])
def check_text():
    """API: Проверка текста"""
    try:
        data = request.json
        text = data.get('text', '')
        save_history = data.get('save_history', True)
        
        if not text or not text.strip():
            return jsonify({'error': 'Текст не предоставлен'}), 400
        
        result = get_checker().check_text(text)
        
        # Добавляем рекомендации
        result['recommendations'] = generate_recommendations(result)
        
        # Сохраняем в историю
        if save_history:
            save_to_history('text', result, text[:100])
        
        # Обновляем статистику
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'result': result,
            'timestamp': datetime.now().isoformat(),
            'check_id': str(uuid.uuid4())
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-url', methods=['POST'])
def check_url():
    """API: Проверка URL"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url or not url.startswith('http'):
            return jsonify({'error': 'Некорректный URL'}), 400
        
        # Загрузка страницы
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем ненужное
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # Извлекаем текст и мета-информацию
        text = soup.get_text(separator=' ', strip=True)
        title = soup.find('title')
        title_text = title.get_text() if title else 'Без названия'
        
        result = get_checker().check_text(text)
        result['page_title'] = title_text
        result['recommendations'] = generate_recommendations(result)
        
        # Сохраняем в историю
        save_to_history('url', result, url)
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'url': url,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """API: Пакетная проверка"""
    try:
        data = request.json
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'Список URL пуст'}), 400
        
        results = []
        for url in urls[:50]:  # Лимит 50 URL за раз
            try:
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0'
                })
                soup = BeautifulSoup(response.text, 'html.parser')
                for tag in soup(['script', 'style']):
                    tag.decompose()
                text = soup.get_text(separator=' ', strip=True)
                result = get_checker().check_text(text)
                
                results.append({
                    'url': url,
                    'success': True,
                    'result': result
                })
                
            except Exception as e:
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'total': len(urls),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/deep-check', methods=['POST'])
def deep_check():
    """API: Глубокая проверка слов с использованием морфологии и speller"""
    try:
        data = request.json
        words = data.get('words', [])
        
        if not words:
            return jsonify({'error': 'Список слов пуст'}), 400
        
        checker_instance = get_checker()
        results = []
        
        for word in words:
            result = checker_instance._deep_check_single(word)
            results.append(result)
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API: Статистика словарей"""
    try:
        c = get_checker()
        stats_data = {
            'normative': len(c.normative_words),
            'foreign': len(c.foreign_allowed),
            'nenormative': len(c.nenormative_words),
            'abbreviations': len(c.abbreviations),
            'morph_available': c.morph is not None
        }
        
        return jsonify(stats_data)
    
    except Exception as e:
        return jsonify({
            'normative': 0,
            'foreign': 0,
            'nenormative': 0,
            'abbreviations': 0,
            'morph_available': False,
            'error': str(e)
        }), 500

@app.route('/api/check-word', methods=['POST'])
def check_word():
    """API: Проверка одного слова"""
    try:
        data = request.json
        word = data.get('word', '').strip()
        
        if not word:
            return jsonify({'error': 'Слово не предоставлено'}), 400
        
        if len(word) < 2:
            return jsonify({'error': 'Слишком короткое слово (минимум 2 символа)'}), 400
        
        checker_instance = get_checker()
        
        word_lower = word.lower()
        word_upper = word.upper()
        word_title = word.title()
        
        is_normative = (
            word_lower in checker_instance.normative_words or
            word_upper in checker_instance.normative_words or
            word_title in checker_instance.normative_words
        )
        
        is_foreign = (
            word_lower in checker_instance.foreign_allowed or
            word_upper in checker_instance.foreign_allowed or
            word_title in checker_instance.foreign_allowed
        )
        
        is_nenormative = (
            word_lower in checker_instance.nenormative_words or
            word_upper in checker_instance.nenormative_words or
            word_title in checker_instance.nenormative_words
        )
        
        import re
        has_latin = bool(re.search(r'[a-zA-Z]', word))
        
        is_abbreviation = False
        abbreviation_translation = None
        if word in checker_instance.abbreviations:
            is_abbreviation = True
            abbreviation_translation = checker_instance.abbreviations[word]
        
        is_unknown = not is_normative and not is_foreign and not is_nenormative
        
        is_potential_fine = is_unknown and not is_foreign
        
        result = {
            'word': word,
            'is_normative': is_normative,
            'is_foreign': is_foreign,
            'is_nenormative': is_nenormative,
            'has_latin': has_latin,
            'is_abbreviation': is_abbreviation,
            'abbreviation_translation': abbreviation_translation,
            'is_unknown': is_unknown,
            'is_potential_fine': is_potential_fine,
            'status': 'ok' if is_normative else ('warning' if is_foreign else 'danger')
        }
        
        return jsonify({
            'success': True,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/images/token', methods=['GET', 'POST'])
def image_api_token():
    try:
        provider = (request.args.get('provider') or '').strip().lower()
        if request.method == 'GET':
            provider = provider or (session.get('images_provider') or 'openai')
            tokens = session.get('image_api_tokens', {})
            token = tokens.get(provider, '')
            return jsonify({'success': True, 'provider': provider, 'has_token': bool(token), 'token_masked': _mask_token(token) if token else None})

        data = request.get_json(silent=True) or {}
        provider = (data.get('provider') or provider or 'openai').strip().lower()
        token = (data.get('token') or '').strip()
        if provider not in ('openai', 'google', 'ocrspace'):
            return jsonify({'error': 'Unsupported provider'}), 400
        if not token:
            return jsonify({'error': 'Token is required'}), 400

        tokens = session.get('image_api_tokens', {})
        tokens[provider] = token
        session['image_api_tokens'] = tokens
        session['images_provider'] = provider
        session.modified = True

        return jsonify({'success': True, 'provider': provider, 'token_masked': _mask_token(token)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images/ocr', methods=['POST'])
def image_ocr():
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}
        provider = (data.get('provider') or session.get('images_provider') or 'openai').strip().lower()
        model = (data.get('model') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        image_data_url = (data.get('image_data_url') or '').strip()

        if provider not in ('openai', 'google', 'ocrspace'):
            return jsonify({'error': 'Unsupported provider'}), 400

        token = (session.get('image_api_tokens', {}).get(provider) or '').strip()
        if not token:
            return jsonify({'error': f'Set API token first for provider={provider}'}), 401
        if not image_url and not image_data_url:
            return jsonify({'error': 'Pass image_url or image_data_url'}), 400

        ocr_started = time.perf_counter()
        if provider == 'openai':
            extracted_text, raw_response = _ocr_openai(token, model, image_url=image_url, image_data_url=image_data_url)
        elif provider == 'google':
            extracted_text, raw_response = _ocr_google(token, model, image_url=image_url, image_data_url=image_data_url)
        else:
            extracted_text, raw_response = _ocr_ocrspace(token, model, image_url=image_url, image_data_url=image_data_url)
        ocr_elapsed_ms = round((time.perf_counter() - ocr_started) * 1000, 2)

        if not extracted_text.strip():
            return jsonify({'error': 'OCR returned empty text'}), 422

        resolved_model = model or ('gpt-4.1-mini' if provider == 'openai' else 'DOCUMENT_TEXT_DETECTION' if provider == 'google' else 'rus')
        ocr_payload = {
            'provider': provider,
            'model': resolved_model,
            'source': image_url if image_url else 'uploaded_file',
            'text_length': len(extracted_text),
            'timings_ms': {
                'ocr': ocr_elapsed_ms,
                'total': round((time.perf_counter() - started_at) * 1000, 2)
            },
            'usage': _extract_ocr_usage(provider, raw_response),
            'raw_preview': str(raw_response)[:1500]
        }

        return jsonify({
            'success': True,
            'provider': provider,
            'source_url': image_url,
            'extracted_text': extracted_text,
            'ocr': ocr_payload,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/images/check', methods=['POST'])
def check_images():
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}
        provider = (data.get('provider') or session.get('images_provider') or 'openai').strip().lower()
        model = (data.get('model') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        image_data_url = (data.get('image_data_url') or '').strip()

        if provider not in ('openai', 'google', 'ocrspace'):
            return jsonify({'error': 'Unsupported provider'}), 400

        token = (session.get('image_api_tokens', {}).get(provider) or '').strip()
        if not token:
            return jsonify({'error': f'Set API token first for provider={provider}'}), 401
        if not image_url and not image_data_url:
            return jsonify({'error': 'Pass image_url or image_data_url'}), 400

        ocr_started = time.perf_counter()
        if provider == 'openai':
            extracted_text, raw_response = _ocr_openai(token, model, image_url=image_url, image_data_url=image_data_url)
        elif provider == 'google':
            extracted_text, raw_response = _ocr_google(token, model, image_url=image_url, image_data_url=image_data_url)
        else:
            extracted_text, raw_response = _ocr_ocrspace(token, model, image_url=image_url, image_data_url=image_data_url)
        ocr_elapsed_ms = round((time.perf_counter() - ocr_started) * 1000, 2)

        if not extracted_text.strip():
            return jsonify({'error': 'OCR returned empty text'}), 422

        check_started = time.perf_counter()
        result = get_checker().check_text(extracted_text)
        check_elapsed_ms = round((time.perf_counter() - check_started) * 1000, 2)

        result['recommendations'] = generate_recommendations(result)
        resolved_model = model or ('gpt-4.1-mini' if provider == 'openai' else 'DOCUMENT_TEXT_DETECTION' if provider == 'google' else 'rus')
        result['ocr'] = {
            'provider': provider,
            'model': resolved_model,
            'source': image_url if image_url else 'uploaded_file',
            'text_length': len(extracted_text),
            'timings_ms': {
                'ocr': ocr_elapsed_ms,
                'text_check': check_elapsed_ms,
                'total': round((time.perf_counter() - started_at) * 1000, 2)
            },
            'usage': _extract_ocr_usage(provider, raw_response),
            'raw_preview': str(raw_response)[:1500]
        }
        result['source_url'] = image_url
        result['source_type'] = 'image'
        result['extracted_text'] = extracted_text

        update_statistics(result)
        save_to_history('image', result, image_url or 'uploaded_file')

        return jsonify({'success': True, 'provider': provider, 'result': result, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """API: История проверок"""
    limit = int(request.args.get('limit', 10))
    return jsonify({
        'history': check_history[-limit:][::-1],
        'total': len(check_history)
    })

@app.route('/api/export/txt', methods=['POST'])
def export_txt():
    """Экспорт отчета в TXT с полной информацией и правильной кодировкой"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Формируем улучшенный отчет
        lines = []
        lines.append("=" * 70)
        lines.append("ОТЧЕТ ПРОВЕРКИ ТЕКСТА НА СООТВЕТСТВИЕ ФЗ-168")
        lines.append("=" * 70)
        lines.append(f"Дата проверки: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"ID проверки: {str(uuid.uuid4())[:8]}")
        lines.append("")
        
        # Общая статистика
        lines.append("-" * 70)
        lines.append("ОБЩАЯ СТАТИСТИКА:")
        lines.append("-" * 70)
        lines.append(f"  Всего слов в тексте:     {result.get('total_words', 0)}")
        lines.append(f"  Уникальных слов:         {result.get('unique_words', 0)}")
        lines.append(f"  Нарушений найдено:       {result.get('violations_count', 0)}")
        lines.append("")
        
        # Детальная статистика по категориям
        lines.append("-" * 70)
        lines.append("ДЕТАЛЬНАЯ СТАТИСТИКА:")
        lines.append("-" * 70)
        lines.append(f"  ✅ Нормативные слова:   {result.get('normative_count', result.get('total_words', 0) - result.get('violations_count', 0))}")
        lines.append(f"  🌍 Иностранные слова:   {result.get('foreign_count', result.get('latin_count', 0))}")
        lines.append(f"  🚫 Ненормативная лексика: {result.get('nenormative_count', 0)}")
        lines.append(f"  ✏️ Орфографические:      {result.get('orfograf_count', 0)}")
        lines.append(f"  🔊 Орфоэпические:        {result.get('orfoep_count', 0)}")
        lines.append(f"  ❓ Неизвестные слова:    {result.get('unknown_count', 0)}")
        lines.append("")
        
        # Процент соответствия
        compliance = result.get('compliance_percentage', 0)
        if result.get('law_compliant', result.get('violations_count', 0) == 0):
            compliance = 100.0
            status = "✅ СООТВЕТСТВУЕТ"
        else:
            total = result.get('total_words', 1)
            violations = result.get('violations_count', 0)
            compliance = ((total - violations) / total) * 100 if total > 0 else 0
            status = "❌ НЕ СООТВЕТСТВУЕТ"
        
        lines.append("-" * 70)
        lines.append(f"СТАТУС: {status}")
        lines.append(f"ПРОЦЕНТ СООТВЕТСТВИЯ: {compliance:.2f}%")
        lines.append("-" * 70)
        lines.append("")
        
        # Найденные нарушения с детализацией
        has_violations = False
        
        # Ненормативная лексика
        nenormative_words = result.get('nenormative_words', [])
        if nenormative_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"🚫 НЕНОРМАТИВНАЯ ЛЕКСИКА ({len(nenormative_words)} слов):")
            lines.append("=" * 70)
            for i, word in enumerate(nenormative_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # Слова на латинице
        latin_words = result.get('latin_words', [])
        if latin_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"🌍 ИНОСТРАННЫЕ СЛОВА НА ЛАТИНИЦЕ ({len(latin_words)} слов):")
            lines.append("=" * 70)
            for i, word in enumerate(latin_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # Неизвестные/англицизмы
        unknown_cyrillic = result.get('unknown_cyrillic', [])
        if unknown_cyrillic:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"❓ АНГЛИЦИЗМЫ / НЕИЗВЕСТНЫЕ СЛОВА ({len(unknown_cyrillic)} слов):")
            lines.append("=" * 70)
            for i, word in enumerate(unknown_cyrillic, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # Орфографические ошибки
        orfograf_words = result.get('orfograf_words', [])
        if orfograf_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"✏️ ОРФОГРАФИЧЕСКИЕ ОШИБКИ ({len(orfograf_words)} слов):")
            lines.append("=" * 70)
            for i, word in enumerate(orfograf_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # Орфоэпические ошибки
        orfoep_words = result.get('orfoep_words', [])
        if orfoep_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"🔊 ОРФОЭПИЧЕСКИЕ ОШИБКИ ({len(orfoep_words)} слов):")
            lines.append("=" * 70)
            for i, word in enumerate(orfoep_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        if not has_violations:
            lines.append("=" * 70)
            lines.append("✅ НАРУШЕНИЙ НЕ ОБНАРУЖЕНО")
            lines.append("=" * 70)
            lines.append("")
            lines.append("Текст полностью соответствует требованиям закона о русском языке.")
            lines.append("")
        
        # Рекомендации
        recommendations = result.get('recommendations', [])
        if recommendations:
            lines.append("=" * 70)
            lines.append("РЕКОМЕНДАЦИИ:")
            lines.append("=" * 70)
            for rec in recommendations:
                level = rec.get('level', 'info')
                icon = '🔴' if level == 'critical' else '🟡' if level == 'warning' else '🟢' if level == 'success' else 'ℹ️'
                lines.append(f"{icon} {rec.get('title', '')}")
                lines.append(f"   {rec.get('message', '')}")
                if rec.get('action'):
                    lines.append(f"   → Действие: {rec['action']}")
                lines.append("")
        
        # Подвал
        lines.append("=" * 70)
        lines.append("Создано: LawChecker Online")
        lines.append("Сайт: https://lawcheck-production.up.railway.app")
        lines.append("Закон: Федеральный закон №168-ФЗ «О русском языке»")
        lines.append("=" * 70)
        
        report = "\n".join(lines)
        
        # Создаем файл с BOM для Windows-совместимости
        output = io.BytesIO()
        output.write('\ufeff'.encode('utf-8'))  # UTF-8 BOM
        output.write(report.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/plain; charset=utf-8',
            as_attachment=True,
            download_name=f'lawcheck_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/json', methods=['POST'])
def export_json():
    """Экспорт отчета в JSON"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Добавляем метаданные
        result['exported_at'] = datetime.now().isoformat()
        result['tool'] = 'LawChecker Online'
        
        output = io.BytesIO()
        output.write(json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=f'lawcheck_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/batch-txt', methods=['POST'])
def export_batch_txt():
    """Экспорт пакетного отчета в TXT с детализацией всех нарушений"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        
        if not results:
            return jsonify({'error': 'Нет данных для экспорта'}), 400
        
        lines = []
        lines.append("=" * 80)
        lines.append("ПАКЕТНЫЙ ОТЧЕТ ПРОВЕРКИ САЙТОВ НА СООТВЕТСТВИЕ ФЗ-168")
        lines.append("=" * 80)
        lines.append(f"Дата проверки: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"Всего проверено сайтов: {len(results)}")
        lines.append("")
        
        # Общая сводка
        total_violations = 0
        total_sites_with_violations = 0
        total_critical = 0
        successful_checks = 0
        
        all_latin_words = set()
        all_unknown_words = set()
        all_nenormative_words = set()
        
        for item in results:
            if item.get('success') and item.get('result'):
                successful_checks += 1
                result = item['result']
                if not result.get('law_compliant', True):
                    total_sites_with_violations += 1
                    total_violations += result.get('violations_count', 0)
                    if result.get('nenormative_count', 0) > 0:
                        total_critical += 1
                    # Собираем все слова
                    all_latin_words.update(result.get('latin_words', []))
                    all_unknown_words.update(result.get('unknown_cyrillic', []))
                    all_nenormative_words.update(result.get('nenormative_words', []))
        
        lines.append("-" * 80)
        lines.append("ОБЩАЯ СВОДКА:")
        lines.append("-" * 80)
        lines.append(f"  ✅ Успешно проверено:     {successful_checks} сайтов")
        lines.append(f"  ❌ С нарушениями:         {total_sites_with_violations} сайтов")
        lines.append(f"  🚫 Критических (мат):     {total_critical} сайтов")
        lines.append(f"  📊 Всего нарушений:       {total_violations}")
        lines.append("")
        
        # Уникальные слова по всем сайтам
        if all_latin_words or all_unknown_words or all_nenormative_words:
            lines.append("-" * 80)
            lines.append("УНИКАЛЬНЫЕ НАРУШЕНИЯ ПО ВСЕМ САЙТАМ:")
            lines.append("-" * 80)
            lines.append("")
            
            if all_nenormative_words:
                lines.append(f"🚫 НЕНОРМАТИВНАЯ ЛЕКСИКА ({len(all_nenormative_words)} уникальных слов):")
                for i, word in enumerate(sorted(all_nenormative_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
            
            if all_latin_words:
                lines.append(f"🌍 ЛАТИНИЦА ({len(all_latin_words)} уникальных слов):")
                for i, word in enumerate(sorted(all_latin_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
            
            if all_unknown_words:
                lines.append(f"❓ АНГЛИЦИЗМЫ / НЕИЗВЕСТНЫЕ ({len(all_unknown_words)} уникальных слов):")
                for i, word in enumerate(sorted(all_unknown_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
        
        # Детализация по каждому сайту
        lines.append("=" * 80)
        lines.append("ДЕТАЛЬНЫЙ ОТЧЕТ ПО КАЖДОМУ САЙТУ:")
        lines.append("=" * 80)
        lines.append("")
        
        for i, item in enumerate(results, 1):
            url = item.get('url', 'Неизвестный URL')
            lines.append(f"{'─' * 80}")
            lines.append(f"[{i}] {url}")
            lines.append(f"{'─' * 80}")
            
            if not item.get('success'):
                lines.append(f"  ❌ ОШИБКА: {item.get('error', 'Неизвестная ошибка')}")
                lines.append("")
                continue
            
            result = item.get('result', {})
            
            # Статус
            if result.get('law_compliant', False):
                lines.append("  ✅ СТАТУС: Соответствует закону")
            else:
                lines.append(f"  ⚠️  СТАТУС: Нарушений: {result.get('violations_count', 0)}")
            
            lines.append(f"  📊 Слов в тексте: {result.get('total_words', 0)}")
            lines.append("")
            
            # Нарушения по категориям
            if result.get('nenormative_count', 0) > 0:
                lines.append(f"  🚫 НЕНОРМАТИВНАЯ ЛЕКСИКА ({result['nenormative_count']}):")
                for word in result.get('nenormative_words', []):
                    lines.append(f"      • {word}")
                lines.append("")
            
            if result.get('latin_count', 0) > 0:
                lines.append(f"  🌍 ЛАТИНИЦА ({result['latin_count']}):")
                for word in result.get('latin_words', []):
                    lines.append(f"      • {word}")
                lines.append("")
            
            if result.get('unknown_count', 0) > 0:
                lines.append(f"  ❓ АНГЛИЦИЗМЫ ({result['unknown_count']}):")
                for word in result.get('unknown_cyrillic', []):
                    lines.append(f"      • {word}")
                lines.append("")
        
        # Подвал
        lines.append("=" * 80)
        lines.append("Создано: LawChecker Online")
        lines.append("Сайт: https://lawcheck-production.up.railway.app")
        lines.append("Закон: Федеральный закон №168-ФЗ «О русском языке»")
        lines.append("=" * 80)
        
        report = "\n".join(lines)
        
        # Создаем файл с BOM для Windows-совместимости
        output = io.BytesIO()
        output.write('\ufeff'.encode('utf-8'))  # UTF-8 BOM
        output.write(report.encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/plain; charset=utf-8',
            as_attachment=True,
            download_name=f'lawcheck_batch_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def save_to_history(check_type, result, context):
    """Сохранение в историю"""
    check_history.append({
        'id': str(uuid.uuid4()),
        'type': check_type,
        'timestamp': datetime.now().isoformat(),
        'violations': result['violations_count'],
        'compliant': result['law_compliant'],
        'context': context
    })
    
    # Ограничиваем размер истории
    if len(check_history) > 1000:
        check_history.pop(0)

def update_statistics(result):
    """Обновление статистики"""
    statistics['total_checks'] += 1
    statistics['total_violations'] += result['violations_count']
    
    # Подсчет частых нарушений
    for word in result.get('latin_words', [])[:10]:
        statistics['most_common_violations'][word] += 1
    for word in result.get('unknown_cyrillic', [])[:10]:
        statistics['most_common_violations'][word] += 1

def generate_recommendations(result):
    """Генерация рекомендаций по исправлению"""
    recommendations = []
    
    if result.get('nenormative_count', 0) > 0:
        recommendations.append({
            'level': 'critical',
            'icon': '🚫',
            'title': 'Ненормативная лексика',
            'message': f"Обнаружено {result['nenormative_count']} слов ненормативной лексики. Это КРИТИЧЕСКОЕ нарушение закона.",
            'action': 'Замените или удалите все ненормативные выражения.'
        })
    
    if result.get('latin_count', 0) > 0:
        recommendations.append({
            'level': 'warning',
            'icon': '⚠️',
            'title': 'Латиница в тексте',
            'message': f"Найдено {result['latin_count']} слов на латинице.",
            'action': 'Замените английские слова на русские аналоги или добавьте пояснения в скобках.'
        })
    
    if result.get('unknown_count', 0) > 0:
        recommendations.append({
            'level': 'info',
            'icon': 'ℹ️',
            'title': 'Неизвестные слова',
            'message': f"Обнаружено {result['unknown_count']} потенциальных англицизмов или неизвестных слов.",
            'action': 'Проверьте корректность написания или используйте общепринятые термины.'
        })
    
    if result['law_compliant']:
        recommendations.append({
            'level': 'success',
            'icon': '✅',
            'title': 'Текст соответствует закону',
            'message': 'Нарушений не обнаружено. Текст полностью соответствует требованиям ФЗ №168.',
            'action': 'Можно публиковать без изменений.'
        })
    
    return recommendations

def get_word_suggestions(word):
    """Получение предложений по замене слова"""
    # Здесь можно добавить логику подбора синонимов
    suggestions = []
    
    # Простые примеры замен (расширьте под свои нужды)
    replacements = {
        'hello': 'привет',
        'world': 'мир',
        'computer': 'компьютер',
        'email': 'электронная почта',
        'internet': 'интернет',
        'software': 'программное обеспечение',
    }
    
    word_lower = word.lower()
    if word_lower in replacements:
        suggestions.append(replacements[word_lower])
    
    return suggestions if suggestions else ['Нет предложений']

def calculate_readability(text):
    """Расчет индекса читаемости"""
    words = text.split()
    sentences = [s for s in text.split('.') if s.strip()]
    
    if not words or not sentences:
        return 0
    
    avg_sentence_length = len(words) / len(sentences)
    avg_word_length = sum(len(w) for w in words) / len(words)
    
    # Простой индекс (чем меньше, тем лучше)
    readability = (avg_sentence_length * 0.5) + (avg_word_length * 2)
    
    return round(readability, 2)

def get_word_frequency(text):
    """Частотность слов"""
    words = text.lower().split()
    frequency = defaultdict(int)
    
    for word in words:
        if len(word) > 3:
            frequency[word] += 1
    
    return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:10])

def calculate_complexity(text):
    """Оценка сложности текста (0-100)"""
    words = text.split()
    
    if not words:
        return 0
    
    avg_word_length = sum(len(w) for w in words) / len(words)
    unique_words = len(set(words))
    lexical_diversity = unique_words / len(words)
    
    complexity = (avg_word_length * 10) + (lexical_diversity * 30)
    
    return min(100, round(complexity, 2))

def calculate_improvement(result1, result2):
    """Расчет процента улучшения"""
    if result1['violations_count'] == 0:
        return 0
    
    improvement = ((result1['violations_count'] - result2['violations_count']) / result1['violations_count']) * 100
    return round(improvement, 2)

def generate_text_report(result):
    """Генерация текстового отчета"""
    output = "="*100 + "\n"
    output += "ОТЧЁТ ПО ПРОВЕРКЕ ЗАКОНА О РУССКОМ ЯЗЫКЕ №168-ФЗ\n"
    output += f"Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    output += "="*100 + "\n\n"
    
    output += f"Всего слов: {result.get('total_words', 0)}\n"
    output += f"Уникальных слов: {result.get('unique_words', 0)}\n"
    output += f"Нарушений: {result.get('violations_count', 0)}\n\n"
    
    if result.get('law_compliant'):
        output += "✅ ТЕКСТ СООТВЕТСТВУЕТ ТРЕБОВАНИЯМ ЗАКОНА\n\n"
    else:
        output += f"⚠️ ОБНАРУЖЕНО НАРУШЕНИЙ: {result.get('violations_count', 0)}\n\n"
        
        if result.get('nenormative_count', 0) > 0:
            output += f"🚫 Ненормативная лексика: {result['nenormative_count']}\n"
        if result.get('latin_count', 0) > 0:
            output += f"⚠️ Латиница: {result['latin_count']}\n"
            for i, word in enumerate(result.get('latin_words', [])[:50], 1):
                output += f"  {i}. {word}\n"
            output += "\n"
        if result.get('unknown_count', 0) > 0:
            output += f"⚠️ Англицизмы: {result['unknown_count']}\n"
            for i, word in enumerate(result.get('unknown_cyrillic', [])[:50], 1):
                output += f"  {i}. {word}\n"
    
    return output

def generate_csv_report(result):
    """Генерация CSV отчета"""
    output = "Тип,Количество,Слова\n"
    
    output += f"Латиница,{result.get('latin_count', 0)},\"{', '.join(result.get('latin_words', [])[:20])}\"\n"
    output += f"Англицизмы,{result.get('unknown_count', 0)},\"{', '.join(result.get('unknown_cyrillic', [])[:20])}\"\n"
    output += f"Ненормативная,{result.get('nenormative_count', 0)},\"[скрыто]\"\n"
    
    return output

def generate_html_report(result):
    """Генерация HTML отчета"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Отчет проверки ФЗ №168</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 50px auto; padding: 20px; }}
            .header {{ background: #1976D2; color: white; padding: 20px; border-radius: 8px; }}
            .status {{ padding: 20px; margin: 20px 0; border-radius: 8px; text-align: center; font-size: 1.5rem; }}
            .success {{ background: #E8F5E9; color: #2E7D32; }}
            .error {{ background: #FFEBEE; color: #C62828; }}
            .violations {{ margin: 20px 0; }}
            .word-tag {{ display: inline-block; background: #FFF3E0; color: #E65100; 
                        padding: 5px 10px; margin: 5px; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🇷🇺 Отчет по проверке ФЗ №168</h1>
            <p>Создан: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="status {'success' if result.get('law_compliant') else 'error'}">
            {'✅ ТЕКСТ СООТВЕТСТВУЕТ ТРЕБОВАНИЯМ' if result.get('law_compliant') else f"⚠️ НАРУШЕНИЙ: {result.get('violations_count', 0)}"}
        </div>
        
        <div class="violations">
            <h2>Статистика:</h2>
            <p>Всего слов: {result.get('total_words', 0)}</p>
            <p>Уникальных: {result.get('unique_words', 0)}</p>
            <p>Латиница: {result.get('latin_count', 0)}</p>
            <p>Англицизмы: {result.get('unknown_count', 0)}</p>
            
            {f"<h3>Слова на латинице:</h3>" if result.get('latin_words') else ''}
            {''.join([f'<span class="word-tag">{w}</span>' for w in result.get('latin_words', [])[:50]])}
        </div>
    </body>
    </html>
    """
    return html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
