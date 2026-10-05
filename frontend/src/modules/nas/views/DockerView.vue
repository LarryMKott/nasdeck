<script setup>
/** Docker：容器运行状态与资源占用表（后端 + 演示回退） */
import { computed } from 'vue';
import { docker as mockDocker } from '../mock';
import { useViewData } from '../composables/useViewData';
import { fetchDocker } from '../services/system';
import UPageHeader from '../components/UPageHeader.vue';

defineOptions({ name: 'NasDocker' });

const { data: d, live, lastUpdated } = useViewData(fetchDocker, mockDocker);

const runningCount = computed(() => d.value.containers.filter((c) => c.running).length);
const headerTag = computed(() => {
  if (live.value) {
    return {
      type: 'ok',
      text: `${runningCount.value} 个运行中 · ${d.value.containers.length - runningCount.value} 已退出`,
    };
  }
  return { type: 'acc', text: '演示数据（本机无 Docker 或后端不可达）' };
});
</script>

<template>
  <section>
    <u-page-header
      title="Docker"
      sub="容器运行状态 · 资源占用"
      :tag="headerTag"
      :updated="lastUpdated"
    />

    <div class="wg" style="margin-bottom: 0">
      <div class="tscroll">
        <table class="u">
          <thead>
            <tr>
              <th>容器</th>
              <th>状态</th>
              <th class="r">内存</th>
              <th class="r">CPU</th>
              <th class="r">网速</th>
              <th class="r">端口映射</th>
              <th class="r">运行时长</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in d.containers" :key="c.name">
              <td>
                <span class="cav" :class="c.avClass">{{ c.av }}</span
                ><b>{{ c.name }}</b>
              </td>
              <td>
                <span class="st" :class="{ bad: !c.running }"
                  ><span class="dot" />{{ c.running ? '运行中' : '已退出' }}</span
                >
              </td>
              <td class="r num" :class="{ muted: !c.running }">{{ c.mem ?? '—' }}</td>
              <td class="r num" :class="{ muted: !c.running }">{{ c.cpu ?? '—' }}</td>
              <td class="r num" :class="{ muted: !c.running }">{{ c.net ?? '—' }}</td>
              <td class="r num" :class="{ muted: !c.running }">{{ c.ports ?? '—' }}</td>
              <td class="r num" :class="{ muted: !c.running }">{{ c.up ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="wg-b small muted" style="border-top: 1px solid var(--bd)">
        移动端：表格横向滚动（卡片化列入迭代评估）
      </div>
    </div>
  </section>
</template>
