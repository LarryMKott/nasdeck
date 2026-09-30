'use strict';

/**
 * 用户域状态：本地固定会话。
 * 面板鉴权由飞牛登录态承担（index.cgi 反代前已校验，见 fpk/README.md），
 * 应用内不再有登录流程；admin 角色仅用于放行全部动态路由。
 */
import { defineStore } from 'pinia';
import { STORAGE_PREFIX } from '@/constants';

/** 本地会话固定身份 */
const LOCAL_USER = {
  userId: 1,
  username: 'admin',
  nickname: 'admin',
  avatar: '',
  roles: ['admin'],
  permissions: [],
};

export const useUserStore = defineStore('user', {
  state: () => ({
    /** 用户信息（持久化，刷新后无需等待即可渲染昵称等） */
    userInfo: {},
    /** 角色编码列表（每次会话由 ensureSession 注入） */
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
    /** 幂等注入本地会话（无网络请求），由路由守卫在动态路由生成前调用 */
    ensureSession() {
      if (this.roles.length) return;
      this.userInfo = { ...LOCAL_USER };
      this.roles = [...LOCAL_USER.roles];
      this.permissions = [...LOCAL_USER.permissions];
    },
  },

  persist: {
    key: `${STORAGE_PREFIX}user`,
    storage: localStorage,
    paths: ['userInfo'],
  },
});
