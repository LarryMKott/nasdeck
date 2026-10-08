<script setup>
/**
 * UNRAID 风格主布局：顶部横向页签导航（分组）+ 居中单列内容。
 * 左上角菜单按钮切换「完整样式 ↔ 纯图标」页签；右上角搜索/通知/主题/用户。
 */
import { nextTick, onBeforeUnmount, ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAppStore } from '@/stores/modules/app';
import { useUserStore } from '@/stores/modules/user';
import { usePermissionStore } from '@/stores/modules/permission';
import { useIdentityStore } from '@/modules/nas/stores/identity';
import { navGroups, activeAlerts as mockAlerts } from '@/modules/nas/mock';
import { useViewData } from '@/modules/nas/composables/useViewData';
import { fetchActiveAlerts } from '@/modules/nas/services/automation';
import IconSprite from '@/modules/nas/components/IconSprite.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';
import NDanmaku from '@/modules/nas/components/NDanmaku.vue';
import UCommandPalette from '@/modules/nas/components/UCommandPalette.vue';
import { refreshChartColors } from '@/modules/nas/utils/themeColors';

defineOptions({ name: 'UnraidLayout' });

const NAV_ICONS_KEY = 'nd_nav_icons';

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const userStore = useUserStore();
const permissionStore = usePermissionStore();
// 头像身份：管理员带标识 + 点击进设置页；普通用户点击进关于页
const identity = useIdentityStore();
identity.ensure();

// 图表色板随皮肤切换刷新（canvas 不吃 CSS 变量，需 JS 读取）
import { watch as vueWatch } from 'vue';
vueWatch(
  () => appStore.resolvedTheme,
  () => refreshChartColors(),
  { immediate: true }
);

const avatarTitle = computed(() =>
  identity.canWrite
    ? `${userStore.nickname || '用户'} · 管理员（设置）`
    : userStore.nickname || '用户'
);

// 事件弹幕开关（花活 H）：localStorage 持久化，切给 NDanmaku 的 CustomEvent 通知
const danmakuOn = ref(localStorage.getItem('nd_danmaku') === '1');
function toggleDanmaku() {
  danmakuOn.value = !danmakuOn.value;
  localStorage.setItem('nd_danmaku', danmakuOn.value ? '1' : '0');
  window.dispatchEvent(new CustomEvent('nd-danmaku-toggle', { detail: danmakuOn.value }));
}

// 命令面板（脑洞 E）：Ctrl+K / / 呼出；快捷动作注入
const cmdkOpen = ref(false);
const cmdkActions = computed(() => [
  {
    label: `切换主题（当前：${themeMeta.value.title.split('，')[0]}）`,
    icon: themeMeta.value.icon,
    run: () => appStore.toggleTheme(),
  },
  {
    label: `事件弹幕${danmakuOn.value ? '（点击关闭）' : '（点击开启）'}`,
    icon: 'alert',
    run: toggleDanmaku,
  },
  { label: '大屏轮播模式', icon: 'play', run: () => router.push('/nasdeck/kiosk') },
]);

function onAvatarClick() {
  router.push(identity.canWrite ? '/nasdeck/settings' : '/nasdeck/about');
}

/** 通知铃数据：后端 firing 事件，不可达回退演示值 */
const { data: activeAlerts } = useViewData(fetchActiveAlerts, mockAlerts);

const cachedViews = computed(() => permissionStore.cachedViews);

/** 页签纯图标模式（localStorage 持久化） */
const iconsMode = ref(localStorage.getItem(NAV_ICONS_KEY) === '1');

function toggleIconsMode() {
  iconsMode.value = !iconsMode.value;
  localStorage.setItem(NAV_ICONS_KEY, iconsMode.value ? '1' : '0');
}

/**
 * 响应式三档（阈值与 unraid.scss 媒体查询保持一致，15 页签实测标定）：
 * ≥1760 文本页签；1210–1759 强制纯图标（文本 15 项实测 1750 起才放得下）；
 * <1210 隐藏页签条，改用抽屉导航（小屏/手机；纯图标 15 项实测 1220 起放得下）。
 */
