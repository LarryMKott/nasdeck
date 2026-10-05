<script setup>
/** 硬件检测：系统/主板/CPU/内存/网络/RAID/硬盘 七个折叠分区（后端 /hardware + 演示回退） */
import { computed, reactive, ref } from 'vue';
import { detect as mockDetect } from '../mock';
import { useViewData } from '../composables/useViewData';
import { fetchDetect } from '../services/system';
import UPageHeader from '../components/UPageHeader.vue';
import UModal from '../components/UModal.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasDetect' });

const { data: d, live, lastUpdated } = useViewData(fetchDetect, mockDetect);
const headerTag = computed(() => ({
  type: live.value ? 'ok' : 'acc',
  text: live.value ? '正常' : '演示数据',
}));
/** 真实数据无每核序列时隐藏核心小柱 */
const hasCores = computed(
  () => !d.value.cpu?.noCores && Array.isArray(d.value.cpu?.cores) && d.value.cpu.cores.length
);

/** 分区折叠状态（默认全部展开） */
const open = reactive({
  env: true,
  cpu: true,
  mem: true,
  net: true,
  raid: true,
  disks: true,
});

function toggle(key) {
  open[key] = !open[key];
}

/** DIMM 详情弹窗 */
const dimmModalOpen = ref(false);
const activeDimm = ref(null);

function showDimm(dimm) {
  if (dimm.empty) return;
  activeDimm.value = dimm;
  dimmModalOpen.value = true;
}
</script>

