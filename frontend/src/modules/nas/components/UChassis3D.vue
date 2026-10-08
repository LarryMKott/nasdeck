<script setup>
/** 立体机箱（花活三期 R1）：等距 SVG 渲染器（方案 B，「模型即数据」）——
 * inventory × 模板生成 layout JSON（utils/isochassis/templates.js），渲染器固定不变：
 * 每盒体投影出顶/左/右三面（同一色相三种不透明度 = 烘焙光影），面板色按实时温度
 * 分级（60/75），无源部件灰显悬停显"—"；悬停浮出实时读数 tooltip，点击跳对应页。
 * 纯 2D SVG 无 3D transform——老 WebView 无 z 排序兼容雷区（三期方案比选结论 B）。 */
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';
import { boxFaces, boxCenter, depthCompare, sceneViewBox } from '../utils/isochassis/project';
import { buildLayout, tempGrade } from '../utils/isochassis/templates';

defineOptions({ name: 'UChassis3D' });

const props = defineProps({
  /** inventory：{ board, dimms, nics, sensors, fans, disks }（fetchChassis 形状） */
  sensors: { type: Array, default: () => [] },
  fans: { type: Array, default: () => [] },
  disks: { type: Array, default: () => [] },
  board: { type: Object, default: null },
  dimms: { type: Number, default: 2 },
  nics: { type: Number, default: 1 },
  /** 实时数据（realtime 快照分量）：每盘 IO / 每网口吞吐 / RAPL 功耗 / GPU 可用 */
  io: { type: Object, default: null }, // { <device>: {read_iops, write_iops, ...} }
  net: { type: Object, default: null }, // { <iface>: {rx_kbps, tx_kbps, ...} }
  power: { type: Object, default: null }, // { available, watts }
  gpuAvailable: { type: Boolean, default: false },
  warmAt: { type: Number, default: 60 },
  hotAt: { type: Number, default: 75 },
});

const emit = defineEmits(['jump']);
const router = useRouter();

/** layout：纯函数生成（模板自动选择 tower/virtual；R3 提供手动切换与持久化） */
const layout = computed(() =>
  buildLayout({
    sensors: props.sensors,
    fans: props.fans,
    disks: props.disks,
    board: props.board,
    dimms: props.dimms,
    nics: props.nics,
    gpuAvailable: props.gpuAvailable,
  })
);

const viewBox = computed(() => sceneViewBox(layout.value.size));

/** 深度排序后的可见盒体（含三面投影点串与数据绑定求值） */
const drawn = computed(() =>
  [...layout.value.boxes].sort(depthCompare).map((b) => {
    const bind = b.bind ?? {};
    let celsius = bind.celsius ?? null;
    let iops = null;
    let watts = null;
    let kbps = null;
    if (bind.type === 'bay' && bind.device) {
      celsius = bind.celsius;
      iops = props.io?.[bind.device] ?? null;
    } else if (bind.type === 'temp') {
      celsius = bind.celsius;
    } else if (bind.type === 'power') {
      watts = props.power?.available ? props.power.watts : null;
    } else if (bind.type === 'net') {
      const vals = Object.values(props.net ?? {});
      const i = bind.index ?? 0;
      kbps = vals[i] ? vals[i].rx_kbps + vals[i].tx_kbps : null;
    } else if (bind.type === 'gpu') {
      celsius = null;
    }
    return {
      ...b,
      faces: boxFaces(b),
      center: boxCenter(b),
      grade: tempGrade(celsius),
      celsius,
      iops,
      watts,
      kbps,
    };
  })
);

const KIND_JUMP = {
  cpu: '/nasdeck/system',
  bay: '/nasdeck/disks',
  fan: '/nasdeck/fan',
  gpu: '/nasdeck/dash',
};

function onClick(box) {
  const to = KIND_JUMP[box.kind] ?? (box.kind === 'net' ? '/nasdeck/ports' : null);
  if (to) router.push(to);
  emit('jump', box);
}