const mqTextTabs = window.matchMedia('(min-width: 1760px)');
const mqDrawer = window.matchMedia('(max-width: 1209px)');
const wideEnough = ref(mqTextTabs.matches);
const isNarrow = ref(mqDrawer.matches);

/** 实际图标模式：用户偏好，或中档宽度下文本页签放不下时强制 */
const effectiveIcons = computed(() => iconsMode.value || !wideEnough.value);

/** 抽屉菜单（<1100px 时经左上角按钮呼出） */
const drawerOpen = ref(false);

function openDrawer() {
  drawerOpen.value = true;
  // 抽屉展开期间锁住背景滚动
  document.body.style.overflow = 'hidden';
}

function closeDrawer() {
  if (!drawerOpen.value) return;
  drawerOpen.value = false;
  document.body.style.overflow = '';
}

function onMenuClick() {
  if (isNarrow.value) openDrawer();
  else toggleIconsMode();
}

function onMqChange() {
  wideEnough.value = mqTextTabs.matches;
  isNarrow.value = mqDrawer.matches;
  // 跨过断点回到桌面档时收起抽屉，避免残留遮罩
  if (!isNarrow.value) closeDrawer();
}

function bindMq(mq, fn) {
  // 旧版 Chromium/Safari 兼容：无 addEventListener 时退回 addListener
  if (mq.addEventListener) mq.addEventListener('change', fn);
  else mq.addListener(fn);
}

function unbindMq(mq, fn) {
  if (mq.removeEventListener) mq.removeEventListener('change', fn);
  else mq.removeListener(fn);
}

bindMq(mqTextTabs, onMqChange);
bindMq(mqDrawer, onMqChange);

// 路由切换即收起抽屉（抽屉内点击跳转后不停留在遮罩下）
watch(() => route.path, closeDrawer);

/** 页签搜索：过滤页签，回车跳首个命中 */
const searchText = ref('');
const filteredGroups = computed(() =>
  navGroups
    .map((group) => ({
      ...group,
      items: group.items.filter(
        (item) =>
          !searchText.value || item.title.toLowerCase().includes(searchText.value.toLowerCase())
      ),
    }))
    .filter((group) => group.items.length)
);

function onSearchKeydown(e) {
  if (e.key !== 'Enter') return;
  const first = filteredGroups.value[0]?.items[0];
  if (first) {
    router.push(first.path);
    closeDrawer();
  }
  searchText.value = '';
}

/** 通知下拉 */
const bellOpen = ref(false);
const bellBtnRef = ref(null);
const bellPopRef = ref(null);

async function toggleBell() {
  bellOpen.value = !bellOpen.value;
  if (!bellOpen.value) return;
  await nextTick();
  const pop = bellPopRef.value;
  const btn = bellBtnRef.value;
  if (!pop || !btn) return;
  const r = btn.getBoundingClientRect();
  const left = Math.min(r.right - pop.offsetWidth, window.innerWidth - pop.offsetWidth - 10);
  pop.style.left = `${Math.max(10, left)}px`;
  pop.style.top = `${r.bottom + 8}px`;
}

function onDocClick(e) {
  if (!e.target.closest('.nd-bell-pop') && !e.target.closest('.nd-bell-host')) {
    bellOpen.value = false;
  }
}

function onDocKeydown(e) {
  if (e.key === 'Escape') closeDrawer();
}

document.addEventListener('click', onDocClick);
document.addEventListener('keydown', onDocKeydown);
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick);
  document.removeEventListener('keydown', onDocKeydown);
  unbindMq(mqTextTabs, onMqChange);
  unbindMq(mqDrawer, onMqChange);
  closeDrawer();
});

function jump(path) {
  bellOpen.value = false;
  closeDrawer();
  router.push(path);
}

