'use strict';

/**
 * fnOS 宿主主题桥（主题跟随）：飞牛桌面亮/暗模式 → 应用「跟随系统」档。
 *
 * 为什么需要：prefers-color-scheme 跟的是浏览器/操作系统，飞牛桌面自身换肤不触发
 * 该媒体查询（真机实测）——嵌入桌面（micro_app iframe）时必须走 @trimjs/web-app
 * SDK：getPlatformConfig() 读初值 + $on('os/theme') 监听变化。
 * 独立浏览器页签（isStandaloneWeb）无宿主环境，返回 false 由调用方回退媒体查询。
 *
 * 真机实测（fnOS 1.2.0701）：初值正确，但桌面换肤不派发 os/theme postMessage——
 * 官方平台配置文档（developer.fnnas.com/api/platform-config/）也只有 getPlatformConfig
 * 读取、无任何变更事件，服务端 API 读不到 theme——故以 10s 轮询兜底实时性
 * （一次 postMessage 往返，开销可忽略）；事件在新系统上若正常派发，则轮询成为冗余
 * 保险，语义不变。前端 SDK 调用官方口径无需 Scope（api-scope 为老版本兼容保险）。
 */

const TRIM_THEME = { dark: 'dark', light: 'light' };
const POLL_MS = 10000;

let sdk = null;

/**
 * 尝试接通 fnOS 宿主信号（主题 + 语言）
 * @param {(theme: 'dark' | 'light') => void} onTheme 桌面主题变化回调
 * @param {(language: string) => void} [onLanguage] 桌面语言变化回调
 * @returns {Promise<boolean>} true = 已接通（后续变化经回调推送）
 */
export async function initFnosThemeBridge(onTheme, onLanguage) {
  try {
    const { TrimApp } = await import('@trimjs/web-app');
    sdk = new TrimApp();
    // 非微应用宿主（独立浏览器 / 移动内嵌）不提供宿主事件
    if (sdk.isWeb !== true || sdk.isStandaloneWeb === true) return false;
    const pull = async () => {
      const cfg = await sdk.getPlatformConfig();
      const next = TRIM_THEME[cfg?.theme];
      if (next) onTheme(next);
      if (cfg?.language && onLanguage) onLanguage(cfg.language);
    };
    await pull();
    // 事件监听优先（官方口径）；1.2.0701 实测不派发，轮询兜底保实时
    try {
      await sdk.$on('os/theme', (theme) => {
        const next = TRIM_THEME[theme];
        if (next) onTheme(next);
      });
      if (onLanguage) {
        await sdk.$on('os/language', (language) => {
          if (language) onLanguage(language);
        });
      }
    } catch {
      /* 事件不可用不影响轮询 */
    }
    setInterval(() => pull().catch(() => {}), POLL_MS);
    return true;
  } catch {
    // SDK 缺失 / 桥未建立 / Scope 未声明：静默回退 prefers-color-scheme
    return false;
  }
}
