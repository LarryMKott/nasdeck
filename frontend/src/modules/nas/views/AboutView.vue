<script setup>
/** 关于：品牌信息 + 检查更新 + 构建信息（后端 /system/info + 演示回退） */
import { computed } from 'vue';
import { about as mockAbout } from '../mock';
import { useViewData } from '../composables/useViewData';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';

defineOptions({ name: 'NasAbout' });

const { data: d, live } = useViewData(nasData.fetchAbout, mockAbout);
const headerTag = computed(() =>
  live.value ? { type: 'ok', text: '后端已连接' } : { type: 'acc', text: '演示数据' }
);
</script>

<template>
  <section>
    <u-page-header title="关于 nasdeck" sub="版本 · 更新 · 构建信息" :tag="headerTag" />

    <div class="grid" style="margin-bottom: 0">
      <div class="wg t6">
        <div class="wg-b brandhero">
          <span class="mark">
            <svg viewBox="0 0 24 24">
              <rect x="6" y="4.5" width="12" height="3.4" rx="1.7" />
              <rect x="6" y="10.3" width="7.5" height="3.4" rx="1.7" />
              <rect x="6" y="16.1" width="12" height="3.4" rx="1.7" />
            </svg>
          </span>
          <div>
            <div class="nm">
              nasdeck<span class="ver">{{ d.version }}</span>
            </div>
            <div class="ds">{{ d.desc }}</div>
            <div class="num muted small" style="margin-top: 5px">{{ d.slogan }}</div>
          </div>
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="refresh" />
          <h3>检查更新</h3>
        </div>
        <div class="wg-b">
          <div class="kv2">
            <div class="kvrow kvline">
              <span class="muted small">当前版本</span
              ><span class="small num">{{ d.version }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">最新版本</span>
              <span class="small st"><span class="dot" />{{ d.version }}（已是最新）</span>
            </div>
          </div>
          <div class="chips" style="margin-top: 12px">
            <button class="btn sm pri">检查更新</button>
            <button class="btn sm">更新日志</button>
          </div>
        </div>
      </div>

      <div class="wg t12">
        <div class="wg-h">
          <u-icon name="info" />
          <h3>构建信息</h3>
        </div>
        <div class="wg-b">
          <div class="kv2" style="grid-template-columns: repeat(4, 1fr)">
            <div
              v-for="(row, i) in d.build"
              :key="row[0]"
              class="kvrow"
              :class="i < d.build.length - 1 ? 'kvline' : ''"
            >
              <span class="muted small">{{ row[0] }}</span>
              <span class="small num">{{ row[1] }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
