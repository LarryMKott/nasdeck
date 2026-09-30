<script setup>
/**
 * UNRAID 稿图标 sprite（本稿新绘几何风格，约 33 枚）。
 * 在 UnraidLayout 中渲染一次，页面内经 UIcon 以 <use> 引用。
 * symbol id 统一加 nd-i- 前缀避免与其它资产冲突。
 */
defineOptions({ name: 'NdIconSprite' });

/** 原型 symbol 定义（viewBox 0 0 24 24，stroke 风格） */
const symbols = [
  {
    id: 'dash',
    body: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  },
  {
    id: 'array',
    body: '<rect x="3" y="4" width="18" height="6.6" rx="1.6"/><rect x="3" y="13.4" width="18" height="6.6" rx="1.6"/><circle cx="7.2" cy="7.3" r="1.2" fill="currentColor" stroke="none"/><circle cx="7.2" cy="16.7" r="1.2" fill="currentColor" stroke="none"/><path d="M17.5 7.3h.6M17.5 16.7h.6"/>',
  },
  {
    id: 'drive',
    body: '<rect x="3" y="7" width="18" height="10" rx="2"/><circle cx="16.4" cy="12" r="1.8"/><path d="M6.5 12h4"/>',
  },
  {
    id: 'cpu',
    body: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.8" y="9.8" width="4.4" height="4.4" rx=".8"/><path d="M9 2.8v3.2M15 2.8v3.2M9 18v3.2M15 18v3.2M2.8 9H6M2.8 15H6M18 9h3.2M18 15h3.2"/>',
  },
  { id: 'pulse', body: '<path d="M3 12h4l3-7.5 4 15 3-7.5h4"/>' },
  {
    id: 'temp',
    body: '<path d="M12 3.2a1.9 1.9 0 0 1 1.9 1.9v8.1a4.5 4.5 0 1 1-3.8 0V5.1A1.9 1.9 0 0 1 12 3.2Z"/><path d="M12 8.5v6"/>',
  },
  { id: 'hist', body: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.2V12l3.2 2"/>' },
  {
    id: 'fan',
    body: '<circle cx="12" cy="12" r="2.1"/><path d="M12 9.4c-.5-3.8-2.2-5.7-4.2-5.1C5.8 4.9 5.4 7.4 7.3 8.9c1.5 1.1 3.2.7 4.7.5Z"/><path d="M14.2 13.3c3.4 1.8 6 1.5 6.6-.5.6-2-1.3-3.6-3.7-3-1.8.5-2.6 2.1-2.9 3.5Z"/><path d="M9.8 14.1c-3 2.2-3.9 4.6-2.5 6 1.4 1.5 3.8.9 4.6-1.4.6-1.8-.5-3.3-2.1-4.6Z"/>',
  },
  {
    id: 'docker',
    body: '<rect x="3.5" y="3.5" width="17" height="17" rx="2"/><path d="M3.5 9.5h17M9.5 9.5V20.5M15 9.5V20.5"/>',
  },
  { id: 'net', body: '<path d="M4 8.5h13.2l-3.1-3.1M20 15.5H6.8l3.1 3.1"/>' },
  {
    id: 'bell',
    body: '<path d="M6.2 9.6a5.8 5.8 0 0 1 11.6 0c0 4.6 1.7 6 2.4 6.7H3.8c.7-.7 2.4-2.1 2.4-6.7Z"/><path d="M10.3 19.8a1.9 1.9 0 0 0 3.4 0"/>',
  },
  {
    id: 'shield',
    body: '<path d="M12 3l7 2.7v5.5c0 4.6-2.9 7.9-7 9.8-4.1-1.9-7-5.2-7-9.8V5.7Z"/><path d="m9 11.8 2.2 2.2 4.2-4.5"/>',
  },
  {
    id: 'book',
    body: '<path d="M4 4.5h5.5A2.5 2.5 0 0 1 12 7v13a2 2 0 0 0-2-2H4Z"/><path d="M20 4.5h-5.5A2.5 2.5 0 0 0 12 7v13a2 2 0 0 1 2-2h6Z"/>',
  },
  {
    id: 'info',
    body: '<circle cx="12" cy="12" r="8.8"/><path d="M12 11v5.2"/><path d="M12 7.6h.01"/>',
  },
  { id: 'search', body: '<circle cx="11" cy="11" r="7.2"/><path d="m20.5 20.5-4.5-4.5"/>' },
  { id: 'x', body: '<path d="M6 6l12 12M18 6 6 18"/>' },
  { id: 'chev', body: '<path d="m9.5 6 6 6-6 6"/>' },
  { id: 'chevd', body: '<path d="m6 9.5 6 6 6-6"/>' },
  {
    id: 'refresh',
    body: '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20.2 3.6V7.4h-3.8"/>',
  },
  {
    id: 'power',
    body: '<path d="M12 3v8.5"/><path d="M17.8 6.6a8 8 0 1 1-11.6 0"/>',
  },
  { id: 'play', body: '<path d="M8 5.5v13l10.5-6.5Z"/>' },
  { id: 'stop', body: '<rect x="7" y="7" width="10" height="10" rx="1.5"/>' },
  {
    id: 'dl',
    body: '<path d="M12 3.5V15"/><path d="m7 10.5 5 4.5 5-4.5"/><path d="M4.5 19.5h15"/>',
  },
  { id: 'plus', body: '<path d="M12 5v14M5 12h14"/>' },
  { id: 'check', body: '<path d="m5 12.5 4.5 4.5L19 7.5"/>' },
  { id: 'alert', body: '<path d="M12 3.8 21 19.5H3Z"/><path d="M12 10v4"/><path d="M12 17h.01"/>' },
  {
    id: 'sun',
    body: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.3M12 19.2v2.3M2.5 12h2.3M19.2 12h2.3M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/>',
  },
  { id: 'moon', body: '<path d="M20 13.5A8.5 8.5 0 0 1 10.5 4 8.5 8.5 0 1 0 20 13.5Z"/>' },
  {
    id: 'monitor',
    body: '<rect x="3" y="4" width="18" height="12.5" rx="2"/><path d="M12 16.5v4M8.5 20.5h7"/>',
  },
  { id: 'menu', body: '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>' },
  { id: 'send', body: '<path d="M21 3 10.5 13.5"/><path d="M21 3l-6.5 18-4-8-8-4Z"/>' },
  { id: 'clock', body: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.4 2"/>' },
  {
    id: 'server',
    body: '<rect x="4" y="3.5" width="16" height="7" rx="1.6"/><rect x="4" y="13.5" width="16" height="7" rx="1.6"/><path d="M7.5 7h.01M7.5 17h.01"/>',
  },
  {
    id: 'layers',
    body: '<path d="m12 3.5 9 4.5-9 4.5L3 8Z"/><path d="m4.5 12.5 7.5 3.8 7.5-3.8M4.5 16.5l7.5 3.8 7.5-3.8"/>',
  },
  {
    id: 'cloud',
    body: '<path d="M7 18.5a4.5 4.5 0 0 1-.4-9A6 6 0 0 1 18.3 11a3.8 3.8 0 0 1-.8 7.5Z"/>',
  },
];
</script>

<template>
  <!-- symbol 内容为本组件内静态手写路径，无外部输入，v-html 安全 -->
  <!-- eslint-disable vue/no-v-html -->
  <svg xmlns="http://www.w3.org/2000/svg" style="display: none" aria-hidden="true">
    <symbol
      v-for="s in symbols"
      :id="`nd-i-${s.id}`"
      :key="s.id"
      viewBox="0 0 24 24"
      v-html="s.body"
    />
  </svg>
  <!-- eslint-enable vue/no-v-html -->
</template>
