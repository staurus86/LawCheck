#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Маршруты для страниц (HTML)
"""

from datetime import datetime
from flask import Blueprint, render_template, request, send_file, Response

page_bp = Blueprint('pages', __name__)


@page_bp.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@page_bp.route('/about')
def about():
    """Страница о законе"""
    return render_template('about.html')


@page_bp.route('/api-docs')
def api_docs():
    """API документация"""
    return render_template('api_docs.html')


@page_bp.route('/examples')
def examples():
    """Примеры использования"""
    return render_template('examples.html')


@page_bp.route('/payment')
def payment():
    """Страница тарифов/оплаты"""
    tariff = (request.args.get('tariff') or 'symbols-20000').strip()
    return render_template('payment.html', selected_tariff=tariff)


@page_bp.route('/admin/metrics')
def admin_metrics():
    """Простой дашборд метрик (read-only)"""
    return render_template('admin_metrics.html')


@page_bp.route('/robots.txt')
def robots():
    """Robots.txt"""
    return send_file('static/robots.txt', mimetype='text/plain')


@page_bp.route('/sitemap.xml')
def sitemap():
    """Sitemap.xml"""
    base = request.url_root.rstrip('/')
    urls = ['/', '/about', '/api-docs', '/examples', '/payment']
    lastmod = datetime.utcnow().strftime('%Y-%m-%d')
    items = []
    for path in urls:
        items.append(
            f"<url><loc>{base}{path}</loc><lastmod>{lastmod}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>0.8</priority></url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + ''.join(items) +
        '</urlset>'
    )
    return Response(xml, mimetype='application/xml')


@page_bp.route('/favicon.ico')
def favicon():
    """Favicon"""
    return '', 204  # No content - используем data URI в HTML


@page_bp.errorhandler(404)
def not_found(_error):
    """Обработчик 404 ошибки"""
    return render_template('404.html'), 404


@page_bp.errorhandler(500)
def server_error(_error):
    """Обработчик 500 ошибки"""
    return render_template('500.html'), 500