<template>
  <section>
    <u-page-header
      title="硬件检测"
      sub="系统 · 主板 · CPU · 内存 · 网络 · RAID · 硬盘"
      :tag="headerTag"
      :updated="lastUpdated"
    />

    <!-- 系统信息 + 主板（双卡并排，紧凑布局） -->
    <div class="grid">
      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="info" />
          <h3>系统信息</h3>
        </div>
        <div class="wg-b">
          <div
            v-for="(row, i) in d.system"
            :key="row[0]"
            class="kvrow"
            :class="i < d.system.length - 1 ? 'kvline' : ''"
          >
            <span class="muted small">{{ row[0] }}</span>
            <span class="small num">{{ row[1] }}</span>
          </div>
        </div>
      </div>

      <div class="wg t6">
        <div class="wg-h">
          <u-icon name="server" />
          <h3>主板</h3>
        </div>
        <div class="wg-b">
          <div
            v-for="(row, i) in d.board"
            :key="row[0]"
            class="kvrow"
            :class="i < d.board.length - 1 ? 'kvline' : ''"
          >
            <span class="muted small">{{ row[0] }}</span>
            <span class="small num" :class="row[0] === '主板温度' ? 't-ok' : ''">{{ row[1] }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 运行环境自检（安装期自举结果：工具/驱动/运行时/生效配置） -->
    <div class="sec" :class="{ open: open.env }">
      <button class="sec-h" @click="toggle('env')">
        <span class="sico"><u-icon name="info" /></span>运行环境自检
        <span class="small muted" style="font-weight: 400">安装期自举结果 · 实时探测</span>
        <u-icon class="arr" name="chev" />
      </button>
      <div class="sec-b">
        <div class="kv2">
          <div>
            <div class="small muted" style="margin-bottom: 8px">运行时与生效配置</div>
            <div
              v-for="(row, i) in d.env.runtime"
              :key="row[0]"
              class="kvrow"
              :class="i < d.env.runtime.length - 1 ? 'kvline' : ''"
            >
              <span class="muted small">{{ row[0] }}</span>
              <span class="small num">{{ row[1] }}</span>
            </div>
          </div>
          <div>
            <div class="small muted" style="margin-bottom: 8px">
              系统工具与驱动（缺啥装啥 · 失败自动降级）
            </div>
            <div
              v-for="(t, i) in d.env.tools"
              :key="t.name"
              class="kvrow"
              :class="i < d.env.tools.length - 1 ? 'kvline' : ''"
            >
              <span class="muted small">{{ t.name }} · {{ t.desc }}</span>
              <span class="small num" :class="t.ok ? 't-ok' : 't-warn'">
                {{ t.ok ? `✓ ${t.path}` : `✗ 缺 ${t.install}（可手动安装）` }}
              </span>
            </div>
            <div
              v-for="(drv, i) in d.env.drivers"
              :key="drv.name"
              class="kvrow"
              :class="i < d.env.drivers.length - 1 ? 'kvline' : ''"
            >
              <span class="muted small">{{ drv.name }} · {{ drv.desc }}</span>
              <span class="small num" :class="drv.loaded ? 't-ok' : 't-warn'">
                {{ drv.loaded ? '✓ 已加载' : '未加载（对应机型风扇不可见）' }}
              </span>
            </div>
            <div class="kvrow">
              <span class="muted small">storcli · {{ d.env.storcli.desc }}</span>
              <span class="small num" :class="d.env.storcli.ok ? 't-ok' : 't-warn'">
                {{
                  d.env.storcli.ok ? `✓ ${d.env.storcli.path}` : '未检测到（仅 MegaRAID/HBA 需要）'
                }}
              </span>
            </div>
          </div>
        </div>

        <!-- 数据采集方案：逐域本机实际采用的数据源/回退（策略决策层启动判定） -->
        <div v-if="d.env.schemes?.length" style="margin-top: 15px">
          <div class="small muted" style="margin-bottom: 8px">
            数据采集方案（逐域 · 本机实际采用 · 启动时探测判定）
          </div>
          <div
            v-for="(sc, i) in d.env.schemes"
            :key="sc.domain"
            class="kvrow"
            :class="i < d.env.schemes.length - 1 ? 'kvline' : ''"
            style="display: flex; gap: 10px; align-items: baseline"
          >
            <span class="small" style="flex: 0 0 150px; font-weight: 600">{{ sc.label }}</span>
            <span class="small num" :class="sc.ok ? 't-ok' : 't-warn'" style="flex: 0 0 auto">{{
              sc.ok ? sc.primary : '✗ 不可用'
            }}</span>
            <span class="muted small" style="flex: 1" :title="sc.fallback">
              {{ sc.ok ? sc.source : sc.note || sc.fallback }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- CPU -->
    <div class="sec" :class="{ open: open.cpu }">
      <button class="sec-h" @click="toggle('cpu')">
        <span class="sico"><u-icon name="cpu" /></span>CPU<u-icon class="arr" name="chev" />
      </button>
      <div class="sec-b">
        <div class="kv2" style="margin-bottom: 12px">
          <template v-for="(row, i) in d.cpu.rows" :key="row[0]">
            <div class="kvrow" :class="i < d.cpu.rows.length - 2 ? 'kvline' : ''">
              <span class="muted small">{{ row[0] }}</span>
              <span class="small num" :class="row[0] === '实时频率' ? 't-ok' : ''">{{
                row[1]
              }}</span>
            </div>
          </template>
        </div>
        <div v-if="hasCores" class="cores" style="max-width: 420px">
          <span v-for="(v, i) in d.cpu.cores" :key="i" class="core"
            ><i :style="{ height: `${v}%` }"
          /></span>
        </div>
        <div class="small muted" style="margin-top: 6px">每核实时占用</div>
      </div>
    </div>

    <!-- 内存 -->
    <div class="sec" :class="{ open: open.mem }">
      <button class="sec-h" @click="toggle('mem')">
        <span class="sico"><u-icon name="layers" /></span>内存
        <span class="small muted" style="font-weight: 400">点击格子看详情</span>
        <u-icon class="arr" name="chev" />
      </button>
      <div class="sec-b">
        <div class="slots">
          <button
            v-for="dimm in d.dimms"
            :key="dimm.slot"
            class="slot"
            :class="{ empty: dimm.empty }"
            @click="showDimm(dimm)"
          >
            <div class="sn">{{ dimm.slot }}</div>
            <div class="sv">{{ dimm.size }}</div>
            <div class="sd">
              {{ dimm.empty ? '—' : dimm.detail ? '详情见弹窗' : 'DDR4-2400 · 正常' }}
            </div>
          </button>
        </div>
      </div>
    </div>

    <!-- 网络 -->
    <div class="sec" :class="{ open: open.net }">
      <button class="sec-h" @click="toggle('net')">
        <span class="sico"><u-icon name="net" /></span>网络<u-icon class="arr" name="chev" />
      </button>
      <div class="sec-b">
        <div class="kv2">
          <template v-for="(row, i) in d.network" :key="row[0]">
            <div class="kvrow" :class="i < d.network.length - 2 ? 'kvline' : ''">
              <span class="muted small">{{ row[0] }}</span>
              <span class="small">
                <span class="st" :class="row[1].up ? '' : 'mute off'">
                  <span class="dot" /><span :class="{ num: row[1].up }">{{ row[1].text }}</span>
                </span>
              </span>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- RAID 阵列卡 -->
    <div class="sec" :class="{ open: open.raid }">
      <button class="sec-h" @click="toggle('raid')">
        <span class="sico"><u-icon name="array" /></span>RAID 阵列卡<u-icon
          class="arr"
          name="chev"
        />
      </button>
      <div class="sec-b">
        <div class="kv2" style="margin-bottom: 12px">
          <template v-for="(row, i) in d.raid.rows" :key="row[0]">
            <div class="kvrow" :class="i < d.raid.rows.length - 2 ? 'kvline' : ''">
              <span class="muted small">{{ row[0] }}</span>
              <span v-if="row[0] === 'BBU'" class="small st"><span class="dot" />{{ row[1] }}</span>
              <span v-else class="small num">{{ row[1] }}</span>
            </div>
          </template>
        </div>
        <div class="chips">
          <button v-for="chip in d.raid.chips" :key="chip" class="btn sm">{{ chip }}</button>
        </div>
        <div v-if="d.raid.note" class="small muted" style="margin-top: 10px">
          {{ d.raid.note }}
        </div>
      </div>
    </div>

    <!-- 硬盘概览 -->
    <div class="sec" :class="{ open: open.disks }">
      <button class="sec-h" @click="toggle('disks')">
        <span class="sico"><u-icon name="drive" /></span>硬盘概览
        <span class="small muted" style="font-weight: 400">6 盘位</span>
        <u-icon class="arr" name="chev" />
      </button>
      <div class="sec-b">
        <div class="slots" style="margin-bottom: 12px">
          <div
            v-for="slot in d.diskSlots"
            :key="slot.slot"
            class="slot"
            :class="{ warn: slot.warn, empty: slot.empty }"
            style="cursor: default"
          >
            <div class="sn">{{ slot.slot }}</div>
            <div class="sv">{{ slot.size }}</div>
            <div class="sd">{{ slot.desc }}</div>
          </div>
        </div>
        <div class="chips">
          <button v-for="chip in d.diskChips" :key="chip" class="btn sm">{{ chip }}</button>
        </div>
      </div>
    </div>

    <!-- DIMM 详情弹窗 -->
    <u-modal v-model="dimmModalOpen" :title="`内存详情 · ${activeDimm?.slot ?? ''}`" icon="layers">
      <div class="kv2">
        <div v-for="(val, key) in activeDimm?.detail" :key="key" class="kvrow kvline">
          <span class="muted small">{{ key }}</span>
          <span
            class="small"
            :class="{ num: key !== '类型' && key !== '厂商' && key !== '通道' && key !== '状态' }"
          >
            <span v-if="key === '状态'" class="st"><span class="dot" />{{ val }}</span>
            <template v-else>{{ val }}</template>
          </span>
        </div>
      </div>
    </u-modal>
  </section>
</template>
