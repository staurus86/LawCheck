#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных (PostgreSQL)
"""

import time
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

LIMIT_KEYS = (
    'text_chars',
    'site_checks',
    'word_checks',
    'batch_urls',
    'multiscan_urls',
)


def _zero_usage() -> Dict[str, int]:
    return {key: 0 for key in LIMIT_KEYS}


class DatabaseManager:
    """Менеджер для работы с базой данных"""

    def __init__(
        self,
        database_url: Optional[str],
        retention_days: int = 60,
        cleanup_interval_sec: int = 3600,
        free_limits: Optional[Dict[str, int]] = None,
        default_admin_username: str = 'admin',
        default_admin_password: str = 'admin123',
    ):
        self.db_engine: Optional[Engine] = None
        self.retention_days = retention_days
        self.cleanup_interval_sec = cleanup_interval_sec
        self._last_metrics_cleanup_ts = 0.0
        self.free_limits = {
            'text_chars': int((free_limits or {}).get('text_chars', 10000)),
            'site_checks': int((free_limits or {}).get('site_checks', 3)),
            'word_checks': int((free_limits or {}).get('word_checks', 10)),
            'batch_urls': int((free_limits or {}).get('batch_urls', 10)),
            'multiscan_urls': int((free_limits or {}).get('multiscan_urls', 15)),
        }
        self.default_admin_username = (default_admin_username or 'admin').strip().lower()
        self.default_admin_password = default_admin_password or 'admin123'

        if database_url:
            try:
                self.db_engine = create_engine(
                    database_url,
                    pool_pre_ping=True,
                    pool_size=2,
                    max_overflow=3,
                    pool_recycle=1800,
                    future=True
                )
                logger.info("Database engine initialized successfully")
            except Exception as e:
                logger.warning(f"Database init failed: {e}")
                self.db_engine = None
        else:
            logger.info("No DATABASE_URL provided, running without database")

    def _extract_limits_from_row(self, row) -> Dict[str, Optional[int]]:
        return {
            key: (
                int(row.get(f'{key}_daily'))
                if row.get(f'{key}_daily') is not None
                else None
            )
            for key in LIMIT_KEYS
        }

    def _extract_usage_from_row(self, row) -> Dict[str, int]:
        usage = _zero_usage()
        for key in LIMIT_KEYS:
            usage[key] = int(row.get(f'{key}_used') or 0)
        return usage

    def _remaining_from_limits(self, limits: Dict[str, Optional[int]], usage: Dict[str, int]) -> Dict[str, Optional[int]]:
        remaining: Dict[str, Optional[int]] = {}
        for key in LIMIT_KEYS:
            limit_value = limits.get(key)
            if limit_value is None:
                remaining[key] = None
            else:
                remaining[key] = max(0, int(limit_value) - int(usage.get(key, 0)))
        return remaining

    def _serialize_user_row(self, row, include_usage: bool = False) -> Dict[str, Any]:
        limits = self._extract_limits_from_row(row)
        user = {
            'id': int(row['id']),
            'username': row['username'],
            'role': row['role'],
            'is_active': bool(row['is_active']),
            'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
            'updated_at': row['updated_at'].isoformat() if row.get('updated_at') else None,
            'limits': limits,
            'is_unlimited': row['role'] == 'admin',
        }
        if include_usage:
            usage = self._extract_usage_from_row(row)
            user['usage'] = usage
            user['remaining'] = self._remaining_from_limits(
                {key: None for key in LIMIT_KEYS} if user['is_unlimited'] else limits,
                usage
            )
        return user

    def init_schema(self) -> None:
        """Инициализация схемы БД (создание таблиц)"""
        if self.db_engine is None:
            return

        try:
            with self.db_engine.begin() as conn:
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

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        username VARCHAR(64) NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        role VARCHAR(16) NOT NULL DEFAULT 'user',
                        is_active BOOLEAN NOT NULL DEFAULT TRUE
                    )
                """))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS user_limits (
                        user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        text_chars_daily INTEGER,
                        site_checks_daily INTEGER,
                        word_checks_daily INTEGER,
                        batch_urls_daily INTEGER,
                        multiscan_urls_daily INTEGER
                    )
                """))

                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS usage_counters (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        counter_date DATE NOT NULL DEFAULT CURRENT_DATE,
                        subject_key VARCHAR(128) NOT NULL,
                        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        text_chars_used INTEGER NOT NULL DEFAULT 0,
                        site_checks_used INTEGER NOT NULL DEFAULT 0,
                        word_checks_used INTEGER NOT NULL DEFAULT 0,
                        batch_urls_used INTEGER NOT NULL DEFAULT 0,
                        multiscan_urls_used INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(subject_key, counter_date)
                    )
                """))

                logger.info("Database schema initialized successfully")

            self.ensure_default_admin()
        except Exception as e:
            logger.error(f"DB schema init failed: {e}")

    def ensure_default_admin(self) -> None:
        if self.db_engine is None:
            return

        try:
            with self.db_engine.begin() as conn:
                admin_id = conn.execute(text("""
                    INSERT INTO users (username, password_hash, role, is_active, updated_at)
                    VALUES (:username, :password_hash, 'admin', TRUE, NOW())
                    ON CONFLICT (username)
                    DO UPDATE SET
                        role = 'admin',
                        is_active = TRUE,
                        updated_at = NOW()
                    RETURNING id
                """), {
                    'username': self.default_admin_username,
                    'password_hash': generate_password_hash(self.default_admin_password),
                }).scalar()

                conn.execute(text("""
                    INSERT INTO user_limits (
                        user_id, updated_at, text_chars_daily, site_checks_daily,
                        word_checks_daily, batch_urls_daily, multiscan_urls_daily
                    ) VALUES (
                        :user_id, NOW(), NULL, NULL, NULL, NULL, NULL
                    )
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        updated_at = NOW(),
                        text_chars_daily = NULL,
                        site_checks_daily = NULL,
                        word_checks_daily = NULL,
                        batch_urls_daily = NULL,
                        multiscan_urls_daily = NULL
                """), {'user_id': int(admin_id)})
        except Exception as e:
            logger.error(f"Failed to ensure default admin: {e}")

    def log_event(self, event_type: str, endpoint: str, success: bool,
                  duration_ms: Optional[float] = None, source_type: Optional[str] = None,
                  items_total: int = 0, items_error: int = 0,
                  violations_total: int = 0) -> None:
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
                conn.execute(text("""
                    DELETE FROM run_history
                    WHERE id NOT IN (
                        SELECT id FROM run_history ORDER BY created_at DESC LIMIT 5
                    )
                """))
        except Exception as e:
            logger.error(f"Failed to insert run history: {e}")

    def upsert_violation_words(self, words: List[str]) -> None:
        if self.db_engine is None:
            return

        clean_words = []
        for raw in (words or []):
            if not isinstance(raw, str):
                continue
            word = raw.strip()
            if word:
                clean_words.append(word[:255])

        clean_words = clean_words[:30]
        if not clean_words:
            return

        try:
            with self.db_engine.begin() as conn:
                for word in clean_words:
                    conn.execute(text("""
                        INSERT INTO violation_words (word, count, last_seen_at)
                        VALUES (:word, 1, NOW())
                        ON CONFLICT (word)
                        DO UPDATE SET
                            count = violation_words.count + 1,
                            last_seen_at = NOW()
                    """), {'word': word})
        except Exception as e:
            logger.error(f"Failed to upsert violation words: {e}")

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        if self.db_engine is None or not user_id:
            return None

        try:
            with self.db_engine.begin() as conn:
                row = conn.execute(text("""
                    SELECT
                        u.id, u.created_at, u.updated_at, u.username, u.role, u.is_active,
                        ul.text_chars_daily, ul.site_checks_daily, ul.word_checks_daily,
                        ul.batch_urls_daily, ul.multiscan_urls_daily
                    FROM users u
                    LEFT JOIN user_limits ul ON ul.user_id = u.id
                    WHERE u.id = :user_id
                    LIMIT 1
                """), {'user_id': int(user_id)}).mappings().first()
            return self._serialize_user_row(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch user by id: {e}")
            return None

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        if self.db_engine is None:
            return None

        clean_username = (username or '').strip().lower()
        if not clean_username or not password:
            return None

        try:
            with self.db_engine.begin() as conn:
                row = conn.execute(text("""
                    SELECT
                        u.id, u.created_at, u.updated_at, u.username, u.role, u.is_active,
                        u.password_hash,
                        ul.text_chars_daily, ul.site_checks_daily, ul.word_checks_daily,
                        ul.batch_urls_daily, ul.multiscan_urls_daily
                    FROM users u
                    LEFT JOIN user_limits ul ON ul.user_id = u.id
                    WHERE LOWER(u.username) = :username
                    LIMIT 1
                """), {'username': clean_username}).mappings().first()

            if not row or not row.get('is_active'):
                return None
            if not check_password_hash(row['password_hash'], password):
                return None
            return self._serialize_user_row(row)
        except Exception as e:
            logger.error(f"Failed to authenticate user: {e}")
            return None

    def list_users(self) -> List[Dict[str, Any]]:
        if self.db_engine is None:
            return []

        try:
            with self.db_engine.begin() as conn:
                rows = conn.execute(text("""
                    SELECT
                        u.id, u.created_at, u.updated_at, u.username, u.role, u.is_active,
                        ul.text_chars_daily, ul.site_checks_daily, ul.word_checks_daily,
                        ul.batch_urls_daily, ul.multiscan_urls_daily,
                        COALESCE(uc.text_chars_used, 0) AS text_chars_used,
                        COALESCE(uc.site_checks_used, 0) AS site_checks_used,
                        COALESCE(uc.word_checks_used, 0) AS word_checks_used,
                        COALESCE(uc.batch_urls_used, 0) AS batch_urls_used,
                        COALESCE(uc.multiscan_urls_used, 0) AS multiscan_urls_used
                    FROM users u
                    LEFT JOIN user_limits ul ON ul.user_id = u.id
                    LEFT JOIN usage_counters uc
                        ON uc.user_id = u.id
                       AND uc.counter_date = CURRENT_DATE
                    ORDER BY
                        CASE WHEN u.role = 'admin' THEN 0 ELSE 1 END,
                        u.username ASC
                """)).mappings().all()
            return [self._serialize_user_row(row, include_usage=True) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list users: {e}")
            return []

    def create_user(self, username: str, password: str, limits: Optional[Dict[str, Optional[int]]] = None) -> Dict[str, Any]:
        if self.db_engine is None:
            raise RuntimeError('Database not available')

        clean_username = (username or '').strip().lower()
        if not clean_username:
            raise ValueError('Username is required')
        if not password:
            raise ValueError('Password is required')

        clean_limits = {
            key: (int(limits[key]) if limits and limits.get(key) is not None else None)
            for key in LIMIT_KEYS
        }

        try:
            with self.db_engine.begin() as conn:
                user_id = conn.execute(text("""
                    INSERT INTO users (username, password_hash, role, is_active, updated_at)
                    VALUES (:username, :password_hash, 'user', TRUE, NOW())
                    RETURNING id
                """), {
                    'username': clean_username,
                    'password_hash': generate_password_hash(password),
                }).scalar()

                conn.execute(text("""
                    INSERT INTO user_limits (
                        user_id, updated_at, text_chars_daily, site_checks_daily,
                        word_checks_daily, batch_urls_daily, multiscan_urls_daily
                    ) VALUES (
                        :user_id, NOW(), :text_chars_daily, :site_checks_daily,
                        :word_checks_daily, :batch_urls_daily, :multiscan_urls_daily
                    )
                """), {
                    'user_id': int(user_id),
                    'text_chars_daily': clean_limits['text_chars'],
                    'site_checks_daily': clean_limits['site_checks'],
                    'word_checks_daily': clean_limits['word_checks'],
                    'batch_urls_daily': clean_limits['batch_urls'],
                    'multiscan_urls_daily': clean_limits['multiscan_urls'],
                })

            user = self.get_user_by_id(int(user_id))
            if not user:
                raise RuntimeError('User created but not found')
            return user
        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            raise

    def update_user(
        self,
        user_id: int,
        password: Optional[str] = None,
        is_active: Optional[bool] = None,
        limits: Optional[Dict[str, Optional[int]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.db_engine is None:
            return None

        existing = self.get_user_by_id(int(user_id))
        if not existing:
            return None

        if existing.get('role') == 'admin':
            is_active = True

        clean_limits = None
        if limits is not None:
            clean_limits = {
                key: (int(limits[key]) if limits.get(key) is not None else None)
                for key in LIMIT_KEYS
            }

        try:
            with self.db_engine.begin() as conn:
                if password:
                    conn.execute(text("""
                        UPDATE users
                        SET password_hash = :password_hash, updated_at = NOW()
                        WHERE id = :user_id
                    """), {
                        'user_id': int(user_id),
                        'password_hash': generate_password_hash(password),
                    })

                if is_active is not None:
                    conn.execute(text("""
                        UPDATE users
                        SET is_active = :is_active, updated_at = NOW()
                        WHERE id = :user_id
                    """), {
                        'user_id': int(user_id),
                        'is_active': bool(is_active),
                    })

                if clean_limits is not None:
                    if existing.get('role') == 'admin':
                        clean_limits = {key: None for key in LIMIT_KEYS}
                    conn.execute(text("""
                        INSERT INTO user_limits (
                            user_id, updated_at, text_chars_daily, site_checks_daily,
                            word_checks_daily, batch_urls_daily, multiscan_urls_daily
                        ) VALUES (
                            :user_id, NOW(), :text_chars_daily, :site_checks_daily,
                            :word_checks_daily, :batch_urls_daily, :multiscan_urls_daily
                        )
                        ON CONFLICT (user_id)
                        DO UPDATE SET
                            updated_at = NOW(),
                            text_chars_daily = EXCLUDED.text_chars_daily,
                            site_checks_daily = EXCLUDED.site_checks_daily,
                            word_checks_daily = EXCLUDED.word_checks_daily,
                            batch_urls_daily = EXCLUDED.batch_urls_daily,
                            multiscan_urls_daily = EXCLUDED.multiscan_urls_daily
                    """), {
                        'user_id': int(user_id),
                        'text_chars_daily': clean_limits['text_chars'],
                        'site_checks_daily': clean_limits['site_checks'],
                        'word_checks_daily': clean_limits['word_checks'],
                        'batch_urls_daily': clean_limits['batch_urls'],
                        'multiscan_urls_daily': clean_limits['multiscan_urls'],
                    })

            return self.get_user_by_id(int(user_id))
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return None

    def get_usage_for_subject(self, subject_key: str) -> Dict[str, int]:
        if self.db_engine is None or not subject_key:
            return _zero_usage()

        try:
            with self.db_engine.begin() as conn:
                row = conn.execute(text("""
                    SELECT
                        text_chars_used, site_checks_used, word_checks_used,
                        batch_urls_used, multiscan_urls_used
                    FROM usage_counters
                    WHERE subject_key = :subject_key
                      AND counter_date = CURRENT_DATE
                    LIMIT 1
                """), {'subject_key': subject_key}).mappings().first()
            return self._extract_usage_from_row(row or {})
        except Exception as e:
            logger.error(f"Failed to fetch usage for subject: {e}")
            return _zero_usage()

    def increment_usage(self, subject_key: str, user_id: Optional[int], deltas: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        if self.db_engine is None or not subject_key:
            return _zero_usage()

        clean_deltas = {
            key: max(0, int((deltas or {}).get(key, 0) or 0))
            for key in LIMIT_KEYS
        }

        try:
            with self.db_engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO usage_counters (
                        subject_key, user_id, counter_date, updated_at
                    ) VALUES (
                        :subject_key, :user_id, CURRENT_DATE, NOW()
                    )
                    ON CONFLICT (subject_key, counter_date)
                    DO NOTHING
                """), {
                    'subject_key': subject_key,
                    'user_id': int(user_id) if user_id else None,
                })

                row = conn.execute(text("""
                    UPDATE usage_counters
                    SET
                        user_id = COALESCE(:user_id, user_id),
                        updated_at = NOW(),
                        text_chars_used = text_chars_used + :text_chars_used,
                        site_checks_used = site_checks_used + :site_checks_used,
                        word_checks_used = word_checks_used + :word_checks_used,
                        batch_urls_used = batch_urls_used + :batch_urls_used,
                        multiscan_urls_used = multiscan_urls_used + :multiscan_urls_used
                    WHERE subject_key = :subject_key
                      AND counter_date = CURRENT_DATE
                    RETURNING
                        text_chars_used, site_checks_used, word_checks_used,
                        batch_urls_used, multiscan_urls_used
                """), {
                    'subject_key': subject_key,
                    'user_id': int(user_id) if user_id else None,
                    'text_chars_used': clean_deltas['text_chars'],
                    'site_checks_used': clean_deltas['site_checks'],
                    'word_checks_used': clean_deltas['word_checks'],
                    'batch_urls_used': clean_deltas['batch_urls'],
                    'multiscan_urls_used': clean_deltas['multiscan_urls'],
                }).mappings().first()

            return self._extract_usage_from_row(row or {})
        except Exception as e:
            logger.error(f"Failed to increment usage: {e}")
            return _zero_usage()

    def cleanup_old_data(self, force: bool = False) -> dict:
        if self.db_engine is None:
            return {'error': 'Database not available'}

        now_ts = time.time()
        if not force and (now_ts - self._last_metrics_cleanup_ts) < self.cleanup_interval_sec:
            return {'skipped': True, 'reason': 'Too soon since last cleanup'}

        self._last_metrics_cleanup_ts = now_ts
        results = {}

        try:
            with self.db_engine.begin() as conn:
                result = conn.execute(text("""
                    DELETE FROM events
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['events_deleted'] = result.rowcount

                result = conn.execute(text("""
                    DELETE FROM errors
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['errors_deleted'] = result.rowcount

                result = conn.execute(text("""
                    DELETE FROM run_history
                    WHERE created_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['history_deleted'] = result.rowcount

                result = conn.execute(text("""
                    DELETE FROM violation_words
                    WHERE last_seen_at < NOW() - make_interval(days => :days)
                """), {'days': self.retention_days})
                results['words_deleted'] = result.rowcount

                result = conn.execute(text("""
                    DELETE FROM usage_counters
                    WHERE counter_date < CURRENT_DATE - CAST(:days AS INTEGER)
                """), {'days': self.retention_days})
                results['usage_deleted'] = result.rowcount

                logger.info(f"Old data cleaned up: {results}")
                results['success'] = True
                return results
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            return {'success': False, 'error': str(e)}

    def cleanup_all_metrics(self) -> dict:
        if self.db_engine is None:
            return {'error': 'Database not available'}

        results = {}

        try:
            with self.db_engine.begin() as conn:
                result = conn.execute(text("DELETE FROM events"))
                results['events_deleted'] = result.rowcount

                result = conn.execute(text("DELETE FROM errors"))
                results['errors_deleted'] = result.rowcount

                result = conn.execute(text("DELETE FROM run_history"))
                results['history_deleted'] = result.rowcount

                result = conn.execute(text("DELETE FROM violation_words"))
                results['words_deleted'] = result.rowcount

                result = conn.execute(text("DELETE FROM usage_counters"))
                results['usage_deleted'] = result.rowcount

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


db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> Optional[DatabaseManager]:
    return db_manager


def init_db_manager(database_url: Optional[str],
                   retention_days: int = 60,
                   cleanup_interval_sec: int = 3600,
                   free_limits: Optional[Dict[str, int]] = None,
                   default_admin_username: str = 'admin',
                   default_admin_password: str = 'admin123') -> DatabaseManager:
    global db_manager
    db_manager = DatabaseManager(
        database_url,
        retention_days,
        cleanup_interval_sec,
        free_limits=free_limits,
        default_admin_username=default_admin_username,
        default_admin_password=default_admin_password,
    )
    db_manager.init_schema()
    db_manager.cleanup_old_data(force=True)
    return db_manager
