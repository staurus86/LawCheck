// API Configuration
const API_BASE = window.API_BASE_URL || 'http://localhost:5000';
console.log('🔗 Using API:', API_BASE);

// Global variables
let currentResults = {
    text: null,
    url: null,
    batch: null,
    images: null,
    imagesBatch: null,
    multi: null
};
const ACTIVE_TAB_KEY = 'lawchecker.activeTab';

// App bootstrap
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initFieldMetrics();
    loadStats();
    onImagesProviderChange();
    loadImageTokenStatus();
    onMultiProviderChange();
    onMultiModeChange();
    console.log('App loaded');
});

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
    meta.textContent = `${chars} chars | ${words} words`;
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
    meta.textContent = `${urls.length} URLs (${unique.size} unique)`;
}

function updateImagesInputMeta() {
    const input = document.getElementById('imagesInput');
    const meta = document.getElementById('imagesInputMeta');
    if (!input || !meta) return;
    const text = input.value || '';
    const chars = text.length;
    const words = (text.trim().match(/\S+/g) || []).length;
    meta.textContent = `${chars} chars | ${words} words`;
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
    meta.textContent = `${urls.length} image URLs (${unique.size} unique)`;
}

function updateMultiUrlsInputMeta() {
    const input = document.getElementById('multiUrlsInput');
    const meta = document.getElementById('multiUrlsInputMeta');
    if (!input || !meta) return;
    const urls = extractHttpUrls(input.value || '');
    const unique = new Set(urls);
    meta.textContent = `${urls.length} URLs (${unique.size} unique)`;
}

