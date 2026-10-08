<script setup>
/** Docker 舰牌墙（花活二期 M）：每容器一卡——状态环（弧 = CPU%）+ CPU/内存/磁盘 IO
 * 三实时条 + 24h 迷你趋势；firing 的 docker_exit 事件联动「意外退出」徽章（点击去
 * 事件时间线）；管理员可直接启/停/重启（后端非 GET 管理员强校验）。
 * 内存条按宿主内存总量归一（realtime 快照，缺则条隐藏显—）；IO 条按 50 MB/s 满刻度。 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { docker as mockDocker } from '../mock';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { useRealtimeStore } from '../stores/realtime';
import { fetchContainerTrend, fetchDocker } from '../services/system';
import { controlContainer } from '../api/endpoints/system';
import { getEvents } from '../api/endpoints/alert';
import UPageHeader from '../components/UPageHeader.vue';
import USpark from '../components/USpark.vue';
import UPop from '../components/UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasDocker' });

// 权限铁律：容器启/停/重启为写操作，仅管理员渲染按钮（后端仍有最终校验）
const identity = useIdentityStore();
identity.ensure();
const router = useRouter();

const { data: d, live, refresh, lastUpdated } = useViewData(fetchDocker, mockDocker);

const realtime = useRealtimeStore();
onMounted(() => realtime.acquire());
onBeforeUnmount(() => realtime.release());

const runningCount = computed(() => d.value.containers.filter((c) => c.running).length);
const headerTag = computed(() => {
  if (live.value) {
    return {
      type: 'ok',
      text: t('{a} 个运行中 · {b} 已退出', {
        a: runningCount.value,
        b: d.value.containers.length - runningCount.value,
      }),
    };
  }
  return { type: 'acc', text: t('演示数据（本机无 Docker 或后端不可达）') };
});

/** 宿主内存总量（MB）：内存条归一基准；快照缺失时内存条隐藏显"—" */
const memTotalMb = computed(() => realtime.snapshot?.mem_total_mb ?? null);

// ---- 意外退出徽章：firing 的 docker_exit 事件按容器名命中（点击去事件时间线） ----
const exitNames = ref(new Set());
onMounted(async () => {
  try {
    const evts = (await getEvents(30)) ?? [];
    const names = new Set();
    for (const e of evts) {
      if (e.metric === 'docker_exit' && e.status === 'firing') {
        const m = /容器 (.+?) 意外退出/.exec(e.message || '');
        if (m) names.add(m[1]);
      }
    }
    exitNames.value = names;
  } catch {
    /* 事件不可达：徽章不出现（合法降级，不影响容器清单） */
  }
});

// ---- 24h 迷你趋势：清单到达后逐卡懒加载一次（1m 桶）；演示回退由适配层负责 ----
const trends = reactive({}); // name → number[]（cpu 序列）
async function loadTrend(name) {
  if (trends[name] || !name) return;
  trends[name] = [];
  try {
    const r = await fetchContainerTrend(name, 24);
    trends[name] = (r.data.points ?? []).map((p) => p.cpu_percent ?? 0);
  } catch {
    trends[name] = [];
  }
}

watch(
  () => d.value.containers?.map((c) => c.name).join(','),
  (names) => {
    if (!names) return;
    d.value.containers.forEach((c) => loadTrend(c.name));
  },
  { immediate: true }
);

// ---- 状态环几何：弧长 = CPU%（>100 满环），颜色随运行状态 ----
const RING_R = 17;
const RING_C = 2 * Math.PI * RING_R;
function ringOffset(cpuPercent) {
  const pct = Math.min(100, Math.max(0, cpuPercent ?? 0));
  return RING_C * (1 - pct / 100);
}

function memPercent(c) {
  if (c.memBytes == null || !memTotalMb.value) return null;
  return Math.min(100, (c.memBytes / (memTotalMb.value * 1024 * 1024)) * 100);
}

const IO_FULL_BPS = 50 * 1024 * 1024; // IO 条满刻度 50 MB/s（示意标尺，非精确）
function ioPercent(c) {
  const v = Math.max(c.readBps ?? 0, c.writeBps ?? 0);
  return v > 0 ? Math.min(100, (v / IO_FULL_BPS) * 100) : 0;
}

function bpsText(v) {
  if (v == null) return '—';
  if (v < 1024) return `${Math.round(v)} B/s`;
  if (v < 1024 ** 2) return `${(v / 1024).toFixed(1)} KB/s`;
  return `${(v / 1024 ** 2).toFixed(1)} MB/s`;
}

// ---- 生命周期控制（管理员）：stop/restart 走确认气泡，操作后刷新整页 ----
const busy = reactive({});
const confirmOpen = reactive({}); // 容器名 → 气泡开合（UPop v-model 为布尔）
async function control(c, action) {
  if (!identity.canWrite || busy[c.name]) return;
  busy[c.name] = true;
  try {
    await controlContainer(c.name, action);
    await refresh();
  } catch {
    /* 失败信封已全局提示；状态以刷新为准 */
  } finally {
    busy[c.name] = false;
  }
}
</script>

