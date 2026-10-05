<script setup>
/** 存储卷：Array Operation 卡 + 阵列设备表 + 卷/数据卷 + 拓扑树（后端 + 演示回退） */
import { computed, ref } from 'vue';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { emptyStorage, fetchStorage } from '../services/storage';
import UPageHeader from '../components/UPageHeader.vue';
import UPop from '../components/UPop.vue';
// unplugin 只扫 src/components：nas 组件须显式 import（此前 u-icon 未导入，图标从未渲染）
import UIcon from '../components/UIcon.vue';

defineOptions({ name: 'NasStorage' });

// 权限铁律：设置类操作仅管理员；非管理员不渲染阵列操作卡
const identity = useIdentityStore();
identity.ensure();

// 初始值用空骨架，避免首帧向非管理员闪现演示阵列操作卡；mock 仅由适配层在 live:false 整页回退
const { data: s, lastUpdated } = useViewData(fetchStorage, emptyStorage());

const stopConfirmOpen = ref(false);
/** 手动「停止阵列」后的本地覆盖（联调阶段不动后端状态） */
const stoppedOverride = ref(null);
const arrayRunning = computed(() => stoppedOverride.value ?? s.value.array?.running ?? false);

/** 移动端卡片展示的代表性设备（正常/警告/缓存各一） */
const mobileCards = computed(() =>
  [s.value.devices[0], s.value.devices[2], s.value.devices[4]].filter(Boolean)
);

// ---- 存储拓扑（真实层级；适配层已组装 arrays/standalone，见 data.js fetchStorage）----
const topo = computed(() => s.value.topology ?? { controller: null, arrays: [], standalone: [] });
const topoHasNodes = computed(
  () => !!(topo.value.controller || topo.value.arrays.length || topo.value.standalone.length)
);
/** 根节点：阵列卡/软阵列/无阵列直连三种形态 */
const topoRoot = computed(() => {
  const c = topo.value.controller;
  if (!c && topo.value.arrays.length) {
    return { icon: 'server', color: 'var(--acc)', label: '软阵列', sub: '内核 md (mdadm)' };
  }
  if (!c) {
    return {
      icon: 'drive',
      color: 'var(--info)',
      label: '直连盘',
      sub: `${topo.value.standalone.length} 块 · 无阵列`,
    };
  }
  if (c.mode === 'soft') {
    return { icon: 'server', color: 'var(--acc)', label: '软阵列', sub: '内核 md (mdadm)' };
  }
  return {
    icon: 'server',
    color: 'var(--acc)',
    label: c.model || (c.mode === 'hba' ? 'HBA 直通' : '阵列卡'),
    sub: c.mode === 'hba' ? 'HBA 直通' : 'MegaRAID',
  };
});