function initFieldMetrics() {
    const textInput = document.getElementById('textInput');
    const batchInput = document.getElementById('batchInput');
    const imagesInput = document.getElementById('imagesInput');
    const imagesBatchInput = document.getElementById('imagesBatchInput');
    const multiUrlsInput = document.getElementById('multiUrlsInput');
    if (textInput) textInput.addEventListener('input', updateTextInputMeta);
    if (batchInput) batchInput.addEventListener('input', updateBatchInputMeta);
    if (imagesInput) imagesInput.addEventListener('input', updateImagesInputMeta);
    if (imagesBatchInput) imagesBatchInput.addEventListener('input', updateImagesBatchInputMeta);
    if (multiUrlsInput) multiUrlsInput.addEventListener('input', updateMultiUrlsInputMeta);
    updateTextInputMeta();
    updateBatchInputMeta();
    updateImagesInputMeta();
    updateImagesBatchInputMeta();
    updateMultiUrlsInputMeta();
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
            normativeEl.textContent = data.normative.toLocaleString('ru-RU');
        }
        
        if (foreignEl && data.foreign !== undefined) {
            foreignEl.textContent = data.foreign.toLocaleString('ru-RU');
        }
        
        if (nenormativeEl && data.nenormative !== undefined) {
            nenormativeEl.textContent = data.nenormative.toLocaleString('ru-RU');
        }
        
        if (abbrEl && data.abbreviations !== undefined) {
            abbrEl.textContent = data.abbreviations.toLocaleString('ru-RU');
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

// Проверка текста
async function checkText() {
    const text = document.getElementById('textInput').value.trim();
    
    if (!text) {
        alert('Введите текст для проверки!');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch(`${API_BASE}/api/check`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentResults.text = data.result;
            displayResults('text', data.result);
            console.log('✅ Текст проверен:', data.result);
        } else {
            alert('Ошибка: ' + data.error);
        }
    } catch (error) {
        alert('Ошибка проверки: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Проверка URL
async function checkUrl() {
    const url = document.getElementById('urlInput').value.trim();
    
    if (!url || !url.startsWith('http')) {
        alert('Введите корректный URL!');
        return;
    }
    
    showLoading();
    document.getElementById('urlProgress').style.display = 'block';
    
    try {
        const response = await fetch(`${API_BASE}/api/check-url`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ url })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentResults.url = data.result;
            displayResults('url', data.result, url);
            console.log('✅ URL проверен:', data.result);
        } else {
            alert('Ошибка: ' + data.error);
        }
    } catch (error) {
        alert('Ошибка загрузки: ' + error.message);
    } finally {
        hideLoading();
        document.getElementById('urlProgress').style.display = 'none';
    }
}

// Пакетная проверка
async function checkBatch() {
    const input = document.getElementById('batchInput').value.trim();
    const urls = input.split('\n').filter(u => u.trim() && u.startsWith('http'));
    
    if (urls.length === 0) {
        alert('Введите хотя бы один URL!');
        return;
    }
    
    const progressBar = document.getElementById('batchProgress');
    const progressFill = document.getElementById('batchProgressBar');
    const progressText = document.getElementById('batchProgressText');
    
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressFill.style.animation = 'none';
    progressText.textContent = `0 / ${urls.length}`;

    try {
        const response = await fetch(`${API_BASE}/api/batch-check`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ urls })
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Batch check failed');
        }

        const results = data.results || [];
        progressFill.style.width = '100%';
        progressText.textContent = `${results.length} / ${results.length}`;
        currentResults.batch = results;
        displayBatchResults(results);
        console.log('✅ Пакетная проверка завершена:', results);
    } catch (error) {
        alert('Ошибка пакетной проверки: ' + error.message);
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
            statusEl.textContent = `token: ${data.token_masked || 'saved'}`;
            statusEl.className = 'images-token-status success';
        } else {
            statusEl.textContent = 'token not set';
            statusEl.className = 'images-token-status';
        }
    } catch (e) {
        statusEl.textContent = 'token status error';
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
        alert('Enter API token');
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
        if (!data.success) throw new Error(data.error || 'Token save failed');
        statusEl.textContent = `token saved: ${data.token_masked || ''}`;
        statusEl.className = 'images-token-status success';
        input.value = '';
    } catch (e) {
        statusEl.textContent = `error: ${e.message}`;
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
        alert('Provide image URL or upload file');
        return;
    }

    if (file) {
        if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
            alert('Only jpg/png/webp are supported');
            return;
        }
        if (file.size > MAX_IMAGE_FILE_SIZE_BYTES) {
            alert('Image is too large. Max size is 8MB');
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
    targetEl.innerHTML += `
        <div class="image-db-summary">
            <h4>OCR log</h4>
            <p>provider: ${ocr.provider || '-'} | model: ${ocr.model || '-'} | source: ${ocr.source || '-'}</p>
            <p>timings ms: ocr=${timings.ocr ?? '-'}, check=${timings.text_check ?? '-'}, total=${timings.total ?? '-'}</p>
            <p>usage: ${Object.keys(usage).length ? Object.entries(usage).map(([k, v]) => `${k}=${v}`).join(', ') : 'n/a'}</p>
        </div>
    `;
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
    displayResults('images', result, result.source_url || '');
    const resultsContent = document.getElementById('imagesResultsContent');
    appendImageOcrSummary(result.ocr, resultsContent);
}

async function scrapTextFromImageAndCheck() {
    const extractedTextArea = document.getElementById('imagesInput');
    const payload = await buildImagesPayload();
    if (!payload) return;

    showLoading();
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
        if (!extractedText) throw new Error('OCR returned empty text');
        if (extractedTextArea) {
            extractedTextArea.value = extractedText;
            updateImagesInputMeta();
        }

        await runStandardCheckForImageText(extractedText, data.source_url || '', data.ocr || null);
    } catch (e) {
        alert('Image scrape error: ' + e.message);
    } finally {
        hideLoading();
    }
}

