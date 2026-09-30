<script setup>
import UserStatusTag from '../components/UserStatusTag.vue';
import { useUserManagementStore } from '../stores/user-management';
import { isValidPhone } from '@/utils/validate';

defineOptions({ name: 'UserList' });

const userStore = useUserManagementStore();

/** 状态筛选项 */
const STATUS_OPTIONS = [
  { label: '启用', value: 1 },
  { label: '停用', value: 0 },
];

/** 弹窗与表单状态 */
const dialogVisible = ref(false);
const editingId = ref(null);
const formRef = ref(null);
const form = reactive({
  username: '',
  nickname: '',
  mobile: '',
  dept: '',
  status: 1,
  remark: '',
});

const rules = {
  username: [
    { required: true, message: '请输入账号', trigger: 'blur' },
    { min: 3, max: 20, message: '账号长度为 3-20 位', trigger: 'blur' },
  ],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  mobile: [
    {
      validator: (_rule, value, callback) => {
        if (!value || isValidPhone(value)) callback();
        else callback(new Error('手机号格式不正确'));
      },
      trigger: 'blur',
    },
  ],
};

// 翻页 / 调整每页条数时重新拉取
watch(
  () => [userStore.query.page, userStore.query.pageSize],
  () => userStore.fetchPage()
);

onMounted(() => {
  userStore.fetchPage();
});

/**
 * 打开弹窗：无参数为新增，传入行数据为编辑
 * @param {object} [row] 用户行数据
 */
function openDialog(row) {
  editingId.value = row?.id ?? null;
  Object.assign(form, {
    username: '',
    nickname: '',
    mobile: '',
    dept: '',
    status: 1,
    remark: '',
    ...(row ?? {}),
  });
  dialogVisible.value = true;
}

/** 提交表单：按 editingId 区分创建 / 更新 */
async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  const payload = { ...form };
  if (editingId.value) await userStore.updateUser(editingId.value, payload);
  else await userStore.createUser(payload);
  dialogVisible.value = false;
}

/**
 * 删除用户（二次确认）
 * @param {object} row 用户行数据
 */
async function handleRemove(row) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.nickname}」吗？删除后不可恢复。`, '警告', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    });
  } catch {
    return;
  }
  await userStore.removeUser(row.id);
}
</script>

<template>
  <div class="user-list">
    <page-container title="用户管理">
      <template #header>
        <el-button v-permission="['system:user:add']" type="primary" @click="openDialog()"
          >新增用户</el-button
        >
      </template>

      <el-form inline class="user-list__search" @submit.prevent>
        <el-form-item label="关键词">
          <el-input
            v-model.trim="userStore.query.keyword"
            placeholder="账号 / 昵称"
            clearable
            style="width: 200px"
            @keyup.enter="userStore.search()"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select
            v-model="userStore.query.status"
            placeholder="全部"
            clearable
            style="width: 120px"
          >
            <el-option
              v-for="item in STATUS_OPTIONS"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="userStore.search()">查询</el-button>
          <el-button @click="userStore.resetQuery()">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table v-loading="userStore.loading" :data="userStore.list" border stripe>
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column prop="username" label="账号" min-width="110" />
        <el-table-column prop="nickname" label="昵称" min-width="100" />
        <el-table-column prop="dept" label="部门" min-width="100" />
        <el-table-column prop="mobile" label="手机号" min-width="130" />
        <el-table-column prop="roles" label="角色" min-width="100">
          <template #default="{ row }">
            <el-tag
              v-for="role in row.roles"
              :key="role"
              size="small"
              type="info"
              class="user-list__role"
            >
              {{ role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <user-status-tag :status="row.status" />
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170" />
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-permission="['system:user:edit']"
              link
              type="primary"
              @click="openDialog(row)"
            >
              编辑
            </el-button>
            <el-button
              v-permission="['system:user:delete']"
              link
              type="danger"
              @click="handleRemove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <table-pagination
        v-model:page="userStore.query.page"
        v-model:limit="userStore.query.pageSize"
        :total="userStore.total"
      />
    </page-container>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑用户' : '新增用户'"
      width="520px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="账号" prop="username">
          <el-input
            v-model.trim="form.username"
            placeholder="请输入账号"
            :disabled="Boolean(editingId)"
          />
        </el-form-item>
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model.trim="form.nickname" placeholder="请输入昵称" />
        </el-form-item>
        <el-form-item label="手机号" prop="mobile">
          <el-input v-model.trim="form.mobile" placeholder="请输入手机号" maxlength="11" />
        </el-form-item>
        <el-form-item label="部门">
          <el-input v-model.trim="form.dept" placeholder="请输入部门" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
            <el-radio v-for="item in STATUS_OPTIONS" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model.trim="form.remark" type="textarea" :rows="2" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="userStore.saving" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style lang="scss" scoped>
.user-list {
  &__search {
    margin-bottom: 4px;
  }

  &__role {
    margin-right: 4px;
  }
}
</style>
