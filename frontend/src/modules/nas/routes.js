'use strict';

/** nasdeck 硬件面板模块路由：UNRAID 风格 13 视图（界面阶段全部使用本地 mock） */
import UnraidLayout from '@/layouts/UnraidLayout.vue';

/** 视图懒加载简写 */
const view = (file) => () => import(`./views/${file}.vue`);

export const nasRoutes = [
  {
    path: '/nasdeck',
    name: 'Nasdeck',
    component: UnraidLayout,
    redirect: '/nasdeck/dash',
    meta: { title: 'nasdeck', hidden: true },
    children: [
      {
        path: 'dash',
        name: 'NasDash',
        component: view('DashView'),
        meta: { title: '总览', keepAlive: true },
      },
      {
        path: 'storage',
        name: 'NasStorage',
        component: view('StorageView'),
        meta: { title: '存储卷', keepAlive: true },
      },
      {
        path: 'disks',
        name: 'NasDisks',
        component: view('DisksView'),
        meta: { title: '硬盘 SMART', keepAlive: true },
      },
      {
        path: 'detect',
        name: 'NasDetect',
        component: view('DetectView'),
        meta: { title: '硬件检测', keepAlive: true },
      },
      {
        path: 'system',
        name: 'NasSystem',
        component: view('SystemView'),
        meta: { title: '系统资源', keepAlive: true },
      },
      {
        path: 'temps',
        name: 'NasTemps',
        component: view('TempsView'),
        meta: { title: '温度监控', keepAlive: true },
      },
      {
        path: 'sys-hist',
        name: 'NasSysHist',
        component: view('SysHistView'),
        meta: { title: '历史趋势', keepAlive: true },
      },
      {
        path: 'docker',
        name: 'NasDocker',
        component: view('DockerView'),
        meta: { title: 'Docker', keepAlive: true },
      },
      {
        path: 'ports',
        name: 'NasPorts',
        component: view('PortsView'),
        meta: { title: '端口占用', keepAlive: true },
      },
      {
        path: 'fan',
        name: 'NasFan',
        component: view('FanView'),
        meta: { title: '风扇控制', keepAlive: true },
      },
      {
        path: 'timeline',
        name: 'NasTimeline',
        component: view('TimelineView'),
        meta: { title: '事件时间线', keepAlive: true },
      },
      {
        path: 'automation',
        name: 'NasAutomation',
        component: view('AutomationView'),
        meta: { title: '控制与自动化', keepAlive: true },
      },
      {
        path: 'manual',
        name: 'NasManual',
        component: view('ManualView'),
        meta: { title: '操作手册', keepAlive: true },
      },
      {
        path: 'about',
        name: 'NasAbout',
        component: view('AboutView'),
        meta: { title: '关于 nasdeck', keepAlive: true },
      },
    ],
  },
];
