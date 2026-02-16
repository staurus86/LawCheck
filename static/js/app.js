// API Configuration
const API_BASE = window.API_BASE_URL || 'http://localhost:5000';
console.log('🔗 Using API:', API_BASE);

// Global variables
let currentResults = {
    text: null,
    url: null,
    batch: null
};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadStats();
    console.log('✅ LawChecker Online загружен');
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

// Загрузка статистики словарей
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
    console.log('✅ Пакетная проверка завершена:', results);
}

// Проверка одного слова
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
}

function loadSample() {
    document.getElementById('textInput').value = `Пример текста для проверки закона о русском языке.

Этот сервис проверяет тексты на соответствие федеральному закону №168-ФЗ. 
Он находит слова на латинице, англицизмы и ненормативную лексику.

Попробуйте добавить english words или специальные термины для проверки!`;
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

// Горячие клавиши
document.addEventListener('keydown', (e) => {
    // Ctrl+Enter для проверки текста
    if (e.ctrlKey && e.key === 'Enter') {
        const textTab = document.getElementById('text-tab');
        if (textTab && textTab.classList.contains('active')) {
            checkText();
        }
    }
});
