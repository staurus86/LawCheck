#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API для проверки текста на соответствие закону №168-ФЗ
УЛУЧШЕННАЯ ВЕРСИЯ с максимальным функционалом
"""

from flask import Flask, render_template, request, jsonify, send_file, session, Response
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
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from collections import deque
from urllib.parse import urljoin, urldefrag, urlparse
from sqlalchemy import create_engine, text

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max request size
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.getenv('SECRET_KEY', 'change-this-secret-key'))
OCR_TIMEOUT = int(os.getenv('OCR_TIMEOUT', '30'))
OPENAI_OCR_BASE_URL = os.getenv('OPENAI_OCR_BASE_URL', 'https://api.openai.com/v1').strip()
GOOGLE_VISION_BASE_URL = os.getenv('GOOGLE_VISION_BASE_URL', 'https://vision.googleapis.com/v1').strip()
OCRSPACE_BASE_URL = os.getenv('OCRSPACE_BASE_URL', 'https://api.ocr.space').strip()
MULTISCAN_MAX_URLS_HARD = int(os.getenv('MULTISCAN_MAX_URLS_HARD', '2000'))
MULTISCAN_MAX_PAGES_HARD = int(os.getenv('MULTISCAN_MAX_PAGES_HARD', '2000'))
MULTISCAN_MAX_RESOURCES_HARD = int(os.getenv('MULTISCAN_MAX_RESOURCES_HARD', '8000'))
MULTISCAN_MAX_TEXT_CHARS = int(os.getenv('MULTISCAN_MAX_TEXT_CHARS', '200000'))
MULTISCAN_MAX_DOWNLOAD_BYTES = int(os.getenv('MULTISCAN_MAX_DOWNLOAD_BYTES', str(8 * 1024 * 1024)))
MULTISCAN_USER_AGENT = os.getenv('MULTISCAN_USER_AGENT', 'LawChecker-MultiScan/1.0')
METRICS_RETENTION_DAYS = int(os.getenv('METRICS_RETENTION_DAYS', '60'))
METRICS_CLEANUP_INTERVAL_SEC = int(os.getenv('METRICS_CLEANUP_INTERVAL_SEC', '3600'))

# Database (Railway PostgreSQL)
RAW_DATABASE_URL = (os.getenv('DATABASE_URL') or os.getenv('database_URL') or '').strip()
if RAW_DATABASE_URL.startswith('postgres://'):
    RAW_DATABASE_URL = RAW_DATABASE_URL.replace('postgres://', 'postgresql://', 1)

db_engine = None
if RAW_DATABASE_URL:
    try:
        db_engine = create_engine(RAW_DATABASE_URL, pool_pre_ping=True, future=True)
    except Exception as _db_init_error:
        print(f"[WARN] Database init failed: {_db_init_error}")
        db_engine = None

_last_metrics_cleanup_ts = 0.0
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


def init_analytics_db():
    if db_engine is None:
        return
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    event_type VARCHAR(32) NOT NULL,
                    endpoint VARCHAR(128) NOT NULL,
                    success BOOLEAN NOT NULL,
                    duration_ms DOUBLE PRECISION,
                    source_type VARCHAR(32),
                    items_total INTEGER NOT NULL DEFAULT 0,
                    items_error INTEGER NOT NULL DEFAULT 0,
                    violations_total INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS errors (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    endpoint VARCHAR(128) NOT NULL,
                    status_code INTEGER NOT NULL,
                    message_short TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS run_history (
                    id BIGSERIAL PRIMARY KEY,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    check_type VARCHAR(32) NOT NULL,
                    endpoint VARCHAR(128) NOT NULL,
                    source_type VARCHAR(32),
                    context_short VARCHAR(255),
                    success BOOLEAN NOT NULL,
                    duration_ms DOUBLE PRECISION,
                    violations_count INTEGER NOT NULL DEFAULT 0
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS violation_words (
                    word VARCHAR(255) PRIMARY KEY,
                    count BIGINT NOT NULL DEFAULT 0,
                    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
    except Exception as e:
        print(f"[WARN] DB schema init failed: {e}")


def log_event(event_type, endpoint, success, duration_ms=None, source_type=None, items_total=0, items_error=0, violations_total=0):
    if db_engine is None:
        return
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO events (
                    event_type, endpoint, success, duration_ms, source_type, items_total, items_error, violations_total
                ) VALUES (
                    :event_type, :endpoint, :success, :duration_ms, :source_type, :items_total, :items_error, :violations_total
                )
            """), {
                'event_type': event_type,
                'endpoint': endpoint,
                'success': bool(success),
                'duration_ms': float(duration_ms) if duration_ms is not None else None,
                'source_type': source_type,
                'items_total': int(items_total or 0),
                'items_error': int(items_error or 0),
                'violations_total': int(violations_total or 0)
            })
    except Exception:
        pass
    cleanup_analytics_db()


