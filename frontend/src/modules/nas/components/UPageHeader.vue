<script setup>
/** UNRAID 稿页头：标题 + 副题 + 状态徽标 + 「最后更新 / 立即刷新」+ 右侧扩展插槽。
 *  立即刷新为真实刷新（原型 D1）：emit('refresh') 由视图接 useViewData.refresh，
 *  转圈跟随 refreshing prop（真实请求时长）；refreshable=false 隐藏按钮（静态页）。
 */
import { computed, ref, watch } from 'vue';

defineOptions({ name: 'UPageHeader' });

const props = defineProps({
  title: { type: String, required: true },
  sub: { type: String, default: '' },
  /** 状态徽标 { type: 'ok'|'warn'|'acc', text } */
  tag: { type: Object, default: null },
  /** 「最后更新」初始时刻（HH:mm:ss） */
  updated: { type: String, default: '' },
  /** 真实请求进行中（useViewData.refreshing）：按钮转圈跟随 */
  refreshing: { type: Boolean, default: false },
  /** 静态页（手册等）隐藏刷新按钮 */
  refreshable: { type: Boolean, default: true },
});

const emit = defineEmits(['refresh']);

const lastUpdated = ref(props.updated);

// 页面数据刷新会更新 updated prop（useViewData.lastUpdated / 实时时刻），同步到内部显示
watch(
  () => props.updated,
  (v) => {
    if (v && v !== '—') lastUpdated.value = v;
  }
);

const spinning = computed(() => props.refreshing);
</script>

<template>
  <div class="ph">
    <h1>{{ title }}</h1>
    <span v-if="sub" class="sub">{{ sub }}</span>
    <span v-if="tag" class="tag" :class="tag.type"> <span class="dot" />{{ tag.text }} </span>
    <div class="right">
      <span class="lup num">最后更新 {{ lastUpdated }}</span>
      <slot name="right" />
      <button v-if="refreshable" class="btn sm" @click="emit('refresh')">
        <svg class="ico" :class="{ spin: spinning }"><use href="#nd-i-refresh" /></svg>立即刷新
      </button>
    </div>
  </div>
</template>
