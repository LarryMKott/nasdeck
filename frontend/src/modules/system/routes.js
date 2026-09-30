'use strict';

/** 系统管理模块路由（权限演示：角色管理要求 system:role:list 权限） */
import Layout from '@/layouts/index.vue';

export const systemRoutes = [
  {
    path: '/system',
    name: 'System',
    component: Layout,
    redirect: '/system/user',
    meta: { title: '系统管理', icon: 'Setting' },
    children: [
      {
        path: 'user',
        name: 'UserList',
        component: () => import('./views/UserList.vue'),
        meta: { title: '用户管理', icon: 'User', keepAlive: true },
      },
      {
        path: 'role',
        name: 'RoleList',
        component: () => import('./views/RoleList.vue'),
        meta: { title: '角色管理', icon: 'Avatar', permissions: ['system:role:list'] },
      },
    ],
  },
];
