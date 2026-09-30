'use strict';

/** 实时推送域状态：WS 快照 + 轮询降级（契约 §4/§7.4），视图只订阅本 store。 */
import { defineStore } from 'pinia';
import { apiData } from '@/modules/nas/api/client';
import { createRealtimeSocket } from '@/modules/nas/api/ws';

export const useRealtimeStore = defineStore('nas-realtime', {
  state: () => ({
    /** RealtimeSnapshot（WS 1s 推送或 2s 轮询降级） */
    snapshot: null,
    /** 最新风扇调速输出（WS fans 事件） */
    fanOutputs: [],
    connected: false,
    _socket: null,
    _refCount: 0,
  }),

  actions: {
    /** 首个订阅视图调用；引用计数避免多视图重复建连 */
    acquire() {
      this._refCount += 1;
      if (this._socket) return;
      this._socket = createRealtimeSocket({
        onSnapshot: (snap) => {
          this.snapshot = snap;
          this.connected = true;
        },
        onFans: (fans) => {
          this.fanOutputs = fans;
        },
        pollFallback: () => apiData('/api/v1/monitor/realtime'),
      });
    },

    release() {
      this._refCount = Math.max(0, this._refCount - 1);
      if (!this._refCount && this._socket) {
        this._socket.close();
        this._socket = null;
        this.connected = false;
      }
    },
  },
});