def log_error(endpoint, status_code, message):
    if db_engine is None:
        return
    short = (message or '').strip()[:1000]
    if not short:
        short = 'unknown error'
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO errors (endpoint, status_code, message_short)
                VALUES (:endpoint, :status_code, :message_short)
            """), {
                'endpoint': endpoint,
                'status_code': int(status_code),
                'message_short': short
            })
    except Exception:
        pass
    cleanup_analytics_db()


def insert_run_history(check_type, endpoint, success, duration_ms=None, source_type=None, context_short=None, violations_count=0):
    if db_engine is None:
        return
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO run_history (
                    check_type, endpoint, source_type, context_short, success, duration_ms, violations_count
                ) VALUES (
                    :check_type, :endpoint, :source_type, :context_short, :success, :duration_ms, :violations_count
                )
            """), {
                'check_type': (check_type or 'unknown')[:32],
                'endpoint': (endpoint or '')[:128],
                'source_type': (source_type or '')[:32] or None,
                'context_short': ((context_short or '').strip()[:255] or None),
                'success': bool(success),
                'duration_ms': float(duration_ms) if duration_ms is not None else None,
                'violations_count': int(violations_count or 0)
            })
    except Exception:
        pass


def upsert_violation_words(words):
    if db_engine is None:
        return
    clean_words = []
    for raw in (words or []):
        word = (raw or '').strip()
        if word:
            clean_words.append(word[:255])
    if not clean_words:
        return
    try:
        with db_engine.begin() as conn:
            for word in clean_words:
                conn.execute(text("""
                    INSERT INTO violation_words (word, count, last_seen_at)
                    VALUES (:word, 1, NOW())
                    ON CONFLICT (word)
                    DO UPDATE SET count = violation_words.count + 1, last_seen_at = NOW()
                """), {'word': word})
    except Exception:
        pass


def cleanup_analytics_db(force=False):
    global _last_metrics_cleanup_ts
    if db_engine is None:
        return
    now_ts = time.time()
    if not force and (now_ts - _last_metrics_cleanup_ts) < METRICS_CLEANUP_INTERVAL_SEC:
        return
    _last_metrics_cleanup_ts = now_ts
    try:
        with db_engine.begin() as conn:
            conn.execute(text("""
                DELETE FROM events
                WHERE created_at < NOW() - make_interval(days => :days)
            """), {'days': METRICS_RETENTION_DAYS})
            conn.execute(text("""
                DELETE FROM errors
                WHERE created_at < NOW() - make_interval(days => :days)
            """), {'days': METRICS_RETENTION_DAYS})
            conn.execute(text("""
                DELETE FROM run_history
                WHERE created_at < NOW() - make_interval(days => :days)
            """), {'days': METRICS_RETENTION_DAYS})
            conn.execute(text("""
                DELETE FROM violation_words
                WHERE last_seen_at < NOW() - make_interval(days => :days)
            """), {'days': METRICS_RETENTION_DAYS})
    except Exception:
        pass


init_analytics_db()
cleanup_analytics_db(force=True)

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

@app.route('/payment')
def payment():
    """Страница тарифов/оплаты"""
    tariff = (request.args.get('tariff') or 'symbols-20000').strip()
    return render_template('payment.html', selected_tariff=tariff)

@app.route('/admin/metrics')
def admin_metrics():
    """Простой дашборд метрик (read-only)"""
    return render_template('admin_metrics.html')
    
@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap():
    """Sitemap.xml"""
    base = request.url_root.rstrip('/')
    urls = ['/', '/about', '/api-docs', '/examples', '/payment']
    lastmod = datetime.utcnow().strftime('%Y-%m-%d')
    items = []
    for path in urls:
        items.append(
            f"<url><loc>{base}{path}</loc><lastmod>{lastmod}</lastmod><changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + ''.join(items) +
        '</urlset>'
    )
    return Response(xml, mimetype='application/xml')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - используем data URI в HTML


