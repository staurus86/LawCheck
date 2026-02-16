// API Configuration
const API_BASE = window.API_BASE_URL || 'http://localhost:5000';
console.log('рџ”— Using API:', API_BASE);

// Global variables
let currentResults = {
    text: null,
    url: null,
    batch: null,
    images: null
};

// РРЅРёС†РёР°Р»РёР·Р°С†РёСЏ РїСЂРё Р·Р°РіСЂСѓР·РєРµ СЃС‚СЂР°РЅРёС†С‹
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadStats();
    onImagesProviderChange();
    loadImageTokenStatus();
    console.log('вњ… LawChecker Online Р·Р°РіСЂСѓР¶РµРЅ');
});

// РџРµСЂРµРєР»СЋС‡РµРЅРёРµ РІРєР»Р°РґРѕРє
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            
            // РЈРґР°Р»СЏРµРј Р°РєС‚РёРІРЅС‹Рµ РєР»Р°СЃСЃС‹
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Р”РѕР±Р°РІР»СЏРµРј Р°РєС‚РёРІРЅС‹Рµ РєР»Р°СЃСЃС‹
            btn.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Р—Р°РіСЂСѓР·РєР° СЃС‚Р°С‚РёСЃС‚РёРєРё СЃР»РѕРІР°СЂРµР№
async function loadStats() {
    try {
        const response = await fetch(`${API_BASE}/api/stats`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        // Р‘РµР·РѕРїР°СЃРЅРѕРµ РѕР±РЅРѕРІР»РµРЅРёРµ СЃ РїСЂРѕРІРµСЂРєР°РјРё
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
        // РџРѕРєР°Р·С‹РІР°РµРј "0" РІРјРµСЃС‚Рѕ РѕС€РёР±РєРё
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

// РџСЂРѕРІРµСЂРєР° С‚РµРєСЃС‚Р°
async function checkText() {
    const text = document.getElementById('textInput').value.trim();
    
    if (!text) {
        alert('Р’РІРµРґРёС‚Рµ С‚РµРєСЃС‚ РґР»СЏ РїСЂРѕРІРµСЂРєРё!');
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
            console.log('вњ… РўРµРєСЃС‚ РїСЂРѕРІРµСЂРµРЅ:', data.result);
        } else {
            alert('РћС€РёР±РєР°: ' + data.error);
        }
    } catch (error) {
        alert('РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё: ' + error.message);
    } finally {
        hideLoading();
    }
}

// РџСЂРѕРІРµСЂРєР° URL
async function checkUrl() {
    const url = document.getElementById('urlInput').value.trim();
    
    if (!url || !url.startsWith('http')) {
        alert('Р’РІРµРґРёС‚Рµ РєРѕСЂСЂРµРєС‚РЅС‹Р№ URL!');
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
            console.log('вњ… URL РїСЂРѕРІРµСЂРµРЅ:', data.result);
        } else {
            alert('РћС€РёР±РєР°: ' + data.error);
        }
    } catch (error) {
        alert('РћС€РёР±РєР° Р·Р°РіСЂСѓР·РєРё: ' + error.message);
    } finally {
        hideLoading();
        document.getElementById('urlProgress').style.display = 'none';
    }
}

// РџР°РєРµС‚РЅР°СЏ РїСЂРѕРІРµСЂРєР°
async function checkBatch() {
    const input = document.getElementById('batchInput').value.trim();
    const urls = input.split('\n').filter(u => u.trim() && u.startsWith('http'));
    
    if (urls.length === 0) {
        alert('Р’РІРµРґРёС‚Рµ С…РѕС‚СЏ Р±С‹ РѕРґРёРЅ URL!');
        return;
    }
    
    const progressBar = document.getElementById('batchProgress');
    const progressFill = document.getElementById('batchProgressBar');
    const progressText = document.getElementById('batchProgressText');
    
    progressBar.style.display = 'block';
    progressFill.style.width = '0%';
    progressFill.style.animation = 'none';
    
    const results = [];
    let completed = 0;
    
    for (const url of urls) {
        progressText.textContent = `${completed} / ${urls.length}`;
        
        try {
            const response = await fetch(`${API_BASE}/api/check-url`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ url })
            });
            
            const data = await response.json();
            results.push({
                url,
                success: data.success,
                result: data.result,
                error: data.error
            });
        } catch (error) {
            results.push({
                url,
                success: false,
                error: error.message
            });
        }
        
        completed++;
        progressFill.style.width = `${(completed / urls.length) * 100}%`;
    }
    
    progressText.textContent = `${completed} / ${urls.length}`;
    currentResults.batch = results;
    displayBatchResults(results);
    console.log('вњ… РџР°РєРµС‚РЅР°СЏ РїСЂРѕРІРµСЂРєР° Р·Р°РІРµСЂС€РµРЅР°:', results);
}

// РџСЂРѕРІРµСЂРєР° РѕРґРЅРѕРіРѕ СЃР»РѕРІР°
function getImagesProvider() {
    const el = document.getElementById('imagesProviderSelect');
    return el ? el.value : 'openai';
}

function getDefaultModelByProvider(provider) {
    if (provider === 'google') return 'DOCUMENT_TEXT_DETECTION';
    if (provider === 'ocrspace') return 'rus';
    return 'gpt-4.1-mini';
}

