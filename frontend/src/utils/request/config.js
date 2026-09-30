'use strict';

/** 请求层常量配置 */

/** 默认超时时间（毫秒） */
export const REQUEST_TIMEOUT = 15000;

/** 后端约定的成功业务码 */
export const SUCCESS_CODE = 200;

/** 登录过期业务码 */
export const UNAUTHORIZED_CODE = 401;

/** 无权限业务码 */
export const FORBIDDEN_CODE = 403;

/** 刷新令牌接口地址（使用独立 axios 实例调用，避免业务拦截器循环触发） */
export const REFRESH_TOKEN_URL = '/auth/refresh';

/** HTTP 状态码 → 提示文案 */
export const HTTP_STATUS_MESSAGES = {
  400: '请求参数错误',
  401: '登录已过期，请重新登录',
  403: '没有操作权限',
  404: '请求的资源不存在',
  408: '请求超时',
  500: '服务器内部错误',
  502: '网关错误',
  503: '服务暂不可用',
  504: '网关超时',
};
