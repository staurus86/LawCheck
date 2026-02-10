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

@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    """API: Детальный анализ текста"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'Текст не предоставлен'}), 400
        
        result = checker.check_text(text)
        
        # Дополнительная аналитика
        analysis = {
            'readability': calculate_readability(text),
            'word_frequency': get_word_frequency(text),
            'sentence_count': len([s for s in text.split('.') if s.strip()]),
            'avg_word_length': sum(len(w) for w in text.split()) / max(len(text.split()), 1),
            'complexity_score': calculate_complexity(text),
        }
        
        return jsonify({
            'success': True,
            'result': result,
            'analysis': analysis,
            'recommendations': generate_recommendations(result)
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/suggest-fixes', methods=['POST'])
def suggest_fixes():
    """API: Предложения по исправлению"""
    try:
        data = request.json
        words = data.get('words', [])
        
        suggestions = {}
        for word in words[:50]:
            suggestions[word] = get_word_suggestions(word)
        
        return jsonify({
            'success': True,
            'suggestions': suggestions
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/<format>', methods=['POST'])
def export_report(format):
    """API: Экспорт отчёта в разных форматах"""
    try:
        data = request.json
        result = data.get('result')
        
        if not result:
            return jsonify({'error': 'Нет данных'}), 400
        
        if format == 'txt':
            report = generate_text_report(result)
            buffer = io.BytesIO(report.encode('utf-8'))
            mimetype = 'text/plain'
            filename = f'law_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        
        elif format == 'json':
            report = json.dumps(result, ensure_ascii=False, indent=2)
            buffer = io.BytesIO(report.encode('utf-8'))
            mimetype = 'application/json'
            filename = f'law_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        elif format == 'csv':
            report = generate_csv_report(result)
            buffer = io.BytesIO(report.encode('utf-8'))
            mimetype = 'text/csv'
            filename = f'law_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        elif format == 'html':
            report = generate_html_report(result)
            buffer = io.BytesIO(report.encode('utf-8'))
            mimetype = 'text/html'
            filename = f'law_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
        
        else:
            return jsonify({'error': 'Неподдерживаемый формат'}), 400
        
        buffer.seek(0)
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/compare', methods=['POST'])
def compare_texts():
    """API: Сравнение двух текстов"""
    try:
        data = request.json
        text1 = data.get('text1', '')
        text2 = data.get('text2', '')
        
        result1 = checker.check_text(text1)
        result2 = checker.check_text(text2)
        
        comparison = {
            'text1': result1,
            'text2': result2,
            'difference': {
                'violations_delta': result2['violations_count'] - result1['violations_count'],
                'improved': result2['violations_count'] < result1['violations_count'],
                'improvement_percent': calculate_improvement(result1, result2)
            }
        }
        
        return jsonify({
            'success': True,
            'comparison': comparison
        })
    
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
    
    # Подсчёт частых нарушений
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
            'message': f'Обнаружено {result["nenormative_count"]} слов ненормативной лексики. Это КРИТИЧЕСКОЕ нарушение закона.',
            'action': 'Замените или удалите все ненормативные выражения.'
        })
    
    if result.get('latin_count', 0) > 0:
        recommendations.append({
            'level': 'warning',
            'icon': '⚠️',
            'title': 'Латиница в тексте',
            'message': f'Найдено {result["latin_count"]} слов на латинице.',
            'action': 'Замените английские слова на русские аналоги или добавьте пояснения в скобках.'
        })
    
    if result.get('unknown_count', 0) > 0:
        recommendations.append({
            'level': 'info',
            'icon': 'ℹ️',
            'title': 'Неизвестные слова',
            'message': f'Обнаружено {result["unknown_count"]} потенциальных англицизмов или неизвестных слов.',
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
    """Расчёт индекса читаемости"""
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
    """Расчёт процента улучшения"""
    if result1['violations_count'] == 0:
        return 0
    
    improvement = ((result1['violations_count'] - result2['violations_count']) / result1['violations_count']) * 100
    return round(improvement, 2)

def generate_text_report(result):
    """Генерация текстового отчёта"""
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
    """Генерация CSV отчёта"""
    output = "Тип,Количество,Слова\n"
    
    output += f"Латиница,{result.get('latin_count', 0)},\"{', '.join(result.get('latin_words', [])[:20])}\"\n"
    output += f"Англицизмы,{result.get('unknown_count', 0)},\"{', '.join(result.get('unknown_cyrillic', [])[:20])}\"\n"
    output += f"Ненормативная,{result.get('nenormative_count', 0)},\"[скрыто]\"\n"
    
    return output

def generate_html_report(result):
    """Генерация HTML отчёта"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Отчёт проверки ФЗ №168</title>
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
            <h1>🇷🇺 Отчёт по проверке ФЗ №168</h1>
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
