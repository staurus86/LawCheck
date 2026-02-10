#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API РґР»СЏ РїСЂРѕРІРµСЂРєРё С‚РµРєСЃС‚Р° РЅР° СЃРѕРѕС‚РІРµС‚СЃС‚РІРёРµ Р·Р°РєРѕРЅСѓ в„–168-Р¤Р—
РЈР›РЈР§РЁР•РќРќРђРЇ Р’Р•Р РЎРРЇ СЃ РјР°РєСЃРёРјР°Р»СЊРЅС‹Рј С„СѓРЅРєС†РёРѕРЅР°Р»РѕРј
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
# CORS - СЂР°Р·СЂРµС€Р°РµРј РІСЃРµ РґРѕРјРµРЅС‹
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ С‡РµРєРµСЂР°
checker = RussianLanguageChecker()

# РҐСЂР°РЅРёР»РёС‰Рµ РёСЃС‚РѕСЂРёРё РїСЂРѕРІРµСЂРѕРє (РІ РїСЂРѕРґР°РєС€РµРЅРµ РёСЃРїРѕР»СЊР·СѓР№С‚Рµ Redis/Database)
check_history = []
statistics = {
    'total_checks': 0,
    'total_violations': 0,
    'most_common_violations': defaultdict(int)
}

@app.route('/')
def index():
    """Р“Р»Р°РІРЅР°СЏ СЃС‚СЂР°РЅРёС†Р°"""
    return render_template('index.html')

@app.route('/about')
def about():
    """РЎС‚СЂР°РЅРёС†Р° Рѕ Р·Р°РєРѕРЅРµ"""
    return render_template('about.html')

@app.route('/api-docs')
def api_docs():
    """API РґРѕРєСѓРјРµРЅС‚Р°С†РёСЏ"""
    return render_template('api_docs.html')

@app.route('/examples')
def examples():
    """РџСЂРёРјРµСЂС‹ РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЏ"""
    return render_template('examples.html')
    
@app.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')

@app.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - РёСЃРїРѕР»СЊР·СѓРµРј data URI РІ HTML

# ==================== API ENDPOINTS ====================

@app.route('/api/check', methods=['POST'])
def check_text():
    """API: РџСЂРѕРІРµСЂРєР° С‚РµРєСЃС‚Р°"""
    try:
        data = request.json
        text = data.get('text', '')
        save_history = data.get('save_history', True)
        
        if not text or not text.strip():
            return jsonify({'error': 'РўРµРєСЃС‚ РЅРµ РїСЂРµРґРѕСЃС‚Р°РІР»РµРЅ'}), 400
        
        result = checker.check_text(text)
        
        # Р”РѕР±Р°РІР»СЏРµРј СЂРµРєРѕРјРµРЅРґР°С†РёРё
        result['recommendations'] = generate_recommendations(result)
        
        # РЎРѕС…СЂР°РЅСЏРµРј РІ РёСЃС‚РѕСЂРёСЋ
        if save_history:
            save_to_history('text', result, text[:100])
        
        # РћР±РЅРѕРІР»СЏРµРј СЃС‚Р°С‚РёСЃС‚РёРєСѓ
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
    """API: РџСЂРѕРІРµСЂРєР° URL"""
    try:
        data = request.json
        url = data.get('url', '')
        
        if not url or not url.startswith('http'):
            return jsonify({'error': 'РќРµРєРѕСЂСЂРµРєС‚РЅС‹Р№ URL'}), 400
        
        # Р—Р°РіСЂСѓР·РєР° СЃС‚СЂР°РЅРёС†С‹
        response = requests.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # РЈРґР°Р»СЏРµРј РЅРµРЅСѓР¶РЅРѕРµ
        for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        
        # РР·РІР»РµРєР°РµРј С‚РµРєСЃС‚ Рё РјРµС‚Р°-РёРЅС„РѕСЂРјР°С†РёСЋ
        text = soup.get_text(separator=' ', strip=True)
        title = soup.find('title')
        title_text = title.get_text() if title else 'Р‘РµР· РЅР°Р·РІР°РЅРёСЏ'
        
        result = checker.check_text(text)
        result['page_title'] = title_text
        result['recommendations'] = generate_recommendations(result)
        
        # РЎРѕС…СЂР°РЅСЏРµРј РІ РёСЃС‚РѕСЂРёСЋ
        save_to_history('url', result, url)
        update_statistics(result)
        
        return jsonify({
            'success': True,
            'url': url,
            'result': result,
            'timestamp': datetime.now().isoformat()
        })
    
    except Exception as e:
        return jsonify({'error': f'РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё: {str(e)}'}), 500

