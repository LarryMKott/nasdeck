<script setup>
import { getRoleList } from '../api';
import { useLoading } from '@/composables/useLoading';

defineOptions({ name: 'RoleList' });

const roles = ref([]);
const { loading, wrap } = useLoading(true);

/** 拉取角色列表 */
function fetchRoles() {
  return wrap(async () => {
    const res = await getRoleList();
    roles.value = res.data ?? [];
  });
}

onMounted(() => {
  fetchRoles();
});
</script>

<template>
  <div class="role-list">
    <page-container title="角色管理">
      <template #header>
        <el-button @click="fetchRoles">刷新</el-button>
      </template>

      <el-table v-loading="loading" :data="roles" border stripe>
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column prop="name" label="角色名称" min-width="140" />
        <el-table-column prop="code" label="角色编码" min-width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small">
              {{ row.status === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="180" />
      </el-table>
    </page-container>
  </div>
</template>
