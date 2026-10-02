<script setup>
/** 硬盘 SMART：健康状态表 + 在线自检下拉 + 进行中自检进度（后端 + 演示回退） */
import { computed, reactive } from 'vue';
import { apiData } from '../api/client';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UDropdown from '../components/UDropdown.vue';

defineOptions({ name: 'NasDisks' });

// 权限铁律：设置类操作仅管理员；非管理员不渲染自检入口（写操作 POST /self-tests）
const identity = useIdentityStore();
identity.ensure();

// 初始值用空骨架（mock 只在 live:false 整页演示时由适配层回退），避免首帧闪现假自检
const { data: d, live, refresh, lastUpdated } = useViewData(nasData.fetchDisks, {
  list: [],
  selftest: null,
});

/** 每行独立的自检菜单开合状态 */
const menuOpen = reactive({});

/** 发起自检（POST /storage/self-tests），演示模式下仅收起菜单 */
async function runSelftest(row, type = 'short') {
  menuOpen[row.slot] = false;
  if (!identity.canWrite) return;
  if (!live.value || !row.device) return;
  try {
    await apiData('/api/v1/storage/self-tests', {
      method: 'POST',
      body: { device: row.device, type },
    });
    await refresh();
  } catch {
    /* 互斥 1005 等错误静默，状态由刷新体现 */
  }
}

const headerTag = computed(() => {
  const warned = d.value.list.filter((x) => x.health !== '正常').length;
  if (!live.value) return { type: 'acc', text: '演示数据' };
  return { type: warned ? 'warn' : 'ok', text: warned ? `${warned} 块警告` : '全部正常' };
});
</script>

<template>
  <section>
    <u-page-header title="硬盘 SMART" sub="健康状态 · 自检" :tag="headerTag" :updated="lastUpdated" />

    <!-- 桌面表格 -->
    <div class="wg m-hide">
      <div class="tscroll">
        <table class="u">
          <thead>
            <tr>
              <th>盘位</th>
              <th>型号</th>
              <th class="r">容量</th>
              <th class="r">转速</th>
              <th class="r">温度</th>
              <th class="r">通电时间</th>
              <th>健康</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="disk in d.list" :key="disk.slot">
              <td class="num">{{ disk.slot }}</td>
              <td>
                <b>{{ disk.model }}</b>
              </td>
              <td class="r num">{{ disk.capacity }}</td>
              <td class="r num">{{ disk.rpm }}</td>
              <td class="r num" :class="disk.tempC >= 45 ? 't-warn' : 't-ok'">
                {{ disk.tempC }} °C
              </td>
              <td class="r num">{{ disk.hours }}</td>
              <td>
                <span class="st" :class="disk.health.startsWith('警告') ? 'warn' : ''"
                  ><span class="dot" />{{ disk.health }}</span
                >
              </td>
              <td>
                <!-- 写操作仅管理员：不渲染而非禁用（后端仍有最终校验） -->
                <u-dropdown v-if="identity.canWrite" v-model="menuOpen[disk.slot]" :min-width="190">
                  <template #trigger>
                    <button class="btn sm">
                      自检<svg class="ico" style="width: 11px; height: 11px">
                        <use href="#nd-i-chevd" />
                      </svg>
                    </button>
                  </template>
                  <button @click="runSelftest(disk, 'short')">
                    <u-icon name="pulse" />短自检（B · 约 2 分钟）
                  </button>
                  <button @click="runSelftest(disk, 'long')">
                    <u-icon name="clock" />长自检（C · 约 4 小时）
                  </button>
                  <button @click="runSelftest(disk, 'conveyance')">
                    <u-icon name="refresh" />短修复（A · 离线）
                  </button>
                </u-dropdown>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 移动端卡片 -->
    <div class="m-cards">
      <div v-for="disk in d.list" :key="disk.slot" class="wg" style="margin-bottom: 10px">
        <div class="wg-b">
          <div style="display: flex; justify-content: space-between; margin-bottom: 7px">
            <b>盘位 {{ disk.slot }} · {{ disk.model.split(' ').pop() }}</b>
            <span class="st" :class="disk.health.startsWith('警告') ? 'warn' : ''"
              ><span class="dot" />{{ disk.health }}</span
            >
          </div>
          <div class="small muted num">
            {{ disk.capacity }} · {{ disk.rpm }} · {{ disk.tempC }} °C · {{ disk.hours }}
          </div>
          <div class="chips" style="margin-top: 10px">
            <!-- 写操作仅管理员：不渲染而非禁用 -->
            <u-dropdown v-if="identity.canWrite" v-model="menuOpen[disk.slot]" :min-width="190">
              <template #trigger>
                <button class="btn sm">自检 ▾</button>
              </template>
              <button @click="runSelftest(disk, 'short')">
                <u-icon name="pulse" />短自检（B · 约 2 分钟）
              </button>
              <button @click="runSelftest(disk, 'long')">
                <u-icon name="clock" />长自检（C · 约 4 小时）
              </button>
              <button @click="runSelftest(disk, 'conveyance')">
                <u-icon name="refresh" />短修复（A · 离线）
              </button>
            </u-dropdown>
          </div>
        </div>
      </div>
    </div>

    <!-- 进行中的自检（无自检任务 = 合法真值：整卡隐藏，不显示假进度） -->
    <div v-if="d.selftest" class="wg" style="margin-top: 14px">
      <div class="wg-h">
        <u-icon name="pulse" />
        <h3>进行中的自检</h3>
      </div>
      <div class="wg-b">
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px">
          <span>{{ d.selftest.label }}</span
          ><b class="num">{{ d.selftest.percent }}%</b>
        </div>
        <div class="bar stripes"><i :style="{ width: `${d.selftest.percent}%` }" /></div>
        <div class="small muted" style="margin-top: 9px">
          自检类型：A 短修 / B 短检 / C 长检 · 完成后健康状态在本页更新
        </div>
      </div>
    </div>
  </section>
</template>
