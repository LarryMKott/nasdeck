'use strict';

/** 用户域状态：用户信息、角色、权限标识及登录/登出动作 */
import { defineStore } from 'pinia';
import { apiLogin, apiLogout, apiGetUserInfo } from '@/api/auth';
import { setToken, clearToken } from '@/utils/auth';
import { STORAGE_PREFIX } from '@/constants';
import { usePermissionStore } from './permission';

export const useUserStore = defineStore('user', {
  state: () => ({
    /** 用户信息（持久化，刷新后无需等待即可渲染昵称等） */
    userInfo: {},
    /** 角色编码列表（每次会话由接口刷新） */
    roles: [],
    /** 权限标识列表（如 system:user:add） */
    permissions: [],
  }),

  getters: {
    /** 展示昵称（无昵称时回退账号名） */
    nickname: (state) => state.userInfo.nickname || state.userInfo.username || '',
    /** 头像地址 */
    avatar: (state) => state.userInfo.avatar || '',
  },

  actions: {
    /**
     * 账号密码登录：令牌由 utils/auth 持久化，不进入 store
     * @param {{username: string, password: string}} form 登录表单
     */
    async login(form) {
      const res = await apiLogin(form);
      const { accessToken, refreshToken } = res?.data ?? {};
      if (!accessToken) throw new Error('登录失败：未获取到访问令牌');
      setToken({ accessToken, refreshToken });
    },

    /**
     * 拉取当前登录用户信息
     * @returns {Promise<string[]>} 角色编码列表
     */
    async fetchGetUserInfo() {
      const res = await apiGetUserInfo();
      const info = res?.data ?? {};
      this.userInfo = info;
      this.roles = Array.isArray(info.roles) ? info.roles : [];
      this.permissions = Array.isArray(info.permissions) ? info.permissions : [];
      return this.roles;
    },

    /** 退出登录：忽略登出接口异常，清理令牌、权限路由与本地状态 */
    async logout() {
      try {
        await apiLogout();
      } catch {
        // 登出接口失败不阻断本地清理
      }
      clearToken();
      usePermissionStore().reset();
      this.$reset();
    },
  },

  persist: {
    key: `${STORAGE_PREFIX}user`,
    storage: localStorage,
    paths: ['userInfo'],
  },
});
