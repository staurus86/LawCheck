// API Configuration
const API_BASE = window.API_BASE_URL || 'http://localhost:5000';
console.log('🔗 Using API:', API_BASE);
// Global variables
let currentResults = {
    text: null,
    url: null,
    batch: null
};

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadStats();
});

// Переключение вкладок
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            
            // Удаляем активные классы
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));
            
            // Добавляем активные классы
            btn.classList.add('active');
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Загрузка статистики (ИСПРАВЛЕННАЯ ВЕРСИЯ)
async function loadStats() {
    try {
        console.log('🔄 Загружаю статистику...');
        
        const response = await fetch(`${API_BASE}/api/stats`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('📊 Получена статистика:', data);
        
        // Безопасное обновление с проверками
        const normativeEl = document.getElementById('statNormative');
        const foreignEl = document.getElementById('statForeign');
        const nenormativeEl = document.getElementById('statNenormative');
        
        if (normativeEl && data.normative !== undefined) {
            normativeEl.textContent = data.normative.toLocaleString('ru-RU');
        }
        
        if (foreignEl && data.foreign !== undefined) {
            foreignEl.textContent = data.foreign.toLocaleString('ru-RU');
        }
        
        if (nenormativeEl && data.nenormative !== undefined) {
            nenormativeEl.textContent = data.nenormative.toLocaleString('ru-RU');
        }
        
        console.log('✅ Статистика загружена успешно');
        
    } catch (error) {
        console.error('❌ Ошибка загрузки статистики:', error);
        
        // Показываем "0" вместо ошибки
        const normativeEl = document.getElementById('statNormative');
        const foreignEl = document.getElementById('statForeign');
        const nenormativeEl = document.getElementById('statNenormative');
        
        if (normativeEl) normativeEl.textContent = '0';
        if (foreignEl) foreignEl.textContent = '0';
        if (nenormativeEl) nenormativeEl.textContent = '0';
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
}

// Отображение результатов
function displayResults(type, result, url = '') {
    const resultsCard = document.getElementById(`${type}Results`);
    const resultsContent = document.getElementById(`${type}ResultsContent`);
    
    let html = '';
    
    // Статус
    if (result.law_compliant) {
        html += `
            <div class="result-status success">
                ✅ ✅ ✅ ТЕКСТ СООТВЕТСТВУЕТ ТРЕБОВАНИЯМ ЗАКОНА
            </div>
        `;
    } else {
        html += `
            <div class="result-status error">
                ⚠️ ОБНАРУЖЕНО НАРУШЕНИЙ: ${result.violations_count}
            </div>
        `;
        
        // Нарушения
        html += '<div class="violations-list">';
        
        if (result.nenormative_count > 0) {
            html += `
                <div class="violation-section">
                    <h3>🚫 Ненормативная лексика: ${result.nenormative_count}</h3>
                    <div class="word-list">
                        ${result.nenormative_words.slice(0, 20).map(w => {
                            const censored = w[0] + '*'.repeat(w.length - 2) + w[w.length - 1];
                            return `<span class="word-tag">${censored}</span>`;
                        }).join('')}
                    </div>
                </div>
            `;
        }
        
        if (result.latin_count > 0) {
            html += `
                <div class="violation-section">
                    <h3>⚠️ Слова на латинице: ${result.latin_count}</h3>
                    <div class="word-list">
                        ${result.latin_words.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.latin_words.length > 30 ? `<p>... и ещё ${result.latin_words.length - 30} слов</p>` : ''}
                </div>
            `;
        }
        
        if (result.unknown_count > 0) {
            html += `
                <div class="violation-section">
                    <h3>⚠️ Англицизмы / Неизвестные слова: ${result.unknown_count}</h3>
                    <div class="word-list">
                        ${result.unknown_cyrillic.slice(0, 30).map(w => 
                            `<span class="word-tag">${w}</span>`
                        ).join('')}
                    </div>
                    ${result.unknown_cyrillic.length > 30 ? `<p>... и ещё ${result.unknown_cyrillic.length - 30} слов</p>` : ''}
                </div>
            `;
        }
        
        html += '</div>';
    }
    
    // Статистика
    html += `
        <div style="margin-top: 2rem; padding: 1rem; background: #F5F5F5; border-radius: 8px;">
            <p><strong>Всего слов:</strong> ${result.total_words.toLocaleString('ru-RU')}</p>
            <p><strong>Уникальных:</strong> ${result.unique_words.toLocaleString('ru-RU')}</p>
            ${url ? `<p><strong>URL:</strong> ${url}</p>` : ''}
        </div>
    `;
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Отображение пакетных результатов
function displayBatchResults(results) {
    const resultsCard = document.getElementById('batchResults');
    const resultsContent = document.getElementById('batchResultsContent');
    
    let totalViolations = 0;
    let critical = 0;
    
    let html = `
        <div class="result-status">
            📊 Проверено сайтов: ${results.length}
        </div>
        <div style="margin-top: 1rem;">
    `;
    
    results.forEach((item, index) => {
        const hasViolations = item.success && !item.result.law_compliant;
        if (hasViolations) {
            totalViolations++;
            if (item.result.nenormative_count > 0) critical++;
        }
        
        const statusIcon = !item.success ? '❌' : 
                          item.result.law_compliant ? '✅' : 
                          item.result.nenormative_count > 0 ? '🚫' : '⚠️';
        
        html += `
            <div style="padding: 1rem; margin-bottom: 1rem; background: #F9F9F9; border-radius: 8px; border-left: 4px solid ${!item.success ? '#F44336' : item.result.law_compliant ? '#4CAF50' : '#FF9800'}">
                <h4>${statusIcon} [${index + 1}] ${item.url}</h4>
                ${item.success ? `
                    <p>Нарушений: ${item.result.violations_count} 
                    (латиница: ${item.result.latin_count}, 
                    англицизмы: ${item.result.unknown_count}
                    ${item.result.nenormative_count > 0 ? `, 🚫 ненормативная: ${item.result.nenormative_count}` : ''})
                    </p>
                ` : `<p style="color: #F44336;">Ошибка: ${item.error}</p>`}
            </div>
        `;
    });
    
    html += '</div>';
    
    html += `
        <div class="result-status">
            <p><strong>С нарушениями:</strong> ${totalViolations} / ${results.length}</p>
            <p><strong>Чистых:</strong> ${results.length - totalViolations}</p>
            ${critical > 0 ? `<p style="color: #F44336;"><strong>🚫 Критических:</strong> ${critical}</p>` : ''}
        </div>
    `;
    
    resultsContent.innerHTML = html;
    resultsCard.style.display = 'block';
    resultsCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Экспорт отчёта
async function exportReport(type) {
    const result = currentResults[type];
    if (!result) {
        alert('Нет данных для экспорта!');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/export/txt`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ result })
        });
        
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `law_check_${Date.now()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        alert('Ошибка экспорта: ' + error.message);
    }
}

// Вспомогательные функции
function clearText() {
    document.getElementById('textInput').value = '';
    document.getElementById('textResults').style.display = 'none';
}

function loadSample() {
    document.getElementById('textInput').value = `Пример текста для проверки закона о русском языке.

Этот сервис проверяет тексты на соответствие федеральному закону №168-ФЗ. 
Он находит слова на латинице, англицизмы и ненормативную лексику.

Попробуйте добавить english words или специальные термины для проверки!`;
}

function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}
