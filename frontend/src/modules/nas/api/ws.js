'use strict';

/**
 * 实时推送组合器（契约 §4 + §7.4 建议形态）：
 * - WS /api/v1/ws/realtime：realtime(1s) / fans(5s) / alert 事件 / ping-pong 保活
 * - 指数退避重连（1s 起上限 30s）；连续失败切 HTTP 轮询降级，恢复后切回
 * 经 Pinia store（realtime.js）使用，视图不直连。
 */

const BASE = `${typeof location !== 'undefined' && location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}`;

export function createRealtimeSocket({ onSnapshot, onFans, onAlert, pollFallback } = {}) {
  let ws = null;
  let closed = false;
  let attempt = 0;
  let pollTimer = null;
  let keepaliveTimer = null;

  function startPolling() {
    if (pollTimer || typeof pollFallback !== 'function') return;
    pollTimer = setInterval(async () => {
      try {
        const snap = await pollFallback();
        if (snap) onSnapshot?.(snap);
      } catch {
        /* 轮询失败静默，等待 WS 恢复 */
      }
    }, 2000);
  }

  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function connect() {
    if (closed) return;
    try {
      ws = new WebSocket(`${BASE}/api/v1/ws/realtime`);
    } catch {
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      attempt = 0;
      stopPolling(); // WS 恢复，切回推送
      keepaliveTimer = setInterval(() => {
        if (ws?.readyState === WebSocket.OPEN) ws.send('ping');
      }, 20000);
    };
    ws.onmessage = (event) => {
      let frame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        return;
      }
      if (frame.type === 'realtime') onSnapshot?.(frame.data);
      else if (frame.type === 'fans') onFans?.(frame.data);
      else if (frame.type === 'alert') onAlert?.(frame.data);
      // pong 忽略
    };
    ws.onclose = () => {
      clearInterval(keepaliveTimer);
      keepaliveTimer = null;
      if (!closed) scheduleReconnect();
    };
    ws.onerror = () => ws?.close();
  }

  function scheduleReconnect() {
    attempt += 1;
    // 连续失败 3 次即进入轮询降级（WS 重连在后台继续）
    if (attempt >= 3) startPolling();
    const delay = Math.min(1000 * 2 ** (attempt - 1), 30000);
    setTimeout(() => connect(), attempt >= 3 ? delay : Math.min(delay, 3000));
  }

  connect();

  return {
    close() {
      closed = true;
      stopPolling();
      clearInterval(keepaliveTimer);
      ws?.close();
    },
    /** WS 是否处于 OPEN（供 store 标注数据来源） */
    get open() {
      return ws?.readyState === WebSocket.OPEN;
    },
  };
}
