#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для работы с OCR (распознавание текста с изображений)
"""

import base64
import logging
from typing import Optional, Tuple
import requests

from utils.helpers import extract_data_url_payload, extract_openai_text

logger = logging.getLogger(__name__)


class OCRService:
    """Сервис для распознавания текста с изображений"""

    def __init__(self, openai_base_url: str, google_base_url: str,
                 ocrspace_base_url: str, timeout: int = 30):
        """
        Инициализация OCR сервиса

        Args:
            openai_base_url: Base URL для OpenAI API
            google_base_url: Base URL для Google Vision API
            ocrspace_base_url: Base URL для OCR.Space API
            timeout: Таймаут запросов в секундах
        """
        self.openai_base_url = openai_base_url.rstrip('/')
        self.google_base_url = google_base_url.rstrip('/')
        self.ocrspace_base_url = ocrspace_base_url.rstrip('/')
        self.timeout = timeout

    def ocr_openai(self, api_key: str, model: Optional[str] = None,
                   image_url: Optional[str] = None,
                   image_data_url: Optional[str] = None) -> Tuple[str, dict]:
        """
        OCR через OpenAI API

        Args:
            api_key: API ключ OpenAI
            model: Модель для использования
            image_url: URL изображения
            image_data_url: Data URL изображения (base64)

        Returns:
            Tuple (распознанный текст, сырой ответ)

        Raises:
            ValueError: Если не передан ни image_url, ни image_data_url
            requests.HTTPError: При ошибке API
        """
        input_image = image_url or image_data_url
        if not input_image:
            raise ValueError('Pass image_url or image_data_url')

        payload = {
            'model': model or 'gpt-4.1-mini',
            'input': [{
                'role': 'user',
                'content': [
                    {
                        'type': 'input_text',
                        'text': 'Extract all text from this image and return plain raw OCR text only. '
                               'Do not edit, normalize, translate, summarize, censor, or correct anything. '
                               'Preserve original wording, casing, punctuation, numbers, and line breaks exactly as recognized.'
                    },
                    {'type': 'input_image', 'image_url': input_image}
                ]
            }]
        }

        response = requests.post(
            f"{self.openai_base_url}/responses",
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()

        extracted_text = extract_openai_text(data)
        return extracted_text, data

    def ocr_google(self, api_key: str, model: Optional[str] = None,
                   image_url: Optional[str] = None,
                   image_data_url: Optional[str] = None) -> Tuple[str, dict]:
        """
        OCR через Google Vision API

        Args:
            api_key: API ключ Google
            model: Тип feature (по умолчанию DOCUMENT_TEXT_DETECTION)
            image_url: URL изображения
            image_data_url: Data URL изображения (base64)

        Returns:
            Tuple (распознанный текст, сырой ответ)

        Raises:
            ValueError: Если не передан ни image_url, ни image_data_url
            requests.HTTPError: При ошибке API
        """
        feature_type = model or 'DOCUMENT_TEXT_DETECTION'
        image_block = {}

        if image_data_url:
            image_block['content'] = extract_data_url_payload(image_data_url)
        elif image_url:
            image_block['source'] = {'imageUri': image_url}
        else:
            raise ValueError('Pass image_url or image_data_url')

        payload = {
            'requests': [{
                'image': image_block,
                'features': [{'type': feature_type}]
            }]
        }

        response = requests.post(
            f"{self.google_base_url}/images:annotate?key={api_key}",
            headers={'Content-Type': 'application/json'},
            json=payload,
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()

        # Извлечение текста из ответа
        first = (data.get('responses') or [{}])[0]
        text = (
            (first.get('fullTextAnnotation') or {}).get('text')
            or ((first.get('textAnnotations') or [{}])[0].get('description')
                if first.get('textAnnotations') else '')
            or ''
        )

        return text.strip(), data

    def ocr_ocrspace(self, api_key: str, model: Optional[str] = None,
                     image_url: Optional[str] = None,
                     image_data_url: Optional[str] = None) -> Tuple[str, dict]:
        """
        OCR через OCR.Space API

        Args:
            api_key: API ключ OCR.Space
            model: Язык распознавания (по умолчанию 'rus')
            image_url: URL изображения
            image_data_url: Data URL изображения (base64)

        Returns:
            Tuple (распознанный текст, сырой ответ)

        Raises:
            ValueError: Если не передан ни image_url, ни image_data_url или при ошибке OCR
            requests.HTTPError: При ошибке API
        """
        data = {
            'language': model or 'rus',
            'isOverlayRequired': 'false',
            'OCREngine': '2'
        }
        files = None

        if image_data_url:
            file_bytes = base64.b64decode(extract_data_url_payload(image_data_url))
            files = {'file': ('image.png', file_bytes)}
        elif image_url:
            data['url'] = image_url
        else:
            raise ValueError('Pass image_url or image_data_url')

        response = requests.post(
            f"{self.ocrspace_base_url}/parse/image",
            headers={'apikey': api_key},
            data=data,
            files=files,
            timeout=self.timeout
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get('IsErroredOnProcessing'):
            error_msgs = payload.get('ErrorMessage') or ['OCR.Space error']
            raise ValueError('; '.join(error_msgs))

        parsed = payload.get('ParsedResults') or []
        text_parts = [item.get('ParsedText', '') for item in parsed if item.get('ParsedText')]

        return '\n'.join(text_parts).strip(), payload

    def process_ocr(self, provider: str, api_key: str, model: Optional[str] = None,
                    image_url: Optional[str] = None,
                    image_data_url: Optional[str] = None) -> Tuple[str, dict]:
        """
        Универсальный метод для OCR с автоматическим выбором провайдера

        Args:
            provider: Провайдер OCR (openai, google, ocrspace)
            api_key: API ключ
            model: Модель/настройки
            image_url: URL изображения
            image_data_url: Data URL изображения

        Returns:
            Tuple (распознанный текст, сырой ответ)

        Raises:
            ValueError: При невалидном провайдере или ошибке OCR
        """
        provider = provider.lower()

        if provider == 'openai':
            return self.ocr_openai(api_key, model, image_url, image_data_url)
        elif provider == 'google':
            return self.ocr_google(api_key, model, image_url, image_data_url)
        elif provider == 'ocrspace':
            return self.ocr_ocrspace(api_key, model, image_url, image_data_url)
        else:
            raise ValueError(f"Unknown OCR provider: {provider}")