function onImagesProviderChange() {
    const provider = getImagesProvider();
    const modelInput = document.getElementById('imagesModelInput');
    if (modelInput && !modelInput.value.trim()) {
        modelInput.value = getDefaultModelByProvider(provider);
    }
    loadImageTokenStatus();
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
            statusEl.textContent = `Ключ для ${provider}: ${data.token_masked || 'сохранен'}`;
            statusEl.className = 'images-token-status success';
        } else {
            statusEl.textContent = `Ключ для ${provider} не задан`;
            statusEl.className = 'images-token-status';
        }
    } catch (error) {
        statusEl.textContent = 'Не удалось проверить статус ключа';
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
        alert('Введите API ключ');
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
        if (!data.success) throw new Error(data.error || 'Не удалось сохранить ключ');

        statusEl.textContent = `Ключ для ${provider} сохранен: ${data.token_masked || ''}`;
        statusEl.className = 'images-token-status success';
        input.value = '';
    } catch (error) {
        statusEl.textContent = `Ошибка: ${error.message}`;
        statusEl.className = 'images-token-status error';
    }
}

function fileToDataUrl(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('Ошибка чтения файла'));
        reader.readAsDataURL(file);
    });
}

async function checkImagesByDatabase() {
    const provider = getImagesProvider();
    const modelInput = document.getElementById('imagesModelInput');
    const imageUrlInput = document.getElementById('imagesUrlInput');
    const imageFileInput = document.getElementById('imagesFileInput');
    const extractedTextArea = document.getElementById('imagesInput');

    const model = modelInput && modelInput.value.trim()
        ? modelInput.value.trim()
        : getDefaultModelByProvider(provider);
    const imageUrl = imageUrlInput ? imageUrlInput.value.trim() : '';
    const imageFile = imageFileInput && imageFileInput.files ? imageFileInput.files[0] : null;

    if (!imageUrl && !imageFile) {
        alert('Укажите URL картинки или загрузите файл');
        return;
    }

    let imageDataUrl = '';
    if (imageFile) {
        imageDataUrl = await fileToDataUrl(imageFile);
    }

    showLoading();
    try {
        const response = await fetch(`${API_BASE}/api/images/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({
                provider,
                model,
                image_url: imageUrl || null,
                image_data_url: imageDataUrl || null
            })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка OCR');

        currentResults.images = data.result;
        if (extractedTextArea) extractedTextArea.value = data.result.extracted_text || '';

        displayResults('images', data.result, data.result.source_url || '');

        const resultsContent = document.getElementById('imagesResultsContent');
        if (resultsContent && data.result.ocr) {
            const ocr = data.result.ocr;
            resultsContent.innerHTML += `
                <div class="image-db-summary">
                    <h4>OCR провайдер: ${ocr.provider}</h4>
                    <p>Модель: ${ocr.model || '-'} | Длина текста: ${ocr.text_length || 0} символов</p>
                </div>
            `;
        }
    } catch (error) {
        alert('Ошибка проверки картинки: ' + error.message);
    } finally {
        hideLoading();
    }
}
async function checkWord() {
    const word = document.getElementById('wordInput').value.trim();
    
    if (!word) {
        alert('Р’РІРµРґРёС‚Рµ СЃР»РѕРІРѕ РґР»СЏ РїСЂРѕРІРµСЂРєРё!');
        return;
    }
    
    if (word.length < 2) {
        alert('РЎР»РѕРІРѕ РґРѕР»Р¶РЅРѕ СЃРѕРґРµСЂР¶Р°С‚СЊ РјРёРЅРёРјСѓРј 2 СЃРёРјРІРѕР»Р°!');
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
            console.log('вњ… РЎР»РѕРІРѕ РїСЂРѕРІРµСЂРµРЅРѕ:', data.result);
        } else {
            alert('РћС€РёР±РєР°: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        alert('РћС€РёР±РєР° РїСЂРѕРІРµСЂРєРё: ' + error.message);
    }
}

// РћС‚РѕР±СЂР°Р¶РµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚Р° РїСЂРѕРІРµСЂРєРё СЃР»РѕРІР°
function displayWordResult(result) {
    const resultsCard = document.getElementById('wordResults');
    const resultsContent = document.getElementById('wordResultsContent');
    
    let html = '';
    
    if (result.is_nenormative) {
        html += `
            <div class="result-status error">
                <div class="status-icon">рџљ«</div>
                <div class="status-text">
                    <h3>РћРџРђРЎРќРћР• РЎР›РћР’Рћ - РќР•РќРћР РњРђРўРР’РќРђРЇ Р›Р•РљРЎРРљРђ</h3>
                    <p>Р”Р°РЅРЅРѕРµ СЃР»РѕРІРѕ Р·Р°РїСЂРµС‰РµРЅРѕ Рє РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЋ. Р­С‚Рѕ РєСЂРёС‚РёС‡РµСЃРєРѕРµ РЅР°СЂСѓС€РµРЅРёРµ Р·Р°РєРѕРЅР°.</p>
                </div>
            </div>
        `;
    } else if (result.is_potential_fine) {
        html += `
            <div class="result-status warning">
                <div class="status-icon">вљ пёЏ</div>
                <div class="status-text">
                    <h3>РџРћРўР•РќР¦РРђР›Р¬РќРђРЇ РЈР“Р РћР—Рђ РЁРўР РђР¤Рђ</h3>
                    <p>РЎР»РѕРІРѕ РЅРµ РЅР°Р№РґРµРЅРѕ РІ Р±Р°Р·Рµ РЅРѕСЂРјР°С‚РёРІРЅС‹С… СЃР»РѕРІ. РСЃРїРѕР»СЊР·РѕРІР°РЅРёРµ РјРѕР¶РµС‚ РїРѕРІР»РµС‡СЊ С€С‚СЂР°С„ РґРѕ 500 000 СЂСѓР±Р»РµР№.</p>
                </div>
            </div>
        `;
    } else if (result.is_foreign) {
        html += `
            <div class="result-status warning">
                <div class="status-icon">рџЊЌ</div>
                <div class="status-text">
                    <h3>РРќРћРЎРўР РђРќРќРћР• РЎР›РћР’Рћ</h3>
                    <p>РЎР»РѕРІРѕ СЂР°Р·СЂРµС€РµРЅРѕ Рє РёСЃРїРѕР»СЊР·РѕРІР°РЅРёСЋ РІ РѕРїСЂРµРґРµР»С‘РЅРЅС‹С… РєРѕРЅС‚РµРєСЃС‚Р°С….</p>
                </div>
            </div>
        `;
    } else if (result.is_abbreviation) {
        html += `
            <div class="result-status success">
                <div class="status-icon">рџ“љ</div>
                <div class="status-text">
                    <h3>РђР‘Р‘Р Р•Р’РРђРўРЈР Рђ</h3>
                    <p>Р Р°СЃС€РёС„СЂРѕРІРєР°: ${result.abbreviation_translation.join(', ')}</p>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="result-status success">
                <div class="status-icon">вњ…</div>
                <div class="status-text">
                    <h3>РќРћР РњРђРўРР’РќРћР• РЎР›РћР’Рћ</h3>
                    <p>РЎР»РѕРІРѕ СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ С‚СЂРµР±РѕРІР°РЅРёСЏРј Р·Р°РєРѕРЅР°.</p>
                </div>
            </div>
        `;
    }
    
    html += `
        <div class="word-detail">
            <div class="word-label">РџСЂРѕРІРµСЂСЏРµРјРѕРµ СЃР»РѕРІРѕ:</div>
            <div class="word-value">"${result.word}"</div>
        </div>
    `;
    
    if (result.has_latin) {
        html += `
            <div class="word-detail">
                <div class="word-label">РЎРѕРґРµСЂР¶РёС‚ Р»Р°С‚РёРЅРёС†Сѓ:</div>
                <div class="word-value">Р”Р°</div>
            </div>
        `;
    }
    
    html += `
        <div class="word-detail">
            <div class="word-label">Р’ Р±Р°Р·Рµ РЅРѕСЂРјР°С‚РёРІРЅС‹С…:</div>
            <div class="word-value ${result.is_normative ? 'text-success' : 'text-danger'}">
                ${result.is_normative ? 'вњ… Р”Р°' : 'вќЊ РќРµС‚'}
            </div>
        </div>
        <div class="word-detail">
            <div class="word-label">Р’ Р±Р°Р·Рµ РёРЅРѕСЃС‚СЂР°РЅРЅС‹С…:</div>
            <div class="word-value ${result.is_foreign ? 'text-warning' : ''}">
                ${result.is_foreign ? 'вњ… Р”Р°' : 'вќЊ РќРµС‚'}
            </div>
        </div>
        <div class="word-detail">
            <div class="word-label">Р’ Р±Р°Р·Рµ РЅРµРЅРѕСЂРјР°С‚РёРІРЅС‹С…:</div>
            <div class="word-value ${result.is_nenormative ? 'text-danger' : 'text-success'}">
                ${result.is_nenormative ? 'рџљ« Р”Р° (Р—РђРџР Р•Р©Р•РќРћ)' : 'вњ… РќРµС‚'}
            </div>
        </div>
    `;
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// РћС‚РѕР±СЂР°Р¶РµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РїСЂРѕРІРµСЂРєРё
function displayResults(type, result, url = '') {
    const resultsCard = document.getElementById(`${type}Results`);
    const resultsContent = document.getElementById(`${type}ResultsContent`);
    
    let html = '';
    
    // РЎС‚Р°С‚СѓСЃ РїСЂРѕРІРµСЂРєРё
    if (result.law_compliant) {
        html += `
            <div class="result-status success">
                <div class="status-icon">вњ…</div>
                <div class="status-text">
                    <h3>РўР•РљРЎРў РЎРћРћРўР’Р•РўРЎРўР’РЈР•Рў РўР Р•Р‘РћР’РђРќРРЇРњ Р—РђРљРћРќРђ</h3>
                    <p>РќР°СЂСѓС€РµРЅРёР№ РЅРµ РѕР±РЅР°СЂСѓР¶РµРЅРѕ. РўРµРєСЃС‚ РјРѕР¶РЅРѕ РїСѓР±Р»РёРєРѕРІР°С‚СЊ.</p>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="result-status error">
                <div class="status-icon">вљ пёЏ</div>
                <div class="status-text">
                    <h3>РћР‘РќРђР РЈР–Р•РќРћ РќРђР РЈРЁР•РќРР™: ${result.violations_count}</h3>
                    <p>РўСЂРµР±СѓРµС‚СЃСЏ РёСЃРїСЂР°РІР»РµРЅРёРµ РїРµСЂРµРґ РїСѓР±Р»РёРєР°С†РёРµР№</p>
                </div>
            </div>
        `;
        
        // Р‘Р»РѕРє РЅР°СЂСѓС€РµРЅРёР№
        html += '<div class="violations-list">';
        
        // РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°
        if (result.nenormative_count > 0) {
            html += `
                <div class="violation-section critical">
                    <div class="violation-header">
                        <span class="violation-icon">рџљ«</span>
                        <h3>РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°: ${result.nenormative_count}</h3>
                    </div>
                    <div class="word-list">
                        ${result.nenormative_words.slice(0, 20).map(w => {
                            const censored = w[0] + '*'.repeat(w.length - 2) + w[w.length - 1];
                            return `<span class="word-tag critical">${censored}</span>`;
                        }).join('')}
                    </div>
                    ${result.nenormative_words.length > 20 ? `<p class="more-words">... Рё РµС‰С‘ ${result.nenormative_words.length - 20} СЃР»РѕРІ</p>` : ''}
                </div>
            `;
        }
        
        // РЎР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ
        if (result.latin_count > 0) {
            html += `
                <div class="violation-section">
                    <div class="violation-header">
                        <span class="violation-icon">рџЊЌ</span>
                        <h3>РЎР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ: ${result.latin_count}</h3>
                    </div>
                    <div class="word-list">
                        ${result.latin_words.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.latin_words.length > 30 ? `<p class="more-words">... Рё РµС‰С‘ ${result.latin_words.length - 30} СЃР»РѕРІ</p>` : ''}
                </div>
            `;
        }
        
        // РќРµРёР·РІРµСЃС‚РЅС‹Рµ СЃР»РѕРІР°/Р°РЅРіР»РёС†РёР·РјС‹
        if (result.unknown_count > 0) {
            html += `
                <div class="violation-section">
                    <div class="violation-header">
                        <span class="violation-icon">вќ“</span>
                        <h3>РђРЅРіР»РёС†РёР·РјС‹ / РќРµРёР·РІРµСЃС‚РЅС‹Рµ СЃР»РѕРІР°: ${result.unknown_count}</h3>
                    </div>
                    <div class="word-list">
                        ${result.unknown_cyrillic.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.unknown_cyrillic.length > 30 ? `<p class="more-words">... Рё РµС‰С‘ ${result.unknown_cyrillic.length - 30} СЃР»РѕРІ</p>` : ''}
                </div>
            `;
        }
        
        html += '</div>';
    }
    
    // РЎС‚Р°С‚РёСЃС‚РёРєР°
    html += `
        <div class="stats-summary">
            <h4>рџ“Љ РЎС‚Р°С‚РёСЃС‚РёРєР° РїСЂРѕРІРµСЂРєРё</h4>
            <div class="stats-grid">
                <div class="stat-item">
                    <span class="stat-number">${result.total_words.toLocaleString('ru-RU')}</span>
                    <span class="stat-label">Р’СЃРµРіРѕ СЃР»РѕРІ</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">${result.unique_words.toLocaleString('ru-RU')}</span>
                    <span class="stat-label">РЈРЅРёРєР°Р»СЊРЅС‹С…</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">${result.violations_count}</span>
                    <span class="stat-label">РќР°СЂСѓС€РµРЅРёР№</span>
                </div>
                <div class="stat-item">
                    <span class="stat-number">${result.law_compliant ? '100%' : Math.round(((result.total_words - result.violations_count) / result.total_words) * 100) + '%'}</span>
                    <span class="stat-label">РЎРѕРѕС‚РІРµС‚СЃС‚РІРёРµ</span>
                </div>
            </div>
            ${url ? `<p class="url-info"><strong>URL:</strong> <a href="${url}" target="_blank">${url}</a></p>` : ''}
        </div>
    `;
    
    // Р РµРєРѕРјРµРЅРґР°С†РёРё
    if (result.recommendations && result.recommendations.length > 0) {
        html += `
            <div class="recommendations">
                <h4>рџ’Ў Р РµРєРѕРјРµРЅРґР°С†РёРё</h4>
                <div class="recommendations-list">
                    ${result.recommendations.map(rec => `
                        <div class="recommendation ${rec.level}">
                            <div class="rec-icon">${rec.icon}</div>
                            <div class="rec-content">
                                <h5>${rec.title}</h5>
                                <p>${rec.message}</p>
                                ${rec.action ? `<p class="rec-action">в†’ ${rec.action}</p>` : ''}
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

// РћС‚РѕР±СЂР°Р¶РµРЅРёРµ РїР°РєРµС‚РЅС‹С… СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ СЃ РґРµС‚Р°Р»РёР·Р°С†РёРµР№ РЅР°СЂСѓС€РµРЅРёР№
function displayBatchResults(results) {
    const resultsCard = document.getElementById('batchResults');
    const resultsContent = document.getElementById('batchResultsContent');
    
    let totalViolations = 0;
    let critical = 0;
    let successful = 0;
    
    // РЎРѕР±РёСЂР°РµРј СѓРЅРёРєР°Р»СЊРЅС‹Рµ СЃР»РѕРІР° РїРѕ РІСЃРµРј СЃР°Р№С‚Р°Рј
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
                // РЎРѕР±РёСЂР°РµРј СЃР»РѕРІР°
                (item.result.latin_words || []).forEach(w => allLatinWords.add(w));
                (item.result.unknown_cyrillic || []).forEach(w => allUnknownWords.add(w));
                (item.result.nenormative_words || []).forEach(w => allNenormativeWords.add(w));
            }
        }
    });
    
    let html = `
        <div class="batch-summary">
            <div class="summary-header">
                <h3>рџ“Љ Р РµР·СѓР»СЊС‚Р°С‚С‹ РїР°РєРµС‚РЅРѕР№ РїСЂРѕРІРµСЂРєРё</h3>
                <p>РџСЂРѕРІРµСЂРµРЅРѕ СЃР°Р№С‚РѕРІ: ${results.length}</p>
            </div>
            <div class="summary-stats">
                <div class="summary-item success">
                    <span class="summary-number">${successful - totalViolations}</span>
                    <span class="summary-label">Р‘РµР· РЅР°СЂСѓС€РµРЅРёР№</span>
                </div>
                <div class="summary-item warning">
                    <span class="summary-number">${totalViolations}</span>
                    <span class="summary-label">РЎ РЅР°СЂСѓС€РµРЅРёСЏРјРё</span>
                </div>
                ${critical > 0 ? `
                    <div class="summary-item critical">
                        <span class="summary-number">${critical}</span>
                        <span class="summary-label">РљСЂРёС‚РёС‡РµСЃРєРёС…</span>
                    </div>
                ` : ''}
            </div>
        </div>
    `;
    
    // РЎРІРѕРґРєР° СѓРЅРёРєР°Р»СЊРЅС‹С… РЅР°СЂСѓС€РµРЅРёР№ РїРѕ РІСЃРµРј СЃР°Р№С‚Р°Рј
    if (allLatinWords.size > 0 || allUnknownWords.size > 0 || allNenormativeWords.size > 0) {
        html += `
            <div class="batch-global-violations">
                <h4>рџЊЌ РЈРЅРёРєР°Р»СЊРЅС‹Рµ РЅР°СЂСѓС€РµРЅРёСЏ РїРѕ РІСЃРµРј СЃР°Р№С‚Р°Рј</h4>
                <div class="batch-violations-summary">
                    ${allNenormativeWords.size > 0 ? `
                        <div class="batch-violation-category critical">
                            <h5>рџљ« РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР° (${allNenormativeWords.size})</h5>
                            <div class="word-list">
                                ${Array.from(allNenormativeWords).slice(0, 20).map(w => {
                                    const censored = w[0] + '*'.repeat(Math.max(0, w.length - 2)) + w.slice(-1);
                                    return `<span class="word-tag critical">${censored}</span>`;
                                }).join('')}
                                ${allNenormativeWords.size > 20 ? `<span class="more-words">... Рё РµС‰С‘ ${allNenormativeWords.size - 20}</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    ${allLatinWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>рџЊЌ Р›Р°С‚РёРЅРёС†Р° (${allLatinWords.size})</h5>
                            <div class="word-list">
                                ${Array.from(allLatinWords).slice(0, 30).map(w => 
                                    `<span class="word-tag">${w}</span>`
                                ).join('')}
                                ${allLatinWords.size > 30 ? `<span class="more-words">... Рё РµС‰С‘ ${allLatinWords.size - 30}</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    ${allUnknownWords.size > 0 ? `
                        <div class="batch-violation-category">
                            <h5>вќ“ РђРЅРіР»РёС†РёР·РјС‹ / РќРµРёР·РІРµСЃС‚РЅС‹Рµ (${allUnknownWords.size})</h5>
                            <div class="word-list">
                                ${Array.from(allUnknownWords).slice(0, 30).map(w => 
                                    `<span class="word-tag">${w}</span>`
                                ).join('')}
                                ${allUnknownWords.size > 30 ? `<span class="more-words">... Рё РµС‰С‘ ${allUnknownWords.size - 30}</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    html += '<div class="batch-results-list">';
    
    results.forEach((item, index) => {
        const statusIcon = !item.success ? 'вќЊ' : 
                          item.result.law_compliant ? 'вњ…' : 
                          item.result.nenormative_count > 0 ? 'рџљ«' : 'вљ пёЏ';
        
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
                            РџРѕРєР°Р·Р°С‚СЊ РґРµС‚Р°Р»Рё
                        </button>
                    ` : ''}
                </div>
                ${item.success ? `
                    <div class="batch-item-stats">
                        <span>РќР°СЂСѓС€РµРЅРёР№: ${item.result.violations_count}</span>
                        <span>Р›Р°С‚РёРЅРёС†Р°: ${item.result.latin_count}</span>
                        <span>РђРЅРіР»РёС†РёР·РјС‹: ${item.result.unknown_count}</span>
                        ${item.result.nenormative_count > 0 ? `<span class="critical-badge">РќРµРЅРѕСЂРјР°С‚РёРІ: ${item.result.nenormative_count}</span>` : ''}
                        <span class="batch-words-count">Р’СЃРµРіРѕ СЃР»РѕРІ: ${item.result.total_words || 0}</span>
                    </div>
                ` : `<div class="batch-item-error">РћС€РёР±РєР°: ${item.error}</div>`}
                
                ${hasDetails ? `
                    <div class="batch-details" id="batch-details-${index}" style="display: none;">
                        ${item.result.nenormative_words?.length > 0 ? `
                            <div class="batch-detail-section critical">
                                <h6>рџљ« РќРµРЅРѕСЂРјР°С‚РёРІРЅР°СЏ Р»РµРєСЃРёРєР°:</h6>
                                <div class="word-list">
                                    ${item.result.nenormative_words.slice(0, 15).map(w => {
                                        const censored = w[0] + '*'.repeat(Math.max(0, w.length - 2)) + w.slice(-1);
                                        return `<span class="word-tag critical">${censored}</span>`;
                                    }).join('')}
                                    ${item.result.nenormative_words.length > 15 ? `<span class="more-words">... Рё РµС‰С‘ ${item.result.nenormative_words.length - 15}</span>` : ''}
                                </div>
                            </div>
                        ` : ''}
                        ${item.result.latin_words?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>рџЊЌ Р›Р°С‚РёРЅРёС†Р°:</h6>
                                <div class="word-list">
                                    ${item.result.latin_words.slice(0, 20).map(w => 
                                        `<span class="word-tag">${w}</span>`
                                    ).join('')}
                                    ${item.result.latin_words.length > 20 ? `<span class="more-words">... Рё РµС‰С‘ ${item.result.latin_words.length - 20}</span>` : ''}
                                </div>
                            </div>
                        ` : ''}
                        ${item.result.unknown_cyrillic?.length > 0 ? `
                            <div class="batch-detail-section">
                                <h6>вќ“ РђРЅРіР»РёС†РёР·РјС‹ / РќРµРёР·РІРµСЃС‚РЅС‹Рµ:</h6>
                                <div class="word-list">
                                    ${item.result.unknown_cyrillic.slice(0, 20).map(w => 
                                        `<span class="word-tag">${w}</span>`
                                    ).join('')}
                                    ${item.result.unknown_cyrillic.length > 20 ? `<span class="more-words">... Рё РµС‰С‘ ${item.result.unknown_cyrillic.length - 20}</span>` : ''}
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

// Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р°
async function exportReport(type) {
    const result = currentResults[type];
    if (!result) {
        alert('РќРµС‚ РґР°РЅРЅС‹С… РґР»СЏ СЌРєСЃРїРѕСЂС‚Р°! РЎРЅР°С‡Р°Р»Р° РІС‹РїРѕР»РЅРёС‚Рµ РїСЂРѕРІРµСЂРєСѓ.');
        return;
    }
    
    try {
        showLoading();
        console.log('рџ“Ґ Р­РєСЃРїРѕСЂС‚ РѕС‚С‡РµС‚Р°:', type, result);
        
        // Р”Р»СЏ РїР°РєРµС‚РЅРѕР№ РїСЂРѕРІРµСЂРєРё РёСЃРїРѕР»СЊР·СѓРµРј СЃРїРµС†РёР°Р»СЊРЅС‹Р№ endpoint
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
        
        console.log('вњ… РћС‚С‡РµС‚ СЃРєР°С‡Р°РЅ');
        
    } catch (error) {
        console.error('вќЊ РћС€РёР±РєР° СЌРєСЃРїРѕСЂС‚Р°:', error);
        alert('РћС€РёР±РєР° СЌРєСЃРїРѕСЂС‚Р°: ' + error.message);
    } finally {
        hideLoading();
    }
}

// Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° СЃР»РѕРІ
async function deepCheck(type) {
    const result = currentResults[type];
    if (!result) {
        alert('РќРµС‚ РґР°РЅРЅС‹С… РґР»СЏ РїСЂРѕРІРµСЂРєРё! РЎРЅР°С‡Р°Р»Р° РІС‹РїРѕР»РЅРёС‚Рµ РїСЂРѕРІРµСЂРєСѓ.');
        return;
    }

    const wordsToCheck = [
        ...(result.latin_words || []),
        ...(result.unknown_cyrillic || [])
    ];

    if (wordsToCheck.length === 0) {
        alert('РќРµС‚ СЃР»РѕРІ РґР»СЏ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё!');
        return;
    }

    // РћРіСЂР°РЅРёС‡РёРІР°РµРј РєРѕР»РёС‡РµСЃС‚РІРѕ СЃР»РѕРІ РґР»СЏ РѕРґРЅРѕРіРѕ Р·Р°РїСЂРѕСЃР°
    const maxWords = 200;
    const wordsToProcess = wordsToCheck.slice(0, maxWords);
    const skippedCount = wordsToCheck.length - maxWords;

    showLoading();
    console.log('рџ”¬ Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР°:', wordsToProcess.length, 'СЃР»РѕРІ РёР·', wordsToCheck.length);

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
                alert(`РџРѕРєР°Р·Р°РЅС‹ СЂРµР·СѓР»СЊС‚Р°С‚С‹ РґР»СЏ РїРµСЂРІС‹С… ${maxWords} СЃР»РѕРІ. Р•С‰С‘ ${skippedCount} СЃР»РѕРІ РїСЂРѕРїСѓС‰РµРЅРѕ.`);
            }
            console.log('вњ… Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° Р·Р°РІРµСЂС€РµРЅР°:', data.results.length, 'СЃР»РѕРІ');
        } else {
            alert('РћС€РёР±РєР°: ' + data.error);
        }
    } catch (error) {
        hideLoading();
        alert('РћС€РёР±РєР° РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё: ' + error.message);
    }
}

// Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° РґР»СЏ РїР°РєРµС‚РЅРѕРіРѕ СЂРµР¶РёРјР°
async function deepCheckBatch() {
    const results = currentResults.batch;
    if (!results || !Array.isArray(results)) {
        alert('РќРµС‚ РґР°РЅРЅС‹С… РґР»СЏ РїСЂРѕРІРµСЂРєРё! РЎРЅР°С‡Р°Р»Р° РІС‹РїРѕР»РЅРёС‚Рµ РїР°РєРµС‚РЅСѓСЋ РїСЂРѕРІРµСЂРєСѓ.');
        return;
    }

    // РЎРѕР±РёСЂР°РµРј РІСЃРµ СѓРЅРёРєР°Р»СЊРЅС‹Рµ СЃР»РѕРІР° СЃРѕ РІСЃРµС… URL
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
        alert('РќРµС‚ СЃР»РѕРІ РґР»СЏ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё!');
        return;
    }

    const wordArray = Array.from(allWords);
    const batchSize = 100; // РћР±СЂР°Р±Р°С‚С‹РІР°РµРј РїРѕ 100 СЃР»РѕРІ Р·Р° СЂР°Р·
    const totalBatches = Math.ceil(wordArray.length / batchSize);

    showLoading();
    console.log('рџ”¬ Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° batch:', wordArray.length, 'СЃР»РѕРІ,', totalBatches, 'Р±Р°С‚С‡РµР№');

    try {
        const allDeepResults = [];
        let currentBatch = 0;

        while (currentBatch < totalBatches) {
            const start = currentBatch * batchSize;
            const end = start + batchSize;
            const batchWords = wordArray.slice(start, end);

            // РџРѕРєР°Р·С‹РІР°РµРј РїСЂРѕРіСЂРµСЃСЃ
            updateLoadingText(`РџСЂРѕРІРµСЂРєР° Р±Р°С‚С‡Р° ${currentBatch + 1}/${totalBatches} (${batchWords.length} СЃР»РѕРІ)...`);

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

        // РЎРєСЂС‹РІР°РµРј Р»РѕР°РґРµСЂ РїРµСЂРµРґ РїРѕРєР°Р·РѕРј СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ
        hideLoading();

        if (allDeepResults.length > 0) {
            displayBatchDeepResults(results, allDeepResults, urlMap);
            console.log('вњ… Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° batch Р·Р°РІРµСЂС€РµРЅР°:', allDeepResults.length, 'СЃР»РѕРІ');
        } else {
            alert('РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕР»СѓС‡РёС‚СЊ СЂРµР·СѓР»СЊС‚Р°С‚С‹ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё');
        }

    } catch (error) {
        hideLoading();
        console.error('вќЊ РћС€РёР±РєР° РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё:', error);
        alert('РћС€РёР±РєР° РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё: ' + error.message);
    }
}

function updateLoadingText(text) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        const p = overlay.querySelector('p');
        if (p) p.textContent = text;
    }
}

// РћС‚РѕР±СЂР°Р¶РµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё РґР»СЏ batch
function displayBatchDeepResults(results, deepResults, urlMap) {
    const resultsContent = document.getElementById('batchResultsContent');

    // РЎРѕР·РґР°РµРј СЃР»РѕРІР°СЂСЊ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ
    const resultMap = {};
    deepResults.forEach(r => {
        resultMap[r.word.toLowerCase()] = r;
    });

    // Р“СЂСѓРїРїРёСЂСѓРµРј РїРѕ URL
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

    // РЎС‡РёС‚Р°РµРј РѕР±С‰СѓСЋ СЃС‚Р°С‚РёСЃС‚РёРєСѓ
    const totalAbbr = urlResults.reduce((sum, r) => sum + r.abbreviations.length, 0);
    const totalValid = urlResults.reduce((sum, r) => sum + r.validated.length, 0);
    const totalInvalid = urlResults.reduce((sum, r) => sum + r.invalid.length, 0);

    let html = `
        <div class="deep-check-results">
            <h3>рџ”¬ Р“Р»СѓР±РѕРєР°СЏ РїСЂРѕРІРµСЂРєР° РІСЃРµС… URL</h3>
            <div class="deep-summary">
                <span class="deep-valid">вњ… РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ: ${totalValid}</span>
                <span class="deep-abbr">рџ“љ РђР±Р±СЂРµРІРёР°С‚СѓСЂС‹: ${totalAbbr}</span>
                <span class="deep-invalid">вќЊ РўСЂРµР±СѓСЋС‚ Р·Р°РјРµРЅС‹: ${totalInvalid}</span>
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
                    <span class="deep-label">рџ“љ РђР±Р±СЂРµРІРёР°С‚СѓСЂС‹:</span>
                    <div class="word-list">
                        ${r.abbreviations.map(dr => `
                            <span class="word-tag abbr">
                                ${dr.word}
                                <span class="word-translation">в†’ ${dr.suggestions?.join(', ') || 'РїРµСЂРµРІРѕРґ РЅРµРёР·РІРµСЃС‚РµРЅ'}</span>
                            </span>
                        `).join('')}
                    </div>
                </div>
            `;
        }

        if (r.validated.length > 0) {
            html += `
                <div class="deep-subsection">
                    <span class="deep-label">вњ… РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ:</span>
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
                    <span class="deep-label">вќЊ РўСЂРµР±СѓСЋС‚ Р·Р°РјРµРЅС‹:</span>
                    <div class="word-list">
                        ${r.invalid.map(dr => `
                            <span class="word-tag invalid">
                                ${dr.word}
                                ${dr.suggestions?.length > 0 ? `<span class="word-suggestions">в†’ ${dr.suggestions.join(', ')}</span>` : ''}
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

// РћС‚РѕР±СЂР°Р¶РµРЅРёРµ СЂРµР·СѓР»СЊС‚Р°С‚РѕРІ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё
function displayDeepResults(type, results) {
    const resultsContent = document.getElementById(`${type}ResultsContent`);

    const abbreviations = results.filter(r => r.reasons.includes('abbreviation'));
    const otherValid = results.filter(r => r.is_valid && !r.reasons.includes('abbreviation'));
    const invalidWords = results.filter(r => !r.is_valid);

    let html = `
        <div class="deep-check-results">
            <h3>рџ”¬ Р РµР·СѓР»СЊС‚Р°С‚С‹ РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРё</h3>
            <div class="deep-summary">
                <span class="deep-valid">вњ… РџРѕРґС‚РІРµСЂР¶РґРµРЅРѕ: ${otherValid.length}</span>
                <span class="deep-abbr">рџ“љ ABBR: ${abbreviations.length}</span>
                <span class="deep-invalid">вќЊ РќРµРёР·РІРµСЃС‚РЅРѕ: ${invalidWords.length}</span>
            </div>
    `;

    if (abbreviations.length > 0) {
        html += `
            <div class="deep-section abbreviation">
                <h4>рџ“љ РђР±Р±СЂРµРІРёР°С‚СѓСЂС‹ (С‚СЂРµР±СѓРµС‚СЃСЏ РїРµСЂРµРІРѕРґ)</h4>
                <div class="word-list">
                    ${abbreviations.map(r => `
                        <span class="word-tag abbr">
                            ${r.word}
                            <span class="word-translation" title="${r.reasons.join(', ')}">
                                в†’ ${r.suggestions?.join(', ') || 'РїРµСЂРµРІРѕРґ РЅРµРёР·РІРµСЃС‚РµРЅ'}
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
                <h4>вњ… РЎР»РѕРІР°, РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ РїСЂРё РіР»СѓР±РѕРєРѕР№ РїСЂРѕРІРµСЂРєРµ</h4>
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
                <h4>вќ“ РЎР»РѕРІР°, РЅРµ РїРѕРґС‚РІРµСЂР¶РґС‘РЅРЅС‹Рµ (С‚СЂРµР±СѓСЋС‚ Р·Р°РјРµРЅС‹)</h4>
                <div class="word-list">
                    ${invalidWords.map(r => `
                        <span class="word-tag invalid">
                            ${r.word}
                            ${r.suggestions?.length > 0 ?
                                `<span class="word-suggestions">в†’ ${r.suggestions.join(', ')}</span>` : ''}
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

// РџРµСЂРµРєР»СЋС‡РµРЅРёРµ РѕС‚РѕР±СЂР°Р¶РµРЅРёСЏ РґРµС‚Р°Р»РµР№ РїР°РєРµС‚РЅРѕР№ РїСЂРѕРІРµСЂРєРё
function toggleBatchDetails(index) {
    const detailsEl = document.getElementById(`batch-details-${index}`);
    if (detailsEl) {
        const isVisible = detailsEl.style.display !== 'none';
        detailsEl.style.display = isVisible ? 'none' : 'block';
        
        // РћР±РЅРѕРІР»СЏРµРј С‚РµРєСЃС‚ РєРЅРѕРїРєРё
        const btnEl = document.getElementById(`batch-btn-${index}`);
        if (btnEl) {
            btnEl.textContent = isVisible ? 'РџРѕРєР°Р·Р°С‚СЊ РґРµС‚Р°Р»Рё' : 'РЎРєСЂС‹С‚СЊ РґРµС‚Р°Р»Рё';
        }
    }
}

// Р’СЃРїРѕРјРѕРіР°С‚РµР»СЊРЅС‹Рµ С„СѓРЅРєС†РёРё
function clearText() {
    document.getElementById('textInput').value = '';
    document.getElementById('textResults').style.display = 'none';
    currentResults.text = null;
}

function loadSample() {
    document.getElementById('textInput').value = `РџСЂРёРјРµСЂ С‚РµРєСЃС‚Р° РґР»СЏ РїСЂРѕРІРµСЂРєРё Р·Р°РєРѕРЅР° Рѕ СЂСѓСЃСЃРєРѕРј СЏР·С‹РєРµ.

Р­С‚РѕС‚ СЃРµСЂРІРёСЃ РїСЂРѕРІРµСЂСЏРµС‚ С‚РµРєСЃС‚С‹ РЅР° СЃРѕРѕС‚РІРµС‚СЃС‚РІРёРµ С„РµРґРµСЂР°Р»СЊРЅРѕРјСѓ Р·Р°РєРѕРЅСѓ в„–168-Р¤Р—. 
РћРЅ РЅР°С…РѕРґРёС‚ СЃР»РѕРІР° РЅР° Р»Р°С‚РёРЅРёС†Рµ, Р°РЅРіР»РёС†РёР·РјС‹ Рё РЅРµРЅРѕСЂРјР°С‚РёРІРЅСѓСЋ Р»РµРєСЃРёРєСѓ.

РџРѕРїСЂРѕР±СѓР№С‚Рµ РґРѕР±Р°РІРёС‚СЊ english words РёР»Рё СЃРїРµС†РёР°Р»СЊРЅС‹Рµ С‚РµСЂРјРёРЅС‹ РґР»СЏ РїСЂРѕРІРµСЂРєРё!`;
}

function showLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// Р“РѕСЂСЏС‡РёРµ РєР»Р°РІРёС€Рё
document.addEventListener('keydown', (e) => {
    // Ctrl+Enter РґР»СЏ РїСЂРѕРІРµСЂРєРё С‚РµРєСЃС‚Р°
    if (e.ctrlKey && e.key === 'Enter') {
        const textTab = document.getElementById('text-tab');
        if (textTab && textTab.classList.contains('active')) {
            checkText();
        }
    }
});

