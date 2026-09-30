<script setup>
import StatCard from '../components/StatCard.vue';
import { useDashboardStore } from '../stores/dashboard';
import { useUserStore } from '@/stores/modules/user';

defineOptions({ name: 'DashboardOverview' });

const dashboardStore = useDashboardStore();
const userStore = useUserStore();

onMounted(() => {
  dashboardStore.fetchOverview();
});
</script>

<template>
  <div class="dashboard-view">
    <el-card shadow="never" class="dashboard-view__welcome">
      <h2 class="dashboard-view__hello">你好，{{ userStore.nickname }}！</h2>
      <p class="dashboard-view__hint">欢迎使用 Vue Admin 管理平台，祝您工作顺利。</p>
    </el-card>

    <el-row v-loading="dashboardStore.loading" :gutter="16" class="dashboard-view__cards">
      <el-col v-for="item in dashboardStore.summary" :key="item.label" :xs="24" :sm="12" :lg="6">
        <stat-card :item="item" />
      </el-col>
    </el-row>

    <el-card shadow="never" header="最近动态" class="dashboard-view__logs">
      <el-table :data="dashboardStore.logs" stripe>
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.type === '告警' ? 'danger' : row.type === '系统' ? 'warning' : 'info'"
            >
              {{ row.type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="time" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style lang="scss" scoped>
.dashboard-view {
  &__welcome {
    margin-bottom: 16px;
  }

  &__hello {
    margin: 0 0 6px;
    font-size: 18px;
  }

  &__hint {
    margin: 0;
    font-size: 13px;
    color: $color-text-secondary;
  }

  &__cards {
    margin-bottom: 16px;

    :deep(.el-col) {
      margin-bottom: 16px;
    }
  }
}
</style>
