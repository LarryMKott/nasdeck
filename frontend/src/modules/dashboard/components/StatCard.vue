<script setup>
import { Bell, TrendCharts, User, View } from '@element-plus/icons-vue';

/** 统计卡片：展示单项指标（图标 + 数值 + 环比趋势） */
defineOptions({ name: 'StatCard' });

const props = defineProps({
  /** 指标项 { label, value, icon, trend }，icon 为图标组件名 */
  item: { type: Object, default: () => ({}) },
});

const iconMap = { User, View, TrendCharts, Bell };

const icon = computed(() => iconMap[props.item.icon] ?? null);
const trend = computed(() => Number(props.item.trend ?? 0));
</script>

<template>
  <el-card shadow="hover" class="stat-card">
    <div class="stat-card__inner">
      <div class="stat-card__icon" :class="trend >= 0 ? 'is-up' : 'is-down'">
        <el-icon :size="22">
          <component :is="icon" v-if="icon" />
        </el-icon>
      </div>
      <div class="stat-card__meta">
        <div class="stat-card__value">{{ item.value ?? '--' }}</div>
        <div class="stat-card__label">{{ item.label }}</div>
      </div>
      <div class="stat-card__trend" :class="trend >= 0 ? 'is-up' : 'is-down'">
        {{ trend >= 0 ? '+' : '' }}{{ trend }}%
      </div>
    </div>
  </el-card>
</template>

<style lang="scss" scoped>
.stat-card {
  &__inner {
    display: flex;
    gap: 12px;
    align-items: center;
  }

  &__icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    border-radius: 10px;

    &.is-up {
      color: $color-primary;
      background: rgb(64 158 255 / 12%);
    }

    &.is-down {
      color: $color-danger;
      background: rgb(245 108 108 / 12%);
    }
  }

  &__value {
    font-size: 22px;
    font-weight: 700;
    line-height: 1.2;
  }

  &__label {
    font-size: 13px;
    color: $color-text-secondary;
  }

  &__trend {
    margin-left: auto;
    font-size: 13px;

    &.is-up {
      color: $color-success;
    }

    &.is-down {
      color: $color-danger;
    }
  }
}
</style>
