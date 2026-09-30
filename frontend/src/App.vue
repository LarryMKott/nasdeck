<script setup>
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import { useAppStore } from '@/stores/modules/app';

defineOptions({ name: 'App' });

const appStore = useAppStore();

// 主题联动：UNRAID 界面走 .nd[data-theme]，Element Plus 页面走 html.dark
watchEffect(() => {
  const dark = appStore.theme !== 'light';
  document.documentElement.classList.toggle('dark', dark);
  document.body.classList.toggle('nd-dark', dark);
});
</script>

<template>
  <el-config-provider :locale="zhCn" :size="appStore.size">
    <router-view />
  </el-config-provider>
</template>