function arrSub(arr) {
  return [arr.levelText, arr.sizeText, arr.state, !arr.healthy ? '降级' : null]
    .filter(Boolean)
    .join(' · ');
}
function memberDot(m) {
  if (m.failed) return 'var(--bad)';
  if (m.hotspare) return 'var(--info)';
  return 'var(--ok)';
}
function memberSub(m) {
  return [m.model, m.sizeText, m.state].filter(Boolean).join(' · ');
}
function diskDot(health) {
  if (health === 'failing') return 'var(--bad)';
  if (health === 'warning') return 'var(--warn)';
  return health === 'passed' ? 'var(--ok)' : 'var(--tx3)';
}
function diskSub(disk) {
  return [disk.model, disk.sizeText, disk.tempC != null ? `${disk.tempC} °C` : null, disk.alias]
    .filter(Boolean)
    .join(' · ');
}
function partSub(p) {
  return [p.fstype ? p.fstype.toUpperCase() : null, p.sizeText, p.mountpoint]
    .filter(Boolean)
    .join(' · ');
}

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
              <td class="num">{{ dev.slot ?? '—' }}</td>
              <td>
                <span v-if="dev.role" class="fsbadge">{{ dev.role }}</span>
                <span v-else-if="dev.alias" class="fsbadge">{{ dev.alias }}</span>
                <span v-else-if="dev.fsText" class="fsbadge">{{ dev.fsText }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td class="r num" :class="dev.tempC != null && dev.tempC >= 45 ? 't-warn' : 't-ok'">
                {{ dev.tempC != null ? `${dev.tempC} °C` : '—' }}
              </td>
              <td class="r num">{{ dev.readText }}</td>
              <td class="r num">{{ dev.writeText }}</td>
              <td>
                <div v-if="dev.usagePercent != null" class="meter thin" style="max-width: 180px">
                  <i :class="dev.usageClass" :style="{ width: `${dev.usagePercent}%` }" />
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
              {{ dev.role || dev.alias || dev.fsText || '—' }} ·
              {{ dev.tempC != null ? `${dev.tempC} °C` : '温度 —' }} · {{ dev.readText }}
              {{ dev.writeText }}
            </div>
            <div v-if="dev.usagePercent != null" class="meter thin">
              <i :class="dev.usageClass" :style="{ width: `${dev.usagePercent}%` }" />
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
            <div class="kvrow kvline">
              <span class="muted small">写满预测</span>
              <span class="small" :class="s.volume.forecast?.warn ? 't-warn' : ''">
                {{ s.volume.forecast?.text || '—' }}
              </span>
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
            <div class="kvrow kvline">
              <span class="muted small">写满预测</span>
              <span class="small" :class="s.dataVolume.forecast?.warn ? 't-warn' : ''">
                {{ s.dataVolume.forecast?.text || '—' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 存储拓扑：控制器→阵列→成员盘/分区→挂载点，层级边均为真实数据（契约 §2.5/§2.8 v2.3.5） -->
    <div v-if="topoHasNodes" class="wg" style="margin-top: 14px">
      <div class="wg-h">
        <u-icon name="array" />
        <h3>存储拓扑</h3>
      </div>
      <div class="wg-b">
        <div class="tree" style="overflow-x: auto">
          <div class="row">
            <u-icon :name="topoRoot.icon" :style="{ color: topoRoot.color }" />
            <span class="tn">{{ topoRoot.label }}</span>
            <span class="sub">{{ topoRoot.sub }}</span>
          </div>
          <ul v-if="topo.arrays.length || topo.standalone.length">
            <!-- 阵列：硬件 VD（成员=物理盘，槽位 E:S）与软阵列 md（成员=分区） -->
            <li v-for="arr in topo.arrays" :key="'a' + arr.key">
              <div class="row">
                <u-icon
                  name="layers"
                  :style="{ color: arr.healthy ? 'var(--purp)' : 'var(--bad)' }"
                />
                <span class="tn">{{ arr.name }}</span>
                <span class="sub">{{ arrSub(arr) }}</span>
              </div>
              <div v-if="arr.sync" style="margin: 6px 0 2px">
                <div class="small num" style="margin-bottom: 4px">
                  {{ arr.sync.text
                  }}<template v-if="arr.sync.finishText">
                    · 预计剩余 {{ arr.sync.finishText }}</template
                  >
                  <template v-if="arr.sync.speedText"> · {{ arr.sync.speedText }}</template>
                </div>
                <div class="bar stripes">
                  <i :style="{ width: `${arr.sync.percent ?? 3}%` }" />
                </div>
              </div>
              <ul v-if="arr.members.length || arr.volume">
                <li v-for="(m, mi) in arr.members" :key="mi">
                  <div class="row">
                    <span class="ddot" :style="{ background: memberDot(m) }" />
                    <span class="tn">{{ m.label }}</span>
                    <span class="sub">{{ memberSub(m) }}</span>
                    <span v-if="m.hotspare" class="fsbadge">热备</span>
                  </div>
                </li>
                <li v-if="arr.volume">
                  <div class="row">
                    <u-icon name="layers" :style="{ color: 'var(--info)' }" />
                    <span class="tn">{{ arr.volume.mount }}</span>
                    <span class="sub">
                      {{ [arr.volume.fs, arr.volume.usedText].filter(Boolean).join(' · ') }}
                    </span>
                  </div>
                </li>
              </ul>
            </li>
            <!-- 直连/未归属盘：分区与挂载点为叶子 -->
            <li v-for="disk in topo.standalone" :key="'d' + disk.name">
              <div class="row">
                <span class="ddot" :style="{ background: diskDot(disk.health) }" />
                <span class="tn">{{ disk.name }}</span>
                <span class="sub">{{ diskSub(disk) }}</span>
              </div>
              <ul v-if="disk.partitions.length">
                <li v-for="p in disk.partitions" :key="p.name">
                  <div class="row">
                    <span class="tn" style="font-weight: 500">{{ p.name }}</span>
                    <span class="sub">{{ partSub(p) }}</span>
                  </div>
                </li>
              </ul>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </section>
</template>
