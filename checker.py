#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Класс проверки текста - ИСПРАВЛЕННАЯ ВЕРСИЯ"""

import re
from pathlib import Path
import sys

try:
    import pymorphy3
    MORPH_AVAILABLE = True
except:
    MORPH_AVAILABLE = False

class RussianLanguageChecker:
    def __init__(self):
        self.normative_words = set()
        self.foreign_allowed = set()
        self.nenormative_words = set()
        
        print("\n" + "="*60)
        print("ИНИЦИАЛИЗАЦИЯ RussianLanguageChecker")
        print("="*60)
        
        # Морфология
        if MORPH_AVAILABLE:
            try:
                self.morph = pymorphy3.MorphAnalyzer()
                print("✓ pymorphy3 загружен")
            except Exception as e:
                self.morph = None
                print(f"⚠️ pymorphy3 ошибка: {e}")
        else:
            self.morph = None
            print("⚠️ pymorphy3 недоступен")
        
        self.add_common_words()
        self.load_dictionaries()
        
        print("\n" + "="*60)
        print("ИТОГО ЗАГРУЖЕНО:")
        print("="*60)
        print(f"✓ Нормативные: {len(self.normative_words):,}")
        print(f"✓ Иностранные: {len(self.foreign_allowed):,}")
        print(f"✓ Ненормативные: {len(self.nenormative_words):,}")
        print("="*60 + "\n")
    
    def add_common_words(self):
        """Базовые слова"""
        common = {
            'и', 'в', 'на', 'по', 'от', 'до', 'из', 'к', 'с', 'у', 'о', 'об',
            'но', 'да', 'не', 'за', 'во', 'а', 'я', 'ты', 'он', 'она', 'оно',
            'это', 'этот', 'эта', 'эти', 'тот', 'та', 'те',
            'который', 'которые', 'которая', 'которое',
            'весь', 'вся', 'все', 'или', 'если', 'чтобы', 'когда', 'где',
            'так', 'также', 'очень', 'более', 'менее',
            'готовый', 'готовая', 'современный', 'необходимый', 'технический',
            'высокий', 'широкий', 'различный', 'профессиональный'
        }
        self.normative_words.update(common)
        print(f"✓ Базовый словарь: {len(common)} слов")
    
    def load_dictionaries(self):
        """Загрузка словарей"""
        # ВАЖНО: Все возможные пути
        possible_paths = [
            Path('dictionaries'),                    # dictionaries/
            Path('.') / 'dictionaries',              # ./dictionaries/
            Path(__file__).parent / 'dictionaries',  # рядом с checker.py
            Path.cwd() / 'dictionaries',             # текущая директория
        ]
        
        dict_path = None
        for path in possible_paths:
            if path.exists() and path.is_dir():
                dict_path = path
                print(f"✓ Найдена папка словарей: {path.absolute()}")
                break
        
        if not dict_path:
            print("⚠️ ПАПКА dictionaries НЕ НАЙДЕНА!")
            print("   Проверьте, что папка dictionaries/ существует")
            print("   Текущая директория:", Path.cwd())
            return
        
        # Загружаем файлы
        files_to_load = {
            'orfograf_words.txt': 'normative_words',
            'orfoep_words.txt': 'normative_words',
            'foreign_words.txt': 'foreign_allowed',
            'Nenormativnye_slova.txt': 'nenormative_words'
        }
        
        loaded = 0
        for filename, target_attr in files_to_load.items():
            filepath = dict_path / filename
            
            if not filepath.exists():
                print(f"⚠️ Файл не найден: {filename}")
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    words = set()
                    line_count = 0
                    for line in f:
                        line_count += 1
                        word = line.strip().lower()
                        if word and not word.startswith('#') and len(word) > 1:
                            words.add(word)
                    
                    if words:
                        getattr(self, target_attr).update(words)
                        print(f"✓ {filename}: {len(words):,} слов (строк: {line_count})")
                        loaded += 1
                    else:
                        print(f"⚠️ {filename}: файл пуст")
            
            except Exception as e:
                print(f"❌ Ошибка загрузки {filename}: {e}")
        
        print(f"\nЗагружено файлов: {loaded}/{len(files_to_load)}")
    
    def is_known_word(self, word):
        """Проверка известности слова"""
        word_lower = word.lower()
        
        if word_lower in self.normative_words or word_lower in self.foreign_allowed:
            return True
        
        if self.morph:
            try:
                parsed = self.morph.parse(word_lower)
                if parsed and parsed[0].score >= 0.1:
                    return True
            except:
                pass
        
        return word.isupper() and len(word) <= 6
    
    def is_nenormative(self, word):
        """Проверка ненормативности"""
        word_lower = word.lower()
        
        if word_lower in self.nenormative_words:
            return True
        
        if self.morph:
            try:
                parsed = self.morph.parse(word_lower)
                if parsed and parsed[0].normal_form in self.nenormative_words:
                    return True
            except:
                pass
        
        return False
    
    def check_text(self, text):
        """Проверка текста"""
        if not text or not text.strip():
            return {
                'latin_words': [],
                'unknown_cyrillic': [],
                'nenormative_words': [],
                'latin_count': 0,
                'unknown_count': 0,
                'nenormative_count': 0,
                'violations_count': 0,
                'law_compliant': True,
                'total_words': 0,
                'unique_words': 0
            }
        
        # Очистка
        text = re.sub(r'https?://[^\s]+', ' ', text)
        text = re.sub(r'\+?\d[\d\s\-\(\)]{7,}', ' ', text)
        
        all_words = re.findall(r'\b[а-яёА-ЯЁa-zA-Z][а-яёА-ЯЁa-zA-Z\-]*\b', text)
        
        latin_words = []
        unknown_cyrillic = []
        nenormative_found = []
        
        skip = {'и', 'в', 'на', 'по', 'от', 'до', 'из', 'к', 'с', 'у', 'о',
                'но', 'да', 'не', 'за', 'об', 'во', 'а', 'я'}
        
        for word in all_words:
            if len(word) == 1 or word.lower() in skip:
                continue
            
            if self.is_nenormative(word):
                nenormative_found.append(word)
                continue
            
            if re.search(r'[a-zA-Z]', word):
                latin_words.append(word)
                continue
            
            if not self.is_known_word(word):
                unknown_cyrillic.append(word)
        
        latin_words = sorted(list(set(latin_words)))
        unknown_cyrillic = sorted(list(set(unknown_cyrillic)))
        nenormative_found = sorted(list(set(nenormative_found)))
        
        return {
            'latin_words': latin_words,
            'unknown_cyrillic': unknown_cyrillic,
            'nenormative_words': nenormative_found,
            'latin_count': len(latin_words),
            'unknown_count': len(unknown_cyrillic),
            'nenormative_count': len(nenormative_found),
            'violations_count': len(latin_words) + len(unknown_cyrillic) + len(nenormative_found),
            'law_compliant': (len(latin_words) + len(unknown_cyrillic) + len(nenormative_found)) == 0,
            'total_words': len(all_words),
            'unique_words': len(set(all_words))
        }


# Тест при запуске
if __name__ == "__main__":
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ RussianLanguageChecker")
    print("="*60)
    
    checker = RussianLanguageChecker()
    
    test_text = "Это тестовый текст для проверки. Hello world! Профессиональный подход."
    result = checker.check_text(test_text)
    
    print("\n" + "="*60)
    print("РЕЗУЛЬТАТ ТЕСТА:")
    print("="*60)
    print(f"Нарушений: {result['violations_count']}")
    print(f"Латиница: {result['latin_words']}")
    print(f"Неизвестные: {result['unknown_cyrillic']}")
    print("="*60 + "\n")
