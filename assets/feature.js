/* 特集記事の共通機能：読み方（やさしく／くわしく）の切り替えと、図のツールチップ。 */
(() => {
  'use strict';
  const buttons = document.querySelectorAll('[data-depth-set]');
  function setDepth(value, save) {
    if (value !== 'detail') value = 'basic';
    document.documentElement.dataset.depth = value;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.depthSet === value)));
    document.querySelectorAll('details.deep').forEach(d => { d.open = value === 'detail'; });
    if (save) { try { localStorage.setItem('psychology-depth', value); } catch (_) { /* 保存は任意 */ } }
  }
  if (buttons.length) {
    document.querySelectorAll('.depth-switch').forEach(x => { x.hidden = false; });
    let saved = 'basic';
    try { saved = localStorage.getItem('psychology-depth') || 'basic'; } catch (_) { /* 既定はやさしく */ }
    setDepth(saved, false);
    buttons.forEach(b => b.addEventListener('click', () => setDepth(b.dataset.depthSet, true)));
  }
  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  tip.hidden = true;
  tip.setAttribute('role', 'presentation');
  document.body.append(tip);
  function show(target, x, y) {
    tip.textContent = target.dataset.tip;
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(innerWidth - w - 8, x - w / 2)) + 'px';
    tip.style.top = (y - h - 12 < 8 ? y + 18 : y - h - 12) + 'px';
  }
  ['pointermove', 'pointerdown'].forEach(type => document.addEventListener(type, event => {
    const target = event.target.closest && event.target.closest('[data-tip]');
    if (!target) { tip.hidden = true; return; }
    show(target, event.clientX, event.clientY);
  }));
  document.addEventListener('pointerleave', () => { tip.hidden = true; });
  addEventListener('scroll', () => { tip.hidden = true; }, {passive: true});
})();
