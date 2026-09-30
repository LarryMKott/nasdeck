<script setup>
/**
 * UNRAID 稿风扇曲线编辑器：温度(x)-占空比(y) 折线，圆点可拖拽。
 * 温度区间底色分档（<45 正常 / 45-60 偏高 / >60 过热）。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

defineOptions({ name: 'UCurveEditor' });

const props = defineProps({
  /** 曲线点 [[温度 °C, 占空比 %], ...]，x 升序 */
  modelValue: { type: Array, required: true },
});

const emit = defineEmits(['update:modelValue', 'drag']);

const host = ref(null);
const X0 = 25;
const X1 = 70;
const Y0 = 0;
const Y1 = 100;

function buildSvg(pts) {
  const W = host.value?.clientWidth || 560;
  const H = 300;
  const pl = 44;
  const pr = 16;
  const pt = 14;
  const pb = 30;
  const iw = W - pl - pr;
  const ih = H - pt - pb;
  const X = (t) => pl + iw * ((t - X0) / (X1 - X0));
  const Y = (d) => pt + ih * (1 - (d - Y0) / (Y1 - Y0));

  const s = [`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">`];
  s.push(
    '<defs><linearGradient id="nd-ucg" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0" stop-color="#F15A2C" stop-opacity=".22"/>' +
      '<stop offset="1" stop-color="#F15A2C" stop-opacity="0"/></linearGradient></defs>'
  );
  s.push(
    `<rect x="${X(X0)}" y="${Y(100)}" width="${X(45) - X(X0)}" height="${Y(0) - Y(100)}" fill="var(--okbg)" opacity=".5"/>`
  );
  s.push(
    `<rect x="${X(45)}" y="${Y(100)}" width="${X(60) - X(45)}" height="${Y(0) - Y(100)}" fill="var(--warnbg)" opacity=".55"/>`
  );
  s.push(
    `<rect x="${X(60)}" y="${Y(100)}" width="${X(X1) - X(60)}" height="${Y(0) - Y(100)}" fill="var(--badbg)" opacity=".55"/>`
  );
  for (let d = 0; d <= 100; d += 25) {
    s.push(
      `<line x1="${pl}" y1="${Y(d)}" x2="${W - pr}" y2="${Y(d)}" stroke="var(--grid)"/>` +
        `<text x="${pl - 8}" y="${Y(d) + 3.5}" text-anchor="end" font-size="10" fill="var(--axis)">${d}%</text>`
    );
  }
  for (let t = X0; t <= X1; t += 5) {
    s.push(
      `<line x1="${X(t)}" y1="${pt}" x2="${X(t)}" y2="${pt + ih}" stroke="var(--grid)" opacity=".55"/>` +
        `<text x="${X(t)}" y="${H - 8}" text-anchor="middle" font-size="10" fill="var(--axis)">${t}°</text>`
    );
  }
  const pointStr = pts.map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`);
  s.push(
    `<path d="M${X(pts[0][0]).toFixed(1)},${Y(0)} L${pointStr.join(' L')} ` +
      `L${X(pts[pts.length - 1][0]).toFixed(1)},${Y(0)} Z" fill="url(#nd-ucg)"/>`
  );
  s.push(
    `<path d="M${pointStr.join(' L')}" fill="none" stroke="var(--acc)" stroke-width="2.2" stroke-linejoin="round"/>`
  );
  pts.forEach((p, i) => {
    s.push(
      `<circle class="pt" data-i="${i}" cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="6"/>`
    );
  });
  s.push('</svg>');
  return { svg: s.join(''), X, Y, iw };
}

function paint() {
  if (!host.value || !props.modelValue.length) return;
  host.value.innerHTML = buildSvg(props.modelValue).svg;
  host.value.querySelectorAll('.pt').forEach((circle) => {
    circle.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      const i = Number(circle.getAttribute('data-i'));
      const svgEl = host.value.querySelector('svg');
      const onMove = (ev) => {
        const r = svgEl.getBoundingClientRect();
        const W = r.width;
        const H = 300;
        const pl2 = 44;
        const pr = 16;
        const pt = 14;
        const pb = 30;
        const iw2 = W - pl2 - pr;
        const ih = H - pt - pb;
        const t = Math.round(X0 + ((ev.clientX - r.left - pl2) / iw2) * (X1 - X0));
        const d = Math.round(Y0 + (1 - (ev.clientY - r.top - pt) / ih) * (Y1 - Y0));
        const next = props.modelValue.map((p) => [...p]);
        const lo = i === 0 ? X0 : next[i - 1][0] + 1;
        const hi = i === next.length - 1 ? X1 : next[i + 1][0] - 1;
        next[i] = [Math.max(lo, Math.min(hi, t)), Math.max(0, Math.min(100, d))];
        emit('update:modelValue', next);
        emit('drag', next[i]);
      };
      const onUp = () => {
        document.removeEventListener('pointermove', onMove);
        document.removeEventListener('pointerup', onUp);
      };
      document.addEventListener('pointermove', onMove);
      document.addEventListener('pointerup', onUp);
    });
  });
}

let ro = null;
onMounted(() => {
  paint();
  ro = new ResizeObserver(() => paint());
  ro.observe(host.value);
});
onBeforeUnmount(() => ro?.disconnect());
watch(
  () => props.modelValue,
  () => paint(),
  { deep: true }
);
</script>

<template>
  <div ref="host" class="curve-svg" />
</template>

<style scoped>
.curve-svg :deep(svg) {
  display: block;
  width: 100%;
  touch-action: none;
}

.curve-svg :deep(.pt) {
  cursor: grab;
  fill: var(--acc);
  stroke: var(--sf);
  stroke-width: 2;
}

.curve-svg :deep(.pt:hover) {
  r: 7;
}
</style>
