#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API РґР»СЏ РїСЂРѕРІРµСЂРєРё С‚РµРєСЃС‚Р° РЅР° СЃРѕРѕС‚РІРµС‚СЃС‚РІРёРµ Р·Р°РєРѕРЅСѓ в„–168-Р¤Р—
РЈР›РЈР§РЁР•РќРќРђРЇ Р’Р•Р РЎРРЇ СЃ РјР°РєСЃРёРјР°Р»СЊРЅС‹Рј С„СѓРЅРєС†РёРѕРЅР°Р»РѕРј
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
# CORS - СЂР°Р·СЂРµС€Р°РµРј РІСЃРµ РґРѕРјРµРЅС‹
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Lazy initialization - checker Р±СѓРґРµС‚ СЃРѕР·РґР°РЅ РїСЂРё РїРµСЂРІРѕРј Р·Р°РїСЂРѕСЃРµ
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

# РҐСЂР°РЅРёР»РёС‰Рµ РёСЃС‚РѕСЂРёРё РїСЂРѕРІРµСЂРѕРє (РІ РїСЂРѕРґР°РєС€РµРЅРµ РёСЃРїРѕР»СЊР·СѓР№С‚Рµ Redis/Database)
check_history = []
statistics = {
    'total_checks': 0,
    'total_violations': 0,
    'most_common_violations': defaultdict(int)
}

@app.route('/')
def index():
    """Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р°"""
    return render_template('index.html')

@app.route('/about')
def about():
    """РЎС‚СЂР°РЅРёС†Р° Рѕ Р·Р°РєРѕРЅРµ"""
    return render_template('about.html')

@app.route('/api-docs')
def api_docs():
    """API РґРѕРєСѓРјРµРЅС‚Р°С†РёСЏ"""
    return render_template('api_docs.html')

@app.route('/examples')
def examples():
    """РџСЂРёРјРµСЂС‹ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ"""
    return render_template('examples.html')
    
