<script setup>
/** 用户状态标签：1 启用 / 0 停用 */
defineOptions({ name: 'UserStatusTag' });

const props = defineProps({
  /** 状态值：1 启用，0 停用 */
  status: { type: Number, default: 1 },
});

const STATUS_MAP = {
  1: { text: '启用', type: 'success' },
  0: { text: '停用', type: 'danger' },
};

const current = computed(() => STATUS_MAP[props.status] ?? STATUS_MAP[1]);
</script>

<template>
  <el-tag :type="current.type" size="small">{{ current.text }}</el-tag>
</template>
