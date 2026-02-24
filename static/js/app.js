// API Configuration
const API_BASE = window.API_BASE_URL || 'http://localhost:5000';
console.log('Using API:', API_BASE);

// Утилита debounce — откладывает вызов функции на delay мс после последнего вызова
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// Копирование слова по клику на тег (вызывается через делегирование)
function copyWordTag(word) {
    navigator.clipboard.writeText(word).then(
        () => showToast(`Скопировано: «${word}»`, 'success'),
        () => {}
    );
}

// Делегированный обработчик кликов по word-tag (безопасно — без inline JS с аргументом)
document.addEventListener('click', (e) => {
    const tag = e.target.closest('.word-tag[data-word]');
    if (!tag) return;
    const word = tag.dataset.word;
    if (word) copyWordTag(word);
});

// Вспомогательная функция: экранирование для HTML-атрибута
function escAttr(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// Экранирование текстового содержимого HTML (innerHTML)
function escHtml(str) {
    return String(str == null ? '' : str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

// Раскрывающийся список слов со спойлером
// words — массив, limit — сколько показывать сразу, tagClass — CSS-класс тега, transform — fn(word)→string
function renderWordList(words, limit, tagClass = '', transform = null) {
    if (!words || !words.length) return '<div class="word-list"></div>';
    const t = transform || (w => w);
    const shown = words.slice(0, limit);
    const hidden = words.slice(limit);
    let html = '<div class="word-list">';
    // data-word хранит оригинальное слово; клик обрабатывается делегированием
    html += shown.map(w => `<span class="word-tag ${tagClass}" data-word="${escAttr(w)}" title="Нажмите, чтобы скопировать">${escHtml(t(w))}</span>`).join('');
    if (hidden.length > 0) {
        const uid = 'ws' + Math.random().toString(36).slice(2, 9);
        html += `<span class="word-spoiler-hidden" id="${uid}" style="display:none">`;
        html += hidden.map(w => `<span class="word-tag ${tagClass}" data-word="${escAttr(w)}" title="Нажмите, чтобы скопировать">${escHtml(t(w))}</span>`).join('');
        html += `</span>`;
        html += `<button class="spoiler-toggle-btn" onclick="toggleWordSpoiler(this,'${uid}',${hidden.length})">▼ Показать ещё ${hidden.length}</button>`;
    }
    html += '</div>';
    return html;
}

// Переключатель спойлера в списке слов
function toggleWordSpoiler(btn, uid, count) {
    const el = document.getElementById(uid);
    if (!el) return;
    const isHidden = el.style.display === 'none';
    el.style.display = isHidden ? 'inline' : 'none';
    btn.textContent = isHidden ? `▲ Скрыть (${count})` : `▼ Показать ещё ${count}`;
}

// Человекочитаемые метки причин глубокой проверки
const DEEP_REASON_LABELS = {
    'normal_form_in_dict': 'в словаре (норм. форма)',
    'proper_name': 'имя собственное',
    'geo_name': 'гео. название',
    'organization': 'организация',
    'abbreviation': 'аббревиатура',
    'speller_confirmed': 'подтверждено орфографией',
};
function deepReasonLabel(reason) {
    if (!reason) return '';
    if (reason.startsWith('speller_variant:')) return `вариант: ${reason.split(':')[1].trim()}`;
    return DEEP_REASON_LABELS[reason] || reason;
}

// Подсветка нарушений прямо в исходном тексте (доп. кнопка)
function toggleHighlight(type, btn) {
    const overlay = document.getElementById(`highlight-${type}`);
    if (!overlay) return;
    if (overlay.style.display !== 'none') {
        overlay.style.display = 'none';
        btn.textContent = '🖍 Подсветить в тексте';
        return;
    }
    const result = currentResults[type];
    if (!result) return;
    let source = '';
    if (type === 'text') source = document.getElementById('textInput')?.value || '';
    else if (type === 'url') source = overlay.dataset.source || '';
    else if (type === 'images') source = currentResults.images?.extracted_text || '';
    if (!source) { showToast('Исходный текст недоступен', 'warning'); return; }

    const latinSet   = new Set((result.latin_words     || []).map(w => w.toLowerCase()));
    const unknownSet = new Set((result.unknown_cyrillic || []).map(w => w.toLowerCase()));
    const nenormSet  = new Set((result.nenormative_words || []).map(w => w.toLowerCase()));

    const escaped = source.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const highlighted = escaped.replace(/[а-яёА-ЯЁa-zA-Z][а-яёА-ЯЁa-zA-Z\-]*/g, match => {
        const lower = match.toLowerCase();
        if (nenormSet.has(lower)) return `<mark class="hl-critical">${match}</mark>`;
        if (latinSet.has(lower))  return `<mark class="hl-latin">${match}</mark>`;
        if (unknownSet.has(lower))return `<mark class="hl-unknown">${match}</mark>`;
        return match;
    });
    overlay.innerHTML = `
        <div class="highlight-legend">
            <span class="hl-badge hl-critical-badge">🚫 Ненормативная</span>
            <span class="hl-badge hl-latin-badge">🌍 Латиница</span>
            <span class="hl-badge hl-unknown-badge">❓ Неизвестные</span>
        </div>
        <div class="highlight-text">${highlighted}</div>`;
    overlay.style.display = 'block';
    btn.textContent = '✖ Скрыть подсветку';
}

// Подсветка нарушений в batch-item
function toggleBatchHighlight(index, btn) {
    const ovId = `batch-hl-${index}`;
    let overlay = document.getElementById(ovId);
    if (overlay && overlay.style.display !== 'none') {
        overlay.style.display = 'none';
        btn.textContent = '🖍 Подсветить';
        return;
    }
    const item = (currentResults.batch || [])[index];
    if (!item) return;
    const source = item.source_text || '';
    if (!source) { showToast('Исходный текст недоступен', 'warning'); return; }
    const result = item.result || {};
    const latinSet   = new Set((result.latin_words     || []).map(w => w.toLowerCase()));
    const unknownSet = new Set((result.unknown_cyrillic || []).map(w => w.toLowerCase()));
    const nenormSet  = new Set((result.nenormative_words || []).map(w => w.toLowerCase()));
    const escaped = source.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const highlighted = escaped.replace(/[а-яёА-ЯЁa-zA-Z][а-яёА-ЯЁa-zA-Z\-]*/g, match => {
        const lower = match.toLowerCase();
        if (nenormSet.has(lower)) return `<mark class="hl-critical">${match}</mark>`;
        if (latinSet.has(lower))  return `<mark class="hl-latin">${match}</mark>`;
        if (unknownSet.has(lower))return `<mark class="hl-unknown">${match}</mark>`;
        return match;
    });
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = ovId;
        overlay.className = 'highlight-overlay';
        btn.closest('.batch-item').appendChild(overlay);
    }
    overlay.innerHTML = `
        <div class="highlight-legend">
            <span class="hl-badge hl-critical-badge">🚫 Ненормативная</span>
            <span class="hl-badge hl-latin-badge">🌍 Латиница</span>
            <span class="hl-badge hl-unknown-badge">❓ Неизвестные</span>
        </div>
        <div class="highlight-text">${highlighted}</div>`;
    overlay.style.display = 'block';
    btn.textContent = '✖ Скрыть';
}

// Подсветка нарушений в multiscan-item
function toggleMultiHighlight(index, btn) {
    const ovId = `multi-hl-${index}`;
    let overlay = document.getElementById(ovId);
    if (overlay && overlay.style.display !== 'none') {
        overlay.style.display = 'none';
        btn.textContent = '🖍 Подсветить';
        return;
    }
    const results = (currentResults.multi && currentResults.multi.results) || [];
    const item = results[index];
    if (!item) return;
    const source = item.source_text || '';
    if (!source) { showToast('Исходный текст недоступен', 'warning'); return; }
    const result = item.result || {};
    const latinSet   = new Set((result.latin_words     || []).map(w => w.toLowerCase()));
    const unknownSet = new Set((result.unknown_cyrillic || []).map(w => w.toLowerCase()));
    const nenormSet  = new Set((result.nenormative_words || []).map(w => w.toLowerCase()));
    const escaped = source.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const highlighted = escaped.replace(/[а-яёА-ЯЁa-zA-Z][а-яёА-ЯЁa-zA-Z\-]*/g, match => {
        const lower = match.toLowerCase();
        if (nenormSet.has(lower)) return `<mark class="hl-critical">${match}</mark>`;
        if (latinSet.has(lower))  return `<mark class="hl-latin">${match}</mark>`;
        if (unknownSet.has(lower))return `<mark class="hl-unknown">${match}</mark>`;
        return match;
    });
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = ovId;
        overlay.className = 'highlight-overlay';
        btn.closest('.batch-item').appendChild(overlay);
    }
    overlay.innerHTML = `
        <div class="highlight-legend">
            <span class="hl-badge hl-critical-badge">🚫 Ненормативная</span>
            <span class="hl-badge hl-latin-badge">🌍 Латиница</span>
            <span class="hl-badge hl-unknown-badge">❓ Неизвестные</span>
        </div>
        <div class="highlight-text">${highlighted}</div>`;
    overlay.style.display = 'block';
    btn.textContent = '✖ Скрыть';
}

// ── Dark Mode ──────────────────────────────────────────────────
function toggleDarkMode() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('lawchecker.theme', next);
    const icon = document.getElementById('darkModeIcon');
    if (icon) icon.textContent = next === 'dark' ? '☀️' : '🌙';
}
function initTheme() {
    const saved = localStorage.getItem('lawchecker.theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    const icon = document.getElementById('darkModeIcon');
    if (icon) icon.textContent = saved === 'dark' ? '☀️' : '🌙';
}

// ── Toast уведомления ──────────────────────────────────────────
function showToast(message, type = 'info', duration = 4500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }
    const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span>
        <span class="toast-message">${escHtml(message)}</span>
        <button class="toast-close" aria-label="Закрыть">✕</button>`;
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    container.appendChild(toast);
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('toast-visible')));
    setTimeout(() => {
        toast.classList.remove('toast-visible');
        setTimeout(() => toast.remove(), 350);
    }, duration);
}

// Toast с кнопкой «Отменить» (для soft-delete операций)
function showToastWithUndo(message, undoCallback, duration = 7000) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = 'toast toast-info';
    toast.innerHTML = `<span class="toast-icon">ℹ️</span>
        <span class="toast-message">${escHtml(message)}</span>
        <button class="toast-undo-btn">Отменить</button>
        <button class="toast-close" aria-label="Закрыть">✕</button>`;
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    let done = false;
    const undoBtn = toast.querySelector('.toast-undo-btn');
    undoBtn.onclick = () => {
        if (!done) { done = true; undoCallback(); toast.remove(); }
    };
    container.appendChild(toast);
    requestAnimationFrame(() => requestAnimationFrame(() => toast.classList.add('toast-visible')));
    const tid = setTimeout(() => {
        toast.classList.remove('toast-visible');
        setTimeout(() => toast.remove(), 350);
    }, duration);
    undoBtn.addEventListener('click', () => clearTimeout(tid));
}

// ── Count-up анимация ─────────────────────────────────────────
function countUpAnimate(el, target, duration = 1600) {
    const numTarget = typeof target === 'number' ? target
        : parseInt(String(target).replace(/\D/g, ''), 10) || 0;
    if (numTarget === 0) { el.textContent = '0'; return; }
    const startTime = performance.now();
    function update(now) {
        const p = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(numTarget * eased).toLocaleString('ru-RU');
        if (p < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

// ── Compliance Gauge (SVG donut) ──────────────────────────────
function renderGauge(percent, size = 88) {
    const r = size / 2 - 9;
    const circ = 2 * Math.PI * r;
    const pct = Math.min(Math.max(percent, 0), 100);
    const offset = circ * (1 - pct / 100);
    const color = pct >= 90 ? '#4CAF50' : pct >= 70 ? '#FF9800' : '#EF4444';
    const cx = size / 2, cy = size / 2;
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" style="display:block">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#E0E0E0" stroke-width="9"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="9"
        stroke-dasharray="${circ.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}"
        stroke-linecap="round" transform="rotate(-90 ${cx} ${cy})"/>
      <text x="${cx}" y="${cy + 5}" text-anchor="middle" font-size="15" font-weight="700" fill="${color}">${pct}%</text>
    </svg>`;
}

// Global variables
let currentResults = {
    text: null,
    url: null,
    batch: null,
    images: null,
    imagesBatch: null,
    multi: null
};
let currentDeepResults = {
    text: null,
    url: null,
    images: null,
    batch: null,
    multi: null
};
const ACTIVE_TAB_KEY = 'lawchecker.activeTab';

// App bootstrap
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initSectionMotion();
    initFieldMetrics();
    initKeyboardShortcuts();
    initDragDrop();
    initBackToTop();
    loadStats();
    loadRunHistory();
    onImagesProviderChange();
    loadImageTokenStatus();
    onMultiProviderChange();
    onMultiModeChange();
    renderWordHistory();
    initUrlValidation();
    console.log('App loaded');
});

// ── Горячие клавиши ────────────────────────────────────────────
// Ctrl+Enter (Cmd+Enter на Mac) запускает проверку в активной вкладке
function initKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            const tab = getActiveTabName();
            if (tab === 'text')    checkText();
            else if (tab === 'url')    checkUrl();
            else if (tab === 'batch')  checkBatch();
            else if (tab === 'word')   checkWord();
            else if (tab === 'images') checkImagesByDatabase();
            else if (tab === 'multi')  runMultiScan();
        }
    });
}

// ── Drag & Drop для текстового поля ───────────────────────────
// Перетаскивание текстового файла (.txt) прямо в поле текста
function initDragDrop() {
    const textInput = document.getElementById('textInput');
    if (!textInput) return;

    textInput.addEventListener('dragover', (e) => {
        e.preventDefault();
        textInput.classList.add('drag-over');
    });
    textInput.addEventListener('dragleave', () => {
        textInput.classList.remove('drag-over');
    });
    textInput.addEventListener('drop', (e) => {
        e.preventDefault();
        textInput.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (!file) return;
        if (!file.type.startsWith('text/') && !file.name.endsWith('.txt')) {
            showToast('Поддерживаются только .txt-файлы', 'warning');
            return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
            textInput.value = ev.target.result || '';
            updateTextInputMeta();
            localStorage.setItem(TEXT_AUTOSAVE_KEY, textInput.value);
            showToast('Файл загружен — нажмите «Проверить текст»', 'success');
        };
        reader.readAsText(file, 'UTF-8');
    });
}

function initBackToTop() {
    const btn = document.getElementById('backToTop');
    if (!btn) return;
    const onScroll = () => btn.classList.toggle('visible', window.scrollY > 400);
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
}

// Inline-валидация поля URL + автодобавление https://
function initUrlValidation() {
    const urlInput = document.getElementById('urlInput');
    if (!urlInput) return;
    const validate = debounce(() => {
        const val = urlInput.value.trim();
        const empty = !val || val === 'https://';
        const valid = empty || /^https?:\/\/.{3,}/.test(val);
        urlInput.classList.toggle('input-invalid', !valid && val.length > 6);
        urlInput.classList.toggle('input-valid', valid && !empty);
    }, 250);
    urlInput.addEventListener('input', validate);
    urlInput.addEventListener('blur', () => {
        let val = urlInput.value.trim();
        // Автодобавление https:// если введён домен без протокола
        if (val && val !== 'https://' && !/^https?:\/\//.test(val) && /\.[a-z]{2,}/.test(val)) {
            urlInput.value = 'https://' + val;
        }
        validate();
    });
}

// Печать конкретной карточки результатов
function printCard(cardId) {
    document.querySelectorAll('.main .card').forEach(c => {
        if (c.id !== cardId) c.classList.add('print-hidden');
    });
    window.print();
    setTimeout(() => {
        document.querySelectorAll('.print-hidden').forEach(c => c.classList.remove('print-hidden'));
    }, 500);
}

