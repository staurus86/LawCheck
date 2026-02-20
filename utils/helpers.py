#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Вспомогательные функции для приложения
"""

from typing import Any, Optional
from urllib.parse import urldefrag


def mask_token(token: Optional[str]) -> str:
    """
    Маскировка токена для безопасного отображения

    Args:
        token: Токен для маскировки

    Returns:
        Замаскированный токен
    """
    if not token:
        return ''
    if len(token) <= 8:
        return '*' * len(token)
    return f"{token[:4]}...{token[-4:]}"


def extract_data_url_payload(image_data_url: str) -> str:
    """
    Извлечение base64 payload из data URL

    Args:
        image_data_url: Data URL изображения

    Returns:
        Base64 payload

    Raises:
        ValueError: Если data URL невалидный
    """
    if not image_data_url or ';base64,' not in image_data_url:
        raise ValueError('Invalid image data URL')
    return image_data_url.split(';base64,', 1)[1]


def normalize_http_url(raw_url: Optional[str]) -> str:
    """
    Нормализация HTTP/HTTPS URL

    Args:
        raw_url: Сырой URL

    Returns:
        Нормализованный URL (без фрагмента) или пустая строка
    """
    url = (raw_url or '').strip()
    if not url:
        return ''
    if not url.startswith('http://') and not url.startswith('https://'):
        return ''
    return urldefrag(url)[0]


def safe_int(value: Any, default_value: int, min_value: int, max_value: int) -> int:
    """
    Безопасное преобразование в int с ограничениями

    Args:
        value: Значение для преобразования
        default_value: Значение по умолчанию
        min_value: Минимальное значение
        max_value: Максимальное значение

    Returns:
        Целое число в пределах [min_value, max_value]
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default_value
    return max(min_value, min(parsed, max_value))


def safe_bool(value: Any, default_value: bool = False) -> bool:
    """
    Безопасное преобразование в bool

    Args:
        value: Значение для преобразования
        default_value: Значение по умолчанию

    Returns:
        Boolean значение
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default_value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def extract_openai_text(response_json: dict) -> str:
    """
    Извлечение текста из ответа OpenAI API

    Args:
        response_json: JSON ответ от OpenAI

    Returns:
        Извлеченный текст
    """
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


def extract_ocr_usage(provider: str, raw_response: dict) -> dict:
    """
    Извлечение информации об использовании из OCR ответа

    Args:
        provider: Провайдер OCR (openai, google, ocrspace)
        raw_response: Сырой ответ от провайдера

    Returns:
        Словарь с метриками использования
    """
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
        return {
            'pages_detected': len(pages),
            'text_annotations': len(text_annotations)
        }

    if provider == 'ocrspace':
        parsed = raw_response.get('ParsedResults') or []
        processing_ms = None
        if parsed:
            value = parsed[0].get('ProcessingTimeInMilliseconds')
            try:
                processing_ms = int(float(value))
            except (TypeError, ValueError):
                processing_ms = None
        return {
            'parsed_results': len(parsed),
            'processing_ms': processing_ms
        }

    return {}
