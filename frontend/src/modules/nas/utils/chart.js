'use strict';

/**
 * 自研 SVG 折线图引擎（移植自 prototype/nasdeck-unraid.html 的 mkline/spark）。
 * DOM 直绘，不依赖图表库；十字线 tooltip、dataZoom 拖拽缩放与原型行为一致。
 */

/** 计算美观刻度（1/2/5 步长）
 * @param {number} rawMin 数据最小值
 * @param {number} rawMax 数据最大值
 * @param {number} n 期望刻度数
 */
function niceScale(rawMin, rawMax, n) {
  let min = rawMin;
  let max = rawMax;
  if (min === Infinity || min === undefined) {
    min = 0;
    max = 1;
  }
  if (max - min < 1e-9) {
    max = min + 1;
  }
  const span = max - min;
  const step0 = span / n;
  const mag = 10 ** Math.floor(Math.log(step0) / Math.LN10);
  const norm = step0 / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step * 1e-6; v += step) ticks.push(Math.round(v * 1e6) / 1e6);
  return { lo, hi, ticks };
}

/**
 * 在宿主元素内绘制折线图（含 area 渐变、十字线 tooltip、可选 dataZoom）
 * @param {HTMLElement} host 宿主（需有 .chartbox 样式与 id）
 * @param {object} cfg { series:[{name,color,data,dash?,area?}], labels, height?, zoom?, tipFmt?, yTickFmt? }
 */
