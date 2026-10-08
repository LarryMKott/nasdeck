'use strict';

/**
 * 英文字典（key = 中文原文，与模板/脚本中的 t('…') 一字不差，统一加引号——
 * 全角标点/空格不是合法标识符，不加引号会解析失败）。
 * 迁移是渐进的：未收录的 key 在英文界面下回退显示中文原文。
 */

export default {
  // ---- 导航页签（mock.navGroups 标题） ----
  总览: 'Overview',
  存储卷: 'Storage',
  硬盘: 'Disks',
  硬件: 'Hardware',
  系统: 'System',
  温度: 'Temps',
  趋势: 'Trends',
  示波器: 'Scope',
  Docker: 'Docker',
  端口: 'Ports',
  风扇: 'Fans',
  事件: 'Events',
  自动化: 'Automation',
  手册: 'Manual',
  关于: 'About',

  // ---- 顶栏与抽屉 ----
  打开导航菜单: 'Open navigation menu',
  关闭菜单: 'Close menu',
  关闭: 'Close',
  通知: 'Notifications',
  导航菜单: 'Navigation menu',
  '页签：纯图标（点击切换完整样式）': 'Tabs: icons only (click for full style)',
  '页签：完整样式（点击切换纯图标）': 'Tabs: full style (click for icons only)',

  // ---- 主题按钮 ----
  '当前黑主题，点击切换白主题': 'Dark theme. Click for light theme',
  '当前白主题，点击切换跟随系统': 'Light theme. Click to follow system',
  '当前跟随系统（解析为{c}），点击切换跟随飞牛':
    'Follow system (resolved: {c}). Click for follow-fnOS',
  '当前跟随飞牛（桌面为{c}），点击切换赛博朋克': 'Follow fnOS (desktop: {c}). Click for cyberpunk',
  '当前跟随飞牛（未接入桌面宿主，暂按系统偏好解析为{c}），点击切换赛博朋克':
    'Follow fnOS (no desktop host, resolved via system: {c}). Click for cyberpunk',
  '当前赛博朋克，点击切换终端绿': 'Cyberpunk theme. Click for terminal green',
  '当前终端绿 CRT，点击切换黑主题': 'Terminal green CRT. Click for dark theme',
  深色: 'dark',
  浅色: 'light',

  // ---- 通用 ----
  立即刷新: 'Refresh',
  最后更新: 'Updated',
  返回: 'Back',
  演示数据: 'Demo data',
  正常: 'Normal',
  偏高: 'Warm',
  过热: 'Hot',
  警告: 'Warning',
  故障: 'Failing',
  未知: 'Unknown',
  型号: 'Model',
  容量: 'Capacity',
  介质: 'Media',
  健康: 'Health',
  序列号: 'Serial',

  // ---- 命令面板 / 铃铛菜单 ----
  '切换主题（当前：{c}）': 'Switch theme (current: {c})',
  '事件弹幕（点击关闭）': 'Event danmaku (click to turn off)',
  '事件弹幕（点击开启）': 'Event danmaku (click to turn on)',
  大屏轮播模式: 'Kiosk / TV wall mode',
  查看全部告警与规则: 'View all alerts & rules',
  '管理员（设置）': 'Admin (Settings)',
  用户: 'User',
  黑主题: 'Dark',
  白主题: 'Light',
  跟随系统: 'Follow system',
  跟随飞牛: 'Follow fnOS',
  赛博朋克: 'Cyberpunk',
  终端绿: 'Terminal green',

  // ---- 页头（title / sub） ----
  温度监控: 'Temperatures',
  '关键传感器速览 · 温度墙': 'Key sensors · temperature wall',
  控制与自动化: 'Control & Automation',
  '告警 · 通知 · 报告': 'Alerts · Notifications · Reports',
  设置: 'Settings',
  '告警阈值 · 推送渠道': 'Alert rules · Push channels',
  '关于 nasdeck': 'About nasdeck',
  '版本 · 更新 · 构建信息': 'Version · Update · Build info',

  // ---- 温度页 ----
  速览: 'Quick view',
  机箱: 'Chassis',
  温度墙: 'Temperature wall',
  '全部传感器 · 按温度分档着色': 'All sensors · colored by grade',
  机箱热力图: 'Chassis heatmap',
  '传感器按温度着色 · 气流随实际转速': 'Sensors colored by temp · airflow follows fan speed',
  编辑布局: 'Edit layout',
  重置布局: 'Reset layout',
  完成: 'Done',
  未定位: 'Unplaced',
  空位: 'Empty',
  电源: 'PSU',
  主板: 'Mainboard',
  硬盘笼: 'Drive cage',
  '气流方向 进→排': 'Airflow: intake → exhaust',
  '占空比 {d}%': 'Duty {d}%',
  '其余 {n} 个风扇：{names}': '{n} more fans: {names}',
  '其余 {n} 块盘请到硬盘页查看': '{n} more disks — see the Disks page',
  '盘{n}': 'Disk {n}',
  '空位 {n}': 'Empty {n}',
  '盘位 {n} · 空': 'Slot {n} · empty',
  '盘位 {n} · {d}': 'Slot {n} · {d}',
  无硬盘读数: 'No disk readings',
  后端暂无温度传感器读数: 'No temperature sensor readings',
  '拖动传感器芯片摆放到主板开阔区；拖回下方托盘移出机箱；占用格不可落。':
    'Drag sensor chips onto the mainboard area; drag back to the tray to remove them; occupied cells reject drops.',
  'SMART 详情与在线自检请到「硬盘」页。':
    'For SMART details and online self-tests, see the Disks page.',

  // ---- 自动化页内页签 ----
  活动告警: 'Active alerts',
  告警规则与通知: 'Alert rules & notifications',
  报告导出: 'Report export',
};
