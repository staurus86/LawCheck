#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для проверки текстов на соответствие закону №168-ФЗ
"""

import logging
import time
from typing import Optional

from checker import RussianLanguageChecker

logger = logging.getLogger(__name__)


class CheckerService:
    """Сервис для проверки текстов (singleton с lazy initialization)"""

    _instance: Optional['CheckerService'] = None
    _checker: Optional[RussianLanguageChecker] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_checker(cls) -> RussianLanguageChecker:
        """
        Получить экземпляр RussianLanguageChecker (lazy initialization)

        Returns:
            Экземпляр RussianLanguageChecker
        """
        if cls._checker is None:
            logger.info("Initializing RussianLanguageChecker...")
            start_time = time.time()
            cls._checker = RussianLanguageChecker()
            elapsed = time.time() - start_time
            logger.info(f"Checker initialized in {elapsed:.2f}s")
        return cls._checker

    def check_text(self, text: str) -> dict:
        """
        Проверка текста

        Args:
            text: Текст для проверки

        Returns:
            Результат проверки
        """
        checker = self.get_checker()
        return checker.check_text(text)

    def deep_check_words(self, words: list) -> list:
        """
        Глубокая проверка списка слов

        Args:
            words: Список слов для проверки

        Returns:
            Список результатов проверки
        """
        checker = self.get_checker()
        return checker.deep_check_words(words)

    def is_nenormative(self, word: str) -> bool:
        """
        Проверка слова на ненормативность

        Args:
            word: Слово для проверки

        Returns:
            True если слово ненормативное
        """
        checker = self.get_checker()
        return checker.is_nenormative(word)


# Singleton экземпляр
checker_service = CheckerService()


def get_checker_service() -> CheckerService:
    """Получить экземпляр CheckerService"""
    return checker_service