/** 主题按钮：图标反映当前模式，提示语说明点击后的去向（dark → light → system → fnos → cyber → terminal 循环）。
 * system=浏览器/操作系统深浅色，fnos=飞牛桌面亮暗（桌面内数秒联动）。带出解析结果：
 * 与期望不符时可一眼定位信号源——fnos 档未接入桌面宿主（独立页签打开）时注明回退口径 */
const themeMeta = computed(() => {
  const resolved = appStore.resolvedTheme === 'light' ? '浅' : '深';
  const meta = {
    dark: { icon: 'moon', title: '当前黑主题，点击切换白主题' },
    light: { icon: 'sun', title: '当前白主题，点击切换跟随系统' },
    system: { icon: 'monitor', title: `当前跟随系统（解析为${resolved}色），点击切换跟随飞牛` },
    fnos: {
      icon: 'cloud',
      title: appStore.hostTheme
        ? `当前跟随飞牛（桌面为${appStore.hostTheme === 'light' ? '浅' : '深'}色），点击切换赛博朋克`
        : `当前跟随飞牛（未接入桌面宿主，暂按系统偏好解析为${resolved}色），点击切换赛博朋克`,
    },
    cyber: { icon: 'pulse', title: '当前赛博朋克，点击切换终端绿' },
    terminal: { icon: 'server', title: '当前终端绿 CRT，点击切换黑主题' },
  };
  return meta[appStore.theme] || meta.dark;
});
</script>

