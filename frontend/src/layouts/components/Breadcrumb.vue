<script setup>
/** 面包屑：基于当前路由 matched 链生成 */
defineOptions({ name: 'LayoutBreadcrumb' });

const route = useRoute();

const items = computed(() => route.matched.filter((item) => item.meta?.title));
</script>

<template>
  <el-breadcrumb separator="/" class="breadcrumb">
    <el-breadcrumb-item
      v-for="item in items"
      :key="item.path"
      :to="item.path !== route.path ? item.path : undefined"
    >
      {{ item.meta.title }}
    </el-breadcrumb-item>
  </el-breadcrumb>
</template>
