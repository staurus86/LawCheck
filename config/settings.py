#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конфигурация приложения LawChecker
"""

import os
from typing import Optional


class Config:
    """Базовая конфигурация приложения"""

    # Flask
    SECRET_KEY: str = os.getenv('FLASK_SECRET_KEY', os.getenv('SECRET_KEY', 'change-this-secret-key'))
    MAX_CONTENT_LENGTH: int = 16 * 1024 * 1024  # 16MB max request size

    # OCR настройки
    OCR_TIMEOUT: int = int(os.getenv('OCR_TIMEOUT', '30'))
    OPENAI_OCR_BASE_URL: str = os.getenv('OPENAI_OCR_BASE_URL', 'https://api.openai.com/v1').strip()
    GOOGLE_VISION_BASE_URL: str = os.getenv('GOOGLE_VISION_BASE_URL', 'https://vision.googleapis.com/v1').strip()
    OCRSPACE_BASE_URL: str = os.getenv('OCRSPACE_BASE_URL', 'https://api.ocr.space').strip()

    # MultiScan лимиты
    MULTISCAN_MAX_URLS_HARD: int = int(os.getenv('MULTISCAN_MAX_URLS_HARD', '2000'))
    MULTISCAN_MAX_PAGES_HARD: int = int(os.getenv('MULTISCAN_MAX_PAGES_HARD', '2000'))
    MULTISCAN_MAX_RESOURCES_HARD: int = int(os.getenv('MULTISCAN_MAX_RESOURCES_HARD', '8000'))
    MULTISCAN_MAX_TEXT_CHARS: int = int(os.getenv('MULTISCAN_MAX_TEXT_CHARS', '200000'))
    MULTISCAN_MAX_DOWNLOAD_BYTES: int = int(os.getenv('MULTISCAN_MAX_DOWNLOAD_BYTES', str(8 * 1024 * 1024)))
    MULTISCAN_USER_AGENT: str = os.getenv('MULTISCAN_USER_AGENT', 'LawChecker-MultiScan/1.0')

    # Метрики и БД
    METRICS_RETENTION_DAYS: int = int(os.getenv('METRICS_RETENTION_DAYS', '60'))
    METRICS_CLEANUP_INTERVAL_SEC: int = int(os.getenv('METRICS_CLEANUP_INTERVAL_SEC', '3600'))

    # Database (Railway PostgreSQL)
    @staticmethod
    def get_database_url() -> Optional[str]:
        """Получить URL базы данных с автоматической конвертацией postgres:// в postgresql://"""
        raw_url = (os.getenv('DATABASE_URL') or os.getenv('database_URL') or '').strip()
        if not raw_url:
            return None
        if raw_url.startswith('postgres://'):
            return raw_url.replace('postgres://', 'postgresql://', 1)
        return raw_url

    DATABASE_URL: Optional[str] = get_database_url.__func__()

    # CORS настройки
    CORS_ORIGINS: str = "*"
    CORS_METHODS: list = ["GET", "POST", "OPTIONS"]
    CORS_ALLOW_HEADERS: list = ["Content-Type"]

    # Rate Limiting (будет добавлено позже)
    RATELIMIT_STORAGE_URL: str = os.getenv('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT: str = "200 per day;50 per hour"

    # Логирование
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: str = 'logs/app.log'
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 10


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    TESTING = False


class TestingConfig(Config):
    """Конфигурация для тестов"""
    DEBUG = True
    TESTING = True
    DATABASE_URL = None  # Используем in-memory для тестов


# Выбор конфигурации в зависимости от окружения
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config() -> Config:
    """Получить конфигурацию в зависимости от ENV"""
    env = os.getenv('FLASK_ENV', 'development')
    return config_by_name.get(env, DevelopmentConfig)