<template>
  <!-- 纯图标类须加在 .nd 根容器（unraid.scss 的 &.nav-icons 编译为 .nd.nav-icons）：
       此前绑定在 .nav 上且类名不匹配，切换从未生效 -->
  <div class="nd" :data-theme="appStore.resolvedTheme" :class="{ 'nav-icons': effectiveIcons }">
    <icon-sprite />
    <n-danmaku />
    <u-command-palette v-model="cmdkOpen" :actions="cmdkActions" />

    <div class="nav">
      <button
        v-if="wideEnough || isNarrow"
        class="iconbtn"
        :title="
          isNarrow
            ? '打开导航菜单'
            : iconsMode
              ? '页签：纯图标（点击切换完整样式）'
              : '页签：完整样式（点击切换纯图标）'
        "
        :aria-expanded="isNarrow ? drawerOpen : undefined"
        @click="onMenuClick"
      >
        <u-icon name="menu" />
      </button>

      <div class="brand">
        <span class="logo">
          <svg viewBox="0 0 24 24">
            <rect x="6" y="4.5" width="12" height="3.4" rx="1.7" />
            <rect x="6" y="10.3" width="7.5" height="3.4" rx="1.7" />
            <rect x="6" y="16.1" width="12" height="3.4" rx="1.7" />
          </svg>
        </span>
        nasdeck
      </div>

      <nav class="tabs">
        <div v-for="(group, gi) in filteredGroups" :key="gi" class="tgroup">
          <button
            v-for="item in group.items"
            :key="item.path"
            class="tab"
            :class="{ on: route.path === item.path }"
            :title="item.title"
            @click="router.push(item.path)"
          >
            <u-icon :name="item.icon" />
            <span class="lbl">{{ item.title }}</span>
            <span v-if="item.badge" class="n" :class="{ hot: item.badgeHot }">{{
              item.badge
            }}</span>
          </button>
        </div>
      </nav>

      <div class="hd-x">
        <div class="search">
          <u-icon name="search" />
          <input
            v-model="searchText"
            type="text"
            placeholder="搜索页签"
            @keydown="onSearchKeydown"
          />
        </div>

        <span class="nd-bell-host">
          <button class="iconbtn" title="通知" @click.stop="toggleBell">
            <u-icon name="bell" />
            <span v-if="activeAlerts.length" class="b">{{ activeAlerts.length }}</span>
          </button>
        </span>

        <button class="iconbtn" :title="themeMeta.title" @click="appStore.toggleTheme()">
          <u-icon :name="themeMeta.icon" />
        </button>

        <!-- 头像：管理员带盾徽标识，点击进设置页（普通用户进关于页） -->
        <button
          class="avatar"
          :class="{ admin: identity.canWrite }"
          :title="avatarTitle"
          @click="onAvatarClick"
        >
          {{ (userStore.nickname || 'u').slice(0, 1) }}
          <svg v-if="identity.canWrite" class="adm-badge" aria-hidden="true">
            <use href="#nd-i-shield" />
          </svg>
        </button>
      </div>
    </div>

    <!-- 通知下拉 -->
    <div ref="bellPopRef" class="popmenu nd-bell-pop" :class="{ show: bellOpen }">
      <div class="pm-h">活动告警 · {{ activeAlerts.length }}</div>
      <button
        v-for="(alert, i) in activeAlerts"
        :key="i"
        class="pm-i"
        @click="jump(alert.jump.path)"
      >
        <svg class="ico" style="margin-top: 2px; color: var(--warn)">
          <use href="#nd-i-alert" />
        </svg>
        <span>
          <span class="t">{{ alert.text }}</span>
          <span class="d">{{ alert.time }} · {{ alert.jump.action }}</span>
        </span>
      </button>
      <div class="pm-f">
        <button @click="toggleDanmaku">
          <u-icon :name="danmakuOn ? 'check' : 'x'" />事件弹幕：{{
            danmakuOn ? '已开启' : '已关闭'
          }}
        </button>
        <button @click="jump('/nasdeck/automation')">查看全部告警与规则</button>
      </div>
    </div>

    <!-- 小屏抽屉导航（<1100px）：遮罩 + 左滑面板，Esc/遮罩/选中项均可关闭；
         关闭态加 inert——面板虽移出屏外但仍可被读屏/Tab 聚焦到 -->
    <div class="ndrawer-back" :class="{ show: drawerOpen }" @click="closeDrawer" />
    <aside
      class="ndrawer"
      :class="{ show: drawerOpen }"
      role="dialog"
      aria-modal="true"
      aria-label="导航菜单"
      :inert="!drawerOpen"
    >
      <div class="ndrawer-h">
        <span class="brand">
          <span class="logo">
            <svg viewBox="0 0 24 24">
              <rect x="6" y="4.5" width="12" height="3.4" rx="1.7" />
              <rect x="6" y="10.3" width="7.5" height="3.4" rx="1.7" />
              <rect x="6" y="16.1" width="12" height="3.4" rx="1.7" />
            </svg>
          </span>
          nasdeck
        </span>
        <button class="iconbtn" title="关闭菜单" @click="closeDrawer">
          <u-icon name="x" />
        </button>
      </div>

      <div class="search ndrawer-search">
        <u-icon name="search" />
        <input v-model="searchText" type="text" placeholder="搜索页签" @keydown="onSearchKeydown" />
      </div>

      <nav class="ndrawer-nav">
        <div v-for="(group, gi) in filteredGroups" :key="gi" class="ndrawer-g">
          <button
            v-for="item in group.items"
            :key="item.path"
            class="ndrawer-i"
            :class="{ on: route.path === item.path }"
            @click="jump(item.path)"
          >
            <u-icon :name="item.icon" />
            <span>{{ item.title }}</span>
            <span v-if="item.badge" class="n" :class="{ hot: item.badgeHot }">{{
              item.badge
            }}</span>
          </button>
        </div>
      </nav>
    </aside>

    <main class="content">
      <router-view v-slot="{ Component, route: viewRoute }">
        <!-- 不用 <transition>：其 enter 流程依赖 rAF，后台节流时视图会卡在 enter-from；
             改用挂载时的纯 CSS 入场动画（nd-vin），节流环境下静态可见、优雅降级 -->
        <keep-alive :include="cachedViews">
          <component :is="Component" :key="viewRoute.path" class="nd-vin" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>