/** 悬停 tooltip：标签 + 实时读数（无源显"—"） */
const hover = ref(null);
function tipText(box) {
  const parts = [];
  if (box.kind === 'cpu' || box.kind === 'free' || box.kind === 'm2') {
    parts.push(box.celsius != null ? `${box.celsius} °C` : '—');
  } else if (box.kind === 'bay') {
    parts.push(box.celsius != null ? `${box.celsius} °C` : '—');
    if (box.iops) {
      parts.push(`↓${box.iops.read_iops} ↑${box.iops.write_iops} IOPS`);
    } else {
      parts.push('IO —');
    }
  } else if (box.kind === 'psu') {
    parts.push(box.watts != null ? `${box.watts} W` : '—');
  } else if (box.kind === 'fan') {
    parts.push(`${box.bind?.rpm ?? 0} RPM`);
  } else if (box.kind === 'net') {
    parts.push(box.kbps != null ? `${box.kbps.toFixed(0)} KB/s` : '—');
  } else if (box.tooltip) {
    parts.push(box.tooltip);
  }
  return `${box.label || box.id} · ${parts.join(' · ')}`;
}
</script>

<template>
  <div class="iso">
    <svg
      :viewBox="`${viewBox.minX} ${viewBox.minY} ${viewBox.vw} ${viewBox.vh}`"
      role="img"
      :aria-label="t('立体机箱')"
    >
      <g
        v-for="b in drawn"
        :key="b.id"
        class="box"
        :class="[b.kind, b.grade, { clickable: !!b.label }]"
        @mouseenter="hover = b"
        @mouseleave="hover = null"
        @click="onClick(b)"
      >
        <polygon :points="b.faces.top" class="f top" />
        <polygon :points="b.faces.left" class="f left" />
        <polygon :points="b.faces.right" class="f right" />
        <!-- 顶面读数牌：CPU/盘位温度、电源瓦数（无源显"—"，不造假） -->
        <text
          v-if="b.label && (b.kind === 'cpu' || b.kind === 'psu')"
          :x="b.center.x"
          :y="b.center.y + 3"
          class="lbl"
          :class="b.grade"
          text-anchor="middle"
        >
          {{
            b.kind === 'psu'
              ? b.watts != null
                ? `${b.watts}W`
                : '—'
              : b.celsius != null
                ? `${b.celsius}°`
                : '—'
          }}
        </text>
      </g>
    </svg>
    <!-- 悬停读数浮层 -->
    <div v-if="hover" class="tip small num">{{ tipText(hover) }}</div>
    <!-- 模板徽标：当前自动选择的机型视图（R3 提供手动切换与持久化） -->
    <span class="tpl small muted">{{
      layout.kind === 'virtual' ? t('逻辑视图（虚拟机）') : t('塔式侧透')
    }}</span>
  </div>
</template>

<style scoped lang="scss">
.iso {
  position: relative;
  overflow: hidden;
  background: rgb(3 5 8 / 30%);
  border: 1px solid var(--bd);
  border-radius: 10px;

  svg {
    display: block;
    width: 100%;
    height: 460px;
  }
}

.f {
  stroke: var(--bd);
  stroke-width: 0.4;

  // 烘焙光影：同色相三种不透明度（顶亮/左中/右暗），主题换装直连
  &.top {
    fill-opacity: 0.92;
  }

  &.left {
    fill-opacity: 0.68;
  }

  &.right {
    fill-opacity: 0.45;
  }
}

.box {
  // 各部件基色（CSS 变量 = 四套主题直连换装）
  polygon {
    fill: var(--sf2);
  }

  &.case polygon {
    fill: var(--sf3);
  }

  &.mobo polygon {
    fill: var(--sf2);
  }

  &.ram polygon {
    fill: var(--info);
  }

  &.m2 polygon,
  &.net polygon {
    fill: var(--info);
  }

  &.psu polygon {
    fill: var(--purp);
  }

  &.fan polygon {
    fill: var(--sf2);
  }

  &.free polygon {
    fill: var(--sf2);
  }

  // 温度分级面色（cpu/bay/m2 顶面按实时温度着色）
  &.cpu polygon,
  &.bay polygon {
    fill: var(--ok);
  }

  &.warm polygon {
    fill: var(--warn);
  }

  &.hot polygon {
    fill: var(--bad);
  }

  &.neutral polygon {
    fill: var(--sf3);
  }

  &.clickable {
    cursor: pointer;

    &:hover .f {
      stroke: var(--acc);
      stroke-width: 0.9;
    }
  }
}

.lbl {
  font-size: 3.6px;
  font-weight: 600;
  pointer-events: none;
  fill: var(--tx0);

  &.neutral {
    fill: var(--tx3);
  }
}

.tip {
  position: absolute;
  top: 10px;
  left: 12px;
  padding: 5px 10px;
  font-size: 12px;
  pointer-events: none;
  background: rgb(0 0 0 / 55%);
  border-radius: 6px;
}

.tpl {
  position: absolute;
  right: 12px;
  bottom: 8px;
}
</style>