function initSectionMotion() {
    const items = document.querySelectorAll(
        '.main .card, .knowledge-card, .workflow-step, .audience-card, .faq-box details, .run-history-item'
    );
    if (!items.length) return;
    items.forEach((el, idx) => {
        el.classList.add('reveal-item');
        el.style.transitionDelay = `${Math.min(idx * 0.04, 0.28)}s`;
    });

    if (!('IntersectionObserver' in window)) {
        items.forEach(el => el.classList.add('is-visible'));
        return;
    }

    const observer = new IntersectionObserver((entries, obs) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
                obs.unobserve(entry.target);
            }
        });
    }, { threshold: 0.08, rootMargin: '0px 0px -8% 0px' });

    items.forEach(el => observer.observe(el));
}

function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    const hashTab = (window.location.hash || '').replace('#', '').trim();
    const savedTab = localStorage.getItem(ACTIVE_TAB_KEY);
    switchTab(hashTab || savedTab || 'text');
}

function switchTab(tabName) {
    if (!tabName) return;
    const targetBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    const targetContent = document.getElementById(`${tabName}-tab`);
    if (!targetBtn || !targetContent) return;

    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    targetBtn.classList.add('active');
    targetContent.classList.add('active');
    localStorage.setItem(ACTIVE_TAB_KEY, tabName);
    if (window.location.hash !== `#${tabName}`) {
        history.replaceState(null, '', `#${tabName}`);
    }

    // Фокус на главное поле ввода вкладки для удобства
    const focusMap = {
        text: 'textInput', url: 'urlInput',
        batch: 'batchInput', word: 'wordInput'
    };
    const focusId = focusMap[tabName];
    if (focusId) {
        const el = document.getElementById(focusId);
        if (el) setTimeout(() => el.focus(), 80);
    }

    // На мобильных — прокрутить активную кнопку вкладки в видимую область
    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (activeBtn) activeBtn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
}

function getActiveTabName() {
    const activeBtn = document.querySelector('.tab-btn.active');
    return activeBtn ? activeBtn.dataset.tab : 'text';
}

function extractHttpUrls(inputText) {
    return (inputText || '')
        .split(/\r?\n|,|;|\t|\s+/g)
        .map(v => v.trim())
        .filter(v => /^https?:\/\//i.test(v));
}

function updateTextInputMeta() {
    const input = document.getElementById('textInput');
    const meta = document.getElementById('textInputMeta');
    if (!input || !meta) return;
    const text = input.value || '';
    const chars = text.length;
    const words = (text.trim().match(/\S+/g) || []).length;
    let label = `${chars.toLocaleString('ru-RU')} символов | ${words.toLocaleString('ru-RU')} слов`;
    if (chars > 50000) {
        label += ' ⚠️ текст очень длинный, проверка может занять время';
        meta.classList.add('field-meta-warn');
    } else {
        meta.classList.remove('field-meta-warn');
    }
    meta.textContent = label;
}

function updateBatchInputMeta() {
    const input = document.getElementById('batchInput');
    const meta = document.getElementById('batchInputMeta');
    if (!input || !meta) return;
    const urls = (input.value || '')
        .split('\n')
        .map(v => v.trim())
        .filter(v => v.startsWith('http'));
    const unique = new Set(urls);
    meta.textContent = `${urls.length} ссылок (${unique.size} уникальных)`;
}

function updateImagesInputMeta() {
    const input = document.getElementById('imagesInput');
    const meta = document.getElementById('imagesInputMeta');
    if (!input || !meta) return;
    const text = input.value || '';
    const chars = text.length;
    const words = (text.trim().match(/\S+/g) || []).length;
    meta.textContent = `${chars} символов | ${words} слов`;
}

function updateImagesBatchInputMeta() {
    const input = document.getElementById('imagesBatchInput');
    const meta = document.getElementById('imagesBatchInputMeta');
    if (!input || !meta) return;
    const urls = (input.value || '')
        .split('\n')
        .map(v => v.trim())
        .filter(v => v.startsWith('http'));
    const unique = new Set(urls);
    meta.textContent = `${urls.length} ссылок на изображения (${unique.size} уникальных)`;
}

function updateMultiUrlsInputMeta() {
    const input = document.getElementById('multiUrlsInput');
    const meta = document.getElementById('multiUrlsInputMeta');
    if (!input || !meta) return;
    const urls = extractHttpUrls(input.value || '');
    const unique = new Set(urls);
    meta.textContent = `${urls.length} ссылок (${unique.size} уникальных)`;
}

const TEXT_AUTOSAVE_KEY = 'lawchecker.textInput.draft';

function initFieldMetrics() {
    const textInput = document.getElementById('textInput');
    const batchInput = document.getElementById('batchInput');
    const imagesInput = document.getElementById('imagesInput');
    const imagesBatchInput = document.getElementById('imagesBatchInput');
    const multiUrlsInput = document.getElementById('multiUrlsInput');

    // Восстанавливаем сохранённый черновик
    if (textInput) {
        const saved = localStorage.getItem(TEXT_AUTOSAVE_KEY);
        if (saved) textInput.value = saved;
        const debouncedTextMeta = debounce(updateTextInputMeta, 200);
        textInput.addEventListener('input', () => {
            debouncedTextMeta();
            localStorage.setItem(TEXT_AUTOSAVE_KEY, textInput.value);
            _syncBtnDisabled('checkTextBtn', !textInput.value.trim());
        });
        _syncBtnDisabled('checkTextBtn', !textInput.value.trim());
    }

    if (batchInput) {
        // &#10; в placeholder HTML-атрибуте — ненадёжно в Safari; задаём через JS
        batchInput.placeholder = 'https://example1.com\nhttps://example2.com\nhttps://example3.com';
        batchInput.addEventListener('input', debounce(updateBatchInputMeta, 200));
    }
    if (imagesInput) imagesInput.addEventListener('input', debounce(updateImagesInputMeta, 200));
    if (imagesBatchInput) imagesBatchInput.addEventListener('input', debounce(updateImagesBatchInputMeta, 200));
    if (multiUrlsInput) multiUrlsInput.addEventListener('input', debounce(updateMultiUrlsInputMeta, 200));
    updateTextInputMeta();
    updateBatchInputMeta();
    updateImagesInputMeta();
    updateImagesBatchInputMeta();
    updateMultiUrlsInputMeta();
}

/** Включает/выключает кнопку (disabled + aria-disabled) */
function _syncBtnDisabled(id, shouldDisable) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.disabled = shouldDisable;
    btn.setAttribute('aria-disabled', String(shouldDisable));
}

async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Безопасное обновление с проверками
        const normativeEl = document.getElementById('statNormative');
        const foreignEl = document.getElementById('statForeign');
        const nenormativeEl = document.getElementById('statNenormative');
        const abbrEl = document.getElementById('statAbbreviations');
        
        if (normativeEl && data.normative !== undefined) {
            countUpAnimate(normativeEl, data.normative);
        }

        if (foreignEl && data.foreign !== undefined) {
            countUpAnimate(foreignEl, data.foreign);
        }

        if (nenormativeEl && data.nenormative !== undefined) {
            countUpAnimate(nenormativeEl, data.nenormative);
        }

        if (abbrEl && data.abbreviations !== undefined) {
            countUpAnimate(abbrEl, data.abbreviations);
        }
        
    } catch (error) {
        // Показываем "0" вместо ошибки
        const normativeEl = document.getElementById('statNormative');
        const foreignEl = document.getElementById('statForeign');
        const nenormativeEl = document.getElementById('statNenormative');
        const abbrEl = document.getElementById('statAbbreviations');
        
        if (normativeEl) normativeEl.textContent = '0';
        if (foreignEl) foreignEl.textContent = '0';
        if (nenormativeEl) nenormativeEl.textContent = '0';
        if (abbrEl) abbrEl.textContent = '0';
    }
}

function renderRunHistory(items) {
    const container = document.getElementById('runHistoryContent');
    if (!container) return;
    if (!items || !items.length) {
        container.innerHTML = '<div class="text-muted">История пока пуста.</div>';
        return;
    }
    const typeIcon = { text:'📝', url:'🌐', batch:'📦', image:'🖼️', word:'🔤', multiscan:'🔬' };
    const relTime = (ts) => {
        if (!ts) return '';
        const diff = Date.now() - new Date(ts).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 1) return 'только что';
        if (mins < 60) return `${mins} мин назад`;
        const h = Math.floor(mins / 60);
        if (h < 24) return `${h} ч назад`;
        return new Date(ts).toLocaleDateString('ru-RU');
    };
    // Уникальные типы для фильтра
    const types = [...new Set(items.map(i => i.check_type).filter(Boolean))];
    const filterBar = types.length > 1 ? `
        <div class="run-history-filter">
            <button class="run-filter-btn active" data-rfilter="all" onclick="filterRunHistory('all',this)">Все</button>
            ${types.map(t => `<button class="run-filter-btn" data-rfilter="${escAttr(t)}" onclick="filterRunHistory('${escAttr(t)}',this)">${typeIcon[t] || '📄'} ${t}</button>`).join('')}
        </div>
    ` : '';

    container.innerHTML = filterBar + `
        <div class="run-history-list">
            ${items.map(item => `
                <div class="run-history-item ${item.success ? 'ok' : 'fail'}" data-rtype="${escAttr(item.check_type || '')}">
                    <div class="run-main">
                        <span class="run-status-icon">${item.success ? '✅' : '❌'}</span>
                        <span class="run-type-icon" title="${escAttr(item.check_type || '')}">${typeIcon[item.check_type] || '📄'}</span>
                        <span class="run-type">${escHtml(item.check_type || '-')}</span>
                        <span class="run-context" title="${escAttr(item.context_short || '')}">${escHtml(item.context_short || '')}</span>
                    </div>
                    <div class="run-meta">
                        ${(item.violations_count ?? 0) > 0 ? `<span class="run-violations">${item.violations_count} нар.</span>` : ''}
                        <span class="run-time">${item.duration_ms ?? 0} мс</span>
                        <span class="run-date" title="${item.created_at ? new Date(item.created_at).toLocaleString() : ''}">${relTime(item.created_at)}</span>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function filterRunHistory(type, btn) {
    document.querySelectorAll('.run-filter-btn').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.querySelectorAll('.run-history-item[data-rtype]').forEach(item => {
        item.style.display = (type === 'all' || item.dataset.rtype === type) ? '' : 'none';
    });
}

async function loadRunHistory() {
    const container = document.getElementById('runHistoryContent');
    if (!container) return;
    try {
        const response = await fetch(`${API_BASE}/api/run-history?limit=20`);
        const data = await response.json();
        if (!response.ok || !data.enabled) {
            throw new Error(data.error || 'History unavailable');
        }
        renderRunHistory(data.items || []);
    } catch (_e) {
        container.innerHTML = '<div class="text-muted">История недоступна (БД не подключена или пуста).</div>';
    }
}

// Проверка текста
async function checkText() {
    const text = document.getElementById('textInput').value.trim();
    
    if (!text) {
        showToast('Введите текст для проверки!', 'warning');
        return;
    }
    
    showLoading('Анализирую текст...');
    
    try {
        const response = await fetch(`${API_BASE}/api/check`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${response.status}`);
        }
        const data = await response.json();

        if (data.success) {
            currentResults.text = data.result;
            currentDeepResults.text = null;
            displayResults('text', data.result);
            console.log('✅ Текст проверен:', data.result);
        } else {
            showToast('Ошибка: ' + (data.error || 'Неизвестная ошибка'), 'error');
        }
    } catch (error) {
        showToast('Ошибка проверки: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Проверка URL
async function checkUrl() {
    const url = document.getElementById('urlInput').value.trim();

    if (!url || !url.startsWith('http')) {
        showToast('Введите корректный URL!', 'warning');
        return;
    }

    showLoading('Загружаю страницу...');
    document.getElementById('urlProgress').style.display = 'block';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
        const response = await fetch(`${API_BASE}/api/check-url`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
            signal: controller.signal
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${response.status}`);
        }
        const data = await response.json();

        if (data.success) {
            currentResults.url = data.result;
            currentDeepResults.url = null;
            displayResults('url', data.result, url);
            // Сохраняем текст страницы для подсветки
            const urlOverlay = document.getElementById('highlight-url');
            if (urlOverlay) urlOverlay.dataset.source = data.source_text || '';
            console.log('✅ URL проверен:', data.result);
        } else {
            showToast('Ошибка: ' + (data.error || 'Неизвестная ошибка'), 'error');
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            showToast('Превышено время ожидания (30 с). Сайт не отвечает или недоступен.', 'error');
        } else {
            showToast('Ошибка загрузки: ' + error.message, 'error');
        }
    } finally {
        clearTimeout(timeoutId);
        hideLoading();
        document.getElementById('urlProgress').style.display = 'none';
    }
}

