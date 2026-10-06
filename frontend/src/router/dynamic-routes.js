'use strict';

/**
 * 动态路由聚合：按领域模块组织，由 permission store 过滤后注入路由器。
 * 每个模块在自己的 routes.js 中维护路由定义（内聚），此处只负责汇总。
 */
import { kioskRoute, nasRoutes } from '@/modules/nas/routes';
import { NOT_FOUND_ROUTE } from './static-routes';

/**
 * 需要登录后按角色/权限动态注入的路由。
 * meta.roles / meta.permissions 均未配置时默认放行；
 * 末尾追加 404 兜底，保证其匹配优先级低于动态业务路由。
 */
// nasdeck 只保留 nas 模块：脚手架的 dashboard/system 演示模块已整体摘除
export const dynamicRoutes = [...nasRoutes, kioskRoute, NOT_FOUND_ROUTE];
