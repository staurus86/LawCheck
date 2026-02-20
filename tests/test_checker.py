#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для модуля проверки текстов
"""

import pytest
from checker import RussianLanguageChecker


@pytest.fixture
def checker():
    """Fixture для RussianLanguageChecker"""
    return RussianLanguageChecker()


def test_checker_initialization(checker):
    """Тест инициализации checker"""
    assert checker is not None
    assert len(checker.normative_words) > 0


def test_check_valid_russian_text(checker):
    """Тест проверки валидного русского текста"""
    text = "Это простой русский текст для проверки"
    result = checker.check_text(text)

    assert result['law_compliant'] is True
    assert result['latin_count'] == 0
    assert result['nenormative_count'] == 0


def test_check_text_with_latin(checker):
    """Тест проверки текста с латинскими символами"""
    text = "Это текст с hello world"
    result = checker.check_text(text)

    assert result['law_compliant'] is False
    assert result['latin_count'] > 0
    assert 'hello' in result['latin_words'] or 'world' in result['latin_words']


def test_check_empty_text(checker):
    """Тест проверки пустого текста"""
    result = checker.check_text("")

    assert result['law_compliant'] is True
    assert result['total_words'] == 0
    assert result['violations_count'] == 0


def test_check_nenormative_word(checker):
    """Тест проверки ненормативного слова"""
    # Используем нейтральное слово для теста
    assert checker.is_nenormative("нормальное") is False