@app.errorhandler(404)
def not_found(_error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template('500.html'), 500

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


def _normalize_http_url(raw_url):
    url = (raw_url or '').strip()
    if not url:
        return ''
    if not url.startswith('http://') and not url.startswith('https://'):
        return ''
    return urldefrag(url)[0]


def _safe_int(value, default_value, min_value, max_value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default_value
    return max(min_value, min(parsed, max_value))


def _safe_bool(value, default_value=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default_value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def _is_image_url(url):
    lower = (url or '').lower()
    return bool(re.search(r'\.(png|jpe?g|webp|bmp|gif|tiff|svg)(\?.*)?$', lower))


def _is_pdf_url(url):
    lower = (url or '').lower()
    return bool(re.search(r'\.pdf(\?.*)?$', lower))


def _same_domain(url_a, url_b):
    try:
        return (urlparse(url_a).netloc or '').lower() == (urlparse(url_b).netloc or '').lower()
    except Exception:
        return False


def _fetch_url_bytes(url, timeout_sec=15, max_bytes=MULTISCAN_MAX_DOWNLOAD_BYTES):
    response = requests.get(
        url,
        timeout=timeout_sec,
        stream=True,
        headers={'User-Agent': MULTISCAN_USER_AGENT}
    )
    response.raise_for_status()
    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError(f'Resource too large: {total} bytes > {max_bytes} bytes')
        chunks.append(chunk)
    raw = b''.join(chunks)
    content_type = (response.headers.get('Content-Type') or '').lower()
    return raw, content_type


def _extract_visible_text_from_html(html_text):
    soup = BeautifulSoup(html_text, 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
        tag.decompose()
    title = soup.find('title')
    title_text = title.get_text(' ', strip=True) if title else ''
    text = soup.get_text(separator=' ', strip=True)
    return text, title_text, soup


def _extract_links_from_soup(soup, base_url):
    page_links = set()
    image_links = set()
    pdf_links = set()

    for img in soup.select('img[src]'):
        src = _normalize_http_url(urljoin(base_url, img.get('src', '')))
        if src:
            image_links.add(src)

    for source_tag in soup.select('source[src]'):
        src = _normalize_http_url(urljoin(base_url, source_tag.get('src', '')))
        if not src:
            continue
        if _is_image_url(src):
            image_links.add(src)

    for anchor in soup.select('a[href]'):
        href = _normalize_http_url(urljoin(base_url, anchor.get('href', '')))
        if not href:
            continue
        if _is_pdf_url(href):
            pdf_links.add(href)
        else:
            page_links.add(href)

    return page_links, image_links, pdf_links


def _extract_pdf_text(raw_bytes):
    if PdfReader is None:
        raise RuntimeError('PDF parser is unavailable. Install pypdf.')
    reader = PdfReader(io.BytesIO(raw_bytes))
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ''
        if page_text:
            text_parts.append(page_text)
        if sum(len(part) for part in text_parts) >= MULTISCAN_MAX_TEXT_CHARS:
            break
    return '\n'.join(text_parts).strip()


def _build_resource_result(url, resource_type, check_result, source_meta=None):
    source_meta = source_meta or {}
    forbidden_words = sorted(set(
        (check_result.get('nenormative_words') or [])
        + (check_result.get('latin_words') or [])
        + (check_result.get('unknown_cyrillic') or [])
    ))
    return {
        'url': url,
        'resource_type': resource_type,
        'success': True,
        'violations_count': check_result.get('violations_count', 0),
        'law_compliant': bool(check_result.get('law_compliant', True)),
        'forbidden_words': forbidden_words,
        'result': check_result,
        'meta': source_meta
    }

# ==================== API ENDPOINTS ====================

@app.route('/api/check', methods=['POST'])
def check_text():
    """API: Проверка текста"""
    try:
        started_at = time.perf_counter()
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
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            event_type='check',
            endpoint='/api/check',
            success=True,
            duration_ms=duration_ms,
            source_type='text',
            items_total=1,
            items_error=0,
            violations_total=result.get('violations_count', 0)
        )
        insert_run_history(
            check_type='url',
            endpoint='/api/check-url',
            success=True,
            duration_ms=duration_ms,
            source_type='url',
            context_short=url[:255],
            violations_count=result.get('violations_count', 0)
        )
        upsert_violation_words(
            (result.get('latin_words') or [])
            + (result.get('unknown_cyrillic') or [])
            + (result.get('nenormative_words') or [])
        )
        insert_run_history(
            check_type='text',
            endpoint='/api/check',
            success=True,
            duration_ms=duration_ms,
            source_type='text',
            context_short='text input',
            violations_count=result.get('violations_count', 0)
        )
        upsert_violation_words(
            (result.get('latin_words') or [])
            + (result.get('unknown_cyrillic') or [])
            + (result.get('nenormative_words') or [])
        )
        
        return jsonify({
            'success': True,
            'result': result,
            'timestamp': datetime.now().isoformat(),
            'check_id': str(uuid.uuid4())
        })
    
    except Exception as e:
        log_error('/api/check', 500, str(e))
        log_event(event_type='check', endpoint='/api/check', success=False, source_type='text', items_total=1, items_error=1)
        insert_run_history(check_type='text', endpoint='/api/check', success=False, source_type='text', context_short='text input')
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-url', methods=['POST'])
def check_url():
    """API: Проверка URL"""
    try:
        started_at = time.perf_counter()
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
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            event_type='check',
            endpoint='/api/check-url',
            success=True,
            duration_ms=duration_ms,
            source_type='url',
            items_total=1,
            items_error=0,
            violations_total=result.get('violations_count', 0)
        )
        
        return jsonify({
            'success': True,
            'url': url,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        log_error('/api/check-url', 500, str(e))
        log_event(event_type='check', endpoint='/api/check-url', success=False, source_type='url', items_total=1, items_error=1)
        insert_run_history(check_type='url', endpoint='/api/check-url', success=False, source_type='url')
        return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """API: Пакетная проверка"""
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'Список URL пуст'}), 400

        max_urls = int(os.getenv('BATCH_MAX_URLS', '100'))
        max_workers = int(os.getenv('BATCH_MAX_WORKERS', '8'))
        max_workers = max(1, min(max_workers, 32))

        # Нормализуем и ограничиваем список URL
        clean_urls = []
        for raw in urls:
            url = (raw or '').strip()
            if url and url.startswith('http'):
                clean_urls.append(url)
            if len(clean_urls) >= max_urls:
                break

        if not clean_urls:
            return jsonify({'error': 'Нет корректных URL'}), 400

        checker_instance = get_checker()

        def process_single_url(url):
            try:
                response = requests.get(url, timeout=12, headers={
                    'User-Agent': 'Mozilla/5.0'
                })
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()
                text = soup.get_text(separator=' ', strip=True)
                result = checker_instance.check_text(text)
                return {
                    'url': url,
                    'success': True,
                    'result': result
                }
            except Exception as e:
                return {
                    'url': url,
                    'success': False,
                    'error': str(e)
                }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(process_single_url, clean_urls))
        success_items = [item for item in results if item.get('success')]
        error_items = [item for item in results if not item.get('success')]
        violations_total = sum((item.get('result') or {}).get('violations_count', 0) for item in success_items)
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            event_type='batch',
            endpoint='/api/batch-check',
            success=True,
            duration_ms=duration_ms,
            source_type='url',
            items_total=len(clean_urls),
            items_error=len(error_items),
            violations_total=violations_total
        )
        insert_run_history(
            check_type='batch',
            endpoint='/api/batch-check',
            success=True,
            duration_ms=duration_ms,
            source_type='url',
            context_short=f'urls={len(clean_urls)} ok={len(success_items)} err={len(error_items)}',
            violations_count=violations_total
        )
        all_words = []
        for item in success_items:
            r = item.get('result') or {}
            all_words.extend(r.get('latin_words') or [])
            all_words.extend(r.get('unknown_cyrillic') or [])
            all_words.extend(r.get('nenormative_words') or [])
        upsert_violation_words(all_words)
        
        return jsonify({
            'success': True,
            'total': len(clean_urls),
            'results': results,
            'workers': max_workers,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        log_error('/api/batch-check', 500, str(e))
        log_event(event_type='batch', endpoint='/api/batch-check', success=False, source_type='url', items_error=1)
        insert_run_history(check_type='batch', endpoint='/api/batch-check', success=False, source_type='url')
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


@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """Мини-метрики по событиям сервиса из PostgreSQL"""
    if db_engine is None:
        return jsonify({
            'enabled': False,
            'error': 'Database is not configured'
        }), 503
    try:
        with db_engine.begin() as conn:
            totals_row = conn.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS events_24h,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS events_7d,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours' AND success = FALSE) AS errors_24h,
                    COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days' AND success = FALSE) AS errors_7d,
                    AVG(duration_ms) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours') AS avg_duration_24h,
                    AVG(duration_ms) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') AS avg_duration_7d,
                    COALESCE(SUM(violations_total) FILTER (WHERE created_at >= NOW() - INTERVAL '24 hours'), 0) AS violations_24h,
                    COALESCE(SUM(violations_total) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days'), 0) AS violations_7d
                FROM events
            """)).mappings().first()

            by_endpoint = conn.execute(text("""
                SELECT endpoint, COUNT(*) AS total
                FROM events
                WHERE created_at >= NOW() - INTERVAL '7 days'
                GROUP BY endpoint
                ORDER BY total DESC
                LIMIT 10
            """)).mappings().all()

            recent_errors = conn.execute(text("""
                SELECT created_at, endpoint, status_code, message_short
                FROM errors
                ORDER BY created_at DESC
                LIMIT 20
            """)).mappings().all()
            top_words = conn.execute(text("""
                SELECT word, count, last_seen_at
                FROM violation_words
                ORDER BY count DESC, last_seen_at DESC
                LIMIT 20
            """)).mappings().all()

        events_24h = int(totals_row['events_24h'] or 0)
        events_7d = int(totals_row['events_7d'] or 0)
        errors_24h = int(totals_row['errors_24h'] or 0)
        errors_7d = int(totals_row['errors_7d'] or 0)

        return jsonify({
            'enabled': True,
            'window': {
                'events_24h': events_24h,
                'events_7d': events_7d,
                'errors_24h': errors_24h,
                'errors_7d': errors_7d,
                'error_rate_24h': round((errors_24h / events_24h) * 100, 2) if events_24h else 0.0,
                'error_rate_7d': round((errors_7d / events_7d) * 100, 2) if events_7d else 0.0,
                'avg_duration_ms_24h': round(float(totals_row['avg_duration_24h'] or 0), 2),
                'avg_duration_ms_7d': round(float(totals_row['avg_duration_7d'] or 0), 2),
                'violations_24h': int(totals_row['violations_24h'] or 0),
                'violations_7d': int(totals_row['violations_7d'] or 0)
            },
            'top_endpoints_7d': [{'endpoint': row['endpoint'], 'total': int(row['total'])} for row in by_endpoint],
            'top_violation_words': [
                {
                    'word': row['word'],
                    'count': int(row['count']),
                    'last_seen_at': row['last_seen_at'].isoformat() if row.get('last_seen_at') else None
                }
                for row in top_words
            ],
            'recent_errors': [
                {
                    'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
                    'endpoint': row['endpoint'],
                    'status_code': int(row['status_code']),
                    'message_short': row['message_short']
                }
                for row in recent_errors
            ],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        log_error('/api/metrics', 500, str(e))
        return jsonify({'enabled': True, 'error': str(e)}), 500


@app.route('/api/run-history', methods=['GET'])
def get_run_history():
    """Последние запуски проверок из БД (минимальная агрегированная история)"""
    if db_engine is None:
        return jsonify({'enabled': False, 'error': 'Database is not configured'}), 503
    limit = _safe_int(request.args.get('limit', 20), 20, 1, 100)
    try:
        with db_engine.begin() as conn:
            rows = conn.execute(text("""
                SELECT created_at, check_type, endpoint, source_type, context_short, success, duration_ms, violations_count
                FROM run_history
                ORDER BY created_at DESC
                LIMIT :limit
            """), {'limit': limit}).mappings().all()

        return jsonify({
            'enabled': True,
            'limit': limit,
            'items': [
                {
                    'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
                    'check_type': row.get('check_type'),
                    'endpoint': row.get('endpoint'),
                    'source_type': row.get('source_type'),
                    'context_short': row.get('context_short'),
                    'success': bool(row.get('success')),
                    'duration_ms': round(float(row.get('duration_ms') or 0), 2),
                    'violations_count': int(row.get('violations_count') or 0)
                }
                for row in rows
            ],
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        log_error('/api/run-history', 500, str(e))
        return jsonify({'enabled': True, 'error': str(e)}), 500

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
        total_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            event_type='ocr_check',
            endpoint='/api/images/check',
            success=True,
            duration_ms=total_ms,
            source_type='image',
            items_total=1,
            items_error=0,
            violations_total=result.get('violations_count', 0)
        )
        insert_run_history(
            check_type='image',
            endpoint='/api/images/check',
            success=True,
            duration_ms=total_ms,
            source_type='image',
            context_short=(image_url or 'uploaded_file')[:255],
            violations_count=result.get('violations_count', 0)
        )
        upsert_violation_words(
            (result.get('latin_words') or [])
            + (result.get('unknown_cyrillic') or [])
            + (result.get('nenormative_words') or [])
        )

        return jsonify({'success': True, 'provider': provider, 'result': result, 'timestamp': datetime.now().isoformat()})
    except Exception as e:
        log_error('/api/images/check', 500, str(e))
        log_event(event_type='ocr_check', endpoint='/api/images/check', success=False, source_type='image', items_total=1, items_error=1)
        insert_run_history(check_type='image', endpoint='/api/images/check', success=False, source_type='image')
        return jsonify({'error': str(e)}), 500


@app.route('/api/multiscan/run', methods=['POST'])
def multiscan_run():
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}

        mode = (data.get('mode') or 'site').strip().lower()
        provider = (data.get('provider') or session.get('images_provider') or 'openai').strip().lower()
        model = (data.get('model') or '').strip()
        incoming_token = (data.get('token') or '').strip()

        if provider not in ('openai', 'google', 'ocrspace'):
            return jsonify({'error': 'Unsupported provider'}), 400

        if incoming_token:
            tokens = session.get('image_api_tokens', {})
            tokens[provider] = incoming_token
            session['image_api_tokens'] = tokens
            session['images_provider'] = provider
            session.modified = True

        token = (session.get('image_api_tokens', {}).get(provider) or '').strip()
        delay_ms = _safe_int(data.get('delay_ms', 150), 150, 0, 10000)
        timeout_sec = _safe_int(data.get('timeout_sec', 18), 18, 5, 60)
        max_urls = _safe_int(data.get('max_urls', 500), 500, 1, MULTISCAN_MAX_URLS_HARD)
        max_pages = _safe_int(data.get('max_pages', 500), 500, 1, MULTISCAN_MAX_PAGES_HARD)
        max_resources = _safe_int(data.get('max_resources', 2500), 2500, 1, MULTISCAN_MAX_RESOURCES_HARD)
        include_external = _safe_bool(data.get('include_external'), False)
        max_text_chars = _safe_int(data.get('max_text_chars', MULTISCAN_MAX_TEXT_CHARS), MULTISCAN_MAX_TEXT_CHARS, 2000, MULTISCAN_MAX_TEXT_CHARS)

        checker_instance = get_checker()
        results = []
        seen = set()
        crawl_stats = {
            'pages_scanned': 0,
            'images_discovered': 0,
            'pdf_discovered': 0,
            'queue_dropped_by_limits': 0
        }

        def add_result(item):
            results.append(item)
            if len(results) > max_urls:
                raise RuntimeError(f'Max URLs limit reached ({max_urls})')

        def process_text_resource(url, text, resource_type, source_meta=None):
            checked_text = (text or '')[:max_text_chars]
            checked = checker_instance.check_text(checked_text)
            checked['recommendations'] = generate_recommendations(checked)
            add_result(_build_resource_result(url, resource_type, checked, source_meta=source_meta))

        def process_image_resource(image_url):
            if not token:
                add_result({
                    'url': image_url,
                    'resource_type': 'image',
                    'success': False,
                    'error': f'Set API token first for provider={provider}'
                })
                return
            if provider == 'openai':
                extracted_text, raw_response = _ocr_openai(token, model, image_url=image_url)
            elif provider == 'google':
                extracted_text, raw_response = _ocr_google(token, model, image_url=image_url)
            else:
                extracted_text, raw_response = _ocr_ocrspace(token, model, image_url=image_url)

            if not extracted_text.strip():
                add_result({
                    'url': image_url,
                    'resource_type': 'image',
                    'success': False,
                    'error': 'OCR returned empty text'
                })
                return
            checked = checker_instance.check_text(extracted_text[:max_text_chars])
            checked['recommendations'] = generate_recommendations(checked)
            checked['ocr'] = {
                'provider': provider,
                'model': model or ('gpt-4.1-mini' if provider == 'openai' else 'DOCUMENT_TEXT_DETECTION' if provider == 'google' else 'rus'),
                'source': image_url,
                'text_length': len(extracted_text),
                'usage': _extract_ocr_usage(provider, raw_response)
            }
            checked['source_type'] = 'image'
            checked['source_url'] = image_url
            checked['extracted_text'] = extracted_text
            add_result(_build_resource_result(image_url, 'image', checked))

        def process_pdf_resource(pdf_url):
            raw, _content_type = _fetch_url_bytes(pdf_url, timeout_sec=timeout_sec)
            pdf_text = _extract_pdf_text(raw)
            process_text_resource(
                pdf_url,
                pdf_text,
                'pdf',
                source_meta={'text_length': len(pdf_text)}
            )

        def process_page_resource(page_url):
            raw, content_type = _fetch_url_bytes(page_url, timeout_sec=timeout_sec)
            html_text = raw.decode('utf-8', errors='replace')
            page_text, page_title, soup = _extract_visible_text_from_html(html_text)
            process_text_resource(
                page_url,
                page_text,
                'page',
                source_meta={'title': page_title, 'content_type': content_type, 'text_length': len(page_text)}
            )
            return soup

        if mode == 'site':
            site_url = _normalize_http_url(data.get('site_url') or '')
            if not site_url:
                return jsonify({'error': 'Provide valid site_url'}), 400

            page_queue = deque([site_url])
            discovered_images = deque()
            discovered_pdfs = deque()

            while page_queue and crawl_stats['pages_scanned'] < max_pages and len(results) < max_urls:
                current_url = page_queue.popleft()
                if current_url in seen:
                    continue
                seen.add(current_url)
                try:
                    soup = process_page_resource(current_url)
                    crawl_stats['pages_scanned'] += 1
                    page_links, image_links, pdf_links = _extract_links_from_soup(soup, current_url)

                    for page_link in page_links:
                        if page_link in seen:
                            continue
                        if not include_external and not _same_domain(site_url, page_link):
                            continue
                        if len(page_queue) + crawl_stats['pages_scanned'] >= max_pages:
                            crawl_stats['queue_dropped_by_limits'] += 1
                            continue
                        page_queue.append(page_link)

                    for image_link in image_links:
                        if image_link in seen:
                            continue
                        if not include_external and not _same_domain(site_url, image_link):
                            continue
                        if len(discovered_images) + len(discovered_pdfs) >= max_resources:
                            crawl_stats['queue_dropped_by_limits'] += 1
                            continue
                        discovered_images.append(image_link)
                        seen.add(image_link)
                        crawl_stats['images_discovered'] += 1

                    for pdf_link in pdf_links:
                        if pdf_link in seen:
                            continue
                        if not include_external and not _same_domain(site_url, pdf_link):
                            continue
                        if len(discovered_images) + len(discovered_pdfs) >= max_resources:
                            crawl_stats['queue_dropped_by_limits'] += 1
                            continue
                        discovered_pdfs.append(pdf_link)
                        seen.add(pdf_link)
                        crawl_stats['pdf_discovered'] += 1

                except Exception as e:
                    add_result({
                        'url': current_url,
                        'resource_type': 'page',
                        'success': False,
                        'error': str(e)
                    })

                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

            while discovered_images and len(results) < max_urls:
                image_url = discovered_images.popleft()
                try:
                    process_image_resource(image_url)
                except Exception as e:
                    add_result({
                        'url': image_url,
                        'resource_type': 'image',
                        'success': False,
                        'error': str(e)
                    })
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

            while discovered_pdfs and len(results) < max_urls:
                pdf_url = discovered_pdfs.popleft()
                try:
                    process_pdf_resource(pdf_url)
                except Exception as e:
                    add_result({
                        'url': pdf_url,
                        'resource_type': 'pdf',
                        'success': False,
                        'error': str(e)
                    })
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

        elif mode == 'urls':
            incoming_urls = data.get('urls') or []
            if isinstance(incoming_urls, str):
                incoming_urls = [u.strip() for u in incoming_urls.splitlines() if u.strip()]

            normalized_urls = []
            for raw_url in incoming_urls:
                normalized = _normalize_http_url(raw_url)
                if not normalized:
                    continue
                if normalized in seen:
                    continue
                seen.add(normalized)
                normalized_urls.append(normalized)
                if len(normalized_urls) >= max_urls:
                    break

            if not normalized_urls:
                return jsonify({'error': 'No valid URLs provided'}), 400

            for item_url in normalized_urls:
                try:
                    if _is_image_url(item_url):
                        process_image_resource(item_url)
                    elif _is_pdf_url(item_url):
                        process_pdf_resource(item_url)
                    else:
                        raw, content_type = _fetch_url_bytes(item_url, timeout_sec=timeout_sec)
                        if 'pdf' in content_type:
                            pdf_text = _extract_pdf_text(raw)
                            process_text_resource(item_url, pdf_text, 'pdf', source_meta={'content_type': content_type, 'text_length': len(pdf_text)})
                        elif any(x in content_type for x in ('image/', 'octet-stream')) and _is_image_url(item_url):
                            process_image_resource(item_url)
                        else:
                            html_text = raw.decode('utf-8', errors='replace')
                            page_text, page_title, _soup = _extract_visible_text_from_html(html_text)
                            process_text_resource(item_url, page_text, 'page', source_meta={'title': page_title, 'content_type': content_type, 'text_length': len(page_text)})
                except Exception as e:
                    guessed_type = 'image' if _is_image_url(item_url) else 'pdf' if _is_pdf_url(item_url) else 'page'
                    add_result({'url': item_url, 'resource_type': guessed_type, 'success': False, 'error': str(e)})
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)
        else:
            return jsonify({'error': 'Unsupported mode. Use "site" or "urls".'}), 400

        success_items = [r for r in results if r.get('success')]
        error_items = [r for r in results if not r.get('success')]
        with_violations = [r for r in success_items if not r.get('law_compliant', True)]
        totals_by_type = defaultdict(int)
        for item in results:
            totals_by_type[item.get('resource_type', 'unknown')] += 1
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        violations_total = sum(item.get('violations_count', 0) for item in success_items)
        log_event(
            event_type='multiscan',
            endpoint='/api/multiscan/run',
            success=True,
            duration_ms=duration_ms,
            source_type='mixed',
            items_total=len(results),
            items_error=len(error_items),
            violations_total=violations_total
        )
        insert_run_history(
            check_type='multiscan',
            endpoint='/api/multiscan/run',
            success=True,
            duration_ms=duration_ms,
            source_type='mixed',
            context_short=f'mode={mode} total={len(results)} err={len(error_items)}',
            violations_count=violations_total
        )
        all_words = []
        for item in success_items:
            all_words.extend(item.get('forbidden_words') or [])
        upsert_violation_words(all_words)

        return jsonify({
            'success': True,
            'mode': mode,
            'provider': provider,
            'model': model or None,
            'limits': {
                'max_urls': max_urls,
                'max_pages': max_pages,
                'max_resources': max_resources,
                'max_text_chars': max_text_chars
            },
            'crawl_stats': crawl_stats,
            'total': len(results),
            'processed_success': len(success_items),
            'processed_error': len(error_items),
            'with_violations': len(with_violations),
            'totals_by_type': dict(totals_by_type),
            'results': results,
            'timings_ms': {
                'total': duration_ms
            },
            'timestamp': datetime.now().isoformat()
        })
    except RuntimeError as e:
        log_error('/api/multiscan/run', 400, str(e))
        log_event(event_type='multiscan', endpoint='/api/multiscan/run', success=False, source_type='mixed', items_error=1)
        insert_run_history(check_type='multiscan', endpoint='/api/multiscan/run', success=False, source_type='mixed')
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        log_error('/api/multiscan/run', 500, str(e))
        log_event(event_type='multiscan', endpoint='/api/multiscan/run', success=False, source_type='mixed', items_error=1)
        insert_run_history(check_type='multiscan', endpoint='/api/multiscan/run', success=False, source_type='mixed')
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


@app.route('/api/export/multiscan-txt', methods=['POST'])
def export_multiscan_txt():
    """Экспорт отчета MultiScan в TXT с разбивкой по типам ресурсов"""
    try:
        data = request.get_json(silent=True) or {}
        scan = data.get('scan') or {}
        results = scan.get('results') or []

        if not results:
            return jsonify({'error': 'Нет данных для экспорта'}), 400

        lines = []
        lines.append("=" * 90)
        lines.append("MULTISCAN SITE REPORT")
        lines.append("=" * 90)
        lines.append(f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append(f"Режим: {scan.get('mode', '-')}")
        lines.append(f"OCR provider: {scan.get('provider', '-')}")
        lines.append(f"Model: {scan.get('model') or '-'}")
        lines.append("")

        total = len(results)
        success_count = sum(1 for item in results if item.get('success'))
        error_count = total - success_count
        violations_count = sum(1 for item in results if item.get('success') and not item.get('law_compliant', True))

        by_type = defaultdict(int)
        for item in results:
            by_type[item.get('resource_type', 'unknown')] += 1

        lines.append("-" * 90)
        lines.append("СВОДКА")
        lines.append("-" * 90)
        lines.append(f"Всего ресурсов: {total}")
        lines.append(f"Успешно обработано: {success_count}")
        lines.append(f"С ошибками: {error_count}")
        lines.append(f"С нарушениями: {violations_count}")
        lines.append(f"Страницы: {by_type.get('page', 0)}")
        lines.append(f"Картинки: {by_type.get('image', 0)}")
        lines.append(f"PDF: {by_type.get('pdf', 0)}")
        lines.append("")

        lines.append("=" * 90)
        lines.append("ДЕТАЛЬНЫЙ ОТЧЕТ ПО URL")
        lines.append("=" * 90)
        lines.append("")

        all_forbidden = set()
        for idx, item in enumerate(results, 1):
            url = item.get('url', 'unknown')
            resource_type = item.get('resource_type', 'unknown')
            lines.append(f"[{idx}] {url}")
            lines.append(f"Тип: {resource_type}")

            if not item.get('success'):
                lines.append(f"Статус: ОШИБКА ({item.get('error', 'Unknown error')})")
                lines.append("-" * 90)
                continue

            item_result = item.get('result') or {}
            compliant = item.get('law_compliant', True)
            forbidden_words = item.get('forbidden_words') or []
            all_forbidden.update(forbidden_words)

            lines.append(f"Статус: {'OK' if compliant else 'НАРУШЕНИЯ'}")
            lines.append(f"Нарушений: {item.get('violations_count', 0)}")
            lines.append(f"Слов в тексте: {item_result.get('total_words', 0)}")

            if forbidden_words:
                lines.append(f"Запрещенные/подозрительные слова ({len(forbidden_words)}):")
                for word in forbidden_words:
                    lines.append(f"  - {word}")
            else:
                lines.append("Запрещенные/подозрительные слова: не найдены")

            lines.append("-" * 90)

        if all_forbidden:
            lines.append("")
            lines.append("=" * 90)
            lines.append("УНИКАЛЬНЫЕ СЛОВА ПО ВСЕМ РЕСУРСАМ")
            lines.append("=" * 90)
            for word in sorted(all_forbidden):
                lines.append(f"- {word}")

        report = "\n".join(lines)

        output = io.BytesIO()
        output.write('\ufeff'.encode('utf-8'))
        output.write(report.encode('utf-8'))
        output.seek(0)

        return send_file(
            output,
            mimetype='text/plain; charset=utf-8',
            as_attachment=True,
            download_name=f'lawcheck_multiscan_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
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
