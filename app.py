#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API для проверки текста на соответствие закону №168-ФЗ
УЛУЧШЕННАЯ ВЕРСИЯ с максимальным функционалом
"""

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
import os
from datetime import datetime
from checker import RussianLanguageChecker
import requests
from bs4 import BeautifulSoup
import io
import json
import uuid
from collections import defaultdict

app = Flask(__name__)
# CORS - разрешаем все домены
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Инициализация чекера
checker = RussianLanguageChecker()

# Хранилище истории проверок (в продакшене используйте Redis/Database)
check_history = []
statistics = {
    'total_checks': 0,
    'total_violations': 0,
    'most_common_violations': defaultdict(int)
}

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
    
@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - используем data URI в HTML

# ==================== API ENDPOINTS ====================

@app.route('/api/check', methods=['POST'])
def check_text():
    """API: Проверка текста"""
    try:
        data = request.json
        text = data.get('text', '')
        save_history = data.get('save_history', True)
        
        if not text or not text.strip():
            return jsonify({'error': 'Текст не предоставлен'}), 400
        
        result = checker.check_text(text)
        
        # Добавляем рекомендации
        result['recommendations'] = generate_recommendations(result)
        
        # Сохраняем в историю
        if save_history:
            save_to_history('text', result, text[:100])
        
        # Обновляем статистику
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'result': result,
            'timestamp': datetime.now().isoformat(),
            'check_id': str(uuid.uuid4())
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-url', methods=['POST'])
def check_url():
    """API: Проверка URL"""
    try:
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
        
        result = checker.check_text(text)
        result['page_title'] = title_text
        result['recommendations'] = generate_recommendations(result)
        
        # Сохраняем в историю
        save_to_history('url', result, url)
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'url': url,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """API: Пакетная проверка"""
    try:
        data = request.json
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'Список URL пуст'}), 400
        
        results = []
        for url in urls[:50]:  # Лимит 50 URL за раз
            try:
                response = requests.get(url, timeout=10, headers={
                    'User-Agent': 'Mozilla/5.0'
                })
                soup = BeautifulSoup(response.text, 'html.parser')
                for tag in soup(['script', 'style']):
                    tag.decompose()
                text = soup.get_text(separator=' ', strip=True)
                result = checker.check_text(text)
                
                results.append({
                    'url': url,
                    'success': True,
                    'result': result
                })
                
            except Exception as e:
                results.append({
                    'url': url,
                    'success': False,
                    'error': str(e)
                })
        
        return jsonify({
            'success': True,
            'total': len(urls),
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """API: Статистика словарей"""
    try:
        stats_data = {
            'normative': len(checker.normative_words),
            'foreign': len(checker.foreign_allowed),
            'nenormative': len(checker.nenormative_words),
            'morph_available': checker.morph is not None
        }
        
        print(f"📊 Отправка статистики: {stats_data}")  # Для отладки
        
        return jsonify(stats_data)
    
    except Exception as e:
        print(f"❌ Ошибка в /api/stats: {e}")
        return jsonify({
            'normative': 0,
            'foreign': 0,
            'nenormative': 0,
            'morph_available': False,
            'error': str(e)
        }), 500

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
