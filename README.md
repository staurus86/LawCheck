# LawChecker Online

Онлайн-сервис для проверки текстов, сайтов, изображений (OCR) и PDF на соответствие требованиям языка.

## Возможности

- Проверка текста (`Текст`)
- Проверка одной страницы по URL (`Сайт`)
- Пакетная проверка списка URL (`Пакетная`)
- Проверка одного слова (`Слово`)
- OCR и проверка текста с изображения (`Картинка`)
- MultiScan сайта/списка URL (`Мульти-скан`): HTML + IMG + PDF
- Deep-check для уточнения спорных слов
- Экспорт отчетов (обычные и deep)
- Сервисные метрики на PostgreSQL

## Стек

- Python 3.11+
- Flask
- BeautifulSoup4
- pypdf
- SQLAlchemy + PostgreSQL (Railway)
- Vanilla JS + CSS

## Быстрый старт (локально)

1. Клонировать репозиторий
```bash
git clone <YOUR_REPO_URL>
cd law
```

2. Создать и активировать виртуальное окружение
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Установить зависимости
```bash
pip install -r requirements.txt
```

4. Создать `.env` на основе `.env.example`

5. Запустить приложение
```bash
python app.py
```

Сервис будет доступен на `http://localhost:5000`.

## Railway деплой

1. Подключите репозиторий к Railway.
2. Добавьте PostgreSQL в проект.
3. Проверьте, что в Variables есть `DATABASE_URL`.
4. Railway установит зависимости из `requirements.txt` автоматически.
5. После деплоя проверьте:
- `/api/metrics`
- `/api/run-history`
- `/admin/metrics`

## Переменные окружения

Смотрите `.env.example`. Ключевые:

- `DATABASE_URL` или `database_URL` — строка подключения PostgreSQL
- `FLASK_SECRET_KEY` — секрет Flask-сессии
- `OCR_TIMEOUT` — таймаут OCR-запросов
- `MULTISCAN_MAX_URLS_HARD` / `MULTISCAN_MAX_PAGES_HARD` / `MULTISCAN_MAX_RESOURCES_HARD`
- `METRICS_RETENTION_DAYS` — срок хранения метрик
- `METRICS_CLEANUP_INTERVAL_SEC` — интервал фоновой очистки метрик

## Основные API endpoint'ы

- `POST /api/check`
- `POST /api/check-url`
- `POST /api/batch-check`
- `POST /api/deep-check`
- `POST /api/images/token`
- `POST /api/images/ocr`
- `POST /api/images/check`
- `POST /api/multiscan/run`
- `GET /api/metrics`
- `GET /api/run-history`

Документация в UI: `/api-docs`.

## Структура проекта

- `app.py` — Flask приложение и API
- `checker.py` — движок проверки языка/словарей
- `templates/` — HTML шаблоны
- `static/` — CSS/JS/иконки/robots
- `dictionaries/` — словари

## Безопасность и данные

- OCR токены хранятся в сессии пользователя.
- Сервисные метрики в БД агрегированные.
- Полные тексты и токены в метрики не сохраняются.

## Лицензия

MIT (см. `LICENSE`).
