#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для API endpoints
"""

import pytest
import json


@pytest.fixture
def client():
    """Fixture для Flask test client"""
    from app import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    """Тест главной страницы"""
    response = client.get('/')
    assert response.status_code == 200


def test_about_page(client):
    """Тест страницы About"""
    response = client.get('/about')
    assert response.status_code == 200


def test_api_check_valid_text(client):
    """Тест API /api/check с валидным текстом"""
    data = {
        'text': 'Это тестовый русский текст',
        'save_history': False
    }
    response = client.post(
        '/api/check',
        data=json.dumps(data),
        content_type='application/json'
    )

    assert response.status_code == 200
    result = json.loads(response.data)
    assert result['success'] is True
    assert 'result' in result


def test_api_check_empty_text(client):
    """Тест API /api/check с пустым текстом"""
    data = {'text': ''}
    response = client.post(
        '/api/check',
        data=json.dumps(data),
        content_type='application/json'
    )

    assert response.status_code == 400


def test_api_check_with_latin(client):
    """Тест API /api/check с латинскими символами"""
    data = {
        'text': 'Текст с hello world',
        'save_history': False
    }
    response = client.post(
        '/api/check',
        data=json.dumps(data),
        content_type='application/json'
    )

    assert response.status_code == 200
    result = json.loads(response.data)
    assert result['success'] is True
    assert result['result']['law_compliant'] is False
    assert result['result']['latin_count'] > 0


def test_sitemap(client):
    """Тест sitemap.xml"""
    response = client.get('/sitemap.xml')
    assert response.status_code == 200
    assert response.content_type == 'application/xml'


def test_robots_txt(client):
    """Тест robots.txt"""
    response = client.get('/robots.txt')
    assert response.status_code == 200
    assert response.content_type == 'text/plain; charset=utf-8'
