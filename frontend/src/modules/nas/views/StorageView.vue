<script setup>
/** 存储卷：Array Operation 卡 + 阵列设备表 + 卷/数据卷 + 拓扑树（后端 + 演示回退） */
import { computed, ref } from 'vue';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UPop from '../components/UPop.vue';

defineOptions({ name: 'NasStorage' });

// 权限铁律：设置类操作仅管理员；非管理员不渲染阵列操作卡
const identity = useIdentityStore();
identity.ensure();

// 初始值用空骨架，避免首帧向非管理员闪现演示阵列操作卡；mock 仅由适配层在 live:false 整页回退
const { data: s, lastUpdated } = useViewData(nasData.fetchStorage, nasData.emptyStorage());

const stopConfirmOpen = ref(false);
/** 手动「停止阵列」后的本地覆盖（联调阶段不动后端状态） */
const stoppedOverride = ref(null);
const arrayRunning = computed(() => stoppedOverride.value ?? s.value.array?.running ?? false);

/** 移动端卡片展示的代表性设备（正常/警告/缓存各一） */
const mobileCards = computed(() =>
  [s.value.devices[0], s.value.devices[2], s.value.devices[4]].filter(Boolean)
);

function stopArray() {
  stoppedOverride.value = false;
}
</script>

<template>
  <section>
    <u-page-header
      title="存储卷"
      sub="阵列设备 · 卷"
      :tag="{ type: arrayRunning ? 'ok' : 'warn', text: arrayRunning ? '运行中' : '无阵列' }"
      :updated="lastUpdated"
    />

    <!-- 阵列操作卡：写操作入口仅管理员可见（后端仍有最终校验） -->
    <div v-if="identity.canWrite && s.array" class="wg">
      <div class="wg-b opcard" style="padding: 15px 16px">
        <span class="odot" :class="{ off: !arrayRunning }" />
        <div class="ot">
          <b>{{ arrayRunning ? '阵列运行中' : '阵列已停止' }}</b>
          <small class="num"
            >{{ s.array.name }} · {{ s.array.level }} · {{ s.array.totalText }} ·
            {{ s.array.membersText }} · {{ s.array.activityText }}</small
          >
        </div>
        <div class="oa">
          <button class="btn"><u-icon name="refresh" />校验 Parity</button>
          <button class="btn go" :disabled="arrayRunning"><u-icon name="play" />启动阵列</button>
          <u-pop
            v-model="stopConfirmOpen"
            ok-text="停止阵列"
            cancel-text="取消"
            danger
            @confirm="stopArray"
          >
            <template #trigger>
              <button class="btn stop" :disabled="!arrayRunning">
                <u-icon name="power" />停止阵列
              </button>
            </template>
            确认停止阵列？将卸载所有卷并停止 {{ s.array.name }}。
          </u-pop>
        </div>
      </div>
    </div>

    <!-- 阵列卡信息（storcli MegaRAID 或 HBA 直通） -->
    <div v-if="s.arrayController" class="wg">
      <div class="wg-h">
        <u-icon name="array" />
        <h3>阵列卡</h3>
        <span class="x">
          <span class="tag" :class="s.arrayController.mode === 'hba' ? 'acc' : 'ok'">
            <span class="dot" />{{ s.arrayController.mode === 'hba' ? 'HBA 直通' : 'MegaRAID' }}
          </span>
        </span>
      </div>
      <div class="wg-b">
        <div class="chips" style="cursor: default">
          <button class="btn sm">型号：{{ s.arrayController.model }}</button>
          <button v-if="s.arrayController.driver" class="btn sm">
            驱动：{{ s.arrayController.driver }}
          </button>
          <button v-if="s.arrayController.cachevault" class="btn sm">
            CacheVault：{{ s.arrayController.cachevault }}
          </button>
        </div>
        <div v-if="s.arrayController.note" class="small muted" style="margin-top: 10px">
          {{ s.arrayController.note }}
        </div>
      </div>
    </div>

    <!-- 阵列设备表 -->
    <div class="wg">
      <div class="wg-h">
        <u-icon name="drive" />
        <h3>阵列设备</h3>
        <span class="x">温度阈值：40 °C 偏高 · 50 °C 过热</span>
      </div>
      <div class="tscroll m-hide">
        <table class="u">
          <thead>
            <tr>
              <th>设备</th>
              <th>盘位</th>
              <th>文件系统</th>
              <th class="r">温度</th>
              <th class="r">读取</th>
              <th class="r">写入</th>
              <th style="min-width: 190px">容量</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="dev in s.devices" :key="dev.name">
              <td>
                <span class="cav" :class="dev.name.startsWith('nvme') ? 'c3' : 'c1'">{{
                  dev.name.startsWith('nvme') ? 'n' : 's'
                }}</span>
                <b>{{ dev.name }}</b> · {{ dev.model }}
              </td>
              <td class="num">{{ dev.slot }}</td>
              <td>
                <span class="fsbadge">{{ dev.fs }}</span>
              </td>
              <td class="r num" :class="dev.tempC != null && dev.tempC >= 45 ? 't-warn' : 't-ok'">
                {{ dev.tempC != null ? `${dev.tempC} °C` : '—' }}
              </td>
              <td class="r num">{{ dev.readText }}</td>
              <td class="r num">{{ dev.writeText }}</td>
              <td>
                <div class="meter thin" style="max-width: 180px">
                  <i :class="dev.meterClass" :style="{ width: `${dev.meterPercent}%` }" />
                </div>
                <span class="small muted num">{{ dev.capacityText }}</span>
              </td>
              <td>
                <span class="st" :class="dev.status.startsWith('警告') ? 'warn' : ''"
                  ><span class="dot" />{{ dev.status }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- 移动端卡片 -->
      <div class="m-cards" style="padding: 10px 12px 12px">
        <div v-for="dev in mobileCards" :key="dev.name" class="sec" style="margin-bottom: 9px">
          <div class="wg-b" style="padding: 12px">
            <div style="display: flex; justify-content: space-between; margin-bottom: 6px">
              <b>{{ dev.name }} · {{ dev.model.split(' ').pop() }}</b>
              <span class="st" :class="dev.status.startsWith('警告') ? 'warn' : ''"
                ><span class="dot" />{{ dev.status }}</span
              >
            </div>
            <div class="small muted num" style="margin-bottom: 8px">
              盘位 {{ dev.slot }} · {{ dev.fs }} · {{ dev.tempC }} °C · {{ dev.readText }}
              {{ dev.writeText }}
            </div>
            <div class="meter thin">
              <i :class="dev.meterClass" :style="{ width: `${dev.meterPercent}%` }" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 卷 / 数据卷 -->
    <div class="grid" style="margin-bottom: 0">
      <div v-if="s.volume" class="wg t6">
        <div class="wg-h">
          <u-icon name="layers" />
          <h3>卷 {{ s.volume.name }}</h3>
          <span class="x"
            ><span class="st"><span class="dot" />已挂载</span></span
          >
        </div>
        <div class="wg-b">
          <div
            class="num"
            style="display: flex; justify-content: space-between; margin-bottom: 7px"
          >
            <b>{{ s.volume.usedText }}</b
            ><b>{{ s.volume.percent }}%</b>
          </div>
          <div class="meter"><i class="c-ok" :style="{ width: `${s.volume.percent}%` }" /></div>
          <div class="kv2" style="margin-top: 10px">
            <div class="kvrow kvline">
              <span class="muted small">文件系统</span><span class="small">{{ s.volume.fs }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">挂载点</span
              ><span class="small num">{{ s.volume.mount }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="s.dataVolume" class="wg t6">
        <div class="wg-h">
          <u-icon name="cloud" />
          <h3>数据卷 {{ s.dataVolume.name }}</h3>
          <span class="x"
            ><span class="st"><span class="dot" />实时</span></span
          >
        </div>
        <div class="wg-b">
          <div
            class="num"
            style="display: flex; justify-content: space-between; margin-bottom: 7px"
          >
            <b>{{ s.dataVolume.usedText }}</b
            ><b>{{ s.dataVolume.percent }}%</b>
          </div>
          <div class="meter">
            <i class="c-ok" :style="{ width: `${s.dataVolume.percent}%` }" />
          </div>
          <div class="kv2" style="margin-top: 10px">
            <div class="kvrow kvline">
              <span class="muted small">文件系统</span
              ><span class="small">{{ s.dataVolume.fs }}</span>
            </div>
            <div class="kvrow kvline">
              <span class="muted small">挂载点</span
              ><span class="small num">{{ s.dataVolume.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 拓扑树（真实阵列/卷/盘构成；无数据源的节点不虚构） -->
    <div v-if="s.array || s.volume || s.devices.length" class="wg" style="margin-top: 14px">
      <div class="wg-h">
        <u-icon name="array" />
        <h3>存储拓扑</h3>
      </div>
      <div class="wg-b">
        <div class="tree">
          <div v-if="s.array" class="row">
            <u-icon name="server" :style="{ color: 'var(--acc)' }" />
            <span class="nd">{{ s.array.name }}</span
            ><span class="sub">{{ s.array.level }} · {{ s.array.totalText }}</span>
          </div>
          <ul v-if="s.array">
            <li>
              <div class="row">
                <u-icon name="layers" :style="{ color: 'var(--purp)' }" />
                <span class="nd">{{ s.volume?.name ?? '未挂载卷' }}</span
                ><span class="sub">{{ s.volume ? `${s.volume.fs} · ${s.volume.usedText}` : '—' }}</span>
              </div>
              <ul>
                <li v-for="dev in s.devices.slice(0, 8)" :key="dev.name">
                  <div class="row">
                    <span
                      class="ddot"
                      :style="{
                        background: dev.status.startsWith('警告') ? 'var(--warn)' : 'var(--ok)',
                      }"
                    />
                    {{ dev.name }}
                    <span class="sub"
                      >盘位 {{ dev.slot }} · {{ dev.capacityText.split(' ·')[0]
                      }}{{ dev.status.startsWith('警告') ? ' · 警告' : '' }}</span
                    >
                  </div>
                </li>
              </ul>
            </li>
          </ul>
          <div v-else-if="s.devices.length" class="row">
            <u-icon name="drive" :style="{ color: 'var(--info)' }" />
            <span class="nd">直连盘</span
            ><span class="sub">{{ s.devices.length }} 块 · 无阵列</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
