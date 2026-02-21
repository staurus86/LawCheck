#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных (PostgreSQL)
"""

import time
import logging
from typing import Optional, List
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер для работы с базой данных"""

    def __init__(self, database_url: Optional[str],
                 retention_days: int = 60,
                 cleanup_interval_sec: int = 3600):
        """
        Инициализация менеджера БД

        Args:
            database_url: URL подключения к PostgreSQL
            retention_days: Количество дней хранения метрик
            cleanup_interval_sec: Интервал между автоочистками
        """
        self.db_engine: Optional[Engine] = None
        self.retention_days = retention_days
        self.cleanup_interval_sec = cleanup_interval_sec
        self._last_metrics_cleanup_ts = 0.0

        if database_url:
            try:
                self.db_engine = create_engine(
                    database_url,
                    pool_pre_ping=True,
                    future=True
                )
                logger.info("Database engine initialized successfully")
            except Exception as e:
                logger.warning(f"Database init failed: {e}")
                self.db_engine = None
        else:
            logger.info("No DATABASE_URL provided, running without database")

    def init_schema(self) -> None:
        """Инициализация схемы БД (создание таблиц)"""
        if self.db_engine is None:
            return

        try:
            with self.db_engine.begin() as conn:
                # Таблица событий
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

                # Таблица ошибок
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS errors (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        endpoint VARCHAR(128) NOT NULL,
                        status_code INTEGER NOT NULL,
                        message_short TEXT NOT NULL
                    )
                """))

                # Таблица истории проверок
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

                # Таблица слов-нарушений
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS violation_words (
                        word VARCHAR(255) PRIMARY KEY,
                        count BIGINT NOT NULL DEFAULT 0,
                        last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """))

                logger.info("Database schema initialized successfully")
        except Exception as e:
            logger.error(f"DB schema init failed: {e}")

    def log_event(self, event_type: str, endpoint: str, success: bool,
                  duration_ms: Optional[float] = None, source_type: Optional[str] = None,
                  items_total: int = 0, items_error: int = 0,
                  violations_total: int = 0) -> None:
        """
        Логирование события в БД

        Args:
            event_type: Тип события
            endpoint: API endpoint
            success: Успешность операции
            duration_ms: Длительность в миллисекундах
            source_type: Тип источника
            items_total: Всего элементов
            items_error: Элементов с ошибками
            violations_total: Всего нарушений
        """
        if self.db_engine is None:
            return

        try:
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO events (
                        event_type, endpoint, success, duration_ms, source_type,
                        items_total, items_error, violations_total
                    ) VALUES (
                        :event_type, :endpoint, :success, :duration_ms, :source_type,
                        :items_total, :items_error, :violations_total
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
        except Exception as e:
            logger.error(f"Failed to log event: {e}")

        self.cleanup_old_data()

    def log_error(self, endpoint: str, status_code: int, message: str) -> None:
        """
        Логирование ошибки в БД

        Args:
            endpoint: API endpoint
            status_code: HTTP статус код
            message: Сообщение об ошибке
        """
        if self.db_engine is None:
            return

        short_message = (message or '').strip()[:1000]
        if not short_message:
            short_message = 'unknown error'

        try:
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO errors (endpoint, status_code, message_short)
                    VALUES (:endpoint, :status_code, :message_short)
                """), {
                    'endpoint': endpoint,
                    'status_code': int(status_code),
                    'message_short': short_message
                })
        except Exception as e:
            logger.error(f"Failed to log error: {e}")

        self.cleanup_old_data()

    def insert_run_history(self, check_type: str, endpoint: str, success: bool,
                          duration_ms: Optional[float] = None,
                          source_type: Optional[str] = None,
                          context_short: Optional[str] = None,
                          violations_count: int = 0) -> None:
        """
        Добавление записи в историю проверок

        Args:
            check_type: Тип проверки
            endpoint: API endpoint
            success: Успешность
            duration_ms: Длительность
            source_type: Тип источника
            context_short: Краткий контекст
            violations_count: Количество нарушений
        """
        if self.db_engine is None:
            return

        try:
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO run_history (
                        check_type, endpoint, source_type, context_short,
                        success, duration_ms, violations_count
                    ) VALUES (
                        :check_type, :endpoint, :source_type, :context_short,
                        :success, :duration_ms, :violations_count
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
        except Exception as e:
            logger.error(f"Failed to insert run history: {e}")

    def upsert_violation_words(self, words: List[str]) -> None:
        """
        Обновление счетчиков слов-нарушений

        Args:
            words: Список слов-нарушений
        """
        if self.db_engine is None:
            return

        clean_words = []
        for raw in (words or []):
            word = (raw or '').strip()
            if word:
                clean_words.append(word[:255])

        if not clean_words:
            return

        try:
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO violation_words (word, count, last_seen_at)
                    SELECT unnest(:words ::text[]), 1, NOW()
                    ON CONFLICT (word)
                    DO UPDATE SET
                        count = violation_words.count + 1,
                        last_seen_at = NOW()
                """), {'words': clean_words})
        except Exception as e:
            logger.error(f"Failed to upsert violation words: {e}")

    def cleanup_old_data(self, force: bool = False) -> dict:
        """
        Очистка старых данных из БД

        Args:
            force: Принудительная очистка (игнорируя интервал)

        Returns:
            Словарь с результатами очистки
        """
        if self.db_engine is None:
            return {'error': 'Database not available'}

        now_ts = time.time()
        if not force and (now_ts - self._last_metrics_cleanup_ts) < self.cleanup_interval_sec:
            return {'skipped': True, 'reason': 'Too soon since last cleanup'}

        self._last_metrics_cleanup_ts = now_ts
        results = {}

        try:
            with self.db_engine.begin() as conn:
                # Очистка событий
                result = conn.execute(text("""
                    DELETE FROM events
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['events_deleted'] = result.rowcount

                # Очистка ошибок
                result = conn.execute(text("""
                    DELETE FROM errors
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['errors_deleted'] = result.rowcount

                # Очистка истории
                result = conn.execute(text("""
                    DELETE FROM run_history
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['history_deleted'] = result.rowcount

                # Очистка слов-нарушений
                result = conn.execute(text("""
                    DELETE FROM violation_words
                    WHERE last_seen_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['words_deleted'] = result.rowcount

                logger.info(f"Old data cleaned up: {results}")
                results['success'] = True
                return results
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return {'success': False, 'error': str(e)}

    def cleanup_all_metrics(self) -> dict:
        """
        Полная очистка всех метрик (для администратора)

        Returns:
            Словарь с результатами очистки
        """
        if self.db_engine is None:
            return {'error': 'Database not available'}

        results = {}

        try:
            # Шаг 1: Удаление данных (в транзакции)
            with self.db_engine.begin() as conn:
                # Удаление всех событий
                result = conn.execute(text("DELETE FROM events"))
                results['events_deleted'] = result.rowcount

                # Удаление всех ошибок
                result = conn.execute(text("DELETE FROM errors"))
                results['errors_deleted'] = result.rowcount

                # Удаление всей истории
                result = conn.execute(text("DELETE FROM run_history"))
                results['history_deleted'] = result.rowcount

                # Удаление всех слов
                result = conn.execute(text("DELETE FROM violation_words"))
                results['words_deleted'] = result.rowcount

            # Шаг 2: VACUUM вне транзакции (требует autocommit)
            with self.db_engine.connect() as conn:
                conn.execution_options(isolation_level="AUTOCOMMIT")
                conn.execute(text("VACUUM ANALYZE"))
                results['vacuum_completed'] = True

            logger.warning(f"ALL metrics cleaned up: {results}")
            results['success'] = True
            return results
        except Exception as e:
            logger.error(f"Failed to cleanup all metrics: {e}")
            return {'success': False, 'error': str(e)}


# Singleton экземпляр (будет инициализирован в app.py)
db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> Optional[DatabaseManager]:
    """Получить экземпляр DatabaseManager"""
    return db_manager


def init_db_manager(database_url: Optional[str],
                   retention_days: int = 60,
                   cleanup_interval_sec: int = 3600) -> DatabaseManager:
    """
    Инициализировать и вернуть DatabaseManager

    Args:
        database_url: URL базы данных
        retention_days: Количество дней хранения
        cleanup_interval_sec: Интервал очистки

    Returns:
        Экземпляр DatabaseManager
    """
    global db_manager
    db_manager = DatabaseManager(database_url, retention_days, cleanup_interval_sec)
    db_manager.init_schema()
    db_manager.cleanup_old_data(force=True)
    return db_manager
