<script setup>
/**
 * UNRAID 风格主布局：顶部横向页签导航（分组）+ 居中单列内容。
 * 左上角菜单按钮切换「完整样式 ↔ 纯图标」页签；右上角搜索/通知/主题/用户。
 */
import { nextTick, onBeforeUnmount, ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAppStore } from '@/stores/modules/app';
import { useUserStore } from '@/stores/modules/user';
import { usePermissionStore } from '@/stores/modules/permission';
import { navGroups, activeAlerts as mockAlerts } from '@/modules/nas/mock';
import { useViewData } from '@/modules/nas/composables/useViewData';
import { fetchActiveAlerts } from '@/modules/nas/api/data';
import IconSprite from '@/modules/nas/components/IconSprite.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';
import UDropdown from '@/modules/nas/components/UDropdown.vue';

defineOptions({ name: 'UnraidLayout' });

const NAV_ICONS_KEY = 'nd_nav_icons';

const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const userStore = useUserStore();
const permissionStore = usePermissionStore();

/** 通知铃数据：后端 firing 事件，不可达回退演示值 */
const { data: activeAlerts } = useViewData(fetchActiveAlerts, mockAlerts);

const cachedViews = computed(() => permissionStore.cachedViews);

/** 页签纯图标模式（localStorage 持久化） */
const iconsMode = ref(localStorage.getItem(NAV_ICONS_KEY) === '1');

function toggleIconsMode() {
  iconsMode.value = !iconsMode.value;
  localStorage.setItem(NAV_ICONS_KEY, iconsMode.value ? '1' : '0');
}

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
  if (first) router.push(first.path);
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
document.addEventListener('click', onDocClick);
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));

function jump(path) {
  bellOpen.value = false;
  router.push(path);
}

/** 退出登录：清理本地状态后回登录页 */
async function logout() {
  await userStore.logout();
  router.push('/login');
}
</script>

<template>
  <div class="nd" :data-theme="appStore.theme">
    <icon-sprite />

    <div class="nav" :class="{ icons: iconsMode }">
      <button
        class="iconbtn"
        :title="iconsMode ? '页签：纯图标（点击切换完整样式）' : '页签：完整样式（点击切换纯图标）'"
        @click="toggleIconsMode"
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
            <span class="b">{{ activeAlerts.length }}</span>
          </button>
        </span>

        <button
          class="iconbtn"
          :title="appStore.theme === 'dark' ? '切换到白主题' : '切换到黑主题'"
          @click="appStore.toggleTheme()"
        >
          <u-icon :name="appStore.theme === 'dark' ? 'moon' : 'sun'" />
        </button>

        <u-dropdown :min-width="150">
          <template #trigger>
            <span class="avatar" :title="userStore.nickname">
              {{ (userStore.nickname || 'u').slice(0, 1) }}
            </span>
          </template>
          <template #default>
            <button @click="router.push('/nasdeck/about')">
              <u-icon name="info" />{{ userStore.nickname }}
            </button>
            <hr />
            <button class="danger" @click="logout"><u-icon name="power" />退出登录</button>
          </template>
        </u-dropdown>
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
        <button @click="jump('/nasdeck/automation')">查看全部告警与规则</button>
      </div>
    </div>

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
