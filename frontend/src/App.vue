<script setup>
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import en from 'element-plus/es/locale/lang/en';
import { useAppStore } from '@/stores/modules/app';
import { locale } from '@/i18n/locale';

defineOptions({ name: 'App' });

const appStore = useAppStore();

// 主题联动：UNRAID 界面走 .nd[data-theme]，Element Plus 页面走 html.dark；
// system 模式随系统配色实时变化，先初始化监听再求值
appStore.initThemeWatcher();
watchEffect(() => {
  const dark = appStore.resolvedTheme !== 'light';
  document.documentElement.classList.toggle('dark', dark);
  document.body.classList.toggle('nd-dark', dark);
});

// Element Plus 组件语言随 i18n locale 联动
const epLocale = computed(() => (locale.value === 'en-US' ? en : zhCn));
</script>

<template>
  <el-config-provider :locale="epLocale" :size="appStore.size">
    <router-view />
  </el-config-provider>
</template>
