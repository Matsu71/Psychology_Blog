/* 図4：遺伝率シミュレーター。遺伝と環境がたし算で独立に働く単純なモデルの説明図。 */
(() => {
  'use strict';
  const root = document.querySelector('[data-sim]');
  const slider = document.querySelector('#sim-h');
  if (!root || !slider) return;
  const out = document.querySelector('#sim-out');
  const N = 40;
  // 再現できる疑似乱数（線形合同法）と Box–Muller 法。
  let seed = 20261015;
  const rand = () => (seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const normal = () => Math.sqrt(-2 * Math.log(1 - rand())) * Math.cos(2 * Math.PI * rand());
  const standardize = xs => {
    const m = xs.reduce((a, b) => a + b, 0) / xs.length;
    const sd = Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
    return xs.map(x => (x - m) / sd);
  };
  const g = standardize(Array.from({length: N}, normal));
  let e = standardize(Array.from({length: N}, normal));
  // 標本の上でも遺伝と環境を無相関にして、分散の比が遺伝率と正確に一致するようにする。
  const r = g.reduce((a, x, i) => a + x * e[i], 0) / N;
  e = standardize(e.map((x, i) => x - r * g[i]));
  // Aさん：遺伝の値が高く、環境は平均に近い人。
  let a = 0;
  g.forEach((x, i) => { if (x - Math.abs(e[i]) > g[a] - Math.abs(e[a])) a = i; });
  // 重なりを減らすための縦方向のずれ（値には関係しない）。
  const jitter = Array.from({length: N}, () => Math.round((rand() - 0.5) * 20));
  const rows = {};
  root.querySelectorAll('.sim-row').forEach(row => {
    const track = row.querySelector('.sim-trk');
    const band = document.createElement('i');
    band.className = 'sim-band';
    track.append(band);
    const dots = Array.from({length: N}, (_, i) => {
      const dot = document.createElement('i');
      dot.className = 'sim-dot' + (i === a ? ' is-a' : '');
      dot.style.top = `calc(50% + ${i === a ? 0 : jitter[i]}px)`;
      track.append(dot);
      return dot;
    });
    rows[row.dataset.row] = {band, dots, stat: row.querySelector('.sim-stat')};
  });
  const pos = z => Math.max(1, Math.min(99, 50 + z * 15)); // ±3標準偏差 ≒ 端から端
  const pct = x => Math.round(x * 100) + '％';
  function render() {
    const h = Number(slider.value) / 100;
    out.textContent = pct(h);
    const values = {
      p: g.map((x, i) => Math.sqrt(h) * x + Math.sqrt(1 - h) * e[i]),
      e: e.map(x => Math.sqrt(1 - h) * x),
      g: g.map(x => Math.sqrt(h) * x)
    };
    const variance = {p: 1, e: 1 - h, g: h};
    for (const [key, row] of Object.entries(rows)) {
      row.dots.forEach((dot, i) => { dot.style.left = pos(values[key][i]) + '%'; });
      const sd = Math.sqrt(variance[key]);
      row.band.style.left = pos(-sd) + '%';
      row.band.style.width = (pos(sd) - pos(-sd)) + '%';
      row.stat.innerHTML = `ばらつき <b>${pct(variance[key])}</b><span class="pro">（分散）・広がり（標準偏差）${pct(sd)}</span>`;
    }
  }
  slider.addEventListener('input', render);
  render();
})();