// Пакетная проверка
async function checkBatch() {
    const input = document.getElementById('batchInput').value.trim();
    const urls = input.split('\n').map(u => u.trim()).filter(u => {
        if (!u) return false;
        try { new URL(u); return true; } catch { return false; }
    });
    
    if (urls.length === 0) {
        showToast('Введите хотя бы один URL!', 'warning');
        return;
    }
    
    const progressBar = document.getElementById('batchProgress');
    const progressFill = document.getElementById('batchProgressBar');
    const progressText = document.getElementById('batchProgressText');
    
    progressBar.style.display = 'block';
    // Indeterminate анимация во время ожидания ответа сервера
    progressFill.style.width = '60%';
    progressFill.style.animation = 'progress-indeterminate 1.4s ease-in-out infinite';
    progressText.textContent = `Проверяю ${urls.length} ссылок…`;

    try {
        const response = await fetch(`${API_BASE}/api/batch-check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls })
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error || `HTTP ${response.status}`);
        }
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Ошибка пакетной проверки');
        }

        const results = data.results || [];
        progressFill.style.animation = 'none';
        progressFill.style.width = '100%';
        progressText.textContent = `Готово: ${results.length} из ${urls.length}`;
        currentResults.batch = results;
        currentDeepResults.batch = null;
        displayBatchResults(results);
        notifyCheckComplete('Пакетная проверка завершена', `Проверено ${results.length} сайтов`);
        console.log('✅ Пакетная проверка завершена:', results);
    } catch (error) {
        progressFill.style.animation = 'none';
        showToast('Ошибка пакетной проверки: ' + error.message, 'error');
    } finally {
        setTimeout(() => { progressBar.style.display = 'none'; }, 2000);
    }
}


const IMAGE_MODEL_PRESETS = {
    openai: ['gpt-4.1-mini', 'gpt-4.1', 'gpt-4o-mini', 'gpt-4o'],
    google: ['DOCUMENT_TEXT_DETECTION', 'TEXT_DETECTION'],
    ocrspace: [
        'rus', 'eng', 'ger', 'fre', 'spa', 'ita', 'por', 'pol', 'tur',
        'ukr', 'cze', 'hun', 'swe', 'dan', 'dut', 'fin', 'slv', 'hrv',
        'rum', 'bul', 'gre', 'jpn', 'kor', 'chs', 'cht', 'ara'
    ]
};

const MAX_IMAGE_FILE_SIZE_BYTES = 8 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

function getImagesProvider() {
    const el = document.getElementById('imagesProviderSelect');
    return el ? el.value : 'openai';
}

function getDefaultModelByProvider(provider) {
    const list = IMAGE_MODEL_PRESETS[provider] || [];
    return list.length ? list[0] : '';
}

function onImagesProviderChange() {
    const provider = getImagesProvider();
    const presetEl = document.getElementById('imagesModelPresetSelect');
    const modelInput = document.getElementById('imagesModelInput');
    if (!presetEl) return;

    presetEl.innerHTML = '';
    (IMAGE_MODEL_PRESETS[provider] || []).forEach(model => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        presetEl.appendChild(option);
    });
    const customOption = document.createElement('option');
    customOption.value = '__custom__';
    customOption.textContent = 'custom';
    presetEl.appendChild(customOption);

    if (modelInput && !modelInput.value.trim()) {
        modelInput.value = getDefaultModelByProvider(provider);
    }
    onImagesModelPresetChange();
    loadImageTokenStatus();
}

function onImagesModelPresetChange() {
    const presetEl = document.getElementById('imagesModelPresetSelect');
    const modelInput = document.getElementById('imagesModelInput');
    if (!presetEl || !modelInput) return;
    if (presetEl.value !== '__custom__') {
        modelInput.value = presetEl.value;
    }
}

async function loadImageTokenStatus() {
    const statusEl = document.getElementById('imagesTokenStatus');
    if (!statusEl) return;
    const provider = getImagesProvider();
    try {
        const response = await fetch(`${API_BASE}/api/images/token?provider=${encodeURIComponent(provider)}`, {
            credentials: 'same-origin'
        });
        const data = await response.json();
        if (data.success && data.has_token) {
            statusEl.textContent = `токен: ${data.token_masked || 'сохранён'}`;
            statusEl.className = 'images-token-status success';
        } else {
            statusEl.textContent = 'токен не задан';
            statusEl.className = 'images-token-status';
        }
    } catch (e) {
        statusEl.textContent = 'ошибка статуса токена';
        statusEl.className = 'images-token-status error';
    }
}

async function saveImageApiToken() {
    const input = document.getElementById('imagesTokenInput');
    const statusEl = document.getElementById('imagesTokenStatus');
    if (!input || !statusEl) return;
    const provider = getImagesProvider();
    const token = input.value.trim();
    if (!token) {
        showToast('Введите API токен', 'warning');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/api/images/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ provider, token })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка сохранения токена');
        statusEl.textContent = `токен сохранён: ${data.token_masked || ''}`;
        statusEl.className = 'images-token-status success';
        input.value = '';
    } catch (e) {
        statusEl.textContent = `ошибка: ${e.message}`;
        statusEl.className = 'images-token-status error';
    }
}

function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('File read error'));
        reader.readAsDataURL(file);
    });
}

async function buildImagesPayload() {
    const provider = getImagesProvider();
    const modelInput = document.getElementById('imagesModelInput');
    const urlInput = document.getElementById('imagesUrlInput');
    const fileInput = document.getElementById('imagesFileInput');

    const model = modelInput && modelInput.value.trim() ? modelInput.value.trim() : getDefaultModelByProvider(provider);
    const imageUrl = urlInput ? urlInput.value.trim() : '';
    const file = fileInput && fileInput.files ? fileInput.files[0] : null;

    if (!imageUrl && !file) {
        showToast('Укажите URL изображения или загрузите файл', 'warning');
        return;
    }

    if (file) {
        if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
            showToast('Поддерживаются только форматы jpg/png/webp', 'warning');
            return;
        }
        if (file.size > MAX_IMAGE_FILE_SIZE_BYTES) {
            showToast('Файл слишком большой. Максимум 8 МБ', 'warning');
            return;
        }
    }

    let imageDataUrl = '';
    if (file) imageDataUrl = await fileToDataUrl(file);

    return {
        provider,
        model,
        image_url: imageUrl || null,
        image_data_url: imageDataUrl || null
    };
}

function appendImageOcrSummary(ocr, targetEl) {
    if (!targetEl || !ocr) return;
    const timings = ocr.timings_ms || {};
    const usage = ocr.usage || {};
    targetEl.insertAdjacentHTML('beforeend', `
        <div class="image-db-summary">
            <h4>Лог OCR</h4>
            <p>Провайдер: ${escHtml(ocr.provider || '-')} | Модель: ${escHtml(ocr.model || '-')} | Источник: ${escHtml(ocr.source || '-')}</p>
            <p>Время (мс): ocr=${timings.ocr ?? '-'}, проверка=${timings.text_check ?? '-'}, всего=${timings.total ?? '-'}</p>
            <p>Использование: ${Object.keys(usage).length ? Object.entries(usage).map(([k, v]) => `${escHtml(k)}=${escHtml(String(v))}`).join(', ') : 'нет данных'}</p>
        </div>
    `);
}

async function runStandardCheckForImageText(text, sourceUrl = '', ocr = null) {
    const response = await fetch(`${API_BASE}/api/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Text check failed');

    const result = data.result;
    result.source_url = sourceUrl || '';
    result.source_type = 'image';
    result.extracted_text = text;
    if (ocr) result.ocr = ocr;

    currentResults.images = result;
    currentDeepResults.images = null;
    displayResults('images', result, result.source_url || '');
    const resultsContent = document.getElementById('imagesResultsContent');
    appendImageOcrSummary(result.ocr, resultsContent);
}

async function scrapTextFromImageAndCheck() {
    const extractedTextArea = document.getElementById('imagesInput');
    const payload = await buildImagesPayload();
    if (!payload) return;

    showLoading('Распознаю текст на изображении...');
    try {
        const response = await fetch(`${API_BASE}/api/images/ocr`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'OCR failed');

        const extractedText = (data.extracted_text || '').trim();
        if (!extractedText) throw new Error('OCR не распознал текст (пустой результат)');
        if (extractedTextArea) {
            extractedTextArea.value = extractedText;
            updateImagesInputMeta();
        }

        await runStandardCheckForImageText(extractedText, data.source_url || '', data.ocr || null);
    } catch (e) {
        showToast('Ошибка распознавания изображения: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

async function checkExtractedImageText() {
    const extractedTextArea = document.getElementById('imagesInput');
    const text = extractedTextArea ? extractedTextArea.value.trim() : '';
    if (!text) {
        showToast('Нет извлечённого текста для проверки', 'warning');
        return;
    }

    const ocr = currentResults.images && currentResults.images.ocr ? currentResults.images.ocr : null;
    const sourceUrl = currentResults.images && currentResults.images.source_url ? currentResults.images.source_url : '';
    showLoading();
    try {
        await runStandardCheckForImageText(text, sourceUrl, ocr);
    } catch (e) {
        showToast('Ошибка проверки текста: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

async function checkImagesByDatabase() {
    const payload = await buildImagesPayload();
    if (!payload) return;
    const extractedTextArea = document.getElementById('imagesInput');

    showLoading('Распознаю и проверяю изображение...');
    try {
        const response = await fetch(`${API_BASE}/api/images/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'OCR + check failed');

        currentResults.images = data.result;
        currentDeepResults.images = null;
        if (extractedTextArea) {
            extractedTextArea.value = data.result.extracted_text || '';
            updateImagesInputMeta();
        }
        displayResults('images', data.result, data.result.source_url || '');
        const resultsContent = document.getElementById('imagesResultsContent');
        appendImageOcrSummary(data.result.ocr, resultsContent);
    } catch (e) {
        showToast('Ошибка проверки изображения: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

function sleepMs(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function renderImageBatchItem(item, index) {
    if (!item.success || !item.result) {
        return `
            <div class="batch-item error" data-imgbatch-status="error">
                <div class="batch-item-header">
                    <span class="batch-number">[${index + 1}]</span>
                    <a href="${escAttr(item.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(item.url)}</a>
                </div>
                <div class="batch-item-error">Ошибка: ${escHtml(item.error || 'Неизвестная ошибка')}</div>
            </div>
        `;
    }

    const r = item.result;
    const statusCls = r.law_compliant ? 'success' : 'warning';
    const statusIcon = r.law_compliant ? '✅' : '⚠️';
    const statusText = r.law_compliant ? 'соответствует' : `нарушений: ${r.violations_count || 0}`;
    const forbiddenWords = [
        ...(r.nenormative_words || []),
        ...(r.latin_words || []),
        ...(r.unknown_cyrillic || [])
    ].filter((w, i, a) => a.indexOf(w) === i); // unique
    const wordsHtml = forbiddenWords.length
        ? `<div class="batch-global-violations"><span class="text-muted">Слова: </span>${forbiddenWords.map(w => `<span class="word-tag critical">${escHtml(w)}</span>`).join(' ')}</div>`
        : '';
    const ocrLen = (r.extracted_text || '').length;
    return `
        <div class="batch-item ${statusCls}" data-imgbatch-status="${statusCls}">
            <div class="batch-item-header">
                <span class="batch-icon">${statusIcon}</span>
                <span class="batch-number">[${index + 1}]</span>
                <a href="${escAttr(item.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(item.url)}</a>
            </div>
            <div class="batch-item-stats">
                <span class="batch-violations-count">${escHtml(statusText)}</span>
                <span class="batch-words-count">слов: ${r.total_words || 0}</span>
                ${ocrLen > 0 ? `<span class="batch-words-count">OCR: ${ocrLen} симв.</span>` : ''}
            </div>
            ${wordsHtml}
        </div>
    `;
}

function displayImagesBatchResults(results) {
    const resultsCard = document.getElementById('imagesBatchResults');
    const resultsContent = document.getElementById('imagesBatchResultsContent');
    if (!resultsCard || !resultsContent) return;

    const total = results.length;
    const successful = results.filter(r => r.success).length;
    const failed = total - successful;
    const withViolations = results.filter(r => r.success && r.result && !r.result.law_compliant).length;
    const okCount = successful - withViolations;

    let html = `
        <div class="batch-summary">
            <div class="summary-stats">
                <div class="summary-stat">
                    <span class="summary-value">${total}</span>
                    <span class="summary-label">Всего изображений</span>
                </div>
                <div class="summary-stat success">
                    <span class="summary-value">${successful}</span>
                    <span class="summary-label">Обработано</span>
                </div>
                <div class="summary-stat warning">
                    <span class="summary-value">${withViolations}</span>
                    <span class="summary-label">С нарушениями</span>
                </div>
                <div class="summary-stat error">
                    <span class="summary-value">${failed}</span>
                    <span class="summary-label">С ошибками</span>
                </div>
            </div>
        </div>
        <div class="batch-results-list" id="imgsBatchList">
            ${results.map((item, idx) => renderImageBatchItem(item, idx)).join('')}
        </div>
    `;

    resultsContent.innerHTML = html;

    // Панель фильтров + поиск
    const imgList = resultsContent.querySelector('#imgsBatchList');
    if (imgList) {
        const toolbar = document.createElement('div');
        toolbar.className = 'batch-toolbar';
        toolbar.innerHTML = `
            <div class="batch-filter-group">
                <span class="batch-filter-label">Показать:</span>
                <button class="batch-filter-btn active" data-imgfilter="all" onclick="filterImagesBatchItems('all', this)">Все (${total})</button>
                <button class="batch-filter-btn" data-imgfilter="violations" onclick="filterImagesBatchItems('violations', this)">⚠️ Нарушения (${withViolations})</button>
                <button class="batch-filter-btn success" data-imgfilter="ok" onclick="filterImagesBatchItems('ok', this)">✅ OK (${okCount})</button>
                ${failed > 0 ? `<button class="batch-filter-btn error" data-imgfilter="errors" onclick="filterImagesBatchItems('errors', this)">❌ Ошибки (${failed})</button>` : ''}
            </div>
            <div class="batch-search-group">
                <input type="search" id="imgsBatchSearch" class="batch-search-input" placeholder="Поиск по URL…" oninput="searchImagesBatchItems(this.value)">
            </div>
            <span id="imgsBatchVisibleCount" class="batch-visible-count"></span>
        `;
        imgList.insertAdjacentElement('beforebegin', toolbar);
        const emptyState = document.createElement('div');
        emptyState.id = 'imgsBatchEmptyState';
        emptyState.className = 'batch-empty-state';
        emptyState.textContent = 'Нет результатов по выбранному фильтру или запросу.';
        imgList.insertAdjacentElement('afterend', emptyState);
    }

    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function filterImagesBatchItems(filter, btn) {
    const content = document.getElementById('imagesBatchResultsContent');
    if (!content) return;
    content.querySelectorAll('[data-imgfilter]').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    const searchInput = document.getElementById('imgsBatchSearch');
    if (searchInput) searchInput.value = '';
    content.querySelectorAll('#imgsBatchList .batch-item').forEach(item => {
        item.dataset.searchHidden = '';
        applyImagesBatchVisibility(item, filter);
    });
    updateImagesBatchEmptyState();
}

function applyImagesBatchVisibility(item, filter) {
    if (item.dataset.searchHidden === '1') { item.style.display = 'none'; return; }
    const status = item.dataset.imgbatchStatus || '';
    if (filter === 'all') {
        item.style.display = '';
    } else if (filter === 'violations') {
        item.style.display = status === 'warning' ? '' : 'none';
    } else if (filter === 'ok') {
        item.style.display = status === 'success' ? '' : 'none';
    } else if (filter === 'errors') {
        item.style.display = status === 'error' ? '' : 'none';
    }
}

function searchImagesBatchItems(query) {
    const q = (query || '').toLowerCase().trim();
    const content = document.getElementById('imagesBatchResultsContent');
    if (!content) return;
    const activeBtn = content.querySelector('[data-imgfilter].active');
    const filter = activeBtn ? activeBtn.dataset.imgfilter : 'all';
    content.querySelectorAll('#imgsBatchList .batch-item').forEach(item => {
        const urlEl = item.querySelector('.batch-url');
        const urlText = urlEl ? (urlEl.textContent || urlEl.href || '').toLowerCase() : '';
        item.dataset.searchHidden = q && !urlText.includes(q) ? '1' : '';
        applyImagesBatchVisibility(item, filter);
    });
    updateImagesBatchEmptyState();
}

function updateImagesBatchEmptyState() {
    const content = document.getElementById('imagesBatchResultsContent');
    if (!content) return;
    const items = content.querySelectorAll('#imgsBatchList .batch-item');
    let visible = 0;
    items.forEach(item => { if (item.style.display !== 'none') visible++; });
    const emptyState = document.getElementById('imgsBatchEmptyState');
    if (emptyState) emptyState.classList.toggle('visible', items.length > 0 && visible === 0);
    const countEl = document.getElementById('imgsBatchVisibleCount');
    if (countEl && items.length > 0) {
        countEl.textContent = visible < items.length ? `Показано: ${visible} из ${items.length}` : '';
    }
}

async function checkImagesBatchQueue() {
    if (checkImagesBatchQueue._running) {
        showToast('Пакетная обработка уже запущена, дождитесь завершения', 'warning');
        return;
    }
    const batchInput = document.getElementById('imagesBatchInput');
    const delayInput = document.getElementById('imagesBatchDelayMs');
    const progress = document.getElementById('imagesBatchProgress');
    const progressBar = document.getElementById('imagesBatchProgressBar');
    const progressText = document.getElementById('imagesBatchProgressText');
    const modelInput = document.getElementById('imagesModelInput');

    const urls = (batchInput ? batchInput.value : '')
        .split('\n')
        .map(v => v.trim())
        .filter(v => v.startsWith('http'));
    if (!urls.length) {
        showToast('Укажите хотя бы одну ссылку на изображение', 'warning');
        return;
    }

    const provider = getImagesProvider();
    const model = modelInput && modelInput.value.trim() ? modelInput.value.trim() : getDefaultModelByProvider(provider);
    const delayMsRaw = parseInt(delayInput ? delayInput.value : '400', 10);
    const delayMs = Number.isFinite(delayMsRaw) ? Math.max(0, Math.min(delayMsRaw, 10000)) : 400;

    checkImagesBatchQueue._running = true;
    if (progress) progress.style.display = 'block';
    if (progressBar) {
        progressBar.style.animation = 'none';
        progressBar.style.width = '0%';
    }
    if (progressText) progressText.textContent = `0 / ${urls.length}`;

    const results = [];
    try {
        for (let i = 0; i < urls.length; i += 1) {
            const imageUrl = urls[i];
            try {
                const response = await fetch(`${API_BASE}/api/images/check`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                    body: JSON.stringify({
                        provider,
                        model,
                        image_url: imageUrl,
                        image_data_url: null
                    })
                });
                const data = await response.json();
                if (!data.success) {
                    results.push({ url: imageUrl, success: false, error: data.error || 'Request failed' });
                    if (response.status === 401) {
                        throw new Error(data.error || 'Set API token first');
                    }
                } else {
                    results.push({ url: imageUrl, success: true, result: data.result });
                }
            } catch (error) {
                results.push({ url: imageUrl, success: false, error: error.message });
            }

            const completed = i + 1;
            if (progressBar) progressBar.style.width = `${Math.round((completed / urls.length) * 100)}%`;
            if (progressText) progressText.textContent = `${completed} / ${urls.length}`;
            if (completed < urls.length && delayMs > 0) {
                await sleepMs(delayMs);
            }
        }
    } finally {
        checkImagesBatchQueue._running = false;
    }

    currentResults.imagesBatch = results;
    displayImagesBatchResults(results);
}

function getMultiProvider() {
    const el = document.getElementById('multiProviderSelect');
    return el ? el.value : 'openai';
}

function onMultiModeChange() {
    const modeEl = document.getElementById('multiModeSelect');
    const siteInput = document.getElementById('multiSiteUrlInput');
    const urlsInput = document.getElementById('multiUrlsInput');
    if (!modeEl || !siteInput || !urlsInput) return;
    const mode = modeEl.value;
    siteInput.disabled = mode !== 'site';
    urlsInput.disabled = mode !== 'urls';
}

function onMultiProviderChange() {
    const provider = getMultiProvider();
    const presetEl = document.getElementById('multiModelPresetSelect');
    const modelInput = document.getElementById('multiModelInput');
    if (!presetEl) return;

    presetEl.innerHTML = '';
    (IMAGE_MODEL_PRESETS[provider] || []).forEach(model => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        presetEl.appendChild(option);
    });
    const customOption = document.createElement('option');
    customOption.value = '__custom__';
    customOption.textContent = 'custom';
    presetEl.appendChild(customOption);

    if (modelInput && !modelInput.value.trim()) {
        modelInput.value = getDefaultModelByProvider(provider);
    }
    onMultiModelPresetChange();
    loadMultiTokenStatus();
}

function onMultiModelPresetChange() {
    const presetEl = document.getElementById('multiModelPresetSelect');
    const modelInput = document.getElementById('multiModelInput');
    if (!presetEl || !modelInput) return;
    if (presetEl.value !== '__custom__') {
        modelInput.value = presetEl.value;
    }
}

async function loadMultiTokenStatus() {
    const statusEl = document.getElementById('multiTokenStatus');
    if (!statusEl) return;
    const provider = getMultiProvider();
    try {
        const response = await fetch(`${API_BASE}/api/images/token?provider=${encodeURIComponent(provider)}`, {
            credentials: 'same-origin'
        });
        const data = await response.json();
        if (data.success && data.has_token) {
            statusEl.textContent = `токен: ${data.token_masked || 'сохранён'}`;
            statusEl.className = 'images-token-status success';
        } else {
            statusEl.textContent = 'токен не задан';
            statusEl.className = 'images-token-status';
        }
    } catch (_e) {
        statusEl.textContent = 'ошибка статуса токена';
        statusEl.className = 'images-token-status error';
    }
}

async function saveMultiApiToken() {
    const provider = getMultiProvider();
    const input = document.getElementById('multiTokenInput');
    const statusEl = document.getElementById('multiTokenStatus');
    if (!input || !statusEl) return;
    const token = input.value.trim();
    if (!token) {
        showToast('Введите API токен', 'warning');
        return;
    }
    try {
        const response = await fetch(`${API_BASE}/api/images/token`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ provider, token })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка сохранения токена');
        statusEl.textContent = `токен сохранён: ${data.token_masked || ''}`;
        statusEl.className = 'images-token-status success';
        input.value = '';
    } catch (e) {
        statusEl.textContent = `ошибка: ${e.message}`;
        statusEl.className = 'images-token-status error';
    }
}

function parseUrlsFromCsvText(csvText) {
    const lines = (csvText || '').split(/\r?\n/);
    const urls = [];
    lines.forEach(line => {
        line.split(/[;,]/).forEach(cell => {
            const value = cell.trim().replace(/^"|"$/g, '');
            if (/^https?:\/\//i.test(value)) urls.push(value);
        });
    });
    return urls;
}

async function loadMultiUrlsFromFile(event) {
    const file = event && event.target && event.target.files ? event.target.files[0] : null;
    if (!file) return;
    const input = document.getElementById('multiUrlsInput');
    if (!input) return;
    try {
        const text = await file.text();
        let urls = [];
        if (file.name.toLowerCase().endsWith('.csv')) {
            urls = parseUrlsFromCsvText(text);
        } else {
            urls = extractHttpUrls(text);
        }
        const merged = [...extractHttpUrls(input.value || ''), ...urls];
        const unique = Array.from(new Set(merged));
        input.value = unique.join('\n');
        updateMultiUrlsInputMeta();
    } catch (e) {
        showToast('Ошибка чтения файла: ' + e.message, 'error');
    }
}

function renderMultiItem(item, index) {
    if (!item.success) {
        return `
            <div class="batch-item error">
                <div class="batch-item-header">
                    <span class="batch-number">[${index + 1}]</span>
                    <a href="${escAttr(item.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(item.url)}</a>
                    <span class="word-tag invalid">${escHtml(item.resource_type || 'неизвестно')}</span>
                </div>
                <div class="batch-item-error">Ошибка: ${escHtml(item.error || 'Неизвестная ошибка')}</div>
            </div>
        `;
    }

    const statusClass = item.law_compliant ? 'success' : 'warning';
    const forbidden = item.forbidden_words || [];
    const hasViol = !item.law_compliant && forbidden.length > 0;
    const hasText = !!item.source_text;
    return `
        <div class="batch-item ${statusClass}">
            <div class="batch-item-header">
                <span class="batch-number">[${index + 1}]</span>
                <a href="${escAttr(item.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(item.url)}</a>
                <span class="word-tag">${escHtml(item.resource_type || 'неизвестно')}</span>
                ${hasViol && hasText ? `<button class="batch-details-btn" onclick="toggleMultiHighlight(${index}, this)">🖍 Подсветить</button>` : ''}
            </div>
            <div class="batch-item-stats">
                <span class="batch-violations-count">${item.law_compliant ? 'соответствует' : `нарушений: ${item.violations_count || 0}`}</span>
                <span class="batch-words-count">слов: ${(item.result && item.result.total_words) || 0}</span>
            </div>
            ${forbidden.length ? renderWordList(forbidden, 20) : '<div class="text-muted">Запрещённых слов не найдено.</div>'}
        </div>
    `;
}

function displayMultiResults(payload) {
    const card = document.getElementById('multiResults');
    const content = document.getElementById('multiResultsContent');
    if (!card || !content) return;

    const results = payload.results || [];
    const byType = payload.totals_by_type || {};

    // Агрегируем статистику по всем ресурсам
    let totalWords = 0, totalViolations = 0, totalNenorm = 0, totalLatin = 0, totalUnknown = 0;
    const allForbiddenSet = new Set();
    for (const item of results) {
        if (!item.success) continue;
        const r = item.result || {};
        totalWords      += r.total_words      || 0;
        totalViolations += item.violations_count || 0;
        totalNenorm     += r.nenormative_count || 0;
        totalLatin      += r.latin_count       || 0;
        totalUnknown    += r.unknown_count     || 0;
        (item.forbidden_words || []).forEach(w => allForbiddenSet.add(w));
    }
    const compliance = totalWords > 0
        ? Math.round(((totalWords - totalViolations) / totalWords) * 100)
        : 100;
    const withViol = payload.with_violations || 0;

    const summary = `
        <div class="batch-summary">
            <div class="summary-stats">
                <div class="summary-stat">
                    <span class="summary-value">${payload.total || 0}</span>
                    <span class="summary-label">Всего ресурсов</span>
                </div>
                <div class="summary-stat success">
                    <span class="summary-value">${payload.processed_success || 0}</span>
                    <span class="summary-label">Обработано</span>
                </div>
                <div class="summary-stat warning">
                    <span class="summary-value">${withViol}</span>
                    <span class="summary-label">С нарушениями</span>
                </div>
                <div class="summary-stat error">
                    <span class="summary-value">${payload.processed_error || 0}</span>
                    <span class="summary-label">Ошибок загрузки</span>
                </div>
            </div>
            <div class="summary-stats" style="margin-top:10px">
                <div class="summary-stat">
                    <span class="summary-value">${totalWords.toLocaleString('ru-RU')}</span>
                    <span class="summary-label">Всего слов</span>
                </div>
                <div class="summary-stat ${totalViolations > 0 ? 'error' : 'success'}">
                    <span class="summary-value">${totalViolations}</span>
                    <span class="summary-label">Нарушений</span>
                </div>
                <div class="summary-stat ${totalNenorm > 0 ? 'error' : ''}">
                    <span class="summary-value">${totalNenorm}</span>
                    <span class="summary-label">🚫 Ненорм. лексика</span>
                </div>
                <div class="summary-stat ${totalLatin > 0 ? 'warning' : ''}">
                    <span class="summary-value">${totalLatin}</span>
                    <span class="summary-label">🌍 Латиница</span>
                </div>
                <div class="summary-stat ${totalUnknown > 0 ? 'warning' : ''}">
                    <span class="summary-value">${totalUnknown}</span>
                    <span class="summary-label">❓ Неизвестные</span>
                </div>
                <div class="summary-stat ${compliance < 90 ? 'warning' : 'success'}">
                    <span class="summary-value">${compliance}%</span>
                    <span class="summary-label">Соответствие</span>
                </div>
            </div>
            <p class="text-muted" style="margin-top:8px">
                Типы: страниц=${byType.page||0}, изображений=${byType.image||0}, PDF=${byType.pdf||0} &nbsp;|&nbsp;
                Уникальных нарушений: ${allForbiddenSet.size} &nbsp;|&nbsp;
                Время: ${(payload.timings_ms && payload.timings_ms.total) || '-'} мс
            </p>
        </div>
    `;

    content.innerHTML = `
        ${summary}
        <div class="batch-results-list">
            ${results.map((item, idx) => renderMultiItem(item, idx)).join('')}
        </div>
    `;
    card.style.display = 'block';

    // Обновляем заголовок multiscan
    const multiH2 = card.querySelector('.card-header h2');
    if (multiH2) {
        const ok = (payload.processed_success || 0) - (payload.with_violations || 0);
        multiH2.innerHTML = `Мульти-скан: <span style="color:#4CAF50">${ok} ✅</span> / <span style="color:#FF9800">${payload.with_violations || 0} ⚠️</span> из ${payload.total || results.length}`;
    }

    // Панель фильтров для мульти-скана
    const multiList = content.querySelector('.batch-results-list');
    if (multiList && results.length > 1) {
        const processedOk = (payload.processed_success || 0) - withViol;
        const toolbar = document.createElement('div');
        toolbar.className = 'batch-toolbar';
        toolbar.innerHTML = `
            <div class="batch-filter-group">
                <span class="batch-filter-label">Показать:</span>
                <button class="batch-filter-btn active" data-multifilter="all" onclick="filterMultiItems('all', this)">Все (${results.length})</button>
                <button class="batch-filter-btn" data-multifilter="violations" onclick="filterMultiItems('violations', this)">⚠️ Нарушения (${withViol})</button>
                <button class="batch-filter-btn success" data-multifilter="ok" onclick="filterMultiItems('ok', this)">✅ OK (${processedOk})</button>
                ${(payload.processed_error || 0) > 0 ? `<button class="batch-filter-btn error" data-multifilter="errors" onclick="filterMultiItems('errors', this)">❌ Ошибки (${payload.processed_error || 0})</button>` : ''}
            </div>
            <div class="batch-search-group">
                <input type="search" id="multiSearch" class="batch-search-input" placeholder="Поиск по URL…" oninput="searchMultiItems(this.value)">
            </div>
            <span id="multiVisibleCount" class="batch-visible-count"></span>
        `;
        multiList.insertAdjacentElement('beforebegin', toolbar);
        const emptyState = document.createElement('div');
        emptyState.id = 'multiEmptyState';
        emptyState.className = 'batch-empty-state';
        emptyState.textContent = 'Нет результатов по выбранному фильтру или запросу.';
        multiList.insertAdjacentElement('afterend', emptyState);
    }

    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function buildMultiPayload() {
    const mode = (document.getElementById('multiModeSelect') || {}).value || 'site';
    const siteUrl = (document.getElementById('multiSiteUrlInput') || {}).value || '';
    const urlListText = (document.getElementById('multiUrlsInput') || {}).value || '';
    const provider = getMultiProvider();
    const model = (document.getElementById('multiModelInput') || {}).value || '';
    const token = (document.getElementById('multiTokenInput') || {}).value || '';
    const maxUrls = parseInt((document.getElementById('multiMaxUrlsInput') || {}).value || '10', 10);
    const maxPages = parseInt((document.getElementById('multiMaxPagesInput') || {}).value || '10', 10);
    const maxResources = parseInt((document.getElementById('multiMaxResourcesInput') || {}).value || '2500', 10);
    const delayMs = parseInt((document.getElementById('multiDelayMsInput') || {}).value || '150', 10);
    const includeExternal = ((document.getElementById('multiIncludeExternal') || {}).value || 'false') === 'true';

    const urls = Array.from(new Set(extractHttpUrls(urlListText)));
    return {
        mode,
        site_url: siteUrl.trim(),
        urls,
        provider,
        model: model.trim(),
        token: token.trim(),
        max_urls: Number.isFinite(maxUrls) ? maxUrls : 10,
        max_pages: Number.isFinite(maxPages) ? maxPages : 10,
        max_resources: Number.isFinite(maxResources) ? maxResources : 2500,
        delay_ms: Number.isFinite(delayMs) ? delayMs : 150,
        include_external: includeExternal
    };
}

async function runMultiScan() {
    const payload = buildMultiPayload();
    if (payload.mode === 'site') {
        if (!/^https?:\/\//i.test(payload.site_url)) {
            showToast('Введите корректный URL сайта', 'warning');
            return;
        }
    } else if (!payload.urls.length) {
        showToast('Введите хотя бы одну ссылку в списке', 'warning');
        return;
    }

    const progress = document.getElementById('multiProgress');
    const progressBar = document.getElementById('multiProgressBar');
    const progressText = document.getElementById('multiProgressText');
    if (progress) progress.style.display = 'block';
    if (progressBar) {
        progressBar.style.animation = 'progressShine 1.2s linear infinite';
        progressBar.style.width = '100%';
    }
    if (progressText) progressText.textContent = 'Обработка...';

    showLoading('Запускаю мульти-скан...');
    try {
        const response = await fetch(`${API_BASE}/api/multiscan/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка мульти-скана');
        currentResults.multi = data;
        currentDeepResults.multi = null;
        displayMultiResults(data);
        notifyCheckComplete('Мульти-скан завершён', `Проверено ${data.total || 0} ресурсов`);
        const tokenInput = document.getElementById('multiTokenInput');
        if (tokenInput) tokenInput.value = '';
        await loadMultiTokenStatus();
    } catch (e) {
        showToast('Ошибка мульти-скана: ' + e.message, 'error');
    } finally {
        hideLoading();
        if (progress) progress.style.display = 'none';
        if (progressBar) {
            progressBar.style.animation = 'none';
            progressBar.style.width = '0%';
        }
    }
}

function clearMultiScanInputs() {
    const fields = [
        'multiSiteUrlInput',
        'multiUrlsInput',
        'multiTokenInput',
        'multiModelInput'
    ];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const fileInput = document.getElementById('multiUrlsFileInput');
    if (fileInput) fileInput.value = '';
    const resultsCard = document.getElementById('multiResults');
    if (resultsCard) resultsCard.style.display = 'none';
    currentResults.multi = null;
    currentDeepResults.multi = null;
    updateMultiUrlsInputMeta();
    onMultiProviderChange();
    onMultiModeChange();
}

async function deepCheckMultiScan() {
    const payload = currentResults.multi;
    const results = payload && Array.isArray(payload.results) ? payload.results : [];
    if (!results.length) {
        showToast('Нет результатов мульти-скана для глубокой проверки', 'warning');
        return;
    }

    const urlMap = [];
    const allWords = new Set();
    results.forEach((item, index) => {
        if (!item.success || !item.result) return;
        const latin = item.result.latin_words || [];
        const unknown = item.result.unknown_cyrillic || [];
        const words = [...latin, ...unknown];
        if (!words.length) return;
        words.forEach(word => {
            const key = word.toLowerCase();
            if (allWords.has(key)) return;
            allWords.add(key);
            urlMap.push({
                index,
                word,
                url: item.url,
                resourceType: item.resource_type || 'unknown'
            });
        });
    });

    if (!urlMap.length) {
        showToast('Нет слов для глубокой проверки в результатах мульти-скана', 'warning');
        return;
    }

    const words = urlMap.map(x => x.word);
    const batchSize = 100;
    const totalBatches = Math.ceil(words.length / batchSize);
    const deepResults = [];

    showLoading();
    try {
        for (let i = 0; i < totalBatches; i += 1) {
            const start = i * batchSize;
            const chunk = words.slice(start, start + batchSize);
            updateLoadingText(`Deep check batch ${i + 1}/${totalBatches} (${chunk.length} words)...`);
            const response = await fetch(`${API_BASE}/api/deep-check`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ words: chunk })
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            if (data.success && Array.isArray(data.results)) {
                deepResults.push(...data.results);
            }
        }

        currentDeepResults.multi = {
            kind: 'multi',
            deepResults,
            results
        };
        displayMultiDeepResults(results, deepResults);
    } catch (e) {
        showToast('Ошибка глубокой проверки: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

function displayMultiDeepResults(results, deepResults) {
    const resultsContent = document.getElementById('multiResultsContent');
    if (!resultsContent) return;

    const resultMap = {};
    deepResults.forEach(r => {
        resultMap[(r.word || '').toLowerCase()] = r;
    });

    const perResource = [];
    results.forEach(item => {
        if (!item.success || !item.result) return;
        const allWords = [...(item.result.latin_words || []), ...(item.result.unknown_cyrillic || [])];
        if (!allWords.length) return;
        const validated = [];
        const abbreviations = [];
        const invalid = [];
        allWords.forEach(word => {
            const dr = resultMap[word.toLowerCase()];
            if (!dr) return;
            if ((dr.reasons || []).includes('abbreviation')) {
                abbreviations.push(dr);
            } else if (dr.is_valid) {
                validated.push(dr);
            } else {
                invalid.push(dr);
            }
        });
        if (validated.length || abbreviations.length || invalid.length) {
            perResource.push({
                url: item.url,
                resourceType: item.resource_type || 'unknown',
                validated,
                abbreviations,
                invalid
            });
        }
    });

    const totalAbbr = perResource.reduce((sum, r) => sum + r.abbreviations.length, 0);
    const totalValid = perResource.reduce((sum, r) => sum + r.validated.length, 0);
    const totalInvalid = perResource.reduce((sum, r) => sum + r.invalid.length, 0);

    let html = `
        <div class="deep-check-results">
            <h3>🔬 Глубокая проверка: МультиСкан</h3>
            <div class="deep-summary">
                <span class="deep-valid">✅ Подтверждено: ${totalValid}</span>
                <span class="deep-abbr">📚 Аббревиатуры: ${totalAbbr}</span>
                <span class="deep-invalid">❌ Требуют замены: ${totalInvalid}</span>
            </div>
    `;

    perResource.forEach(resource => {
        html += `
            <div class="deep-section batch">
                <h4>
                    <a href="${escAttr(resource.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(resource.url)}</a>
                    <span class="word-tag">${escHtml(resource.resourceType)}</span>
                </h4>
        `;

        if (resource.abbreviations.length) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">📚 Аббревиатуры:</span>
                    <div class="word-list">
                        ${resource.abbreviations.map(dr => `<span class="word-tag abbr" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}<span class="word-translation">→ ${escHtml((dr.suggestions || []).join(', ') || 'перевод неизвестен')}</span></span>`).join('')}
                    </div>
                </div>
            `;
        }

        if (resource.validated.length) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">✅ Подтверждено:</span>
                    <div class="word-list">
                        ${resource.validated.map(dr => `<span class="word-tag valid" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}${dr.normal_form ? `<span class="word-reason">(${escHtml(dr.normal_form)})</span>` : ''}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        if (resource.invalid.length) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">❌ Требуют замены:</span>
                    <div class="word-list">
                        ${resource.invalid.map(dr => `<span class="word-tag invalid" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}${dr.suggestions?.length ? `<span class="word-suggestions">→ ${escHtml(dr.suggestions.join(', '))}</span>` : ''}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        html += `</div>`;
    });

    html += `</div>`;
    resultsContent.insertAdjacentHTML('beforeend', html);
    resultsContent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function checkWord() {
    const inputEl = document.getElementById('wordInput');
    if (!inputEl) return;
    const word = inputEl.value.trim().split(/\s+/)[0] || '';
    inputEl.value = word;
    
    if (!word) {
        showToast('Введите слово для проверки!', 'warning');
        return;
    }
    
    if (word.length < 2) {
        showToast('Слово должно содержать минимум 2 символа!', 'warning');
        return;
    }
    
    showLoading('Проверяю слово...');
    
    try {
        const response = await fetch(`${API_BASE}/api/check-word`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ word })
        });
        
        const data = await response.json();
        
        hideLoading();
        
        if (data.success) {
            currentResults.word = data.result;
            currentDeepResults.word = null;
            displayWordResult(data.result);
            saveWordHistory(word);
            console.log('✅ Слово проверено:', data.result);
        } else {
            showToast('Ошибка: ' + data.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showToast('Ошибка проверки: ' + error.message, 'error');
    }
}

// Отображение результата проверки слова
function displayWordResult(result) {
    const resultsCard = document.getElementById('wordResults');
    const resultsContent = document.getElementById('wordResultsContent');
    if (!resultsCard || !resultsContent || !result) return;
    
    let html = '';
    
    if (result.is_nenormative) {
        html += `
            <div class="result-status error">
                <div class="status-icon">🚫</div>
                <div class="status-text">
                    <h3>ОПАСНОЕ СЛОВО - НЕНОРМАТИВНАЯ ЛЕКСИКА</h3>
                    <p>Данное слово запрещено к использованию. Это критическое нарушение закона.</p>
                </div>
            </div>
        `;
    } else if (result.is_potential_fine) {
        html += `
            <div class="result-status warning">
                <div class="status-icon">⚠️</div>
                <div class="status-text">
                    <h3>ПОТЕНЦИАЛЬНАЯ УГРОЗА ШТРАФА</h3>
                    <p>Слово не найдено в базе нормативных слов. Использование может повлечь штраф до 500 000 рублей.</p>
                </div>
            </div>
        `;
    } else if (result.is_foreign) {
        html += `
            <div class="result-status warning">
                <div class="status-icon">🌍</div>
                <div class="status-text">
                    <h3>ИНОСТРАННОЕ СЛОВО</h3>
                    <p>Слово разрешено к использованию в определённых контекстах.</p>
                </div>
            </div>
        `;
    } else if (result.is_abbreviation) {
        html += `
            <div class="result-status success">
                <div class="status-icon">📚</div>
                <div class="status-text">
                    <h3>АББРЕВИАТУРА</h3>
                    <p>Расшифровка: ${escHtml((result.abbreviation_translation || []).join(', ') || 'не указана')}</p>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="result-status success">
                <div class="status-icon">✅</div>
                <div class="status-text">
                    <h3>НОРМАТИВНОЕ СЛОВО</h3>
                    <p>Слово соответствует требованиям закона.</p>
                </div>
            </div>
        `;
    }
    
    html += `
        <div class="word-detail">
            <div class="word-label">Проверяемое слово:</div>
            <div class="word-value">"${escHtml(result.word)}"</div>
        </div>
    `;
    
    if (result.has_latin) {
        html += `
            <div class="word-detail">
                <div class="word-label">Содержит латиницу:</div>
                <div class="word-value">Да</div>
            </div>
        `;
    }
    
    html += `
        <div class="word-detail">
            <div class="word-label">В базе нормативных:</div>
            <div class="word-value ${result.is_normative ? 'text-success' : 'text-danger'}">
                ${result.is_normative ? '✅ Да' : '❌ Нет'}
            </div>
        </div>
        <div class="word-detail">
            <div class="word-label">В базе иностранных:</div>
            <div class="word-value ${result.is_foreign ? 'text-warning' : ''}">
                ${result.is_foreign ? '✅ Да' : '❌ Нет'}
            </div>
        </div>
        <div class="word-detail">
            <div class="word-label">В базе ненормативных:</div>
            <div class="word-value ${result.is_nenormative ? 'text-danger' : 'text-success'}">
                ${result.is_nenormative ? '🚫 Да (ЗАПРЕЩЕНО)' : '✅ Нет'}
            </div>
        </div>
    `;
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Отображение результатов проверки
function displayResults(type, result, url = '') {
    const resultsCard = document.getElementById(`${type}Results`);
    const resultsContent = document.getElementById(`${type}ResultsContent`);
    
    let html = '';
    
    // Статус проверки
    if (result.law_compliant) {
        html += `
            <div class="result-status success">
                <div class="status-icon">✅</div>
                <div class="status-text">
                    <h3>ТЕКСТ СООТВЕТСТВУЕТ ТРЕБОВАНИЯМ ЗАКОНА</h3>
                    <p>Нарушений не обнаружено. Текст можно публиковать.</p>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="result-status error">
                <div class="status-icon">⚠️</div>
                <div class="status-text">
                    <h3>ОБНАРУЖЕНО НАРУШЕНИЙ: ${result.violations_count}</h3>
                    <p>Требуется исправление перед публикацией</p>
                </div>
            </div>
        `;
        
        // Блок нарушений
        html += '<div class="violations-list">';
        
        // Ненормативная лексика
        if (result.nenormative_count > 0) {
            html += `
                <div class="violation-section critical">
                    <div class="violation-header">
                        <span class="violation-icon">🚫</span>
                        <h3>Ненормативная лексика: ${result.nenormative_count}</h3>
                    </div>
                    ${renderWordList(result.nenormative_words, 20, 'critical', w => w[0] + '*'.repeat(Math.max(0,w.length-2)) + w.slice(-1))}
                </div>
            `;
        }

        // Слова на латинице
        if (result.latin_count > 0) {
            html += `
                <div class="violation-section">
                    <div class="violation-header">
                        <span class="violation-icon">🌍</span>
                        <h3>Слова на латинице: ${result.latin_count}</h3>
                    </div>
                    ${renderWordList(result.latin_words, 30)}
                </div>
            `;
        }

        // Неизвестные слова/англицизмы
        if (result.unknown_count > 0) {
            html += `
                <div class="violation-section">
                    <div class="violation-header">
                        <span class="violation-icon">❓</span>
                        <h3>Англицизмы / Неизвестные слова: ${result.unknown_count}</h3>
                    </div>
                    ${renderWordList(result.unknown_cyrillic, 30)}
                </div>
            `;
        }

        html += '</div>';

        // Кнопка «Копировать все нарушения»
        const allViolationWords = [
            ...(result.latin_words || []),
            ...(result.unknown_cyrillic || []),
            ...(result.nenormative_words || [])
        ];
        if (allViolationWords.length > 0) {
            html += `<button class="btn btn-sm btn-secondary" style="margin-bottom:0.75rem" onclick="copyViolationsList('${type}')" title="Скопировать список нарушающих слов в буфер обмена">📋 Копировать нарушения (${allViolationWords.length})</button>`;
        }

        // Кнопка подсветки нарушений в тексте (для текстовой и URL вкладок)
        if (type === 'text' || type === 'url' || type === 'images') {
            html += `
                <button class="highlight-btn" onclick="toggleHighlight('${type}', this)">🖍 Подсветить в тексте</button>
                <div class="highlight-overlay" id="highlight-${type}" style="display:none" data-source=""></div>
            `;
        }
    }
    
    // Статистика
    html += `
        <div class="stats-summary">
            <h4>📊 Статистика проверки</h4>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-number">${result.total_words.toLocaleString('ru-RU')}</span>
                    <span class="stat-label">Всего слов</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">${result.unique_words.toLocaleString('ru-RU')}</span>
                    <span class="stat-label">Уникальных</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">${result.violations_count}</span>
                    <span class="stat-label">Нарушений</span>
                </div>
                <div class="stat-item">
                    <div class="stat-gauge">${renderGauge(result.law_compliant ? 100 : Math.round(((result.total_words - result.violations_count) / Math.max(result.total_words, 1)) * 100))}</div>
                    <span class="stat-label">Соответствие</span>
                </div>
            </div>
            ${url ? `<p class="url-info"><strong>URL:</strong> <a href="${escAttr(url)}" target="_blank" rel="noopener">${escHtml(url)}</a></p>` : ''}
        </div>
    `;
    
    // Рекомендации
    if (result.recommendations && result.recommendations.length > 0) {
        html += `
            <div class="recommendations">
                <h4>💡 Рекомендации</h4>
                <div class="recommendations-list">
                    ${result.recommendations.map(rec => `
                        <div class="recommendation ${escAttr(rec.level || '')}">
                            <div class="rec-icon">${escHtml(rec.icon || '')}</div>
                            <div class="rec-content">
                                <h5>${escHtml(rec.title || '')}</h5>
                                <p>${escHtml(rec.message || '')}</p>
                                ${rec.action ? `<p class="rec-action">→ ${escHtml(rec.action)}</p>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    // Метка времени последней проверки в заголовке карточки
    const tsEl = resultsCard.querySelector('.card-header .check-timestamp');
    if (tsEl) tsEl.textContent = `Проверено: ${new Date().toLocaleTimeString('ru-RU')}`;
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Отображение пакетных результатов с детализацией нарушений
function displayBatchResults(results) {
    const resultsCard = document.getElementById('batchResults');
    const resultsContent = document.getElementById('batchResultsContent');
    
    let totalViolations = 0;
    let critical = 0;
    let successful = 0;
    
    // Собираем уникальные слова по всем сайтам
    const allLatinWords = new Set();
    const allUnknownWords = new Set();
    const allNenormativeWords = new Set();
    
    results.forEach(item => {
        if (item.success) {
            successful++;
            const hasViolations = !item.result.law_compliant;
            if (hasViolations) {
                totalViolations++;
                if (item.result.nenormative_count > 0) critical++;
                // Собираем слова
                (item.result.latin_words || []).forEach(w => allLatinWords.add(w));
                (item.result.unknown_cyrillic || []).forEach(w => allUnknownWords.add(w));
                (item.result.nenormative_words || []).forEach(w => allNenormativeWords.add(w));
            }
        }
    });
    
    let html = `
        <div class="batch-summary">
            <div class="summary-header">
                <h3>📊 Результаты пакетной проверки</h3>
                <p>Проверено сайтов: ${results.length}</p>
            </div>
            <div class="summary-stats">
                <div class="summary-item success">
                    <span class="summary-number">${successful - totalViolations}</span>
                    <span class="summary-label">Без нарушений</span>
                </div>
                <div class="summary-item warning">
                    <span class="summary-number">${totalViolations}</span>
                    <span class="summary-label">С нарушениями</span>
                </div>
                ${critical > 0 ? `
                    <div class="summary-item critical">
                        <span class="summary-number">${critical}</span>
                        <span class="summary-label">Критических</span>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    // Сводка уникальных нарушений по всем сайтам
    if (allLatinWords.size > 0 || allUnknownWords.size > 0 || allNenormativeWords.size > 0) {
        html += `
            <div class="batch-global-violations">
                <h4>🌍 Уникальные нарушения по всем сайтам</h4>
                <div class="batch-violations-summary">
                    ${allNenormativeWords.size > 0 ? `
                        <div class="batch-violation-category critical">
                            <h5>🚫 Ненормативная лексика (${allNenormativeWords.size})</h5>
                            ${renderWordList(Array.from(allNenormativeWords), 20, 'critical', w => w[0] + '*'.repeat(Math.max(0,w.length-2)) + w.slice(-1))}
                        </div>
                    ` : ''}
                    ${allLatinWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>🌍 Латиница (${allLatinWords.size})</h5>
                            ${renderWordList(Array.from(allLatinWords), 30)}
                        </div>
                    ` : ''}
                    ${allUnknownWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>❓ Англицизмы / Неизвестные (${allUnknownWords.size})</h5>
                            ${renderWordList(Array.from(allUnknownWords), 30)}
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    html += '<div class="batch-results-list">';
    
    results.forEach((item, index) => {
        const statusIcon = !item.success ? '❌' : 
                          item.result.law_compliant ? '✅' : 
                          item.result.nenormative_count > 0 ? '🚫' : '⚠️';
        
        const statusClass = !item.success ? 'error' : 
                           item.result.law_compliant ? 'success' : 
                           item.result.nenormative_count > 0 ? 'critical' : 'warning';
        
        const hasDetails = item.success && !item.result.law_compliant && 
                          (item.result.latin_words?.length > 0 || 
                           item.result.unknown_cyrillic?.length > 0 || 
                           item.result.nenormative_words?.length > 0);
        
        html += `
            <div class="batch-item ${statusClass}">
                <div class="batch-item-header">
                    <span class="batch-icon">${statusIcon}</span>
                    <span class="batch-number">[${index + 1}]</span>
                    <a href="${escAttr(item.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(item.url)}</a>
                    <button class="batch-copy-url-btn" data-copy-url="${escAttr(item.url)}" title="Скопировать URL">📋</button>
                    ${hasDetails ? `
                        <button class="batch-details-btn" id="batch-btn-${index}" onclick="toggleBatchDetails(${index})">
                            Показать детали
                        </button>
                    ` : ''}
                    ${hasDetails && item.source_text ? `
                        <button class="batch-details-btn" onclick="toggleBatchHighlight(${index}, this)">🖍 Подсветить</button>
                    ` : ''}
                </div>
                ${item.success ? `
                    <div class="batch-item-stats">
                        <span>Нарушений: ${item.result.violations_count}</span>
                        <span>Латиница: ${item.result.latin_count}</span>
                        <span>Англицизмы: ${item.result.unknown_count}</span>
                        ${item.result.nenormative_count > 0 ? `<span class="critical-badge">Ненорматив: ${item.result.nenormative_count}</span>` : ''}
                        <span class="batch-words-count">Всего слов: ${item.result.total_words || 0}</span>
                    </div>
                ` : `<div class="batch-item-error">Ошибка: ${escHtml(item.error || 'Неизвестная ошибка')}</div>`}
                
                ${hasDetails ? `
                    <div class="batch-details" id="batch-details-${index}" style="display: none;">
                        ${item.result.nenormative_words?.length > 0 ? `
                            <div class="batch-detail-section critical">
                                <h6>🚫 Ненормативная лексика:</h6>
                                ${renderWordList(item.result.nenormative_words, 15, 'critical', w => w[0] + '*'.repeat(Math.max(0,w.length-2)) + w.slice(-1))}
                            </div>
                        ` : ''}
                        ${item.result.latin_words?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>🌍 Латиница:</h6>
                                ${renderWordList(item.result.latin_words, 20)}
                            </div>
                        ` : ''}
                        ${item.result.unknown_cyrillic?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>❓ Англицизмы / Неизвестные:</h6>
                                ${renderWordList(item.result.unknown_cyrillic, 20)}
                            </div>
                        ` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    });
    
    html += '</div>';
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';

    // Обновляем заголовок карточки: краткая сводка
    const batchH2 = resultsCard.querySelector('.card-header h2');
    if (batchH2) {
        const ok = successful - totalViolations;
        batchH2.innerHTML = `Пакетная проверка: <span style="color:#4CAF50">${ok} ✅</span> / <span style="color:#FF9800">${totalViolations} ⚠️</span> из ${results.length}`;
    }

    // Добавляем панель фильтров и expand/collapse
    const batchList = resultsContent.querySelector('.batch-results-list');
    if (batchList) {
        const toolbar = document.createElement('div');
        toolbar.className = 'batch-toolbar';
        toolbar.innerHTML = `
            <div class="batch-filter-group">
                <span class="batch-filter-label">Показать:</span>
                <button class="batch-filter-btn active" data-filter="all" onclick="filterBatchItems('all', this)">Все (${results.length})</button>
                <button class="batch-filter-btn" data-filter="violations" onclick="filterBatchItems('violations', this)">⚠️ Нарушения (${totalViolations})</button>
                <button class="batch-filter-btn success" data-filter="ok" onclick="filterBatchItems('ok', this)">✅ OK (${successful - totalViolations})</button>
                ${results.length - successful > 0 ? `<button class="batch-filter-btn error" data-filter="errors" onclick="filterBatchItems('errors', this)">❌ Ошибки (${results.length - successful})</button>` : ''}
            </div>
            <div class="batch-search-group">
                <input type="search" id="batchSearch" class="batch-search-input" placeholder="Поиск по URL…" oninput="searchBatchItems(this.value)">
            </div>
            <div class="batch-expand-group">
                <button class="batch-filter-btn" onclick="expandAllBatchDetails(true)">Раскрыть все</button>
                <button class="batch-filter-btn" onclick="expandAllBatchDetails(false)">Свернуть все</button>
                ${results.length - successful > 0 ? `<button class="batch-filter-btn error" onclick="retryFailedBatchItems()" title="Повторить проверку ошибочных URL">🔄 Перепроверить (${results.length - successful})</button>` : ''}
            </div>
            <div class="batch-sort-group">
                <select class="batch-search-input" id="batchSortSelect" onchange="sortBatchItems(this.value)" title="Сортировка">
                    <option value="default">↕ Порядок</option>
                    <option value="violations-desc">↓ Нарушения</option>
                    <option value="violations-asc">↑ Нарушения</option>
                    <option value="url-asc">A→Я URL</option>
                </select>
            </div>
            <span id="batchVisibleCount" class="batch-visible-count"></span>
        `;
        batchList.insertAdjacentElement('beforebegin', toolbar);
        // Пустое состояние — показывается когда все элементы скрыты фильтром/поиском
        const emptyState = document.createElement('div');
        emptyState.id = 'batchEmptyState';
        emptyState.className = 'batch-empty-state';
        emptyState.textContent = 'Нет результатов по выбранному фильтру или запросу.';
        batchList.insertAdjacentElement('afterend', emptyState);
    }

    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Поиск batch-элементов по URL
function searchBatchItems(query) {
    const q = (query || '').toLowerCase().trim();
    const batchContent = document.getElementById('batchResultsContent');
    if (!batchContent) return;
    const activeFilter = batchContent.querySelector('[data-filter].active');
    const filter = activeFilter ? activeFilter.dataset.filter : 'all';
    batchContent.querySelectorAll('.batch-item').forEach(item => {
        const urlEl = item.querySelector('.batch-url');
        const urlText = urlEl ? (urlEl.textContent || urlEl.href || '').toLowerCase() : '';
        item.dataset.searchHidden = q && !urlText.includes(q) ? '1' : '';
        applyBatchVisibility(item, filter);
    });
    updateBatchEmptyState();
}

// Фильтрация batch-элементов по статусу
function filterBatchItems(filter, btn) {
    const batchContent = document.getElementById('batchResultsContent');
    if (!batchContent) return;
    batchContent.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    // Сбрасываем поиск при смене фильтра
    const searchInput = document.getElementById('batchSearch');
    if (searchInput) searchInput.value = '';
    batchContent.querySelectorAll('.batch-item').forEach(item => {
        item.dataset.searchHidden = '';
        applyBatchVisibility(item, filter);
    });
    updateBatchEmptyState();
}

function applyBatchVisibility(item, filter) {
    if (item.dataset.searchHidden === '1') { item.style.display = 'none'; return; }
    if (filter === 'all') {
        item.style.display = '';
    } else if (filter === 'violations') {
        item.style.display = (item.classList.contains('warning') || item.classList.contains('critical')) ? '' : 'none';
    } else if (filter === 'ok') {
        item.style.display = item.classList.contains('success') ? '' : 'none';
    } else if (filter === 'errors') {
        item.style.display = item.classList.contains('error') ? '' : 'none';
    }
}

// Сортировка batch-элементов
function sortBatchItems(order) {
    const batchList = document.querySelector('#batchResultsContent .batch-results-list');
    if (!batchList) return;
    const items = Array.from(batchList.querySelectorAll('.batch-item'));
    if (!items.length) return;
    const getViolations = el => parseInt(el.querySelector('.batch-item-stats span')?.textContent?.match(/\d+/) || '0', 10) || 0;
    const getUrl = el => (el.querySelector('.batch-url')?.textContent || '').toLowerCase();
    items.sort((a, b) => {
        if (order === 'violations-desc') return getViolations(b) - getViolations(a);
        if (order === 'violations-asc')  return getViolations(a) - getViolations(b);
        if (order === 'url-asc')         return getUrl(a).localeCompare(getUrl(b));
        return 0; // default: no change
    });
    items.forEach(item => batchList.appendChild(item));
}

// Раскрыть/свернуть все детали batch
function expandAllBatchDetails(expand) {
    document.querySelectorAll('[id^="batch-details-"]').forEach(el => {
        el.style.display = expand ? 'block' : 'none';
    });
    document.querySelectorAll('[id^="batch-btn-"]').forEach(btn => {
        btn.textContent = expand ? 'Скрыть детали' : 'Показать детали';
    });
}

// Повторная проверка ошибочных URL в пакетной проверке
async function retryFailedBatchItems() {
    const results = currentResults.batch;
    if (!results) return;
    const failedIndices = [];
    const failedUrls = [];
    results.forEach((item, i) => {
        if (!item.success) { failedIndices.push(i); failedUrls.push(item.url); }
    });
    if (!failedUrls.length) { showToast('Нет ошибочных URL для повторной проверки', 'info'); return; }
    showToast(`Повторная проверка ${failedUrls.length} URL…`, 'info');
    try {
        const response = await fetch(`${API_BASE}/api/batch-check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ urls: failedUrls })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка');
        (data.results || []).forEach((newItem, i) => {
            if (failedIndices[i] !== undefined) {
                currentResults.batch[failedIndices[i]] = newItem;
            }
        });
        displayBatchResults(currentResults.batch);
        const stillFailed = currentResults.batch.filter(x => !x.success).length;
        showToast(
            stillFailed > 0 ? `Готово. Ещё не удалось: ${stillFailed}` : 'Повторная проверка успешна',
            stillFailed > 0 ? 'warning' : 'success'
        );
    } catch (e) {
        showToast('Ошибка повторной проверки: ' + e.message, 'error');
    }
}

// Поделиться ссылкой через Web Share API (с fallback на clipboard)
async function shareCurrentUrl() {
    const url = window.location.href;
    if (navigator.share) {
        try {
            await navigator.share({ title: 'LawChecker Online', url });
            return;
        } catch (e) {
            if (e.name === 'AbortError') return; // пользователь отменил
        }
    }
    // Fallback: copy to clipboard
    try {
        await navigator.clipboard.writeText(url);
        showToast('Ссылка скопирована в буфер обмена', 'success');
    } catch (_e) {
        showToast('Не удалось скопировать ссылку', 'warning');
    }
}

// Подсветить активную кнопку вкладки при прокрутке к ней
function scrollTabIntoView(tabName) {
    const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (btn) btn.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
}

// Экспорт отчета
function downloadUtf8Txt(filename, text) {
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + (text || '')], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Копировать URL с нарушениями из multiscan
function copyMultiViolationUrls() {
    const data = currentResults.multi;
    if (!data || !(data.results || []).length) {
        showToast('Нет данных мульти-скана', 'warning');
        return;
    }
    const urls = (data.results || [])
        .filter(item => item.success && !item.law_compliant)
        .map(item => item.url);
    if (!urls.length) {
        showToast('Нарушений не найдено — все ресурсы соответствуют', 'info');
        return;
    }
    navigator.clipboard.writeText(urls.join('\n')).then(
        () => showToast(`Скопировано ${urls.length} URL с нарушениями`, 'success'),
        () => showToast('Не удалось скопировать', 'error')
    );
}

// Экспорт multiscan-результатов в CSV
function exportMultiCsv() {
    const data = currentResults.multi;
    if (!data || !(data.results || []).length) {
        showToast('Нет данных для экспорта!', 'warning');
        return;
    }
    const csvRow = (cells) => cells.map(c => `"${String(c == null ? '' : c).replace(/"/g, '""')}"`).join(',');
    const rows = [
        csvRow(['URL', 'Тип', 'Статус', 'Нарушений', 'Всего слов', 'Ошибка'])
    ];
    (data.results || []).forEach(item => {
        if (!item.success) {
            rows.push(csvRow([item.url, item.resource_type || '', 'ошибка', '', '', item.error || '']));
        } else {
            const r = item.result || {};
            rows.push(csvRow([
                item.url,
                item.resource_type || '',
                item.law_compliant ? 'соответствует' : 'нарушения',
                item.violations_count ?? 0,
                r.total_words ?? 0,
                ''
            ]));
        }
    });
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + rows.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `multiscan_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    showToast(`CSV экспортирован (${(data.results || []).length} строк)`, 'success');
}

// Экспорт batch-результатов в CSV (с BOM для корректного открытия в Excel)
function exportBatchCsv() {
    const results = currentResults.batch;
    if (!results || !results.length) {
        showToast('Нет данных для экспорта! Сначала выполните проверку.', 'warning');
        return;
    }
    const csvRow = (cells) => cells.map(c => `"${String(c == null ? '' : c).replace(/"/g, '""')}"`).join(',');
    const rows = [
        csvRow(['URL', 'Статус', 'Нарушений', 'Латиница', 'Англицизмы', 'Ненорматив', 'Всего слов', 'Ошибка'])
    ];
    results.forEach(item => {
        if (!item.success) {
            rows.push(csvRow([item.url, 'ошибка', '', '', '', '', '', item.error || '']));
        } else {
            const r = item.result || {};
            rows.push(csvRow([
                item.url,
                r.law_compliant ? 'соответствует' : 'нарушения',
                r.violations_count ?? 0,
                r.latin_count ?? 0,
                r.unknown_count ?? 0,
                r.nenormative_count ?? 0,
                r.total_words ?? 0,
                ''
            ]));
        }
    });
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + rows.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `batch_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    showToast(`CSV экспортирован (${results.length} строк)`, 'success');
}

// Экспорт результатов пакетной проверки изображений в CSV
function exportImagesBatchCsv() {
    const results = currentResults.imagesBatch;
    if (!results || !results.length) {
        showToast('Нет данных для экспорта! Сначала выполните проверку.', 'warning');
        return;
    }
    const csvRow = (cells) => cells.map(c => `"${String(c == null ? '' : c).replace(/"/g, '""')}"`).join(',');
    const rows = [
        csvRow(['URL', 'Статус', 'Нарушений', 'Латиница', 'Ненорматив', 'Иностр. слова', 'Всего слов', 'OCR символов', 'Ошибка'])
    ];
    results.forEach(item => {
        if (!item.success) {
            rows.push(csvRow([item.url, 'ошибка', '', '', '', '', '', '', item.error || '']));
        } else {
            const r = item.result || {};
            const ocrLen = (r.extracted_text || '').length;
            rows.push(csvRow([
                item.url,
                r.law_compliant ? 'соответствует' : 'нарушения',
                r.violations_count ?? 0,
                (r.latin_words || []).length,
                (r.nenormative_words || []).length,
                (r.unknown_cyrillic || []).length,
                r.total_words ?? 0,
                ocrLen,
                ''
            ]));
        }
    });
    const BOM = '\uFEFF';
    const blob = new Blob([BOM + rows.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `images_batch_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    showToast(`CSV экспортирован (${results.length} строк)`, 'success');
}

function deepSummaryFromList(deepResults) {
    const list = Array.isArray(deepResults) ? deepResults : [];
    const abbreviations = list.filter(r => (r.reasons || []).includes('abbreviation'));
    const valid = list.filter(r => r.is_valid && !(r.reasons || []).includes('abbreviation'));
    const invalid = list.filter(r => !r.is_valid);
    return { abbreviations, valid, invalid };
}

function buildSingleDeepReport(type, result, deepPayload) {
    const deepResults = (deepPayload && deepPayload.deepResults) || [];
    const summary = deepSummaryFromList(deepResults);
    const lines = [];
    lines.push('======================================================================');
    lines.push(`ОТЧЁТ ГЛУБОКОЙ ПРОВЕРКИ: ${type.toUpperCase()}`);
    lines.push('======================================================================');
    lines.push(`Дата: ${new Date().toLocaleString('ru-RU')}`);
    lines.push(`Всего слов в тексте: ${result?.total_words || 0}`);
    lines.push(`Нарушений (базовая проверка): ${result?.violations_count || 0}`);
    lines.push(`Подтверждено (глубокая): ${summary.valid.length}`);
    lines.push(`Аббревиатуры: ${summary.abbreviations.length}`);
    lines.push(`Требует замены: ${summary.invalid.length}`);
    lines.push('');

    if (summary.abbreviations.length) {
        lines.push('[АББРЕВИАТУРЫ]');
        summary.abbreviations.forEach(item => {
            lines.push(`- ${item.word} -> ${(item.suggestions || []).join(', ') || 'перевод неизвестен'}`);
        });
        lines.push('');
    }

    if (summary.valid.length) {
        lines.push('[ПОДТВЕРЖДЕНО]');
        summary.valid.forEach(item => {
            lines.push(`- ${item.word}${item.normal_form ? ` (${item.normal_form})` : ''}`);
        });
        lines.push('');
    }

    if (summary.invalid.length) {
        lines.push('[ТРЕБУЕТ ЗАМЕНЫ]');
        summary.invalid.forEach(item => {
            lines.push(`- ${item.word}${item.suggestions?.length ? ` -> ${item.suggestions.join(', ')}` : ''}`);
        });
        lines.push('');
    }

    return lines.join('\n');
}

function buildCollectionDeepReport(type, results, deepPayload) {
    const deepResults = (deepPayload && deepPayload.deepResults) || [];
    const resultMap = {};
    deepResults.forEach(item => {
        resultMap[(item.word || '').toLowerCase()] = item;
    });

    const lines = [];
    lines.push('======================================================================');
    lines.push(`ОТЧЁТ ГЛУБОКОЙ ПРОВЕРКИ: ${type.toUpperCase()}`);
    lines.push('======================================================================');
    lines.push(`Дата: ${new Date().toLocaleString('ru-RU')}`);
    lines.push(`Всего ресурсов: ${results.length}`);
    lines.push('');

    let totalValid = 0;
    let totalAbbr = 0;
    let totalInvalid = 0;

    results.forEach((entry, idx) => {
        lines.push('----------------------------------------------------------------------');
        lines.push(`[${idx + 1}] ${entry.url || '-'}`);
        if (entry.resource_type) lines.push(`Тип: ${entry.resource_type}`);

        if (!entry.success || !entry.result) {
            lines.push(`Статус: ОШИБКА (${entry.error || 'Неизвестная ошибка'})`);
            lines.push('');
            return;
        }

        const words = [...(entry.result.latin_words || []), ...(entry.result.unknown_cyrillic || [])];
        const abbreviations = [];
        const valid = [];
        const invalid = [];
        words.forEach(word => {
            const dr = resultMap[word.toLowerCase()];
            if (!dr) return;
            if ((dr.reasons || []).includes('abbreviation')) {
                abbreviations.push(dr);
            } else if (dr.is_valid) {
                valid.push(dr);
            } else {
                invalid.push(dr);
            }
        });

        totalValid += valid.length;
        totalAbbr += abbreviations.length;
        totalInvalid += invalid.length;
        lines.push(`Итог: подтверждено=${valid.length}, аббревиатур=${abbreviations.length}, требует_замены=${invalid.length}`);

        if (abbreviations.length) {
            lines.push('  АББРЕВИАТУРЫ:');
            abbreviations.forEach(item => {
                lines.push(`    - ${item.word} -> ${(item.suggestions || []).join(', ') || 'перевод неизвестен'}`);
            });
        }
        if (valid.length) {
            lines.push('  ПОДТВЕРЖДЕНО:');
            valid.forEach(item => {
                lines.push(`    - ${item.word}${item.normal_form ? ` (${item.normal_form})` : ''}`);
            });
        }
        if (invalid.length) {
            lines.push('  ТРЕБУЕТ ЗАМЕНЫ:');
            invalid.forEach(item => {
                lines.push(`    - ${item.word}${item.suggestions?.length ? ` -> ${item.suggestions.join(', ')}` : ''}`);
            });
        }
        lines.push('');
    });

    lines.splice(5, 0, `Общий итог: подтверждено=${totalValid}, аббревиатур=${totalAbbr}, требует_замены=${totalInvalid}`);
    return lines.join('\n');
}

function buildDeepExportText(type) {
    const deep = currentDeepResults[type];
    const result = currentResults[type];
    if (!deep || !result) return null;
    if (type === 'batch') {
        return buildCollectionDeepReport(type, result, deep);
    }
    if (type === 'multi') {
        const multiItems = Array.isArray(result.results) ? result.results : [];
        return buildCollectionDeepReport(type, multiItems, deep);
    }
    return buildSingleDeepReport(type, result, deep);
}

async function exportReport(type) {
    const result = currentResults[type];
    if (!result) {
        showToast('Нет данных для экспорта! Сначала выполните проверку.', 'warning');
        return;
    }
    
    try {
        showLoading();
        console.log('📥 Экспорт отчета:', type, result);
        const deepText = buildDeepExportText(type);
        if (deepText) {
            const filename = `lawcheck_${type}_deep_${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`;
            downloadUtf8Txt(filename, deepText);
            return;
        }
        
        // Для пакетной проверки используем специальный endpoint
        const isBatch = type === 'batch';
        const isMulti = type === 'multi';
        let endpoint = '/api/export/txt';
        let payload = { result };
        let prefix = 'lawcheck_';
        if (isBatch) {
            endpoint = '/api/export/batch-txt';
            payload = { results: result };
            prefix = 'lawcheck_batch_';
        } else if (isMulti) {
            endpoint = '/api/export/multiscan-txt';
            payload = { scan: result };
            prefix = 'lawcheck_multiscan_';
        }
        
        const response = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${prefix}${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        console.log('✅ Отчет скачан');
        
    } catch (error) {
        console.error('❌ Ошибка экспорта:', error);
        showToast('Ошибка экспорта: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Экспорт отчёта в Word (DOCX)
async function exportDocx(type) {
    const result = currentResults[type];
    if (!result) { showToast('Нет данных для экспорта! Сначала выполните проверку.', 'warning'); return; }
    try {
        showLoading();
        let endpoint, payload, prefix;
        if (type === 'batch') {
            endpoint = '/api/export/batch-docx';
            payload  = { results: result };
            prefix   = 'lawcheck_batch_';
        } else if (type === 'multi') {
            endpoint = '/api/export/multiscan-docx';
            payload  = { scan: result };
            prefix   = 'lawcheck_multiscan_';
        } else {
            endpoint = '/api/export/docx';
            const urlVal = type === 'url' ? (document.getElementById('urlInput')?.value || '') : '';
            payload  = { result, url: urlVal };
            prefix   = 'lawcheck_';
        }
        const resp = await fetch(`${API_BASE}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
        const blob = await resp.blob();
        const a = document.createElement('a');
        a.href = window.URL.createObjectURL(blob);
        a.download = `${prefix}${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.docx`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        window.URL.revokeObjectURL(a.href);
    } catch (e) {
        showToast('Ошибка экспорта Word: ' + e.message, 'error');
    } finally {
        hideLoading();
    }
}

// Глубокая проверка слов
async function deepCheck(type) {
    const result = currentResults[type];
    if (!result) {
        showToast('Нет данных для проверки! Сначала выполните проверку.', 'warning');
        return;
    }

    const wordsToCheck = type === 'word'
        ? [result.word].filter(Boolean)
        : [
            ...(result.latin_words || []),
            ...(result.unknown_cyrillic || [])
        ];

    if (wordsToCheck.length === 0) {
        showToast('Нет слов для глубокой проверки!', 'warning');
        return;
    }

    // Ограничиваем количество слов для одного запроса
    const maxWords = 200;
    const wordsToProcess = wordsToCheck.slice(0, maxWords);
    const skippedCount = wordsToCheck.length - maxWords;

    showLoading('Глубокий анализ слов...');
    console.log('🔬 Глубокая проверка:', wordsToProcess.length, 'слов из', wordsToCheck.length);

    try {
        const response = await fetch(`${API_BASE}/api/deep-check`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ words: wordsToProcess })
        });

        const data = await response.json();

        hideLoading();

        if (data.success) {
            currentDeepResults[type] = {
                kind: 'single',
                deepResults: data.results || [],
                checkedWords: wordsToProcess,
                totalWords: wordsToCheck.length,
                createdAt: new Date().toISOString()
            };
            displayDeepResults(type, data.results);
            if (skippedCount > 0) {
                showToast(`Показаны результаты для первых ${maxWords} слов. Ещё ${skippedCount} слов пропущено.`, 'info');
            }
            console.log('✅ Глубокая проверка завершена:', data.results.length, 'слов');
        } else {
            showToast('Ошибка: ' + data.error, 'error');
        }
    } catch (error) {
        hideLoading();
        showToast('Ошибка глубокой проверки: ' + error.message, 'error');
    }
}

// Глубокая проверка для пакетного режима
async function deepCheckBatch() {
    const results = currentResults.batch;
    if (!results || !Array.isArray(results)) {
        showToast('Нет данных для проверки! Сначала выполните пакетную проверку.', 'warning');
        return;
    }

    // Собираем все уникальные слова со всех URL
    const allWords = new Set();
    const urlMap = [];

    results.forEach((item, index) => {
        if (item.success && item.result) {
            const latin = item.result.latin_words || [];
            const unknown = item.result.unknown_cyrillic || [];
            if (latin.length > 0 || unknown.length > 0) {
                const words = [...latin, ...unknown];
                words.forEach(w => {
                    if (!allWords.has(w)) {
                        allWords.add(w);
                        urlMap.push({ word: w, urlIndex: index });
                    }
                });
            }
        }
    });

    if (allWords.size === 0) {
        showToast('Нет слов для глубокой проверки!', 'warning');
        return;
    }

    const wordArray = Array.from(allWords);
    const batchSize = 100; // Обрабатываем по 100 слов за раз
    const totalBatches = Math.ceil(wordArray.length / batchSize);

    showLoading('Глубокий анализ (пакетная)...');
    console.log('🔬 Глубокая проверка batch:', wordArray.length, 'слов,', totalBatches, 'батчей');

    try {
        const allDeepResults = [];
        let currentBatch = 0;

        while (currentBatch < totalBatches) {
            const start = currentBatch * batchSize;
            const end = start + batchSize;
            const batchWords = wordArray.slice(start, end);

            // Показываем прогресс
            updateLoadingText(`Проверка батча ${currentBatch + 1}/${totalBatches} (${batchWords.length} слов)...`);

            const response = await fetch(`${API_BASE}/api/deep-check`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ words: batchWords })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            if (data.success && data.results) {
                allDeepResults.push(...data.results);
            }

            currentBatch++;
        }

        // Скрываем лоадер перед показом результатов
        hideLoading();

        if (allDeepResults.length > 0) {
            currentDeepResults.batch = {
                kind: 'batch',
                deepResults: allDeepResults,
                results
            };
            displayBatchDeepResults(results, allDeepResults, urlMap);
            console.log('✅ Глубокая проверка batch завершена:', allDeepResults.length, 'слов');
        } else {
            showToast('Не удалось получить результаты глубокой проверки', 'error');
        }

    } catch (error) {
        hideLoading();
        console.error('❌ Ошибка глубокой проверки:', error);
        showToast('Ошибка глубокой проверки: ' + error.message, 'error');
    }
}

function updateLoadingText(text) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        const p = overlay.querySelector('p');
        if (p) p.textContent = text;
    }
}

// Отображение результатов глубокой проверки для batch
function displayBatchDeepResults(results, deepResults, urlMap) {
    const resultsContent = document.getElementById('batchResultsContent');

    // Создаем словарь результатов
    const resultMap = {};
    deepResults.forEach(r => {
        resultMap[r.word.toLowerCase()] = r;
    });

    // Группируем по URL
    const urlResults = results.map((item, index) => {
        if (!item.success || !item.result) return null;

        const latin = item.result.latin_words || [];
        const unknown = item.result.unknown_cyrillic || [];
        const allWords = [...latin, ...unknown];

        const validated = [];
        const abbreviations = [];
        const invalid = [];

        allWords.forEach(word => {
            const dr = resultMap[word.toLowerCase()];
            if (dr) {
                if (dr.reasons.includes('abbreviation')) {
                    abbreviations.push(dr);
                } else if (dr.is_valid) {
                    validated.push(dr);
                } else {
                    invalid.push(dr);
                }
            }
        });

        return {
            url: item.url,
            index,
            validated,
            abbreviations,
            invalid
        };
    }).filter(r => r !== null && (r.validated.length > 0 || r.abbreviations.length > 0 || r.invalid.length > 0));

    // Считаем общую статистику
    const totalAbbr = urlResults.reduce((sum, r) => sum + r.abbreviations.length, 0);
    const totalValid = urlResults.reduce((sum, r) => sum + r.validated.length, 0);
    const totalInvalid = urlResults.reduce((sum, r) => sum + r.invalid.length, 0);

    let html = `
        <div class="deep-check-results">
            <h3>🔬 Глубокая проверка всех URL</h3>
            <div class="deep-summary">
                <span class="deep-valid">✅ Подтверждено: ${totalValid}</span>
                <span class="deep-abbr">📚 Аббревиатуры: ${totalAbbr}</span>
                <span class="deep-invalid">❌ Требуют замены: ${totalInvalid}</span>
            </div>
    `;

    urlResults.forEach(r => {
        html += `
            <div class="deep-section batch">
                <h4><a href="${escAttr(r.url)}" target="_blank" rel="noopener" class="batch-url">${escHtml(r.url)}</a></h4>
        `;

        if (r.abbreviations.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">📚 Аббревиатуры:</span>
                    <div class="word-list">
                        ${r.abbreviations.map(dr => `<span class="word-tag abbr" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}<span class="word-translation">→ ${escHtml((dr.suggestions || []).join(', ') || 'перевод неизвестен')}</span></span>`).join('')}
                    </div>
                </div>
            `;
        }

        if (r.validated.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">✅ Подтверждено:</span>
                    <div class="word-list">
                        ${r.validated.map(dr => `<span class="word-tag valid" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}${dr.normal_form ? `<span class="word-reason">(${escHtml(dr.normal_form)})</span>` : ''}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        if (r.invalid.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">❌ Требуют замены:</span>
                    <div class="word-list">
                        ${r.invalid.map(dr => `<span class="word-tag invalid" data-word="${escAttr(dr.word)}" title="Нажмите, чтобы скопировать">${escHtml(dr.word)}${dr.suggestions?.length > 0 ? `<span class="word-suggestions">→ ${escHtml(dr.suggestions.join(', '))}</span>` : ''}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        html += `</div>`;
    });

    html += '</div>';

    resultsContent.insertAdjacentHTML('beforeend', html);
    resultsContent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Отображение результатов глубокой проверки
// Рендер списка deep-check тегов (НЕ использует renderWordList — теги уже HTML)
function renderDeepTagList(items, limit) {
    if (!items.length) return '<div class="word-list"></div>';
    const shown = items.slice(0, limit);
    const rest  = items.slice(limit);
    let html = '<div class="word-list">' + shown.join('');
    if (rest.length > 0) {
        const uid = 'ws' + Math.random().toString(36).slice(2, 9);
        html += `<span class="word-spoiler-hidden" id="${uid}" style="display:none">${rest.join('')}</span>`;
        html += `<button class="spoiler-toggle-btn" onclick="toggleWordSpoiler(this,'${uid}',${rest.length})">▼ Показать ещё ${rest.length}</button>`;
    }
    return html + '</div>';
}

function displayDeepResults(type, results) {
    const resultsContent = document.getElementById(`${type}ResultsContent`);

    const abbreviations = results.filter(r => r.reasons.includes('abbreviation'));
    const otherValid    = results.filter(r => r.is_valid && !r.reasons.includes('abbreviation'));
    const invalidWords  = results.filter(r => !r.is_valid);

    let html = `
        <div class="deep-check-results">
            <h3>🔬 Результаты глубокой проверки</h3>
            <div class="deep-summary">
                <span class="deep-valid">✅ Подтверждено: ${otherValid.length}</span>
                <span class="deep-abbr">📚 Аббревиатуры: ${abbreviations.length}</span>
                <span class="deep-invalid">❌ Неизвестно: ${invalidWords.length}</span>
            </div>
    `;

    if (abbreviations.length > 0) {
        const tags = abbreviations.map(r => {
            const sug = (r.suggestions || []).join(', ') || 'перевод неизвестен';
            const tip = escAttr(r.reasons.map(deepReasonLabel).join(', '));
            return `<span class="word-tag abbr" data-word="${escAttr(r.word)}" title="${tip}">${escHtml(r.word)}<span class="word-translation">→ ${escHtml(sug)}</span></span>`;
        });
        html += `<div class="deep-section abbreviation"><h4>📚 Аббревиатуры (${abbreviations.length})</h4>${renderDeepTagList(tags, 20)}</div>`;
    }

    if (otherValid.length > 0) {
        const tags = otherValid.map(r => {
            const label = escAttr(r.reasons.map(deepReasonLabel).join(', '));
            const norm  = r.normal_form && r.normal_form !== r.word.toLowerCase()
                ? `<span class="word-reason">(${escHtml(r.normal_form)})</span>` : '';
            return `<span class="word-tag valid" data-word="${escAttr(r.word)}" title="${label}">${escHtml(r.word)}${norm}</span>`;
        });
        html += `<div class="deep-section valid"><h4>✅ Подтверждено (${otherValid.length})</h4>${renderDeepTagList(tags, 30)}</div>`;
    }

    if (invalidWords.length > 0) {
        const tags = invalidWords.map(r => {
            const sug = r.suggestions?.length
                ? `<span class="word-suggestions">→ ${escHtml(r.suggestions.slice(0, 3).join(', '))}</span>` : '';
            return `<span class="word-tag invalid" data-word="${escAttr(r.word)}" title="Нажмите, чтобы скопировать">${escHtml(r.word)}${sug}</span>`;
        });
        const copyInvalidBtn = `<button class="btn btn-sm btn-secondary" style="margin-left:auto;font-size:0.8rem" onclick="copyDeepInvalid('${escAttr(type)}')" title="Скопировать все слова, требующие замены">📋 Копировать (${invalidWords.length})</button>`;
        html += `<div class="deep-section invalid"><h4 style="display:flex;align-items:center;gap:0.5rem">❓ Требуют замены (${invalidWords.length})${copyInvalidBtn}</h4>${renderDeepTagList(tags, 30)}</div>`;
    }

    html += '</div>';

    resultsContent.insertAdjacentHTML('beforeend', html);
    resultsContent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Переключение отображения деталей пакетной проверки
function toggleBatchDetails(index) {
    const detailsEl = document.getElementById(`batch-details-${index}`);
    if (detailsEl) {
        const isVisible = detailsEl.style.display !== 'none';
        detailsEl.style.display = isVisible ? 'none' : 'block';
        
        // Обновляем текст кнопки
        const btnEl = document.getElementById(`batch-btn-${index}`);
        if (btnEl) {
            btnEl.textContent = isVisible ? 'Показать детали' : 'Скрыть детали';
        }
    }
}

// Вспомогательные функции

// Вставка текста из буфера обмена в поле textInput
async function pasteFromClipboard() {
    try {
        const text = await navigator.clipboard.readText();
        if (!text) { showToast('Буфер обмена пуст', 'warning'); return; }
        const el = document.getElementById('textInput');
        if (!el) return;
        el.value = text;
        updateTextInputMeta();
        localStorage.setItem(TEXT_AUTOSAVE_KEY, text);
        el.focus();
        showToast('Текст вставлен из буфера обмена', 'success');
    } catch (_e) {
        showToast('Нет доступа к буферу — нажмите Ctrl+V в поле текста', 'info');
    }
}

function clearText() {
    const el = document.getElementById('textInput');
    if (!el) return;
    const backup = el.value;
    el.value = '';
    document.getElementById('textResults').style.display = 'none';
    currentResults.text = null;
    currentDeepResults.text = null;
    localStorage.removeItem(TEXT_AUTOSAVE_KEY);
    updateTextInputMeta();
    if (backup.trim()) {
        showToastWithUndo('Текст очищен', () => {
            el.value = backup;
            localStorage.setItem(TEXT_AUTOSAVE_KEY, backup);
            updateTextInputMeta();
            el.focus();
        });
    }
}

function loadSample() {
    const sampleText = `Пример текста для проверки закона о русском языке.

Этот сервис проверяет тексты на соответствие федеральному закону №168-ФЗ.
Он находит слова на латинице, англицизмы и ненормативную лексику.

Попробуйте добавить english words или специальные термины для проверки!`;
    const textInput = document.getElementById('textInput');
    if (textInput) {
        textInput.value = sampleText;
        localStorage.setItem(TEXT_AUTOSAVE_KEY, sampleText);
    }
    updateTextInputMeta();
}

async function copyExtractedImageText() {
    const input = document.getElementById('imagesInput');
    if (!input || !input.value.trim()) {
        showToast('Нет извлечённого текста для копирования', 'warning');
        return;
    }
    try {
        await navigator.clipboard.writeText(input.value);
    } catch (_e) {
        input.select();
        document.execCommand('copy');
    }
}

function clearImageInputs() {
    const urlInput = document.getElementById('imagesUrlInput');
    const fileInput = document.getElementById('imagesFileInput');
    const textInput = document.getElementById('imagesInput');
    const batchInput = document.getElementById('imagesBatchInput');
    const resultsCard = document.getElementById('imagesResults');
    const batchResultsCard = document.getElementById('imagesBatchResults');
    const batchProgress = document.getElementById('imagesBatchProgress');
    if (urlInput) urlInput.value = '';
    if (fileInput) fileInput.value = '';
    if (textInput) textInput.value = '';
    if (batchInput) batchInput.value = '';
    if (resultsCard) resultsCard.style.display = 'none';
    if (batchResultsCard) batchResultsCard.style.display = 'none';
    if (batchProgress) batchProgress.style.display = 'none';
    currentResults.images = null;
    currentResults.imagesBatch = null;
    currentDeepResults.images = null;
    updateImagesInputMeta();
    updateImagesBatchInputMeta();
}

function showLoading(message = 'Проверяю...') {
    const overlay = document.getElementById('loadingOverlay');
    const msg = document.getElementById('loadingMessage');
    if (msg) msg.textContent = message;
    document.querySelectorAll('.btn').forEach(btn => { btn.disabled = true; });
    if (overlay) overlay.style.display = 'flex';
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    document.querySelectorAll('.btn').forEach(btn => {
        btn.disabled = false;
    });
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// === Browser notifications для долгих проверок ===
function notifyCheckComplete(title, body) {
    if (!('Notification' in window)) return;
    if (Notification.permission === 'granted') {
        new Notification(title, { body, icon: '/favicon.ico' });
    } else if (Notification.permission !== 'denied') {
        Notification.requestPermission().then(perm => {
            if (perm === 'granted') new Notification(title, { body });
        });
    }
}

// === История недавних слов (word-tab) ===
const WORD_HISTORY_KEY = 'lawchecker.wordHistory';
const WORD_HISTORY_MAX = 10;

function saveWordHistory(word) {
    try {
        let hist = JSON.parse(localStorage.getItem(WORD_HISTORY_KEY) || '[]');
        hist = [word, ...hist.filter(w => w !== word)].slice(0, WORD_HISTORY_MAX);
        localStorage.setItem(WORD_HISTORY_KEY, JSON.stringify(hist));
        renderWordHistory();
    } catch(e) {}
}

function removeWordFromHistory(word) {
    try {
        let hist = JSON.parse(localStorage.getItem(WORD_HISTORY_KEY) || '[]');
        hist = hist.filter(w => w !== word);
        localStorage.setItem(WORD_HISTORY_KEY, JSON.stringify(hist));
        renderWordHistory();
    } catch(e) {}
}

function renderWordHistory() {
    const container = document.getElementById('wordHistory');
    if (!container) return;
    try {
        const hist = JSON.parse(localStorage.getItem(WORD_HISTORY_KEY) || '[]');
        if (!hist.length) { container.innerHTML = ''; return; }
        container.innerHTML = `<span class="word-history-label">Недавние:</span>` +
            hist.map(w => `<span class="word-history-chip" data-recheck="${escAttr(w)}">${escAttr(w)}<button class="chip-remove" data-remove="${escAttr(w)}" title="Удалить из истории">×</button></span>`).join('') +
            `<button class="word-history-clear" onclick="clearWordHistory()" title="Очистить всю историю">Очистить</button>`;
    } catch(e) { container.innerHTML = ''; }
}

function clearWordHistory() {
    localStorage.removeItem(WORD_HISTORY_KEY);
    renderWordHistory();
}

// Делегирование кликов для word history + batch copy url
document.addEventListener('click', (e) => {
    const removeBtn = e.target.closest('.chip-remove[data-remove]');
    if (removeBtn) {
        e.stopPropagation();
        removeWordFromHistory(removeBtn.dataset.remove);
        return;
    }
    const chip = e.target.closest('.word-history-chip[data-recheck]');
    if (chip) {
        const word = chip.dataset.recheck;
        const inp = document.getElementById('wordInput');
        if (inp) { inp.value = word; checkWord(); }
        return;
    }
    const copyUrlBtn = e.target.closest('.batch-copy-url-btn[data-copy-url]');
    if (copyUrlBtn) {
        const url = copyUrlBtn.dataset.copyUrl;
        navigator.clipboard.writeText(url).then(
            () => showToast('URL скопирован', 'success', 2000),
            () => showToast('Не удалось скопировать', 'error')
        );
        return;
    }
});

// === Копирование невалидных слов из deep check ===
function copyDeepInvalid(type) {
    const deep = currentDeepResults[type];
    if (!deep) { showToast('Нет данных', 'warning'); return; }
    const deepResults = (deep.deepResults) || (Array.isArray(deep) ? deep : []);
    const invalid = deepResults.filter(r => !r.is_valid).map(r => r.word);
    if (!invalid.length) { showToast('Нет слов для копирования', 'info'); return; }
    navigator.clipboard.writeText(invalid.join(', ')).then(
        () => showToast(`Скопировано ${invalid.length} слов`, 'success'),
        () => showToast('Не удалось скопировать', 'error')
    );
}

// === Копирование всех нарушений в буфер ===
function copyViolationsList(type) {
    const result = currentResults[type];
    if (!result) return;
    const words = [
        ...(result.latin_words || []),
        ...(result.unknown_cyrillic || []),
        ...(result.nenormative_words || [])
    ];
    if (!words.length) { showToast('Нарушений не найдено', 'info'); return; }
    navigator.clipboard.writeText(words.join(', ')).then(
        () => showToast(`Скопировано ${words.length} слов`, 'success'),
        () => showToast('Не удалось скопировать', 'error')
    );
}

// === Фильтр мульти-скана ===
function filterMultiItems(filter, btn) {
    document.querySelectorAll('[data-multifilter]').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    const searchInput = document.getElementById('multiSearch');
    if (searchInput) searchInput.value = '';
    const content = document.getElementById('multiResultsContent');
    if (!content) return;
    content.querySelectorAll('.batch-item').forEach(item => {
        item.dataset.searchHidden = '';
        applyMultiVisibility(item, filter);
    });
    updateMultiEmptyState();
}

// Поиск по URL в мульти-скане
function searchMultiItems(query) {
    const q = (query || '').toLowerCase().trim();
    const content = document.getElementById('multiResultsContent');
    if (!content) return;
    const activeFilter = content.querySelector('[data-multifilter].active');
    const filter = activeFilter ? activeFilter.dataset.multifilter : 'all';
    content.querySelectorAll('.batch-item').forEach(item => {
        const urlEl = item.querySelector('.batch-url');
        const urlText = urlEl ? (urlEl.textContent || urlEl.href || '').toLowerCase() : '';
        item.dataset.searchHidden = q && !urlText.includes(q) ? '1' : '';
        applyMultiVisibility(item, filter);
    });
    updateMultiEmptyState();
}

function applyMultiVisibility(item, filter) {
    if (item.dataset.searchHidden === '1') { item.style.display = 'none'; return; }
    if (filter === 'all') { item.style.display = ''; }
    else if (filter === 'violations') { item.style.display = (item.classList.contains('warning') || item.classList.contains('critical')) ? '' : 'none'; }
    else if (filter === 'ok') { item.style.display = item.classList.contains('success') ? '' : 'none'; }
    else if (filter === 'errors') { item.style.display = item.classList.contains('error') ? '' : 'none'; }
}

function updateMultiEmptyState() {
    const content = document.getElementById('multiResultsContent');
    if (!content) return;
    const items = content.querySelectorAll('.batch-item');
    let visible = 0;
    items.forEach(item => { if (item.style.display !== 'none') visible++; });
    const emptyState = document.getElementById('multiEmptyState');
    if (emptyState) emptyState.classList.toggle('visible', items.length > 0 && visible === 0);
    const countEl = document.getElementById('multiVisibleCount');
    if (countEl && items.length > 0) {
        countEl.textContent = visible < items.length ? `Показано: ${visible} из ${items.length}` : '';
    }
}

// === Пустое состояние batch после фильтрации ===
function updateBatchEmptyState() {
    const batchList = document.querySelector('#batchResultsContent .batch-results-list');
    const items = batchList ? batchList.querySelectorAll('.batch-item') : document.querySelectorAll('#batchResultsContent .batch-item');
    let visible = 0;
    items.forEach(item => { if (item.style.display !== 'none') visible++; });
    const emptyState = document.getElementById('batchEmptyState');
    if (emptyState) emptyState.classList.toggle('visible', items.length > 0 && visible === 0);
    const countEl = document.getElementById('batchVisibleCount');
    if (countEl && items.length > 0) {
        countEl.textContent = visible < items.length ? `Показано: ${visible} из ${items.length}` : '';
    }
}

// Горячие клавиши
document.addEventListener('keydown', (e) => {
    // Alt+1-6 — переключение вкладок
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const tabMap = { '1':'text', '2':'url', '3':'batch', '4':'word', '5':'images', '6':'multi' };
        const tabName = tabMap[e.key];
        if (tabName) { e.preventDefault(); switchTab(tabName); return; }
    }
    // ? — показать подсказки горячих клавиш (только если не в поле ввода)
    if (e.key === '?' && !e.ctrlKey && !e.altKey && !e.metaKey) {
        const active = document.activeElement;
        const inInput = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.tagName === 'SELECT');
        if (!inInput) { e.preventDefault(); toggleKeyboardHelpModal(); return; }
    }
    // Escape — закрыть модальные окна
    if (e.key === 'Escape') {
        const modal = document.getElementById('keyboardHelpModal');
        if (modal && modal.style.display !== 'none') { closeKeyboardHelpModal(); return; }
    }
    if (!(e.ctrlKey && e.key === 'Enter')) return;

    const activeTab = getActiveTabName();
    if (activeTab === 'text') return checkText();
    if (activeTab === 'url') return checkUrl();
    if (activeTab === 'batch') return checkBatch();
    if (activeTab === 'word') return checkWord();
    if (activeTab === 'images') return checkExtractedImageText();
});

// Модальное окно с горячими клавишами
function toggleKeyboardHelpModal() {
    const modal = document.getElementById('keyboardHelpModal');
    if (!modal) return;
    const isVisible = modal.style.display !== 'none';
    if (isVisible) closeKeyboardHelpModal(); else openKeyboardHelpModal();
}
function openKeyboardHelpModal() {
    let modal = document.getElementById('keyboardHelpModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'keyboardHelpModal';
        modal.className = 'kb-modal-overlay';
        modal.innerHTML = `
            <div class="kb-modal" role="dialog" aria-modal="true" aria-label="Горячие клавиши">
                <div class="kb-modal-header">
                    <h3>⌨️ Горячие клавиши</h3>
                    <button class="kb-modal-close" onclick="closeKeyboardHelpModal()" title="Закрыть">✕</button>
                </div>
                <div class="kb-modal-body">
                    <table class="kb-table">
                        <tr><td><kbd>Ctrl</kbd>+<kbd>Enter</kbd></td><td>Запустить проверку (активная вкладка)</td></tr>
                        <tr><td><kbd>Alt</kbd>+<kbd>1</kbd>…<kbd>6</kbd></td><td>Переключить вкладку (Текст/URL/Пакет/Слово/Фото/Мульти)</td></tr>
                        <tr><td><kbd>?</kbd></td><td>Показать это окно</td></tr>
                        <tr><td><kbd>Esc</kbd></td><td>Закрыть это окно</td></tr>
                    </table>
                    <p class="kb-modal-hint">Горячие клавиши не работают когда фокус в поле ввода</p>
                </div>
            </div>
        `;
        modal.addEventListener('click', e => { if (e.target === modal) closeKeyboardHelpModal(); });
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
    requestAnimationFrame(() => modal.classList.add('kb-visible'));
}
function closeKeyboardHelpModal() {
    const modal = document.getElementById('keyboardHelpModal');
    if (!modal) return;
    modal.classList.remove('kb-visible');
    setTimeout(() => { if (modal) modal.style.display = 'none'; }, 220);
}
