<script setup>
/** UNRAID 稿页头：标题 + 副题 + 状态徽标 + 「最后更新 / 立即刷新」+ 右侧扩展插槽 */
import { ref } from 'vue';
import { nowHMS } from '../utils/series';

defineOptions({ name: 'UPageHeader' });

const props = defineProps({
  title: { type: String, required: true },
  sub: { type: String, default: '' },
  /** 状态徽标 { type: 'ok'|'warn'|'acc', text } */
  tag: { type: Object, default: null },
  /** 「最后更新」初始时刻（HH:mm:ss） */
  updated: { type: String, default: '' },
});

const spinning = ref(false);
const lastUpdated = ref(props.updated);

function refresh() {
  if (spinning.value) return;
  spinning.value = true;
  // 与原型一致的刷新动效：旋转 650ms 后更新时刻
  setTimeout(() => {
    spinning.value = false;
    lastUpdated.value = nowHMS();
  }, 650);
}
</script>

<template>
  <div class="ph">
    <h1>{{ title }}</h1>
    <span v-if="sub" class="sub">{{ sub }}</span>
    <span v-if="tag" class="tag" :class="tag.type"> <span class="dot" />{{ tag.text }} </span>
    <div class="right">
      <span class="lup num">最后更新 {{ lastUpdated }}</span>
      <slot name="right" />
      <button class="btn sm" @click="refresh">
        <svg class="ico" :class="{ spin: spinning }"><use href="#nd-i-refresh" /></svg>立即刷新
      </button>
    </div>
  </div>
</template>
