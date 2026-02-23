/* common.js — утилиты, работающие на всех страницах */

// ─── Применить тему немедленно, без ожидания DOM ──────────────────────────
(function () {
    var t = localStorage.getItem('lawchecker.theme');
    if (t) document.documentElement.setAttribute('data-theme', t);
}());

// ─── Глобальная функция переключения (index.html перекрывает через app.js) ─
window.toggleDarkMode = function () {
    var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    var next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('lawchecker.theme', next);
    var icon = document.getElementById('darkModeIcon');
    if (icon) icon.textContent = next === 'dark' ? '☀️' : '🌙';
};

document.addEventListener('DOMContentLoaded', function () {

    // ─── Синхронизация иконки темы ─────────────────────────────────────────
    var saved = localStorage.getItem('lawchecker.theme') || 'light';
    var icon = document.getElementById('darkModeIcon');
    if (icon) icon.textContent = saved === 'dark' ? '☀️' : '🌙';

    // ─── Кнопка «Вернуться наверх» ─────────────────────────────────────────
    var topBtn = document.createElement('button');
    topBtn.className = 'back-to-top';
    topBtn.textContent = '↑';
    topBtn.title = 'Наверх';
    topBtn.setAttribute('aria-label', 'Вернуться наверх');
    topBtn.onclick = function () { window.scrollTo({ top: 0, behavior: 'smooth' }); };
    document.body.appendChild(topBtn);
    window.addEventListener('scroll', function () {
        topBtn.classList.toggle('visible', window.scrollY > 350);
    }, { passive: true });

    // ─── Scroll-reveal (IntersectionObserver) ──────────────────────────────
    if ('IntersectionObserver' in window) {
        var revealObs = new IntersectionObserver(function (entries) {
            entries.forEach(function (e) {
                if (e.isIntersecting) {
                    e.target.classList.add('is-visible');
                    revealObs.unobserve(e.target);
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -30px 0px' });

        // Дочерние элементы сеток — со стаггером
        var grids = [
            '.knowledge-grid', '.workflow-grid', '.audience-grid',
            '.pricing-grid', '.stats-cards', '.info-boxes', '.timeline-list'
        ];
        grids.forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (grid) {
                Array.from(grid.children).forEach(function (child, i) {
                    child.classList.add('reveal-item');
                    child.style.transitionDelay = Math.min(i * 0.09, 0.36) + 's';
                    revealObs.observe(child);
                });
            });
        });

        // Одиночные секции
        ['.faq-box', '.formats-box', '.cta-box', '.step-list', '.api-quickstart'].forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                if (!el.classList.contains('reveal-item')) {
                    el.classList.add('reveal-item');
                    revealObs.observe(el);
                }
            });
        });
    }

    // ─── Кнопки копирования для блоков кода ────────────────────────────────
    document.querySelectorAll('pre.api-code').forEach(function (pre) {
        var wrapper = document.createElement('div');
        wrapper.className = 'api-code-wrapper';
        pre.parentNode.insertBefore(wrapper, pre);
        wrapper.appendChild(pre);

        var btn = document.createElement('button');
        btn.className = 'copy-code-btn';
        btn.textContent = 'Скопировать';
        btn.onclick = function () {
            if (!navigator.clipboard) return;
            navigator.clipboard.writeText(pre.textContent.trim()).then(function () {
                btn.textContent = '✓ Скопировано';
                btn.classList.add('copied');
                setTimeout(function () {
                    btn.textContent = 'Скопировать';
                    btn.classList.remove('copied');
                }, 2200);
            });
        };
        wrapper.appendChild(btn);
    });
});
