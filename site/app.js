/* Progressive enhancement: the topic index and every article work without JS. */
(() => {
  'use strict';
  const normalize = value => value.normalize('NFKC').toLocaleLowerCase('ja')
    .replace(/[\u30a1-\u30f6]/g, ch => String.fromCharCode(ch.charCodeAt(0) - 0x60));
  const toc = document.querySelector('.reader-toc');
  if (toc) toc.open = matchMedia('(min-width: 761px)').matches;
  const sizes = document.querySelectorAll('[data-reader-size]');
  function setSize(size) {
    if (!['18','20','22'].includes(size)) size = '18';
    document.documentElement.style.setProperty('--reader-size', `${size}px`);
    sizes.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.readerSize === size)));
    try { localStorage.setItem('psychology-reader-size', size); } catch (_) { /* Storage is optional. */ }
  }
  if (sizes.length) {
    try { setSize(localStorage.getItem('psychology-reader-size') || '18'); } catch (_) { setSize('18'); }
    sizes.forEach(button => button.addEventListener('click', () => setSize(button.dataset.readerSize)));
  }
  const form = document.querySelector('#topic-search');
  if (!form) return;
  const query = document.querySelector('#search-query');
  const group = document.querySelector('#search-group');
  const status = document.querySelector('#search-status');
  const list = [...document.querySelectorAll('.search-result')];
  const corpus = list.map(element => ({element, text: normalize(element.dataset.search), group: element.dataset.group, status: element.dataset.status}));
  const summary = document.querySelector('#result-summary');
  const empty = document.querySelector('#no-results');
  const pager = document.querySelector('#pagination');
  const previous = document.querySelector('#previous');
  const next = document.querySelector('#next');
  const pageInfo = document.querySelector('#page-info');
  const PAGE_SIZE = 24;
  let page = 1;
  document.querySelector('#search-enhancements').hidden = false;
  function fromURL() {
    const params = new URLSearchParams(location.search);
    query.value = (params.get('q') || '').slice(0, 150);
    group.value = params.get('group') || '';
    status.value = params.get('status') || '';
    if (group.selectedIndex < 0) group.value = '';
    if (status.selectedIndex < 0) status.value = '';
    page = Math.max(1, Number.parseInt(params.get('page'), 10) || 1);
  }
  function render(writeURL = true) {
    const words = normalize(query.value.trim()).split(/\s+/).filter(Boolean);
    const found = corpus.filter(item => (!group.value || item.group === group.value) && (!status.value || item.status === status.value) && words.every(word => item.text.includes(word)));
    const pages = Math.max(1, Math.ceil(found.length / PAGE_SIZE));
    page = Math.min(page, pages);
    corpus.forEach(item => { item.element.hidden = true; });
    found.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE).forEach(item => { item.element.hidden = false; });
    summary.textContent = `${found.length}件のテーマ` + (found.length ? ` · ${(page-1)*PAGE_SIZE+1}〜${Math.min(page*PAGE_SIZE, found.length)}件を表示` : '');
    empty.hidden = found.length !== 0;
    pager.hidden = pages === 1;
    pageInfo.textContent = `${page} / ${pages}`;
    previous.disabled = page === 1;
    next.disabled = page === pages;
    if (writeURL) {
      const params = new URLSearchParams();
      if (query.value.trim()) params.set('q', query.value.trim());
      if (group.value) params.set('group', group.value);
      if (status.value) params.set('status', status.value);
      if (page > 1) params.set('page', String(page));
      try { history.replaceState(null, '', location.pathname + (params.size ? '?' + params.toString() : '') + location.hash); } catch (_) { /* Downloaded file previews may disallow history writes. */ }
    }
  }
  form.addEventListener('submit', event => { event.preventDefault(); page=1; render(); });
  let timer;
  query.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { page=1; render(); }, 120); });
  [group,status].forEach(control => control.addEventListener('change', () => { page=1; render(); }));
  document.querySelectorAll('[data-reset-search]').forEach(button => button.addEventListener('click', () => { query.value=''; group.value=''; status.value=''; page=1; render(); query.focus(); }));
  function move(delta) { page += delta; render(); summary.focus(); summary.scrollIntoView({block:'start'}); }
  previous.addEventListener('click', () => move(-1)); next.addEventListener('click', () => move(1));
  addEventListener('popstate', () => { fromURL(); render(false); });
  fromURL(); render(false);
})();
