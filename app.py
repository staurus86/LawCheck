#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API для проверки текста на соответствие закону №168-ФЗ
РЕФАКТОРЕННАЯ ВЕРСИЯ с модульной архитектурой
"""

from flask import Flask, render_template, request, jsonify, send_file, session, Response
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
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
from sqlalchemy import text

# Импорты новых модулей
from config import get_config
from utils import init_db_manager, get_db_manager
from utils.helpers import (
    mask_token, extract_data_url_payload, normalize_http_url,
    safe_int, safe_bool, extract_openai_text, extract_ocr_usage
)
from services import get_checker_service, OCRService
from routes import page_bp

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

# Создание приложения с конфигурацией
app = Flask(__name__)
config = get_config()

# Применение конфигурации
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.secret_key = config.SECRET_KEY

# Настройка логирования
if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('LawChecker startup')

# Конфигурационные переменные (для совместимости)
OCR_TIMEOUT = config.OCR_TIMEOUT
OPENAI_OCR_BASE_URL = config.OPENAI_OCR_BASE_URL
GOOGLE_VISION_BASE_URL = config.GOOGLE_VISION_BASE_URL
OCRSPACE_BASE_URL = config.OCRSPACE_BASE_URL
MULTISCAN_MAX_URLS_HARD = config.MULTISCAN_MAX_URLS_HARD
MULTISCAN_MAX_PAGES_HARD = config.MULTISCAN_MAX_PAGES_HARD
MULTISCAN_MAX_RESOURCES_HARD = config.MULTISCAN_MAX_RESOURCES_HARD
MULTISCAN_MAX_TEXT_CHARS = config.MULTISCAN_MAX_TEXT_CHARS
MULTISCAN_MAX_DOWNLOAD_BYTES = config.MULTISCAN_MAX_DOWNLOAD_BYTES
MULTISCAN_USER_AGENT = config.MULTISCAN_USER_AGENT
METRICS_RETENTION_DAYS = config.METRICS_RETENTION_DAYS
METRICS_CLEANUP_INTERVAL_SEC = config.METRICS_CLEANUP_INTERVAL_SEC

# Инициализация БД через новый модуль
db_manager = init_db_manager(
    database_url=config.DATABASE_URL,
    retention_days=config.METRICS_RETENTION_DAYS,
    cleanup_interval_sec=config.METRICS_CLEANUP_INTERVAL_SEC
)

# Для совместимости с существующим кодом
db_engine = db_manager.db_engine if db_manager else None

# CORS - разрешаем все домены
CORS(app, resources={
    r"/api/*": {
        "origins": config.CORS_ORIGINS,
        "methods": config.CORS_METHODS,
        "allow_headers": config.CORS_ALLOW_HEADERS
    }
})

# Инициализация сервисов
ocr_service = OCRService(
    openai_base_url=config.OPENAI_OCR_BASE_URL,
    google_base_url=config.GOOGLE_VISION_BASE_URL,
    ocrspace_base_url=config.OCRSPACE_BASE_URL,
    timeout=config.OCR_TIMEOUT
)

# Получение checker через сервис
def get_checker():
    """Get or create checker instance with lazy initialization"""
    return get_checker_service().get_checker()

# Хранилище истории проверок (в продакшене используйте Redis/Database)
check_history = deque(maxlen=1000)
statistics = {
    'total_checks': 0,
    'total_violations': 0,
    'most_common_violations': defaultdict(int)
}

# Регистрация page routes blueprint
app.register_blueprint(page_bp)

# Rate limiting для защиты API
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=config.RATELIMIT_STORAGE_URL
)


# Функции работы с БД (обертки для совместимости)
def log_event(event_type, endpoint, success, duration_ms=None, source_type=None, items_total=0, items_error=0, violations_total=0):
    """Логирование события через db_manager"""
    if db_manager:
        db_manager.log_event(event_type, endpoint, success, duration_ms, source_type, items_total, items_error, violations_total)


def log_error(endpoint, status_code, message):
    """Логирование ошибки через db_manager"""
    if db_manager:
        db_manager.log_error(endpoint, status_code, message)


def insert_run_history(check_type, endpoint, success, duration_ms=None, source_type=None, context_short=None, violations_count=0):
    """Добавление записи в историю через db_manager"""
    if db_manager:
        db_manager.insert_run_history(check_type, endpoint, success, duration_ms, source_type, context_short, violations_count)


def upsert_violation_words(words):
    """Обновление счетчиков слов-нарушений через db_manager"""
    if db_manager:
        db_manager.upsert_violation_words(words)


def cleanup_analytics_db(force=False):
    """Очистка старых данных через db_manager"""
    if db_manager:
        db_manager.cleanup_old_data(force=force)

# Page routes moved to routes/page_routes.py (registered as blueprint above)

# Global error handlers (дополняют error handlers в blueprint)
@app.errorhandler(404)
def not_found(_error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template('500.html'), 500

# Алиасы для совместимости (функции перенесены в utils.helpers)
_mask_token = mask_token
_extract_data_url_payload = extract_data_url_payload
_normalize_http_url = normalize_http_url
_safe_int = safe_int
_safe_bool = safe_bool
_extract_openai_text = extract_openai_text
_extract_ocr_usage = extract_ocr_usage


# OCR функции через сервис
def _ocr_openai(api_key, model, image_url=None, image_data_url=None):
    """OCR через OpenAI (обертка для совместимости)"""
    return ocr_service.ocr_openai(api_key, model, image_url, image_data_url)


def _ocr_google(api_key, model, image_url=None, image_data_url=None):
    """OCR через Google Vision (обертка для совместимости)"""
    return ocr_service.ocr_google(api_key, model, image_url, image_data_url)


def _ocr_ocrspace(api_key, model, image_url=None, image_data_url=None):
    """OCR через OCR.Space (обертка для совместимости)"""
    return ocr_service.ocr_ocrspace(api_key, model, image_url, image_data_url)


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
@limiter.limit("30 per minute")
def check_text():
    """API: Проверка текста"""
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}
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
@limiter.limit("20 per minute")
def check_url():
    """API: Проверка URL"""
    try:
        started_at = time.perf_counter()
        data = request.get_json(silent=True) or {}
        url = data.get('url', '')
        
        if not url or not url.startswith('http'):
            return jsonify({'error': 'Некорректный URL'}), 400
        
        # Загрузка страницы
        try:
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
        except requests.exceptions.Timeout:
            return jsonify({'error': 'Сайт не отвечает (таймаут 15 сек)'}), 504
        except requests.exceptions.ConnectionError:
            return jsonify({'error': 'Не удалось подключиться к сайту'}), 502
        except requests.exceptions.HTTPError as http_err:
            return jsonify({'error': f'HTTP ошибка: {http_err.response.status_code}'}), 502
        except requests.exceptions.RequestException as req_err:
            return jsonify({'error': f'Ошибка загрузки: {str(req_err)}'}), 502

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
@limiter.limit("10 per hour")
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
@limiter.limit("20 per minute")
def deep_check():
    """API: Глубокая проверка слов с использованием морфологии и speller"""
    try:
        data = request.get_json(silent=True) or {}
        words = data.get('words', [])

        if not isinstance(words, list):
            return jsonify({'error': 'words должен быть массивом'}), 400

        if not words:
            return jsonify({'error': 'Список слов пуст'}), 400

        # Используем метод через checker_service
        checker_instance = get_checker()

        # Вызываем deep_check_words который есть в checker.py
        if hasattr(checker_instance, 'deep_check_words'):
            results = checker_instance.deep_check_words(words)
        else:
            # Fallback на прямой вызов _deep_check_single
            results = []
            for word in words:
                if hasattr(checker_instance, '_deep_check_single'):
                    result = checker_instance._deep_check_single(word)
                    results.append(result)
                else:
                    results.append({
                        'word': word,
                        'is_valid': False,
                        'error': 'Method not available'
                    })

        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        app.logger.error(f"Deep check error: {str(e)}", exc_info=True)
        log_error('/api/deep-check', 500, str(e))
        return jsonify({'error': str(e), 'details': 'Check server logs'}), 500

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


@app.route('/api/metrics/cleanup', methods=['POST'])
@limiter.limit("5 per hour")
def cleanup_metrics():
    """API: Очистка метрик (полная очистка для освобождения места)"""
    try:
        data = request.get_json(silent=True) or {}
        secret = data.get('secret', '').strip()

        # Вариант 1: SECRET_KEY (первые 16 символов)
        # Вариант 2: Простой пароль "CLEANUP_DB" (для удобства)
        valid_secret = app.secret_key[:16]
        simple_password = "CLEANUP_DB"

        if secret != valid_secret and secret != simple_password:
            return jsonify({
                'error': 'Неверный пароль',
                'hint': 'Используйте "CLEANUP_DB" или первые 16 символов SECRET_KEY'
            }), 401

        if db_manager:
            result = db_manager.cleanup_all_metrics()
            app.logger.warning(f"Metrics cleaned up by admin: {result}")
            return jsonify(result)
        else:
            return jsonify({'error': 'Database not available'}), 503
    except Exception as e:
        app.logger.error(f"Cleanup metrics error: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """Мини-метрики по событиям сервиса из PostgreSQL"""
    if db_engine is None:
        return jsonify({
            'enabled': False,
            'error': 'Database is not configured'
        }), 503
    days = _safe_int(request.args.get('days', 7), 7, 1, 90)
    event_type = (request.args.get('event_type') or '').strip()
    source_type = (request.args.get('source_type') or '').strip()
    endpoint_filter = (request.args.get('endpoint') or '').strip()

    where_clauses = ["created_at >= NOW() - make_interval(days => :days)"]
    query_params = {'days': days}
    if event_type:
        where_clauses.append("event_type = :event_type")
        query_params['event_type'] = event_type
    if source_type:
        where_clauses.append("source_type = :source_type")
        query_params['source_type'] = source_type
    if endpoint_filter:
        where_clauses.append("endpoint ILIKE :endpoint_like")
        query_params['endpoint_like'] = f"%{endpoint_filter}%"
    where_sql = " AND ".join(where_clauses)

    try:
        with db_engine.begin() as conn:
            totals_row = conn.execute(text(f"""
                SELECT
                    COUNT(*) AS events_total,
                    COUNT(*) FILTER (WHERE success = FALSE) AS errors_total,
                    AVG(duration_ms) AS avg_duration_ms,
                    COALESCE(SUM(violations_total), 0) AS violations_total
                FROM events
                WHERE {where_sql}
            """), query_params).mappings().first()

            by_endpoint = conn.execute(text(f"""
                SELECT endpoint, COUNT(*) AS total
                FROM events
                WHERE {where_sql}
                GROUP BY endpoint
                ORDER BY total DESC
                LIMIT 10
            """), query_params).mappings().all()

            recent_errors = conn.execute(text("""
                SELECT created_at, endpoint, status_code, message_short
                FROM errors
                ORDER BY created_at DESC
                LIMIT 20
            """)).mappings().all()
            top_words = conn.execute(text("""
                SELECT word, count, last_seen_at
                FROM violation_words
                WHERE last_seen_at >= NOW() - make_interval(days => :days)
                ORDER BY count DESC, last_seen_at DESC
                LIMIT 20
            """), {'days': days}).mappings().all()
            trend_rows = conn.execute(text(f"""
                SELECT date_trunc('day', created_at) AS day, COUNT(*) AS total, COUNT(*) FILTER (WHERE success = FALSE) AS errors
                FROM events
                WHERE {where_sql}
                GROUP BY date_trunc('day', created_at)
                ORDER BY day ASC
            """), query_params).mappings().all()

        events_total = int(totals_row['events_total'] or 0)
        errors_total = int(totals_row['errors_total'] or 0)
        avg_duration = round(float(totals_row['avg_duration_ms'] or 0), 2)
        violations_total = int(totals_row['violations_total'] or 0)

        return jsonify({
            'enabled': True,
            'window': {
                'days': days,
                'events_total': events_total,
                'errors_total': errors_total,
                'error_rate': round((errors_total / events_total) * 100, 2) if events_total else 0.0,
                'avg_duration_ms': avg_duration,
                'violations_total': violations_total
            },
            'filters': {
                'event_type': event_type or None,
                'source_type': source_type or None,
                'endpoint': endpoint_filter or None
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
            'trend_by_day': [
                {
                    'day': row['day'].date().isoformat() if row.get('day') else None,
                    'total': int(row['total'] or 0),
                    'errors': int(row['errors'] or 0)
                }
                for row in trend_rows
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
    days = _safe_int(request.args.get('days', 7), 7, 1, 90)
    check_type = (request.args.get('check_type') or '').strip().lower()
    status_filter = (request.args.get('status') or '').strip().lower()
    try:
        where_clauses = ["created_at >= NOW() - make_interval(days => :days)"]
        params = {'limit': limit, 'days': days}
        if check_type and check_type != 'all':
            where_clauses.append("check_type = :check_type")
            params['check_type'] = check_type
        if status_filter == 'ok':
            where_clauses.append("success = TRUE")
        elif status_filter == 'error':
            where_clauses.append("success = FALSE")
        where_sql = " AND ".join(where_clauses)

        with db_engine.begin() as conn:
            rows = conn.execute(text(f"""
                SELECT created_at, check_type, endpoint, source_type, context_short, success, duration_ms, violations_count
                FROM run_history
                WHERE {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit
            """), params).mappings().all()

        return jsonify({
            'enabled': True,
            'limit': limit,
            'days': days,
            'filters': {'check_type': check_type or 'all', 'status': status_filter or 'all'},
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
        data = request.get_json(silent=True) or {}
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
    limit = _safe_int(request.args.get('limit', 10), 10, 1, 1000)
    history_list = list(check_history)
    return jsonify({
        'history': history_list[-limit:][::-1],
        'total': len(history_list)
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
        site_url = request.host_url.rstrip('/')
        lines.append("=" * 70)
        lines.append("Создано: LawChecker Online")
        lines.append(f"Сайт: {site_url}")
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
    """Сохранение в историю (deque с maxlen=1000 автоматически вытесняет старые записи)"""
    check_history.append({
        'id': str(uuid.uuid4()),
        'type': check_type,
        'timestamp': datetime.now().isoformat(),
        'violations': result['violations_count'],
        'compliant': result['law_compliant'],
        'context': context
    })

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
