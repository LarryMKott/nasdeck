<script setup>
/** 端口占用：搜索 + 可达性筛选 + 释放（终止进程）二次确认（后端 + 演示回退） */
import { computed, reactive, ref } from 'vue';
import { ports as mockPorts } from '../mock';
import { killProcess } from '../api/endpoints/system';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { fetchPorts } from '../services/system';
import UPageHeader from '../components/UPageHeader.vue';
import UPop from '../components/UPop.vue';

defineOptions({ name: 'NasPorts' });

// 权限铁律：设置类操作仅管理员；非管理员禁用「释放进程」
const identity = useIdentityStore();
identity.ensure();

const keyword = ref('');
const reachFilter = ref('');

const { data: d, live, refresh, lastUpdated } = useViewData(fetchPorts, mockPorts);

/** 每行独立的释放确认气泡开合 */
const popOpen = reactive({});
/** 已释放端口从列表移除（本地态，刷新前有效） */
const released = reactive({});

async function releasePort(row) {
  if (live.value && row.pid) {
    try {
      await killProcess(row.pid);
      released[row.port] = true; // 仅成功后隐藏：失败（1004 保护名单等）刷新后原样可见
    } catch {
      /* 释放失败保持行可见，不假装成功 */
    }
    await refresh();
  }
}

const filtered = computed(() =>
  d.value.list.filter((p) => {
    if (released[p.port]) return false;
    const kw = keyword.value.trim().toLowerCase();
    const hitKw = !kw || p.searchText.toLowerCase().includes(kw);
    const hitReach = !reachFilter.value || p.reach === reachFilter.value;
    return hitKw && hitReach;
  })
);
</script>

<template>
  <section>
    <u-page-header
      :title="t('端口占用')"
      :sub="t('监听端口 · 进程 · 可达性')"
      :updated="lastUpdated"
    />

    <div class="wg" style="margin-bottom: 0">
      <div
        class="wg-b"
        style="display: flex; flex-wrap: wrap; gap: 10px; border-bottom: 1px solid var(--bd)"
      >
        <input
          v-model="keyword"
          type="text"
          :placeholder="t('搜索端口 / 进程 / 应用')"
          style="flex: 1; min-width: 180px"
        />
        <select v-model="reachFilter">
          <option value="">{{ t('全部可达性') }}</option>
          <option value="ok">{{ t('可达') }}</option>
          <option value="warn">{{ t('受限') }}</option>
          <option value="err">{{ t('不可达') }}</option>
        </select>
      </div>
      <div class="tscroll">
        <table class="u">
          <thead>
            <tr>
              <th>{{ t('应用') }}</th>
              <th class="r">{{ t('端口') }}</th>
              <th>{{ t('协议') }}</th>
              <th>{{ t('进程 (PID)') }}</th>
              <th>{{ t('可达性') }}</th>
              <th>{{ t('操作') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filtered" :key="p.port">
              <td>
                <span class="cav" :class="p.avClass">{{ p.av }}</span
                ><b>{{ p.app }}</b>
              </td>
              <td class="r num">{{ p.port }}</td>
              <td>{{ p.proto }}</td>
              <td class="num">{{ p.process }}</td>
              <td>
                <span class="st" :class="{ warn: p.reach === 'warn', bad: p.reach === 'err' }">
                  <span class="dot" />{{ p.reachText }}
                </span>
              </td>
              <td>
                <u-pop
                  v-model="popOpen[p.port]"
                  :ok-text="p.danger ? t('确认释放') : t('确认')"
                  :danger="!!p.danger"
                  @confirm="releasePort(p)"
                >
                  <template #trigger>
                    <button v-if="identity.canWrite" class="btn sm">释放</button>
                  </template>
                  {{ p.confirm }}
                </u-pop>
              </td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="6" class="muted" style="padding: 26px 0; text-align: center">
                {{ t('无匹配端口') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