@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - РёСЃРїРѕР»СЊР·СѓРµРј data URI РІ HTML

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
                {'type': 'input_text', 'text': 'Extract all text from this image. Return only recognized text.'},
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
    """API: РџСЂРѕРІРµСЂРєР° С‚РµРєСЃС‚Р°"""
    try:
        data = request.json
        text = data.get('text', '')
        save_history = data.get('save_history', True)
        
        if not text or not text.strip():
            return jsonify({'error': 'РўРµРєСЃС‚ РЅРµ РїСЂРµРґРѕСЃС‚Р°РІР»РµРЅ'}), 400
        
        result = get_checker().check_text(text)
        
        # Р”РѕР±Р°РІР»СЏРµРј СЂРµРєРѕРјРµРЅРґР°С†РёРё
        result['recommendations'] = generate_recommendations(result)
        
        # РЎРѕС…СЂР°РЅСЏРµРј РІ РёСЃС‚РѕСЂРёСЋ
        if save_history:
            save_to_history('text', result, text[:100])
        
        # РћР±РЅРѕРІР»СЏРµРј СЃС‚Р°С‚РёСЃС‚РёРєСѓ
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
    """API: РџСЂРѕРІРµСЂРєР° URL"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url or not url.startswith('http'):
            return jsonify({'error': 'РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ URL'}), 400
        
        # Р—Р°РіСЂСѓР·РєР° СЃС‚СЂР°РЅРёС†С‹
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # РЈРґР°Р»СЏРµРј РЅРµРЅСѓР¶РЅРѕРµ
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # РР·РІР»РµРєР°РµРј С‚РµРєСЃС‚ Рё РјРµС‚Р°-РёРЅС„РѕСЂРјР°С†РёСЋ
        text = soup.get_text(separator=' ', strip=True)
        title = soup.find('title')
        title_text = title.get_text() if title else 'Р‘РµР· РЅР°Р·РІР°РЅРёСЏ'
        
        result = get_checker().check_text(text)
        result['page_title'] = title_text
        result['recommendations'] = generate_recommendations(result)
        
        # РЎРѕС…СЂР°РЅСЏРµРј РІ РёСЃС‚РѕСЂРёСЋ
        save_to_history('url', result, url)
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'url': url,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': f'РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё: {str(e)}'}), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """API: РџР°РєРµС‚РЅР°СЏ РїСЂРѕРІРµСЂРєР°"""
    try:
        data = request.json
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'РЎРїРёСЃРѕРє URL РїСѓСЃС‚'}), 400
        
        results = []
        for url in urls[:50]:  # Р›РёРјРёС‚ 50 URL Р·Р° СЂР°Р·
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
    """API: Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° СЃР»РѕРІ СЃ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёРµРј РјРѕСЂС„РѕР»РѕРіРёРё Рё speller"""
    try:
        data = request.json
        words = data.get('words', [])
        
        if not words:
            return jsonify({'error': 'РЎРїРёСЃРѕРє СЃР»РѕРІ РїСѓСЃС‚'}), 400
        
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
    """API: РЎС‚Р°С‚РёСЃС‚РёРєР° СЃР»РѕРІР°СЂРµР№"""
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
    """API: РџСЂРѕРІРµСЂРєР° РѕРґРЅРѕРіРѕ СЃР»РѕРІР°"""
    try:
        data = request.json
        word = data.get('word', '').strip()
        
        if not word:
            return jsonify({'error': 'РЎР»РѕРІРѕ РЅРµ РїСЂРµРґРѕСЃС‚Р°РІР»РµРЅРѕ'}), 400
        
        if len(word) < 2:
            return jsonify({'error': 'РЎР»РёС€РєРѕРј РєРѕСЂРѕС‚РєРѕРµ СЃР»РѕРІРѕ (РјРёРЅРёРјСѓРј 2 СЃРёРјРІРѕР»Р°)'}), 400
        
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
    """API: РСЃС‚РѕСЂРёСЏ РїСЂРѕРІРµСЂРѕРє"""
    limit = int(request.args.get('limit', 10))
    return jsonify({
        'history': check_history[-limit:][::-1],
        'total': len(check_history)
    })

@app.route('/api/export/txt', methods=['POST'])
def export_txt():
    """Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р° РІ TXT СЃ РїРѕР»РЅРѕР№ РёРЅС„РѕСЂРјР°С†РёРµР№ Рё РїСЂР°РІРёР»СЊРЅРѕР№ РєРѕРґРёСЂРѕРІРєРѕР№"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Р¤РѕСЂРјРёСЂСѓРµРј СѓР»СѓС‡С€РµРЅРЅС‹Р№ РѕС‚С‡РµС‚
        lines = []
        lines.append("=" * 70)
        lines.append("РћРўР§Р•Рў РџР РћР’Р•Р РљР РўР•РљРЎРўРђ РќРђ РЎРћРћРўР’Р•РўРЎРўР’РР• Р¤Р—-168")
        lines.append("=" * 70)
        lines.append(f"Р”Р°С‚Р° РїСЂРѕРІРµСЂРєРё: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"ID РїСЂРѕРІРµСЂРєРё: {str(uuid.uuid4())[:8]}")
        lines.append("")
        
        # РћР±С‰Р°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР°
        lines.append("-" * 70)
        lines.append("РћР‘Р©РђРЇ РЎРўРђРўРРЎРўРРљРђ:")
        lines.append("-" * 70)
        lines.append(f"  Р’СЃРµРіРѕ СЃР»РѕРІ РІ С‚РµРєСЃС‚Рµ:     {result.get('total_words', 0)}")
        lines.append(f"  РЈРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ:         {result.get('unique_words', 0)}")
        lines.append(f"  РќР°СЂСѓС€РµРЅРёР№ РЅР°Р№РґРµРЅРѕ:       {result.get('violations_count', 0)}")
        lines.append("")
        
        # Р”РµС‚Р°Р»СЊРЅР°СЏ СЃС‚Р°С‚РёСЃС‚РёРєР° РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј
        lines.append("-" * 70)
        lines.append("Р”Р•РўРђР›Р¬РќРђРЇ РЎРўРђРўРРЎРўРРљРђ:")
        lines.append("-" * 70)
        lines.append(f"  вњ… РќРѕСЂРјР°С‚РёРІРЅС‹Рµ СЃР»РѕРІР°:   {result.get('normative_count', result.get('total_words', 0) - result.get('violations_count', 0))}")
        lines.append(f"  рџЊЌ РРЅРѕСЃС‚СЂР°РЅРЅС‹Рµ СЃР»РѕРІР°:   {result.get('foreign_count', result.get('latin_count', 0))}")
        lines.append(f"  рџљ« РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°: {result.get('nenormative_count', 0)}")
        lines.append(f"  вњЏпёЏ РћСЂС„РѕРіСЂР°С„РёС‡РµСЃРєРёРµ:      {result.get('orfograf_count', 0)}")
        lines.append(f"  рџ”Љ РћСЂС„РѕСЌРїРёС‡РµСЃРєРёРµ:        {result.get('orfoep_count', 0)}")
        lines.append(f"  вќ“ РќРµРёР·РІРµСЃС‚РЅС‹Рµ СЃР»РѕРІР°:    {result.get('unknown_count', 0)}")
        lines.append("")
        
        # РџСЂРѕС†РµРЅС‚ СЃРѕРѕС‚РІРµС‚СЃС‚РІРёСЏ
        compliance = result.get('compliance_percentage', 0)
        if result.get('law_compliant', result.get('violations_count', 0) == 0):
            compliance = 100.0
            status = "вњ… РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў"
        else:
            total = result.get('total_words', 1)
            violations = result.get('violations_count', 0)
            compliance = ((total - violations) / total) * 100 if total > 0 else 0
            status = "вќЊ РќР• РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў"
        
        lines.append("-" * 70)
        lines.append(f"РЎРўРђРўРЈРЎ: {status}")
        lines.append(f"РџР РћР¦Р•РќРў РЎРћРћРўР’Р•РўРЎРўР’РРЇ: {compliance:.2f}%")
        lines.append("-" * 70)
        lines.append("")
        
        # РќР°Р№РґРµРЅРЅС‹Рµ РЅР°СЂСѓС€РµРЅРёСЏ СЃ РґРµС‚Р°Р»РёР·Р°С†РёРµР№
        has_violations = False
        
        # РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°
        nenormative_words = result.get('nenormative_words', [])
        if nenormative_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"рџљ« РќР•РќРћР РњРђРўРР’РќРђРЇ Р›Р•РљРЎРРљРђ ({len(nenormative_words)} СЃР»РѕРІ):")
            lines.append("=" * 70)
            for i, word in enumerate(nenormative_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # РЎР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ
        latin_words = result.get('latin_words', [])
        if latin_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"рџЊЌ РРќРћРЎРўР РђРќРќР«Р• РЎР›РћР’Рђ РќРђ Р›РђРўРРќРР¦Р• ({len(latin_words)} СЃР»РѕРІ):")
            lines.append("=" * 70)
            for i, word in enumerate(latin_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # РќРµРёР·РІРµСЃС‚РЅС‹Рµ/Р°РЅРіР»РёС†РёР·РјС‹
        unknown_cyrillic = result.get('unknown_cyrillic', [])
        if unknown_cyrillic:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"вќ“ РђРќР“Р›РР¦РР—РњР« / РќР•РР—Р’Р•РЎРўРќР«Р• РЎР›РћР’Рђ ({len(unknown_cyrillic)} СЃР»РѕРІ):")
            lines.append("=" * 70)
            for i, word in enumerate(unknown_cyrillic, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # РћСЂС„РѕРіСЂР°С„РёС‡РµСЃРєРёРµ РѕС€РёР±РєРё
        orfograf_words = result.get('orfograf_words', [])
        if orfograf_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"вњЏпёЏ РћР Р¤РћР“Р РђР¤РР§Р•РЎРљРР• РћРЁРР‘РљР ({len(orfograf_words)} СЃР»РѕРІ):")
            lines.append("=" * 70)
            for i, word in enumerate(orfograf_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        # РћСЂС„РѕСЌРїРёС‡РµСЃРєРёРµ РѕС€РёР±РєРё
        orfoep_words = result.get('orfoep_words', [])
        if orfoep_words:
            has_violations = True
            lines.append("=" * 70)
            lines.append(f"рџ”Љ РћР Р¤РћР­РџРР§Р•РЎРљРР• РћРЁРР‘РљР ({len(orfoep_words)} СЃР»РѕРІ):")
            lines.append("=" * 70)
            for i, word in enumerate(orfoep_words, 1):
                lines.append(f"  {i:3d}. {word}")
            lines.append("")
        
        if not has_violations:
            lines.append("=" * 70)
            lines.append("вњ… РќРђР РЈРЁР•РќРР™ РќР• РћР‘РќРђР РЈР–Р•РќРћ")
            lines.append("=" * 70)
            lines.append("")
            lines.append("РўРµРєСЃС‚ РїРѕР»РЅРѕСЃС‚СЊСЋ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ С‚СЂРµР±РѕРІР°РЅРёСЏРј Р·Р°РєРѕРЅР° Рѕ СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµ.")
            lines.append("")
        
        # Р РµРєРѕРјРµРЅРґР°С†РёРё
        recommendations = result.get('recommendations', [])
        if recommendations:
            lines.append("=" * 70)
            lines.append("Р Р•РљРћРњР•РќР”РђР¦РР:")
            lines.append("=" * 70)
            for rec in recommendations:
                level = rec.get('level', 'info')
                icon = 'рџ”ґ' if level == 'critical' else 'рџџЎ' if level == 'warning' else 'рџџў' if level == 'success' else 'в„№пёЏ'
                lines.append(f"{icon} {rec.get('title', '')}")
                lines.append(f"   {rec.get('message', '')}")
                if rec.get('action'):
                    lines.append(f"   в†’ Р”РµР№СЃС‚РІРёРµ: {rec['action']}")
                lines.append("")
        
        # РџРѕРґРІР°Р»
        lines.append("=" * 70)
        lines.append("РЎРѕР·РґР°РЅРѕ: LawChecker Online")
        lines.append("РЎР°Р№С‚: https://lawcheck-production.up.railway.app")
        lines.append("Р—Р°РєРѕРЅ: Р¤РµРґРµСЂР°Р»СЊРЅС‹Р№ Р·Р°РєРѕРЅ в„–168-Р¤Р— В«Рћ СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµВ»")
        lines.append("=" * 70)
        
        report = "\n".join(lines)
        
        # РЎРѕР·РґР°РµРј С„Р°Р№Р» СЃ BOM РґР»СЏ Windows-СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
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
    """Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р° РІ JSON"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Р”РѕР±Р°РІР»СЏРµРј РјРµС‚Р°РґР°РЅРЅС‹Рµ
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
    """Р­РєСЃРїРѕСЂС‚ РїР°РєРµС‚РЅРѕРіРѕ РѕС‚С‡РµС‚Р° РІ TXT СЃ РґРµС‚Р°Р»РёР·Р°С†РёРµР№ РІСЃРµС… РЅР°СЂСѓС€РµРЅРёР№"""
    try:
        data = request.get_json()
        results = data.get('results', [])
        
        if not results:
            return jsonify({'error': 'РќРµС‚ РґР°РЅРЅС‹С… РґР»СЏ СЌРєСЃРїРѕСЂС‚Р°'}), 400
        
        lines = []
        lines.append("=" * 80)
        lines.append("РџРђРљР•РўРќР«Р™ РћРўР§Р•Рў РџР РћР’Р•Р РљР РЎРђР™РўРћР’ РќРђ РЎРћРћРўР’Р•РўРЎРўР’РР• Р¤Р—-168")
        lines.append("=" * 80)
        lines.append(f"Р”Р°С‚Р° РїСЂРѕРІРµСЂРєРё: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"Р’СЃРµРіРѕ РїСЂРѕРІРµСЂРµРЅРѕ СЃР°Р№С‚РѕРІ: {len(results)}")
        lines.append("")
        
        # РћР±С‰Р°СЏ СЃРІРѕРґРєР°
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
                    # РЎРѕР±РёСЂР°РµРј РІСЃРµ СЃР»РѕРІР°
                    all_latin_words.update(result.get('latin_words', []))
                    all_unknown_words.update(result.get('unknown_cyrillic', []))
                    all_nenormative_words.update(result.get('nenormative_words', []))
        
        lines.append("-" * 80)
        lines.append("РћР‘Р©РђРЇ РЎР’РћР”РљРђ:")
        lines.append("-" * 80)
        lines.append(f"  вњ… РЈСЃРїРµС€РЅРѕ РїСЂРѕРІРµСЂРµРЅРѕ:     {successful_checks} СЃР°Р№С‚РѕРІ")
        lines.append(f"  вќЊ РЎ РЅР°СЂСѓС€РµРЅРёСЏРјРё:         {total_sites_with_violations} СЃР°Р№С‚РѕРІ")
        lines.append(f"  рџљ« РљСЂРёС‚РёС‡РµСЃРєРёС… (РјР°С‚):     {total_critical} СЃР°Р№С‚РѕРІ")
        lines.append(f"  рџ“Љ Р’СЃРµРіРѕ РЅР°СЂСѓС€РµРЅРёР№:       {total_violations}")
        lines.append("")
        
        # РЈРЅРёРєР°Р»СЊРЅС‹Рµ СЃР»РѕРІР° РїРѕ РІСЃРµРј СЃР°Р№С‚Р°Рј
        if all_latin_words or all_unknown_words or all_nenormative_words:
            lines.append("-" * 80)
            lines.append("РЈРќРРљРђР›Р¬РќР«Р• РќРђР РЈРЁР•РќРРЇ РџРћ Р’РЎР•Рњ РЎРђР™РўРђРњ:")
            lines.append("-" * 80)
            lines.append("")
            
            if all_nenormative_words:
                lines.append(f"рџљ« РќР•РќРћР РњРђРўРР’РќРђРЇ Р›Р•РљРЎРРљРђ ({len(all_nenormative_words)} СѓРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ):")
                for i, word in enumerate(sorted(all_nenormative_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
            
            if all_latin_words:
                lines.append(f"рџЊЌ Р›РђРўРРќРР¦Рђ ({len(all_latin_words)} СѓРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ):")
                for i, word in enumerate(sorted(all_latin_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
            
            if all_unknown_words:
                lines.append(f"вќ“ РђРќР“Р›РР¦РР—РњР« / РќР•РР—Р’Р•РЎРўРќР«Р• ({len(all_unknown_words)} СѓРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ):")
                for i, word in enumerate(sorted(all_unknown_words), 1):
                    lines.append(f"  {i:3d}. {word}")
                lines.append("")
        
        # Р”РµС‚Р°Р»РёР·Р°С†РёСЏ РїРѕ РєР°Р¶РґРѕРјСѓ СЃР°Р№С‚Сѓ
        lines.append("=" * 80)
        lines.append("Р”Р•РўРђР›Р¬РќР«Р™ РћРўР§Р•Рў РџРћ РљРђР–Р”РћРњРЈ РЎРђР™РўРЈ:")
        lines.append("=" * 80)
        lines.append("")
        
        for i, item in enumerate(results, 1):
            url = item.get('url', 'РќРµРёР·РІРµСЃС‚РЅС‹Р№ URL')
            lines.append(f"{'в”Ђ' * 80}")
            lines.append(f"[{i}] {url}")
            lines.append(f"{'в”Ђ' * 80}")
            
            if not item.get('success'):
                lines.append(f"  вќЊ РћРЁРР‘РљРђ: {item.get('error', 'РќРµРёР·РІРµСЃС‚РЅР°СЏ РѕС€РёР±РєР°')}")
                lines.append("")
                continue
            
            result = item.get('result', {})
            
            # РЎС‚Р°С‚СѓСЃ
            if result.get('law_compliant', False):
                lines.append("  вњ… РЎРўРђРўРЈРЎ: РЎРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ Р·Р°РєРѕРЅСѓ")
            else:
                lines.append(f"  вљ пёЏ  РЎРўРђРўРЈРЎ: РќР°СЂСѓС€РµРЅРёР№: {result.get('violations_count', 0)}")
            
            lines.append(f"  рџ“Љ РЎР»РѕРІ РІ С‚РµРєСЃС‚Рµ: {result.get('total_words', 0)}")
            lines.append("")
            
            # РќР°СЂСѓС€РµРЅРёСЏ РїРѕ РєР°С‚РµРіРѕСЂРёСЏРј
            if result.get('nenormative_count', 0) > 0:
                lines.append(f"  рџљ« РќР•РќРћР РњРђРўРР’РќРђРЇ Р›Р•РљРЎРРљРђ ({result['nenormative_count']}):")
                for word in result.get('nenormative_words', []):
                    lines.append(f"      вЂў {word}")
                lines.append("")
            
            if result.get('latin_count', 0) > 0:
                lines.append(f"  рџЊЌ Р›РђРўРРќРР¦Рђ ({result['latin_count']}):")
                for word in result.get('latin_words', []):
                    lines.append(f"      вЂў {word}")
                lines.append("")
            
            if result.get('unknown_count', 0) > 0:
                lines.append(f"  вќ“ РђРќР“Р›РР¦РР—РњР« ({result['unknown_count']}):")
                for word in result.get('unknown_cyrillic', []):
                    lines.append(f"      вЂў {word}")
                lines.append("")
        
        # РџРѕРґРІР°Р»
        lines.append("=" * 80)
        lines.append("РЎРѕР·РґР°РЅРѕ: LawChecker Online")
        lines.append("РЎР°Р№С‚: https://lawcheck-production.up.railway.app")
        lines.append("Р—Р°РєРѕРЅ: Р¤РµРґРµСЂР°Р»СЊРЅС‹Р№ Р·Р°РєРѕРЅ в„–168-Р¤Р— В«Рћ СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµВ»")
        lines.append("=" * 80)
        
        report = "\n".join(lines)
        
        # РЎРѕР·РґР°РµРј С„Р°Р№Р» СЃ BOM РґР»СЏ Windows-СЃРѕРІРјРµСЃС‚РёРјРѕСЃС‚Рё
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

# ==================== Р’РЎРџРћРњРћР“РђРўР•Р›Р¬РќР«Р• Р¤РЈРќРљР¦РР ====================

def save_to_history(check_type, result, context):
    """РЎРѕС…СЂР°РЅРµРЅРёРµ РІ РёСЃС‚РѕСЂРёСЋ"""
    check_history.append({
        'id': str(uuid.uuid4()),
        'type': check_type,
        'timestamp': datetime.now().isoformat(),
        'violations': result['violations_count'],
        'compliant': result['law_compliant'],
        'context': context
    })
    
    # РћРіСЂР°РЅРёС‡РёРІР°РµРј СЂР°Р·РјРµСЂ РёСЃС‚РѕСЂРёРё
    if len(check_history) > 1000:
        check_history.pop(0)

def update_statistics(result):
    """РћР±РЅРѕРІР»РµРЅРёРµ СЃС‚Р°С‚РёСЃС‚РёРєРё"""
    statistics['total_checks'] += 1
    statistics['total_violations'] += result['violations_count']
    
    # РџРѕРґСЃС‡РµС‚ С‡Р°СЃС‚С‹С… РЅР°СЂСѓС€РµРЅРёР№
    for word in result.get('latin_words', [])[:10]:
        statistics['most_common_violations'][word] += 1
    for word in result.get('unknown_cyrillic', [])[:10]:
        statistics['most_common_violations'][word] += 1

def generate_recommendations(result):
    """Р“РµРЅРµСЂР°С†РёСЏ СЂРµРєРѕРјРµРЅРґР°С†РёР№ РїРѕ РёСЃРїСЂР°РІР»РµРЅРёСЋ"""
    recommendations = []
    
    if result.get('nenormative_count', 0) > 0:
        recommendations.append({
            'level': 'critical',
            'icon': 'рџљ«',
            'title': 'РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°',
            'message': f"РћР±РЅР°СЂСѓР¶РµРЅРѕ {result['nenormative_count']} СЃР»РѕРІ РЅРµРЅРѕСЂРјР°С‚РёРІРЅРѕР№ Р»РµРєСЃРёРєРё. Р­С‚Рѕ РљР РРўРР§Р•РЎРљРћР• РЅР°СЂСѓС€РµРЅРёРµ Р·Р°РєРѕРЅР°.",
            'action': 'Р—Р°РјРµРЅРёС‚Рµ РёР»Рё СѓРґР°Р»РёС‚Рµ РІСЃРµ РЅРµРЅРѕСЂРјР°С‚РёРІРЅС‹Рµ РІС‹СЂР°Р¶РµРЅРёСЏ.'
        })
    
    if result.get('latin_count', 0) > 0:
        recommendations.append({
            'level': 'warning',
            'icon': 'вљ пёЏ',
            'title': 'Р›Р°С‚РёРЅРёС†Р° РІ С‚РµРєСЃС‚Рµ',
            'message': f"РќР°Р№РґРµРЅРѕ {result['latin_count']} СЃР»РѕРІ РЅР° Р»Р°С‚РёРЅРёС†Рµ.",
            'action': 'Р—Р°РјРµРЅРёС‚Рµ Р°РЅРіР»РёР№СЃРєРёРµ СЃР»РѕРІР° РЅР° СЂСѓСЃСЃРєРёРµ Р°РЅР°Р»РѕРіРё РёР»Рё РґРѕР±Р°РІСЊС‚Рµ РїРѕСЏСЃРЅРµРЅРёСЏ РІ СЃРєРѕР±РєР°С….'
        })
    
    if result.get('unknown_count', 0) > 0:
        recommendations.append({
            'level': 'info',
            'icon': 'в„№пёЏ',
            'title': 'РќРµРёР·РІРµСЃС‚РЅС‹Рµ СЃР»РѕРІР°',
            'message': f"РћР±РЅР°СЂСѓР¶РµРЅРѕ {result['unknown_count']} РїРѕС‚РµРЅС†РёР°Р»СЊРЅС‹С… Р°РЅРіР»РёС†РёР·РјРѕРІ РёР»Рё РЅРµРёР·РІРµСЃС‚РЅС‹С… СЃР»РѕРІ.",
            'action': 'РџСЂРѕРІРµСЂСЊС‚Рµ РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚СЊ РЅР°РїРёСЃР°РЅРёСЏ РёР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РѕР±С‰РµРїСЂРёРЅСЏС‚С‹Рµ С‚РµСЂРјРёРЅС‹.'
        })
    
    if result['law_compliant']:
        recommendations.append({
            'level': 'success',
            'icon': 'вњ…',
            'title': 'РўРµРєСЃС‚ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ Р·Р°РєРѕРЅСѓ',
            'message': 'РќР°СЂСѓС€РµРЅРёР№ РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅРѕ. РўРµРєСЃС‚ РїРѕР»РЅРѕСЃС‚СЊСЋ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ С‚СЂРµР±РѕРІР°РЅРёСЏРј Р¤Р— в„–168.',
            'action': 'РњРѕР¶РЅРѕ РїСѓР±Р»РёРєРѕРІР°С‚СЊ Р±РµР· РёР·РјРµРЅРµРЅРёР№.'
        })
    
    return recommendations

def get_word_suggestions(word):
    """РџРѕР»СѓС‡РµРЅРёРµ РїСЂРµРґР»РѕР¶РµРЅРёР№ РїРѕ Р·Р°РјРµРЅРµ СЃР»РѕРІР°"""
    # Р—РґРµСЃСЊ РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ Р»РѕРіРёРєСѓ РїРѕРґР±РѕСЂР° СЃРёРЅРѕРЅРёРјРѕРІ
    suggestions = []
    
    # РџСЂРѕСЃС‚С‹Рµ РїСЂРёРјРµСЂС‹ Р·Р°РјРµРЅ (СЂР°СЃС€РёСЂСЊС‚Рµ РїРѕРґ СЃРІРѕРё РЅСѓР¶РґС‹)
    replacements = {
        'hello': 'РїСЂРёРІРµС‚',
        'world': 'РјРёСЂ',
        'computer': 'РєРѕРјРїСЊСЋС‚РµСЂ',
        'email': 'СЌР»РµРєС‚СЂРѕРЅРЅР°СЏ РїРѕС‡С‚Р°',
        'internet': 'РёРЅС‚РµСЂРЅРµС‚',
        'software': 'РїСЂРѕРіСЂР°РјРјРЅРѕРµ РѕР±РµСЃРїРµС‡РµРЅРёРµ',
    }
    
    word_lower = word.lower()
    if word_lower in replacements:
        suggestions.append(replacements[word_lower])
    
    return suggestions if suggestions else ['РќРµС‚ РїСЂРµРґР»РѕР¶РµРЅРёР№']

def calculate_readability(text):
    """Р Р°СЃС‡РµС‚ РёРЅРґРµРєСЃР° С‡РёС‚Р°РµРјРѕСЃС‚Рё"""
    words = text.split()
    sentences = [s for s in text.split('.') if s.strip()]
    
    if not words or not sentences:
        return 0
    
    avg_sentence_length = len(words) / len(sentences)
    avg_word_length = sum(len(w) for w in words) / len(words)
    
    # РџСЂРѕСЃС‚РѕР№ РёРЅРґРµРєСЃ (С‡РµРј РјРµРЅСЊС€Рµ, С‚РµРј Р»СѓС‡С€Рµ)
    readability = (avg_sentence_length * 0.5) + (avg_word_length * 2)
    
    return round(readability, 2)

def get_word_frequency(text):
    """Р§Р°СЃС‚РѕС‚РЅРѕСЃС‚СЊ СЃР»РѕРІ"""
    words = text.lower().split()
    frequency = defaultdict(int)
    
    for word in words:
        if len(word) > 3:
            frequency[word] += 1
    
    return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:10])

def calculate_complexity(text):
    """РћС†РµРЅРєР° СЃР»РѕР¶РЅРѕСЃС‚Рё С‚РµРєСЃС‚Р° (0-100)"""
    words = text.split()
    
    if not words:
        return 0
    
    avg_word_length = sum(len(w) for w in words) / len(words)
    unique_words = len(set(words))
    lexical_diversity = unique_words / len(words)
    
    complexity = (avg_word_length * 10) + (lexical_diversity * 30)
    
    return min(100, round(complexity, 2))

def calculate_improvement(result1, result2):
    """Р Р°СЃС‡РµС‚ РїСЂРѕС†РµРЅС‚Р° СѓР»СѓС‡С€РµРЅРёСЏ"""
    if result1['violations_count'] == 0:
        return 0
    
    improvement = ((result1['violations_count'] - result2['violations_count']) / result1['violations_count']) * 100
    return round(improvement, 2)

def generate_text_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ С‚РµРєСЃС‚РѕРІРѕРіРѕ РѕС‚С‡РµС‚Р°"""
    output = "="*100 + "\n"
    output += "РћРўР§РЃРў РџРћ РџР РћР’Р•Р РљР• Р—РђРљРћРќРђ Рћ Р РЈРЎРЎРљРћРњ РЇР—Р«РљР• в„–168-Р¤Р—\n"
    output += f"РЎРѕР·РґР°РЅ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    output += "="*100 + "\n\n"
    
    output += f"Р’СЃРµРіРѕ СЃР»РѕРІ: {result.get('total_words', 0)}\n"
    output += f"РЈРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ: {result.get('unique_words', 0)}\n"
    output += f"РќР°СЂСѓС€РµРЅРёР№: {result.get('violations_count', 0)}\n\n"
    
    if result.get('law_compliant'):
        output += "вњ… РўР•РљРЎРў РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў РўР Р•Р‘РћР’РђРќРРЇРњ Р—РђРљРћРќРђ\n\n"
    else:
        output += f"вљ пёЏ РћР‘РќРђР РЈР–Р•РќРћ РќРђР РЈРЁР•РќРР™: {result.get('violations_count', 0)}\n\n"
        
        if result.get('nenormative_count', 0) > 0:
            output += f"рџљ« РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°: {result['nenormative_count']}\n"
        if result.get('latin_count', 0) > 0:
            output += f"вљ пёЏ Р›Р°С‚РёРЅРёС†Р°: {result['latin_count']}\n"
            for i, word in enumerate(result.get('latin_words', [])[:50], 1):
                output += f"  {i}. {word}\n"
            output += "\n"
        if result.get('unknown_count', 0) > 0:
            output += f"вљ пёЏ РђРЅРіР»РёС†РёР·РјС‹: {result['unknown_count']}\n"
            for i, word in enumerate(result.get('unknown_cyrillic', [])[:50], 1):
                output += f"  {i}. {word}\n"
    
    return output

def generate_csv_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ CSV РѕС‚С‡РµС‚Р°"""
    output = "РўРёРї,РљРѕР»РёС‡РµСЃС‚РІРѕ,РЎР»РѕРІР°\n"
    
    output += f"Р›Р°С‚РёРЅРёС†Р°,{result.get('latin_count', 0)},\"{', '.join(result.get('latin_words', [])[:20])}\"\n"
    output += f"РђРЅРіР»РёС†РёР·РјС‹,{result.get('unknown_count', 0)},\"{', '.join(result.get('unknown_cyrillic', [])[:20])}\"\n"
    output += f"РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ,{result.get('nenormative_count', 0)},\"[СЃРєСЂС‹С‚Рѕ]\"\n"
    
    return output

def generate_html_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ HTML РѕС‚С‡РµС‚Р°"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>РћС‚С‡РµС‚ РїСЂРѕРІРµСЂРєРё Р¤Р— в„–168</title>
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
            <h1>рџ‡·рџ‡є РћС‚С‡РµС‚ РїРѕ РїСЂРѕРІРµСЂРєРµ Р¤Р— в„–168</h1>
            <p>РЎРѕР·РґР°РЅ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="status {'success' if result.get('law_compliant') else 'error'}">
            {'вњ… РўР•РљРЎРў РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў РўР Р•Р‘РћР’РђРќРРЇРњ' if result.get('law_compliant') else f"вљ пёЏ РќРђР РЈРЁР•РќРР™: {result.get('violations_count', 0)}"}
        </div>
        
        <div class="violations">
            <h2>РЎС‚Р°С‚РёСЃС‚РёРєР°:</h2>
            <p>Р’СЃРµРіРѕ СЃР»РѕРІ: {result.get('total_words', 0)}</p>
            <p>РЈРЅРёРєР°Р»СЊРЅС‹С…: {result.get('unique_words', 0)}</p>
            <p>Р›Р°С‚РёРЅРёС†Р°: {result.get('latin_count', 0)}</p>
            <p>РђРЅРіР»РёС†РёР·РјС‹: {result.get('unknown_count', 0)}</p>
            
            {f"<h3>РЎР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ:</h3>" if result.get('latin_words') else ''}
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
