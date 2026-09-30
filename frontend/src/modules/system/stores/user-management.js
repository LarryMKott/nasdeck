'use strict';

/** 系统管理模块状态：用户分页列表 + 增删改查 */
import { defineStore } from 'pinia';
import { ElMessage } from 'element-plus';
import { createUser, deleteUser, getUserPage, updateUser } from '../api';

/** @returns {object} 默认查询条件 */
function defaultQuery() {
  return { page: 1, pageSize: 10, keyword: '', status: '' };
}

export const useUserManagementStore = defineStore('userManagement', {
  state: () => ({
    /** 列表加载中 */
    loading: false,
    /** 保存（创建/更新）中 */
    saving: false,
    /** 用户列表 */
    list: [],
    /** 总条数 */
    total: 0,
    /** 查询条件 */
    query: defaultQuery(),
  }),

  actions: {
    /** 按当前查询条件拉取分页数据 */
    async fetchPage() {
      this.loading = true;
      try {
        const res = await getUserPage(this.query);
        this.list = res.data?.list ?? [];
        this.total = res.data?.total ?? 0;
      } finally {
        this.loading = false;
      }
    },

    /** 触发查询：重置页码后拉取（页码已为 1 时直接拉取） */
    search() {
      if (this.query.page === 1) return this.fetchPage();
      this.query.page = 1;
    },

    /** 重置查询条件并刷新 */
    resetQuery() {
      this.query = defaultQuery();
      return this.fetchPage();
    },

    /**
     * 创建用户并刷新列表
     * @param {object} data 用户表单数据
     */
    async createUser(data) {
      this.saving = true;
      try {
        await createUser(data);
        ElMessage.success('创建成功');
        return this.fetchPage();
      } finally {
        this.saving = false;
      }
    },

    /**
     * 更新用户并刷新列表
     * @param {number} id 用户 ID
     * @param {object} data 用户表单数据
     */
    async updateUser(id, data) {
      this.saving = true;
      try {
        await updateUser(id, data);
        ElMessage.success('更新成功');
        return this.fetchPage();
      } finally {
        this.saving = false;
      }
    },

    /**
     * 删除用户并刷新列表
     * @param {number} id 用户 ID
     */
    async removeUser(id) {
      await deleteUser(id);
      ElMessage.success('删除成功');
      return this.fetchPage();
    },
  },
});