@app.route('/api/batch-check', methods=['POST'])
def batch_check():
    """API: РџР°РєРµС‚РЅР°СЏ РїСЂРѕРІРµСЂРєР°"""
    try:
        data = request.json
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({'error': 'РЎРїРёСЃРѕРє URL РїСѓСЃС‚'}), 400
        
        results = []
        for url in urls[:50]:  # Р›РёРјРёС‚ 50 URL Р·Р° СЂР°Р·
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
    """API: РЎС‚Р°С‚РёСЃС‚РёРєР° СЃР»РѕРІР°СЂРµР№"""
    try:
        stats_data = {
            'normative': len(checker.normative_words),
            'foreign': len(checker.foreign_allowed),
            'nenormative': len(checker.nenormative_words),
            'morph_available': checker.morph is not None
        }
        
        print(f"рџ“Љ РћС‚РїСЂР°РІРєР° СЃС‚Р°С‚РёСЃС‚РёРєРё: {stats_data}")  # Р”Р»СЏ РѕС‚Р»Р°РґРєРё
        
        return jsonify(stats_data)
    
    except Exception as e:
        print(f"вќЊ РћС€РёР±РєР° РІ /api/stats: {e}")
        return jsonify({
            'normative': 0,
            'foreign': 0,
            'nenormative': 0,
            'morph_available': False,
            'error': str(e)
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """API: РСЃС‚РѕСЂРёСЏ РїСЂРѕРІРµСЂРѕРє"""
    limit = int(request.args.get('limit', 10))
    return jsonify({
        'history': check_history[-limit:][::-1],
        'total': len(check_history)
    })

@app.route('/api/export/txt', methods=['POST'])
def export_txt():
    """Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р° РІ TXT"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Р¤РѕСЂРјРёСЂСѓРµРј РѕС‚С‡РµС‚
        lines = []
        lines.append("=" * 60)
        lines.append("РћРўР§Р•Рў РџР РћР’Р•Р РљР РўР•РљРЎРўРђ РќРђ РЎРћРћРўР’Р•РўРЎРўР’РР• Р¤Р—-168")
        lines.append("=" * 60)
        lines.append(f"Р”Р°С‚Р° РїСЂРѕРІРµСЂРєРё: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        lines.append("")
        
        # РЎС‚Р°С‚РёСЃС‚РёРєР°
        lines.append("РЎРўРђРўРРЎРўРРљРђ:")
        lines.append(f"  Р’СЃРµРіРѕ СЃР»РѕРІ: {result.get('total_words', 0)}")
        lines.append(f"  РќРѕСЂРјР°С‚РёРІРЅС‹С…: {result.get('normative_count', 0)}")
        lines.append(f"  РРЅРѕСЃС‚СЂР°РЅРЅС‹С…: {result.get('foreign_count', 0)}")
        lines.append(f"  РќРµРЅРѕСЂРјР°С‚РёРІРЅС‹С…: {result.get('nenormative_count', 0)}")
        lines.append(f"  РћСЂС„РѕРіСЂР°С„РёС‡РµСЃРєРёС…: {result.get('orfograf_count', 0)}")
        lines.append(f"  РћСЂС„РѕСЌРїРёС‡РµСЃРєРёС…: {result.get('orfoep_count', 0)}")
        lines.append("")
        
        # РџСЂРѕС†РµРЅС‚ СЃРѕРѕС‚РІРµС‚СЃС‚РІРёСЏ
        compliance = result.get('compliance_percentage', 0)
        lines.append(f"РџР РћР¦Р•РќРў РЎРћРћРўР’Р•РўРЎРўР’РРЇ: {compliance:.2f}%")
        lines.append("")
        
        # РќР°Р№РґРµРЅРЅС‹Рµ СЃР»РѕРІР°
        if result.get('foreign_words'):
            lines.append("РРќРћРЎРўР РђРќРќР«Р• РЎР›РћР’Рђ:")
            for word in result['foreign_words']:
                lines.append(f"  - {word}")
            lines.append("")
        
        if result.get('nenormative_words'):
            lines.append("РќР•РќРћР РњРђРўРР’РќР«Р• РЎР›РћР’Рђ:")
            for word in result['nenormative_words']:
                lines.append(f"  - {word}")
            lines.append("")
        
        if result.get('orfograf_words'):
            lines.append("РћР Р¤РћР“Р РђР¤РР§Р•РЎРљРР• РћРЁРР‘РљР:")
            for word in result['orfograf_words']:
                lines.append(f"  - {word}")
            lines.append("")
        
        if result.get('orfoep_words'):
            lines.append("РћР Р¤РћР­РџРР§Р•РЎРљРР• РћРЁРР‘РљР:")
            for word in result['orfoep_words']:
                lines.append(f"  - {word}")
            lines.append("")
        
        lines.append("=" * 60)
        lines.append("РЎРѕР·РґР°РЅРѕ: LawChecker Online - https://lawcheck-production.up.railway.app")
        lines.append("=" * 60)
        
        report = "\n".join(lines)
        
        # РЎРѕР·РґР°РµРј С„Р°Р№Р» РІ РїР°РјСЏС‚Рё
        output = io.BytesIO()
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
    """Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р° РІ JSON"""
    try:
        data = request.get_json()
        result = data.get('result', {})
        
        # Р”РѕР±Р°РІР»СЏРµРј РјРµС‚Р°РґР°РЅРЅС‹Рµ
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

@app.route('/api/analyze', methods=['POST'])
def analyze_text():
    """API: Р”РµС‚Р°Р»СЊРЅС‹Р№ Р°РЅР°Р»РёР· С‚РµРєСЃС‚Р°"""
    try:
        data = request.json
        text = data.get('text', '')
        
        if not text:
            return jsonify({'error': 'РўРµРєСЃС‚ РЅРµ РїСЂРµРґРѕСЃС‚Р°РІР»РµРЅ'}), 400
        
        result = checker.check_text(text)
        
        # Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅР°СЏ Р°РЅР°Р»РёС‚РёРєР°
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
    """API: РџСЂРµРґР»РѕР¶РµРЅРёСЏ РїРѕ РёСЃРїСЂР°РІР»РµРЅРёСЋ"""
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
    """API: Р­РєСЃРїРѕСЂС‚ РѕС‚С‡С‘С‚Р° РІ СЂР°Р·РЅС‹С… С„РѕСЂРјР°С‚Р°С…"""
    try:
        data = request.json
        result = data.get('result')
        
        if not result:
            return jsonify({'error': 'РќРµС‚ РґР°РЅРЅС‹С…'}), 400
        
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
            return jsonify({'error': 'РќРµРїРѕРґРґРµСЂР¶РёРІР°РµРјС‹Р№ С„РѕСЂРјР°С‚'}), 400
        
        buffer.seek(0)
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/compare', methods=['POST'])
def compare_texts():
    """API: РЎСЂР°РІРЅРµРЅРёРµ РґРІСѓС… С‚РµРєСЃС‚РѕРІ"""
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

# ==================== Р’РЎРџРћРњРћР“РђРўР•Р›Р¬РќР«Р• Р¤РЈРќРљР¦РР ====================

def save_to_history(check_type, result, context):
    """РЎРѕС…СЂР°РЅРµРЅРёРµ РІ РёСЃС‚РѕСЂРёСЋ"""
    check_history.append({
        'id': str(uuid.uuid4()),
        'type': check_type,
        'timestamp': datetime.now().isoformat(),
        'violations': result['violations_count'],
        'compliant': result['law_compliant'],
        'context': context
    })
    
    # РћРіСЂР°РЅРёС‡РёРІР°РµРј СЂР°Р·РјРµСЂ РёСЃС‚РѕСЂРёРё
    if len(check_history) > 1000:
        check_history.pop(0)

def update_statistics(result):
    """РћР±РЅРѕРІР»РµРЅРёРµ СЃС‚Р°С‚РёСЃС‚РёРєРё"""
    statistics['total_checks'] += 1
    statistics['total_violations'] += result['violations_count']
    
    # РџРѕРґСЃС‡С‘С‚ С‡Р°СЃС‚С‹С… РЅР°СЂСѓС€РµРЅРёР№
    for word in result.get('latin_words', [])[:10]:
        statistics['most_common_violations'][word] += 1
    for word in result.get('unknown_cyrillic', [])[:10]:
        statistics['most_common_violations'][word] += 1

def generate_recommendations(result):
    """Р“РµРЅРµСЂР°С†РёСЏ СЂРµРєРѕРјРµРЅРґР°С†РёР№ РїРѕ РёСЃРїСЂР°РІР»РµРЅРёСЋ"""
    recommendations = []
    
    if result.get('nenormative_count', 0) > 0:
        recommendations.append({
            'level': 'critical',
            'icon': 'рџљ«',
            'title': 'РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°',
            'message': f'РћР±РЅР°СЂСѓР¶РµРЅРѕ {result["nenormative_count"]} СЃР»РѕРІ РЅРµРЅРѕСЂРјР°С‚РёРІРЅРѕР№ Р»РµРєСЃРёРєРё. Р­С‚Рѕ РљР РРўРР§Р•РЎРљРћР• РЅР°СЂСѓС€РµРЅРёРµ Р·Р°РєРѕРЅР°.',
            'action': 'Р—Р°РјРµРЅРёС‚Рµ РёР»Рё СѓРґР°Р»РёС‚Рµ РІСЃРµ РЅРµРЅРѕСЂРјР°С‚РёРІРЅС‹Рµ РІС‹СЂР°Р¶РµРЅРёСЏ.'
        })
    
    if result.get('latin_count', 0) > 0:
        recommendations.append({
            'level': 'warning',
            'icon': 'вљ пёЏ',
            'title': 'Р›Р°С‚РёРЅРёС†Р° РІ С‚РµРєСЃС‚Рµ',
            'message': f'РќР°Р№РґРµРЅРѕ {result["latin_count"]} СЃР»РѕРІ РЅР° Р»Р°С‚РёРЅРёС†Рµ.',
            'action': 'Р—Р°РјРµРЅРёС‚Рµ Р°РЅРіР»РёР№СЃРєРёРµ СЃР»РѕРІР° РЅР° СЂСѓСЃСЃРєРёРµ Р°РЅР°Р»РѕРіРё РёР»Рё РґРѕР±Р°РІСЊС‚Рµ РїРѕСЏСЃРЅРµРЅРёСЏ РІ СЃРєРѕР±РєР°С….'
        })
    
    if result.get('unknown_count', 0) > 0:
        recommendations.append({
            'level': 'info',
            'icon': 'в„№пёЏ',
            'title': 'РќРµРёР·РІРµСЃС‚РЅС‹Рµ СЃР»РѕРІР°',
            'message': f'РћР±РЅР°СЂСѓР¶РµРЅРѕ {result["unknown_count"]} РїРѕС‚РµРЅС†РёР°Р»СЊРЅС‹С… Р°РЅРіР»РёС†РёР·РјРѕРІ РёР»Рё РЅРµРёР·РІРµСЃС‚РЅС‹С… СЃР»РѕРІ.',
            'action': 'РџСЂРѕРІРµСЂСЊС‚Рµ РєРѕСЂСЂРµРєС‚РЅРѕСЃС‚СЊ РЅР°РїРёСЃР°РЅРёСЏ РёР»Рё РёСЃРїРѕР»СЊР·СѓР№С‚Рµ РѕР±С‰РµРїСЂРёРЅСЏС‚С‹Рµ С‚РµСЂРјРёРЅС‹.'
        })
    
    if result['law_compliant']:
        recommendations.append({
            'level': 'success',
            'icon': 'вњ…',
            'title': 'РўРµРєСЃС‚ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ Р·Р°РєРѕРЅСѓ',
            'message': 'РќР°СЂСѓС€РµРЅРёР№ РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅРѕ. РўРµРєСЃС‚ РїРѕР»РЅРѕСЃС‚СЊСЋ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ С‚СЂРµР±РѕРІР°РЅРёСЏРј Р¤Р— в„–168.',
            'action': 'РњРѕР¶РЅРѕ РїСѓР±Р»РёРєРѕРІР°С‚СЊ Р±РµР· РёР·РјРµРЅРµРЅРёР№.'
        })
    
    return recommendations

def get_word_suggestions(word):
    """РџРѕР»СѓС‡РµРЅРёРµ РїСЂРµРґР»РѕР¶РµРЅРёР№ РїРѕ Р·Р°РјРµРЅРµ СЃР»РѕРІР°"""
    # Р—РґРµСЃСЊ РјРѕР¶РЅРѕ РґРѕР±Р°РІРёС‚СЊ Р»РѕРіРёРєСѓ РїРѕРґР±РѕСЂР° СЃРёРЅРѕРЅРёРјРѕРІ
    suggestions = []
    
    # РџСЂРѕСЃС‚С‹Рµ РїСЂРёРјРµСЂС‹ Р·Р°РјРµРЅ (СЂР°СЃС€РёСЂСЊС‚Рµ РїРѕРґ СЃРІРѕРё РЅСѓР¶РґС‹)
    replacements = {
        'hello': 'РїСЂРёРІРµС‚',
        'world': 'РјРёСЂ',
        'computer': 'РєРѕРјРїСЊСЋС‚РµСЂ',
        'email': 'СЌР»РµРєС‚СЂРѕРЅРЅР°СЏ РїРѕС‡С‚Р°',
        'internet': 'РёРЅС‚РµСЂРЅРµС‚',
        'software': 'РїСЂРѕРіСЂР°РјРјРЅРѕРµ РѕР±РµСЃРїРµС‡РµРЅРёРµ',
    }
    
    word_lower = word.lower()
    if word_lower in replacements:
        suggestions.append(replacements[word_lower])
    
    return suggestions if suggestions else ['РќРµС‚ РїСЂРµРґР»РѕР¶РµРЅРёР№']

def calculate_readability(text):
    """Р Р°СЃС‡С‘С‚ РёРЅРґРµРєСЃР° С‡РёС‚Р°РµРјРѕСЃС‚Рё"""
    words = text.split()
    sentences = [s for s in text.split('.') if s.strip()]
    
    if not words or not sentences:
        return 0
    
    avg_sentence_length = len(words) / len(sentences)
    avg_word_length = sum(len(w) for w in words) / len(words)
    
    # РџСЂРѕСЃС‚РѕР№ РёРЅРґРµРєСЃ (С‡РµРј РјРµРЅСЊС€Рµ, С‚РµРј Р»СѓС‡С€Рµ)
    readability = (avg_sentence_length * 0.5) + (avg_word_length * 2)
    
    return round(readability, 2)

def get_word_frequency(text):
    """Р§Р°СЃС‚РѕС‚РЅРѕСЃС‚СЊ СЃР»РѕРІ"""
    words = text.lower().split()
    frequency = defaultdict(int)
    
    for word in words:
        if len(word) > 3:
            frequency[word] += 1
    
    return dict(sorted(frequency.items(), key=lambda x: x[1], reverse=True)[:10])

def calculate_complexity(text):
    """РћС†РµРЅРєР° СЃР»РѕР¶РЅРѕСЃС‚Рё С‚РµРєСЃС‚Р° (0-100)"""
    words = text.split()
    
    if not words:
        return 0
    
    avg_word_length = sum(len(w) for w in words) / len(words)
    unique_words = len(set(words))
    lexical_diversity = unique_words / len(words)
    
    complexity = (avg_word_length * 10) + (lexical_diversity * 30)
    
    return min(100, round(complexity, 2))

def calculate_improvement(result1, result2):
    """Р Р°СЃС‡С‘С‚ РїСЂРѕС†РµРЅС‚Р° СѓР»СѓС‡С€РµРЅРёСЏ"""
    if result1['violations_count'] == 0:
        return 0
    
    improvement = ((result1['violations_count'] - result2['violations_count']) / result1['violations_count']) * 100
    return round(improvement, 2)

def generate_text_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ С‚РµРєСЃС‚РѕРІРѕРіРѕ РѕС‚С‡С‘С‚Р°"""
    output = "="*100 + "\n"
    output += "РћРўР§РЃРў РџРћ РџР РћР’Р•Р РљР• Р—РђРљРћРќРђ Рћ Р РЈРЎРЎРљРћРњ РЇР—Р«РљР• в„–168-Р¤Р—\n"
    output += f"РЎРѕР·РґР°РЅ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    output += "="*100 + "\n\n"
    
    output += f"Р’СЃРµРіРѕ СЃР»РѕРІ: {result.get('total_words', 0)}\n"
    output += f"РЈРЅРёРєР°Р»СЊРЅС‹С… СЃР»РѕРІ: {result.get('unique_words', 0)}\n"
    output += f"РќР°СЂСѓС€РµРЅРёР№: {result.get('violations_count', 0)}\n\n"
    
    if result.get('law_compliant'):
        output += "вњ… РўР•РљРЎРў РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў РўР Р•Р‘РћР’РђРќРРЇРњ Р—РђРљРћРќРђ\n\n"
    else:
        output += f"вљ пёЏ РћР‘РќРђР РЈР–Р•РќРћ РќРђР РЈРЁР•РќРР™: {result.get('violations_count', 0)}\n\n"
        
        if result.get('nenormative_count', 0) > 0:
            output += f"рџљ« РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°: {result['nenormative_count']}\n"
        if result.get('latin_count', 0) > 0:
            output += f"вљ пёЏ Р›Р°С‚РёРЅРёС†Р°: {result['latin_count']}\n"
            for i, word in enumerate(result.get('latin_words', [])[:50], 1):
                output += f"  {i}. {word}\n"
            output += "\n"
        if result.get('unknown_count', 0) > 0:
            output += f"вљ пёЏ РђРЅРіР»РёС†РёР·РјС‹: {result['unknown_count']}\n"
            for i, word in enumerate(result.get('unknown_cyrillic', [])[:50], 1):
                output += f"  {i}. {word}\n"
    
    return output

def generate_csv_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ CSV РѕС‚С‡С‘С‚Р°"""
    output = "РўРёРї,РљРѕР»РёС‡РµСЃС‚РІРѕ,РЎР»РѕРІР°\n"
    
    output += f"Р›Р°С‚РёРЅРёС†Р°,{result.get('latin_count', 0)},\"{', '.join(result.get('latin_words', [])[:20])}\"\n"
    output += f"РђРЅРіР»РёС†РёР·РјС‹,{result.get('unknown_count', 0)},\"{', '.join(result.get('unknown_cyrillic', [])[:20])}\"\n"
    output += f"РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ,{result.get('nenormative_count', 0)},\"[СЃРєСЂС‹С‚Рѕ]\"\n"
    
    return output

def generate_html_report(result):
    """Р“РµРЅРµСЂР°С†РёСЏ HTML РѕС‚С‡С‘С‚Р°"""
    html = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>РћС‚С‡С‘С‚ РїСЂРѕРІРµСЂРєРё Р¤Р— в„–168</title>
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
            <h1>рџ‡·рџ‡є РћС‚С‡С‘С‚ РїРѕ РїСЂРѕРІРµСЂРєРµ Р¤Р— в„–168</h1>
            <p>РЎРѕР·РґР°РЅ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="status {'success' if result.get('law_compliant') else 'error'}">
            {'вњ… РўР•РљРЎРў РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў РўР Р•Р‘РћР’РђРќРРЇРњ' if result.get('law_compliant') else f"вљ пёЏ РќРђР РЈРЁР•РќРР™: {result.get('violations_count', 0)}"}
        </div>
        
        <div class="violations">
            <h2>РЎС‚Р°С‚РёСЃС‚РёРєР°:</h2>
            <p>Р’СЃРµРіРѕ СЃР»РѕРІ: {result.get('total_words', 0)}</p>
            <p>РЈРЅРёРєР°Р»СЊРЅС‹С…: {result.get('unique_words', 0)}</p>
            <p>Р›Р°С‚РёРЅРёС†Р°: {result.get('latin_count', 0)}</p>
            <p>РђРЅРіР»РёС†РёР·РјС‹: {result.get('unknown_count', 0)}</p>
            
            {f"<h3>РЎР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ:</h3>" if result.get('latin_words') else ''}
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