async function checkExtractedImageText() {
    const extractedTextArea = document.getElementById('imagesInput');
    const text = extractedTextArea ? extractedTextArea.value.trim() : '';
    if (!text) {
        alert('No extracted text to check');
        return;
    }

    const ocr = currentResults.images && currentResults.images.ocr ? currentResults.images.ocr : null;
    const sourceUrl = currentResults.images && currentResults.images.source_url ? currentResults.images.source_url : '';
    showLoading();
    try {
        await runStandardCheckForImageText(text, sourceUrl, ocr);
    } catch (e) {
        alert('Text check error: ' + e.message);
    } finally {
        hideLoading();
    }
}

async function checkImagesByDatabase() {
    const payload = await buildImagesPayload();
    if (!payload) return;
    const extractedTextArea = document.getElementById('imagesInput');

    showLoading();
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
        if (extractedTextArea) {
            extractedTextArea.value = data.result.extracted_text || '';
            updateImagesInputMeta();
        }
        displayResults('images', data.result, data.result.source_url || '');
        const resultsContent = document.getElementById('imagesResultsContent');
        appendImageOcrSummary(data.result.ocr, resultsContent);
    } catch (e) {
        alert('Image check error: ' + e.message);
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
            <div class="batch-item error">
                <div class="batch-item-header">
                    <span class="batch-number">[${index + 1}]</span>
                    <a href="${item.url}" target="_blank" class="batch-url">${item.url}</a>
                </div>
                <div class="batch-item-error">Error: ${item.error || 'Unknown error'}</div>
            </div>
        `;
    }

    const r = item.result;
    const statusIcon = r.law_compliant ? '✅' : '⚠️';
    const statusText = r.law_compliant ? 'compliant' : `violations: ${r.violations_count || 0}`;
    return `
        <div class="batch-item ${r.law_compliant ? 'success' : 'warning'}">
            <div class="batch-item-header">
                <span class="batch-icon">${statusIcon}</span>
                <span class="batch-number">[${index + 1}]</span>
                <a href="${item.url}" target="_blank" class="batch-url">${item.url}</a>
            </div>
            <div class="batch-item-stats">
                <span class="batch-violations-count">${statusText}</span>
                <span class="batch-words-count">words: ${r.total_words || 0}</span>
                <span class="batch-words-count">ocr chars: ${(r.extracted_text || '').length}</span>
            </div>
        </div>
    `;
}

function displayImagesBatchResults(results) {
    const resultsCard = document.getElementById('imagesBatchResults');
    const resultsContent = document.getElementById('imagesBatchResultsContent');
    if (!resultsCard || !resultsContent) return;

    const total = results.length;
    const success = results.filter(r => r.success).length;
    const failed = total - success;
    const withViolations = results.filter(r => r.success && r.result && !r.result.law_compliant).length;

    let html = `
        <div class="batch-summary">
            <div class="summary-stats">
                <div class="summary-stat">
                    <span class="summary-value">${total}</span>
                    <span class="summary-label">Total images</span>
                </div>
                <div class="summary-stat success">
                    <span class="summary-value">${success}</span>
                    <span class="summary-label">Processed</span>
                </div>
                <div class="summary-stat warning">
                    <span class="summary-value">${withViolations}</span>
                    <span class="summary-label">With violations</span>
                </div>
                <div class="summary-stat error">
                    <span class="summary-value">${failed}</span>
                    <span class="summary-label">Failed</span>
                </div>
            </div>
        </div>
        <div class="batch-results-list">
            ${results.map((item, idx) => renderImageBatchItem(item, idx)).join('')}
        </div>
    `;

    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function checkImagesBatchQueue() {
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
        alert('Provide at least one image URL');
        return;
    }

    const provider = getImagesProvider();
    const model = modelInput && modelInput.value.trim() ? modelInput.value.trim() : getDefaultModelByProvider(provider);
    const delayMsRaw = parseInt(delayInput ? delayInput.value : '400', 10);
    const delayMs = Number.isFinite(delayMsRaw) ? Math.max(0, Math.min(delayMsRaw, 10000)) : 400;

    if (progress) progress.style.display = 'block';
    if (progressBar) {
        progressBar.style.animation = 'none';
        progressBar.style.width = '0%';
    }
    if (progressText) progressText.textContent = `0 / ${urls.length}`;

    const results = [];
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
            statusEl.textContent = `token: ${data.token_masked || 'saved'}`;
            statusEl.className = 'images-token-status success';
        } else {
            statusEl.textContent = 'token not set';
            statusEl.className = 'images-token-status';
        }
    } catch (_e) {
        statusEl.textContent = 'token status error';
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
        alert('Enter API token');
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
        if (!data.success) throw new Error(data.error || 'Token save failed');
        statusEl.textContent = `token saved: ${data.token_masked || ''}`;
        statusEl.className = 'images-token-status success';
        input.value = '';
    } catch (e) {
        statusEl.textContent = `error: ${e.message}`;
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
        alert('Failed to read file: ' + e.message);
    }
}

function renderMultiItem(item, index) {
    if (!item.success) {
        return `
            <div class="batch-item error">
                <div class="batch-item-header">
                    <span class="batch-number">[${index + 1}]</span>
                    <a href="${item.url}" target="_blank" class="batch-url">${item.url}</a>
                    <span class="word-tag invalid">${item.resource_type || 'unknown'}</span>
                </div>
                <div class="batch-item-error">Error: ${item.error || 'Unknown error'}</div>
            </div>
        `;
    }

    const statusClass = item.law_compliant ? 'success' : 'warning';
    const forbiddenPreview = (item.forbidden_words || []).slice(0, 20);
    return `
        <div class="batch-item ${statusClass}">
            <div class="batch-item-header">
                <span class="batch-number">[${index + 1}]</span>
                <a href="${item.url}" target="_blank" class="batch-url">${item.url}</a>
                <span class="word-tag">${item.resource_type || 'unknown'}</span>
            </div>
            <div class="batch-item-stats">
                <span class="batch-violations-count">${item.law_compliant ? 'compliant' : `violations: ${item.violations_count || 0}`}</span>
                <span class="batch-words-count">words: ${(item.result && item.result.total_words) || 0}</span>
            </div>
            ${forbiddenPreview.length ? `
                <div class="word-list">
                    ${forbiddenPreview.map(w => `<span class="word-tag">${w}</span>`).join('')}
                    ${(item.forbidden_words || []).length > forbiddenPreview.length ? `<span class="more-words">... +${(item.forbidden_words || []).length - forbiddenPreview.length}</span>` : ''}
                </div>
            ` : '<div class="text-muted">No forbidden words found.</div>'}
        </div>
    `;
}

function displayMultiResults(payload) {
    const card = document.getElementById('multiResults');
    const content = document.getElementById('multiResultsContent');
    if (!card || !content) return;

    const results = payload.results || [];
    const byType = payload.totals_by_type || {};
    const summary = `
        <div class="batch-summary">
            <div class="summary-stats">
                <div class="summary-stat">
                    <span class="summary-value">${payload.total || 0}</span>
                    <span class="summary-label">Total</span>
                </div>
                <div class="summary-stat success">
                    <span class="summary-value">${payload.processed_success || 0}</span>
                    <span class="summary-label">Success</span>
                </div>
                <div class="summary-stat error">
                    <span class="summary-value">${payload.processed_error || 0}</span>
                    <span class="summary-label">Errors</span>
                </div>
                <div class="summary-stat warning">
                    <span class="summary-value">${payload.with_violations || 0}</span>
                    <span class="summary-label">With violations</span>
                </div>
            </div>
            <p class="text-muted">Types: pages=${byType.page || 0}, images=${byType.image || 0}, pdf=${byType.pdf || 0}</p>
            <p class="text-muted">Total time: ${(payload.timings_ms && payload.timings_ms.total) || '-'} ms</p>
        </div>
    `;

    content.innerHTML = `
        ${summary}
        <div class="batch-results-list">
            ${results.map((item, idx) => renderMultiItem(item, idx)).join('')}
        </div>
    `;
    card.style.display = 'block';
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function buildMultiPayload() {
    const mode = (document.getElementById('multiModeSelect') || {}).value || 'site';
    const siteUrl = (document.getElementById('multiSiteUrlInput') || {}).value || '';
    const urlListText = (document.getElementById('multiUrlsInput') || {}).value || '';
    const provider = getMultiProvider();
    const model = (document.getElementById('multiModelInput') || {}).value || '';
    const token = (document.getElementById('multiTokenInput') || {}).value || '';
    const maxUrls = parseInt((document.getElementById('multiMaxUrlsInput') || {}).value || '500', 10);
    const maxPages = parseInt((document.getElementById('multiMaxPagesInput') || {}).value || '500', 10);
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
        max_urls: Number.isFinite(maxUrls) ? maxUrls : 500,
        max_pages: Number.isFinite(maxPages) ? maxPages : 500,
        max_resources: Number.isFinite(maxResources) ? maxResources : 2500,
        delay_ms: Number.isFinite(delayMs) ? delayMs : 150,
        include_external: includeExternal
    };
}

async function runMultiScan() {
    const payload = buildMultiPayload();
    if (payload.mode === 'site') {
        if (!/^https?:\/\//i.test(payload.site_url)) {
            alert('Provide valid site URL');
            return;
        }
    } else if (!payload.urls.length) {
        alert('Provide at least one URL in list mode');
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
    if (progressText) progressText.textContent = 'Processing...';

    showLoading();
    try {
        const response = await fetch(`${API_BASE}/api/multiscan/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'MultiScan failed');
        currentResults.multi = data;
        displayMultiResults(data);
        const tokenInput = document.getElementById('multiTokenInput');
        if (tokenInput) tokenInput.value = '';
        await loadMultiTokenStatus();
    } catch (e) {
        alert('MultiScan error: ' + e.message);
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
    updateMultiUrlsInputMeta();
    onMultiProviderChange();
    onMultiModeChange();
}

