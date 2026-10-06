'use strict';

/** 实时推送域状态：WS 快照 + 轮询降级（契约 §4/§7.4），视图只订阅本 store。 */
import { defineStore } from 'pinia';
import { getRealtime } from '@/modules/nas/api/endpoints/monitor';
import { createRealtimeSocket } from '@/modules/nas/api/ws';

export const useRealtimeStore = defineStore('nas-realtime', {
  state: () => ({
    /** RealtimeSnapshot（WS 1s 推送或 2s 轮询降级） */
    snapshot: null,
    /** 最新风扇调速输出（WS fans 事件） */
    fanOutputs: [],
    /** 最近一条 WS alert 帧（事件弹幕等氛围组件订阅；轮询降级形态无此数据） */
    lastAlert: null,
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
        onAlert: (event) => {
          this.lastAlert = event;
        },
        pollFallback: () => getRealtime(),
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
