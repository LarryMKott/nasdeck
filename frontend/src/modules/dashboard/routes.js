'use strict';

/** 工作台模块路由 */
import Layout from '@/layouts/index.vue';

export const dashboardRoutes = [
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: Layout,
    redirect: '/dashboard/index',
    meta: { title: '工作台', icon: 'Odometer' },
    children: [
      {
        path: 'index',
        name: 'DashboardOverview',
        component: () => import('./views/DashboardView.vue'),
        meta: { title: '概览', keepAlive: true },
      },
    ],
  },
];