<template>
  <section>
    <u-page-header
      title="Docker"
      :sub="t('容器舰队 · 资源占用')"
      :tag="headerTag"
      :updated="lastUpdated"
    />

    <div v-if="!live || d.available" class="fleet">
      <div v-for="c in d.containers" :key="c.name" class="wg ship">
        <div class="s-head">
          <!-- 状态环：弧 = CPU%，色随运行状态 -->
          <svg class="ring" viewBox="0 0 44 44">
            <circle
              cx="22"
              cy="22"
              :r="RING_R"
              fill="none"
              stroke="var(--sf3)"
              stroke-width="3.4"
            />
            <circle
              cx="22"
              cy="22"
              :r="RING_R"
              fill="none"
              :stroke="c.running ? 'var(--ok)' : 'var(--bad)'"
              stroke-width="3.4"
              stroke-linecap="round"
              stroke-dasharray="106.8"
              :stroke-dashoffset="c.running ? ringOffset(c.cpuPercent) : 106.8"
              transform="rotate(-90 22 22)"
              class="ring-fg"
            />
          </svg>
          <span class="cav" :class="c.avClass">{{ c.av }}</span>
          <div class="s-name">
            <b>{{ c.name }}</b>
            <small class="muted">{{ c.image || '—' }}</small>
          </div>
          <div class="s-tags">
            <span v-if="!c.running && exitNames.has(c.name)" class="tag bad" style="cursor: pointer"
              ><span class="dot" /><button class="bdg" @click="router.push('/nasdeck/timeline')">
                {{ t('意外退出') }}
              </button></span
            >
            <span class="st" :class="{ bad: !c.running }"
              ><span class="dot" />{{ c.running ? t('运行中') : t('已退出') }}</span
            >
          </div>
        </div>

        <div class="s-bars">
          <div class="bar-row">
            <span class="bl">CPU</span>
            <div class="meter thin">
              <i :style="{ width: `${Math.min(100, c.cpuPercent ?? 0)}%` }" />
            </div>
            <span class="bv num">{{ c.cpu }}</span>
          </div>
          <div class="bar-row">
            <span class="bl">{{ t('内存') }}</span>
            <div class="meter thin">
              <i v-if="memPercent(c) != null" :style="{ width: `${memPercent(c)}%` }" />
            </div>
            <span class="bv num">{{ c.running ? c.mem : '—' }}</span>
          </div>
          <div class="bar-row">
            <span class="bl">{{ t('磁盘 IO') }}</span>
            <div class="meter thin">
              <i class="c-info" :style="{ width: `${ioPercent(c)}%` }" />
            </div>
            <span class="bv num" :title="t('↓ 读 · ↑ 写')">
              {{ c.running ? `↓${bpsText(c.readBps)} ↑${bpsText(c.writeBps)}` : '—' }}
            </span>
          </div>
        </div>

        <div class="s-foot">
          <div class="spark-box">
            <template v-if="trends[c.name]?.length > 1">
              <u-spark :data="trends[c.name]" :color="c.running ? 'var(--acc)' : 'var(--tx3)'" />
              <span class="small muted">{{ t('24h CPU') }}</span>
            </template>
            <span v-else class="small muted">{{ t('暂无 24h 趋势（1m 桶积累中）') }}</span>
          </div>
          <div v-if="identity.canWrite" class="s-acts">
            <template v-if="c.running">
              <u-pop
                v-model="confirmOpen[c.name]"
                :ok-text="t('重启')"
                :cancel-text="t('取消')"
                @confirm="control(c, 'restart')"
              >
                <template #trigger>
                  <button class="btn sm" :disabled="busy[c.name]">
                    <u-icon name="refresh" />{{ t('重启') }}
                  </button>
                </template>
                {{ t('确认重启容器 {n}？', { n: c.name }) }}
              </u-pop>
              <u-pop
                v-model="confirmOpen[c.name + ':stop']"
                :ok-text="t('停止')"
                :cancel-text="t('取消')"
                danger
                @confirm="control(c, 'stop')"
              >
                <template #trigger>
                  <button class="btn sm stop" :disabled="busy[c.name]">
                    <u-icon name="power" />{{ t('停止') }}
                  </button>
                </template>
                {{ t('确认停止容器 {n}？', { n: c.name }) }}
              </u-pop>
            </template>
            <button v-else class="btn sm go" :disabled="busy[c.name]" @click="control(c, 'start')">
              <u-icon name="play" />{{ t('启动') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-else class="wg" style="margin-bottom: 0">
      <div class="wg-b small muted" style="padding: 22px 16px; text-align: center">
        {{ d.reason || t('Docker 不可用（—）') }}
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 舰牌墙（花活二期 M）：自适应卡片栅格 */
.fleet {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 14px;
  margin-bottom: 0;
}

.ship {
  margin-bottom: 0;
}

.s-head {
  position: relative;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 14px 8px;
}

.ring {
  position: absolute;
  width: 44px;
  height: 44px;
}

.ring-fg {
  transition: stroke-dashoffset 0.6s var(--ease);
}

.cav {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  margin-left: 5px;
  font-weight: 800;
  border-radius: 8px;
}

.s-name {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;

  small {
    overflow: hidden;
    font-size: 11.5px;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.s-tags {
  display: flex;
  flex: none;
  flex-direction: column;
  gap: 4px;
  align-items: flex-end;

  .st {
    font-size: 12px;
  }

  .tag {
    font-size: 11.5px;

    .bdg {
      padding: 0;
      color: inherit;
      cursor: pointer;
      background: none;
      border: none;
    }
  }
}

.s-bars {
  display: flex;
  flex-direction: column;
  gap: 7px;
  padding: 4px 14px 8px;
}

.bar-row {
  display: grid;
  grid-template-columns: 52px 1fr 128px;
  gap: 10px;
  align-items: center;

  .bl {
    font-size: 11.5px;
    color: var(--tx2);
  }

  .bv {
    font-size: 11.5px;
    color: var(--tx2);
    text-align: right;
  }
}

.s-foot {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  justify-content: space-between;
  padding: 4px 14px 12px;
  border-top: 1px dashed var(--bd);
}

.spark-box {
  flex: 1;
  min-width: 0;

  .small {
    display: block;
    margin-top: 3px;
  }
}

.s-acts {
  display: flex;
  flex: none;
  gap: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .ring-fg {
    transition: none;
  }
}
</style>
