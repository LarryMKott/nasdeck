'use strict';

/**
 * 身份域状态：当前登录者是否管理员（权限铁律：设置/写操作仅管理员，普通用户只读）。
 * 值来自 /system/info 的 is_admin（后端透传飞牛注入的 X-Trim-Isadmin 头）；
 * SPA 生命周期内只拉一次——页面刷新才会变（登录态变更本就伴随整页跳转）。
 * 非 trim 形态（直连/api_key）后端恒 true，控件不受影响。
 */
import { defineStore } from 'pinia';
import { getSystemInfo } from '@/modules/nas/api/endpoints/system';

export const useIdentityStore = defineStore('nas-identity', {
  state: () => ({
    is_admin: null, // null=未加载；加载失败也保持 null（按非管理员禁用，安全侧）
    loaded: false,
  }),
  getters: {
    /** 控件绑定用：null（未知/加载失败）按非管理员处理，宁禁勿漏 */
    canWrite: (s) => s.is_admin === true,
    /** 提示文案 */
    deniedText: () => '需要管理员账号',
  },
  actions: {
    async ensure() {
      if (this.loaded) return;
      this.loaded = true;
      try {
        const info = await getSystemInfo();
        this.is_admin = info?.is_admin === true;
      } catch {
        this.is_admin = false;
      }
    },
  },
});
