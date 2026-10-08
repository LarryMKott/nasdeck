'use strict';

/**
 * fnOS 宿主主题桥（花活外·主题跟随）：飞牛桌面亮/暗模式 → 应用「跟随系统」档。
 *
 * 为什么需要：prefers-color-scheme 跟的是浏览器/操作系统，飞牛桌面自身换肤不触发
 * 该媒体查询（真机实测）——嵌入桌面（micro_app iframe）时必须走 @trimjs/web-app
 * SDK：getPlatformConfig() 读初值 + $on('os/theme') 监听变化。
 * 独立浏览器页签（isStandaloneWeb）无宿主环境，返回 false 由调用方回退媒体查询。
 */

const TRIM_THEME = { dark: 'dark', light: 'light' };

/**
 * 尝试接通 fnOS 宿主主题信号
 * @param {(theme: 'dark' | 'light') => void} onTheme 桌面主题变化回调
 * @returns {Promise<boolean>} true = 已接通（后续变化经 onTheme 推送）
 */
export async function initFnosThemeBridge(onTheme) {
  try {
    const { TrimApp } = await import('@trimjs/web-app');
    const sdk = new TrimApp();
    // 非微应用宿主（独立浏览器 / 移动内嵌）不提供 os/theme 事件
    if (sdk.isWeb !== true || sdk.isStandaloneWeb === true) return false;
    const cfg = await sdk.getPlatformConfig();
    const initial = TRIM_THEME[cfg?.theme];
    if (initial) onTheme(initial);
    await sdk.$on('os/theme', (theme) => {
      const next = TRIM_THEME[theme];
      if (next) onTheme(next);
    });
    return true;
  } catch {
    // SDK 缺失 / 桥未建立 / Scope 未声明：静默回退 prefers-color-scheme
    return false;
  }
}