function renderLine(host, cfg) {
  host.classList.add('chartbox');
  host.innerHTML = '';
  const W = host.clientWidth || 640;
  const H = cfg.height || 170;
  const pl = 46;
  const pr = 14;
  const pt = 12;
  const pb = 24;
  const iw = W - pl - pr;
  const ih = H - pt - pb;
  const n = cfg.labels.length;
  let i0 = 0;
  let i1 = n - 1;
  let zoomWin = null;

  const tip = document.createElement('div');
  tip.className = 'chart-tip';
  host.appendChild(tip);

  const sliceSeries = () =>
    cfg.series.map((s) => ({
      name: s.name,
      color: s.color,
      dash: s.dash,
      data: s.data.slice(i0, i1 + 1),
      area: s.area,
    }));

  function draw() {
    host.querySelectorAll('svg.plot,.zoombar').forEach((el) => el.remove());
    const ds = sliceSeries();
    const m = ds[0].data.length;
    let mn = Infinity;
    let mx = -Infinity;
    ds.forEach((s) =>
      s.data.forEach((v) => {
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      })
    );
    if (mn === Infinity) {
      mn = 0;
      mx = 1;
    }
    const padY = (mx - mn) * 0.15 || 1;
    const sc = niceScale(Math.max(0, mn - padY), mx + padY, 4);
    const { lo, hi } = sc;

    const X = (i) => pl + iw * (m === 1 ? 0.5 : i / (m - 1));
    const Y = (v) => pt + ih * (1 - (v - lo) / (hi - lo));

    const svg = [`<svg class="plot" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`];
    svg.push('<defs>');
    ds.forEach((s, si) => {
      svg.push(
        `<linearGradient id="nd-ug-${host.id}-${si}" x1="0" y1="0" x2="0" y2="1">` +
          `<stop offset="0" stop-color="${s.color}" stop-opacity=".24"/>` +
          `<stop offset="1" stop-color="${s.color}" stop-opacity="0"/></linearGradient>`
      );
    });
    svg.push('</defs>');
    sc.ticks.forEach((tv) => {
      const y = Y(tv);
      svg.push(`<line x1="${pl}" y1="${y}" x2="${W - pr}" y2="${y}" stroke="var(--grid)"/>`);
      svg.push(
        `<text x="${pl - 8}" y="${y + 3.5}" text-anchor="end" font-size="10" fill="var(--axis)">` +
          `${cfg.yTickFmt ? cfg.yTickFmt(tv) : tv}</text>`
      );
    });
    const xl = Math.min(6, m);
    for (let k = 0; k < xl; k += 1) {
      const idx = Math.round((k * (m - 1)) / (xl - 1 || 1));
      svg.push(
        `<text x="${X(idx)}" y="${H - 6}" text-anchor="middle" font-size="10" fill="var(--axis)">` +
          `${cfg.labels[i0 + idx]}</text>`
      );
    }
    ds.forEach((s, si) => {
      const pts = s.data.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' ');
      if (s.area !== false) {
        svg.push(
          `<path d="M${X(0).toFixed(1)},${Y(lo).toFixed(1)} L${pts.replace(/ /g, ' L')} ` +
            `L${X(m - 1).toFixed(1)},${Y(lo).toFixed(1)} Z" fill="url(#nd-ug-${host.id}-${si})"/>`
        );
      }
      svg.push(
        `<path d="M${pts.replace(/ /g, ' L')}" fill="none" stroke="${s.color}" stroke-width="2" ` +
          'stroke-linejoin="round" stroke-linecap="round"' +
          `${s.dash ? ' stroke-dasharray="5 4"' : ''}/>`
      );
    });
    svg.push(
      `<line class="xh" x1="0" y1="${pt}" x2="0" y2="${pt + ih}" stroke="var(--axis)" ` +
        'stroke-dasharray="3 3" visibility="hidden"/>'
    );
    ds.forEach((s) => {
      svg.push(
        `<circle class="xd" r="3.5" fill="${s.color}" stroke="var(--sf)" stroke-width="1.5" visibility="hidden"/>`
      );
    });
    svg.push('</svg>');
    host.insertAdjacentHTML('beforeend', svg.join(''));

    if (cfg.zoom) {
      const zb = document.createElement('div');
      zb.className = 'zoombar';
      zb.innerHTML =
        '<div class="zb-track"><div class="zb-win"><span class="zb-h l"></span><span class="zb-h r"></span></div></div>';
      host.appendChild(zb);
      zoomWin = zb.querySelector('.zb-win');
      paintZoom();
      bindZoom(zb);
    }
    bindHover(X, Y);
  }

  function paintZoom() {
    if (!zoomWin) return;
    zoomWin.style.left = `${(i0 / (n - 1)) * 100}%`;
    zoomWin.style.width = `${((i1 - i0) / (n - 1)) * 100}%`;
  }

  function bindHover(X, Y) {
    const svg = host.querySelector('svg.plot');
    const xh = svg.querySelector('.xh');
    const dots = [...svg.querySelectorAll('.xd')];
    svg.addEventListener('mousemove', (e) => {
      const ds = sliceSeries();
      const r = svg.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const m = ds[0].data.length;
      const i = Math.max(0, Math.min(m - 1, Math.round((mx - pl) / (iw / (m - 1 || 1)))));
      const px = pl + iw * (m === 1 ? 0.5 : i / (m - 1));
      xh.setAttribute('x1', px);
      xh.setAttribute('x2', px);
      xh.setAttribute('visibility', 'visible');
      let rows = '';
      dots.forEach((d, si) => {
        const v = ds[si].data[i];
        d.setAttribute('cx', px);
        d.setAttribute('cy', Y(v));
        d.setAttribute('visibility', 'visible');
        rows +=
          `<div class="tt-r"><span class="tt-d" style="background:${ds[si].color}"></span>` +
          `${ds[si].name}<b>${cfg.tipFmt ? cfg.tipFmt(v) : v}</b></div>`;
      });
      tip.innerHTML = `<div class="tt-t">${cfg.labels[i0 + i]}</div>${rows}`;
      tip.style.display = 'block';
      const tw = tip.offsetWidth;
      tip.style.left = `${px + 12 + tw > r.width ? px - tw - 12 : px + 12}px`;
      tip.style.top = '8px';
    });
    svg.addEventListener('mouseleave', () => {
      tip.style.display = 'none';
      xh.setAttribute('visibility', 'hidden');
      dots.forEach((d) => d.setAttribute('visibility', 'hidden'));
    });
  }

  function bindZoom(zb) {
    zb.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const rect = zb.getBoundingClientRect();
      const mode = e.target.classList.contains('zb-h')
        ? e.target.classList.contains('l')
          ? 'l'
          : 'r'
        : 'm';
      const sx = e.clientX;
      const oi0 = i0;
      const oi1 = i1;
      const spanPx = rect.width / (n - 1);
      const onMove = (ev) => {
        const d = (ev.clientX - sx) / spanPx;
        if (mode === 'm') {
          const len = oi1 - oi0;
          const s = Math.max(0, Math.min(n - 1 - len, Math.round(oi0 + d)));
          i0 = s;
          i1 = s + len;
        } else if (mode === 'l') {
          i0 = Math.max(0, Math.min(oi1 - 2, Math.round(oi0 + d)));
        } else {
          i1 = Math.min(n - 1, Math.max(oi0 + 2, Math.round(oi1 + d)));
        }
        paintZoom();
        draw();
      };
      const onUp = () => {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
      };
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    });
  }

  draw();
}

/**
 * 在宿主元素内绘制迷你走势线（无轴无交互）
 * @param {HTMLElement} host 宿主
 * @param {number[]} data 序列
 * @param {string} color 线色
 */
function renderSpark(host, data, color) {
  const W = host.clientWidth || 120;
  const H = host.clientHeight || 26;
  const n = data.length;
  const mn = Math.min(...data);
  let mx = Math.max(...data);
  if (mx - mn < 1e-9) mx = mn + 1;
  const pts = data
    .map(
      (v, i) =>
        `${((i / (n - 1)) * W).toFixed(1)},${(H - 2 - ((v - mn) / (mx - mn)) * (H - 5)).toFixed(1)}`
    )
    .join(' ');
  host.innerHTML =
    `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" ` +
    'style="width:100%;height:100%;display:block">' +
    `<path d="M${pts.replace(/ /g, ' L')}" fill="none" stroke="${color}" stroke-width="1.6" ` +
    'stroke-linejoin="round" stroke-linecap="round"/></svg>';
}

export { niceScale, renderLine, renderSpark };
