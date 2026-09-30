<script setup>
/** 硬件检测：系统/主板/CPU/内存/网络/RAID/硬盘 七个折叠分区（后端 /hardware + 演示回退） */
import { computed, reactive, ref } from 'vue';
import { detect as mockDetect } from '../mock';
import { useViewData } from '../composables/useViewData';
import * as nasData from '../api/data';
import UPageHeader from '../components/UPageHeader.vue';
import UModal from '../components/UModal.vue';

defineOptions({ name: 'NasDetect' });

const { data: d, live } = useViewData(nasData.fetchDetect, mockDetect);
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
const activeDimm = ref(mockDetect.dimms[0]);

const autoRefresh = ref(true);
const _ = live; // 模板经 headerTag 消费

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
      updated="10:32:08"
    >
      <template #right>
        <label class="switch" :class="{ on: autoRefresh }" @click="autoRefresh = !autoRefresh">
          <span class="tr" />自动刷新
        </label>
      </template>
    </u-page-header>

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
    <u-modal v-model="dimmModalOpen" :title="`内存详情 · ${activeDimm.slot}`" icon="layers">
      <div class="kv2">
        <div v-for="(val, key) in activeDimm.detail" :key="key" class="kvrow kvline">
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