async function checkWord() {
    const word = document.getElementById('wordInput').value.trim();
    
    if (!word) {
        alert('Введите слово для проверки!');
        return;
    }
    
    if (word.length < 2) {
        alert('Слово должно содержать минимум 2 символа!');
        return;
    }
    
    showLoading();
    
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
            displayWordResult(data.result);
            console.log('✅ Слово проверено:', data.result);
        } else {
            alert('Ошибка: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        alert('Ошибка проверки: ' + error.message);
    }
}

// Отображение результата проверки слова
function displayWordResult(result) {
    const resultsCard = document.getElementById('wordResults');
    const resultsContent = document.getElementById('wordResultsContent');
    
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
                    <p>Расшифровка: ${result.abbreviation_translation.join(', ')}</p>
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
            <div class="word-value">"${result.word}"</div>
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
                    <div class="word-list">
                        ${result.nenormative_words.slice(0, 20).map(w => {
                            const censored = w[0] + '*'.repeat(w.length - 2) + w[w.length - 1];
                            return `<span class="word-tag critical">${censored}</span>`;
                        }).join('')}
                    </div>
                    ${result.nenormative_words.length > 20 ? `<p class="more-words">... и ещё ${result.nenormative_words.length - 20} слов</p>` : ''}
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
                    <div class="word-list">
                        ${result.latin_words.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.latin_words.length > 30 ? `<p class="more-words">... и ещё ${result.latin_words.length - 30} слов</p>` : ''}
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
                    <div class="word-list">
                        ${result.unknown_cyrillic.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.unknown_cyrillic.length > 30 ? `<p class="more-words">... и ещё ${result.unknown_cyrillic.length - 30} слов</p>` : ''}
                </div>
            `;
        }
        
        html += '</div>';
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
                    <span class="stat-number">${result.law_compliant ? '100%' : Math.round(((result.total_words - result.violations_count) / result.total_words) * 100) + '%'}</span>
                    <span class="stat-label">Соответствие</span>
                </div>
            </div>
            ${url ? `<p class="url-info"><strong>URL:</strong> <a href="${url}" target="_blank">${url}</a></p>` : ''}
        </div>
    `;
    
    // Рекомендации
    if (result.recommendations && result.recommendations.length > 0) {
        html += `
            <div class="recommendations">
                <h4>💡 Рекомендации</h4>
                <div class="recommendations-list">
                    ${result.recommendations.map(rec => `
                        <div class="recommendation ${rec.level}">
                            <div class="rec-icon">${rec.icon}</div>
                            <div class="rec-content">
                                <h5>${rec.title}</h5>
                                <p>${rec.message}</p>
                                ${rec.action ? `<p class="rec-action">→ ${rec.action}</p>` : ''}
                            </div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
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
                            <div class="word-list">
                                ${Array.from(allNenormativeWords).slice(0, 20).map(w => {
                                    const censored = w[0] + '*'.repeat(Math.max(0, w.length - 2)) + w.slice(-1);
                                    return `<span class="word-tag critical">${censored}</span>`;
                                }).join('')}
                                ${allNenormativeWords.size > 20 ? `<span class="more-words">... и ещё ${allNenormativeWords.size - 20}</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    ${allLatinWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>🌍 Латиница (${allLatinWords.size})</h5>
                            <div class="word-list">
                                ${Array.from(allLatinWords).slice(0, 30).map(w => 
                                    `<span class="word-tag">${w}</span>`
                                ).join('')}
                                ${allLatinWords.size > 30 ? `<span class="more-words">... и ещё ${allLatinWords.size - 30}</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    ${allUnknownWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>❓ Англицизмы / Неизвестные (${allUnknownWords.size})</h5>
                            <div class="word-list">
                                ${Array.from(allUnknownWords).slice(0, 30).map(w => 
                                    `<span class="word-tag">${w}</span>`
                                ).join('')}
                                ${allUnknownWords.size > 30 ? `<span class="more-words">... и ещё ${allUnknownWords.size - 30}</span>` : ''}
                            </div>
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
                    <a href="${item.url}" target="_blank" class="batch-url">${item.url}</a>
                    ${hasDetails ? `
                        <button class="batch-details-btn" id="batch-btn-${index}" onclick="toggleBatchDetails(${index})">
                            Показать детали
                        </button>
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
                ` : `<div class="batch-item-error">Ошибка: ${item.error}</div>`}
                
                ${hasDetails ? `
                    <div class="batch-details" id="batch-details-${index}" style="display: none;">
                        ${item.result.nenormative_words?.length > 0 ? `
                            <div class="batch-detail-section critical">
                                <h6>🚫 Ненормативная лексика:</h6>
                                <div class="word-list">
                                    ${item.result.nenormative_words.slice(0, 15).map(w => {
                                        const censored = w[0] + '*'.repeat(Math.max(0, w.length - 2)) + w.slice(-1);
                                        return `<span class="word-tag critical">${censored}</span>`;
                                    }).join('')}
                                    ${item.result.nenormative_words.length > 15 ? `<span class="more-words">... и ещё ${item.result.nenormative_words.length - 15}</span>` : ''}
                                </div>
                            </div>
                        ` : ''}
                        ${item.result.latin_words?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>🌍 Латиница:</h6>
                                <div class="word-list">
                                    ${item.result.latin_words.slice(0, 20).map(w => 
                                        `<span class="word-tag">${w}</span>`
                                    ).join('')}
                                    ${item.result.latin_words.length > 20 ? `<span class="more-words">... и ещё ${item.result.latin_words.length - 20}</span>` : ''}
                                </div>
                            </div>
                        ` : ''}
                        ${item.result.unknown_cyrillic?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>❓ Англицизмы / Неизвестные:</h6>
                                <div class="word-list">
                                    ${item.result.unknown_cyrillic.slice(0, 20).map(w => 
                                        `<span class="word-tag">${w}</span>`
                                    ).join('')}
                                    ${item.result.unknown_cyrillic.length > 20 ? `<span class="more-words">... и ещё ${item.result.unknown_cyrillic.length - 20}</span>` : ''}
                                </div>
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
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Экспорт отчета
async function exportReport(type) {
    const result = currentResults[type];
    if (!result) {
        alert('Нет данных для экспорта! Сначала выполните проверку.');
        return;
    }
    
    try {
        showLoading();
        console.log('📥 Экспорт отчета:', type, result);
        
        // Для пакетной проверки используем специальный endpoint
        const isBatch = type === 'batch';
        const endpoint = isBatch ? '/api/export/batch-txt' : '/api/export/txt';
        const payload = isBatch ? { results: result } : { result };
        
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
        const prefix = isBatch ? 'lawcheck_batch_' : 'lawcheck_';
        a.download = `${prefix}${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        console.log('✅ Отчет скачан');
        
    } catch (error) {
        console.error('❌ Ошибка экспорта:', error);
        alert('Ошибка экспорта: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Глубокая проверка слов
async function deepCheck(type) {
    const result = currentResults[type];
    if (!result) {
        alert('Нет данных для проверки! Сначала выполните проверку.');
        return;
    }

    const wordsToCheck = [
        ...(result.latin_words || []),
        ...(result.unknown_cyrillic || [])
    ];

    if (wordsToCheck.length === 0) {
        alert('Нет слов для глубокой проверки!');
        return;
    }

    // Ограничиваем количество слов для одного запроса
    const maxWords = 200;
    const wordsToProcess = wordsToCheck.slice(0, maxWords);
    const skippedCount = wordsToCheck.length - maxWords;

    showLoading();
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
            displayDeepResults(type, data.results);
            if (skippedCount > 0) {
                alert(`Показаны результаты для первых ${maxWords} слов. Ещё ${skippedCount} слов пропущено.`);
            }
            console.log('✅ Глубокая проверка завершена:', data.results.length, 'слов');
        } else {
            alert('Ошибка: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        alert('Ошибка глубокой проверки: ' + error.message);
    }
}

// Глубокая проверка для пакетного режима
async function deepCheckBatch() {
    const results = currentResults.batch;
    if (!results || !Array.isArray(results)) {
        alert('Нет данных для проверки! Сначала выполните пакетную проверку.');
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
        alert('Нет слов для глубокой проверки!');
        return;
    }

    const wordArray = Array.from(allWords);
    const batchSize = 100; // Обрабатываем по 100 слов за раз
    const totalBatches = Math.ceil(wordArray.length / batchSize);

    showLoading();
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
            displayBatchDeepResults(results, allDeepResults, urlMap);
            console.log('✅ Глубокая проверка batch завершена:', allDeepResults.length, 'слов');
        } else {
            alert('Не удалось получить результаты глубокой проверки');
        }

    } catch (error) {
        hideLoading();
        console.error('❌ Ошибка глубокой проверки:', error);
        alert('Ошибка глубокой проверки: ' + error.message);
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
                <h4><a href="${r.url}" target="_blank" class="batch-url">${r.url}</a></h4>
        `;

        if (r.abbreviations.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">📚 Аббревиатуры:</span>
                    <div class="word-list">
                        ${r.abbreviations.map(dr => `
                            <span class="word-tag abbr">
                                ${dr.word}
                                <span class="word-translation">→ ${dr.suggestions?.join(', ') || 'перевод неизвестен'}</span>
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        if (r.validated.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">✅ Подтверждено:</span>
                    <div class="word-list">
                        ${r.validated.map(dr => `
                            <span class="word-tag valid">
                                ${dr.word}
                                ${dr.normal_form ? `<span class="word-reason">(${dr.normal_form})</span>` : ''}
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        if (r.invalid.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">❌ Требуют замены:</span>
                    <div class="word-list">
                        ${r.invalid.map(dr => `
                            <span class="word-tag invalid">
                                ${dr.word}
                                ${dr.suggestions?.length > 0 ? `<span class="word-suggestions">→ ${dr.suggestions.join(', ')}</span>` : ''}
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        html += `</div>`;
    });

    html += '</div>';

    resultsContent.innerHTML += html;
    resultsContent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Отображение результатов глубокой проверки
function displayDeepResults(type, results) {
    const resultsContent = document.getElementById(`${type}ResultsContent`);

    const abbreviations = results.filter(r => r.reasons.includes('abbreviation'));
    const otherValid = results.filter(r => r.is_valid && !r.reasons.includes('abbreviation'));
    const invalidWords = results.filter(r => !r.is_valid);

    let html = `
        <div class="deep-check-results">
            <h3>🔬 Результаты глубокой проверки</h3>
            <div class="deep-summary">
                <span class="deep-valid">✅ Подтверждено: ${otherValid.length}</span>
                <span class="deep-abbr">📚 ABBR: ${abbreviations.length}</span>
                <span class="deep-invalid">❌ Неизвестно: ${invalidWords.length}</span>
            </div>
    `;

    if (abbreviations.length > 0) {
        html += `
            <div class="deep-section abbreviation">
                <h4>📚 Аббревиатуры (требуется перевод)</h4>
                <div class="word-list">
                    ${abbreviations.map(r => `
                        <span class="word-tag abbr">
                            ${r.word}
                            <span class="word-translation" title="${r.reasons.join(', ')}">
                                → ${r.suggestions?.join(', ') || 'перевод неизвестен'}
                            </span>
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    }

    if (otherValid.length > 0) {
        html += `
            <div class="deep-section valid">
                <h4>✅ Слова, подтверждённые при глубокой проверке</h4>
                <div class="word-list">
                    ${otherValid.map(r => `
                        <span class="word-tag valid">
                            ${r.word}
                            <span class="word-reason" title="${r.reasons.join(', ')}">
                                ${r.normal_form ? `(${r.normal_form})` : ''}
                            </span>
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    }

    if (invalidWords.length > 0) {
        html += `
            <div class="deep-section invalid">
                <h4>❓ Слова, не подтверждённые (требуют замены)</h4>
                <div class="word-list">
                    ${invalidWords.map(r => `
                        <span class="word-tag invalid">
                            ${r.word}
                            ${r.suggestions?.length > 0 ?
                                `<span class="word-suggestions">→ ${r.suggestions.join(', ')}</span>` : ''}
                        </span>
                    `).join('')}
                </div>
            </div>
        `;
    }

    html += '</div>';

    resultsContent.innerHTML += html;
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
function clearText() {
    document.getElementById('textInput').value = '';
    document.getElementById('textResults').style.display = 'none';
    currentResults.text = null;
    updateTextInputMeta();
}

function loadSample() {
    document.getElementById('textInput').value = `Пример текста для проверки закона о русском языке.

Этот сервис проверяет тексты на соответствие федеральному закону №168-ФЗ. 
Он находит слова на латинице, англицизмы и ненормативную лексику.

Попробуйте добавить english words или специальные термины для проверки!`;
    updateTextInputMeta();
}

async function copyExtractedImageText() {
    const input = document.getElementById('imagesInput');
    if (!input || !input.value.trim()) {
        alert('No extracted text to copy');
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
    updateImagesInputMeta();
    updateImagesBatchInputMeta();
}

function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    document.querySelectorAll('.btn').forEach(btn => {
        btn.disabled = true;
    });
    if (overlay) {
        overlay.style.display = 'flex';
    }
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

// Горячие клавиши
document.addEventListener('keydown', (e) => {
    if (!(e.ctrlKey && e.key === 'Enter')) return;

    const activeTab = getActiveTabName();
    if (activeTab === 'text') return checkText();
    if (activeTab === 'url') return checkUrl();
    if (activeTab === 'batch') return checkBatch();
    if (activeTab === 'word') return checkWord();
    if (activeTab === 'images') return checkExtractedImageText();
});
