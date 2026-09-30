<script setup>
/**
 * 通用分页器：基于 el-pagination 封装，
 * 支持 v-model:page 与 v-model:limit 双向绑定。
 */
defineOptions({ name: 'TablePagination' });

defineProps({
  /** 数据总条数 */
  total: { type: Number, default: 0 },
  /** 是否禁用 */
  disabled: { type: Boolean, default: false },
});

const page = defineModel('page', { type: Number, default: 1 });
const limit = defineModel('limit', { type: Number, default: 20 });
</script>

<template>
  <div class="table-pagination">
    <el-pagination
      v-model:current-page="page"
      v-model:page-size="limit"
      :page-sizes="[10, 20, 50, 100]"
      :total="total"
      :disabled="disabled"
      background
      layout="total, sizes, prev, pager, next, jumper"
    />
  </div>
</template>

<style lang="scss" scoped>
.table-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
