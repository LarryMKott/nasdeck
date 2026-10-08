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

  // ---- 总览页 ----
  '系统 · 阵列 · 风扇 · 服务': 'System · Array · Fans · Services',
  自动: 'Auto',
  状态卡: 'Status card',
  '生成状态分享图（PNG）': 'Generate shareable status card (PNG)',
  'CPU 使用率': 'CPU usage',
  使用率: 'Usage',
  频率: 'Frequency',
  '线程 {n}': 'Thread {n}',
  总大小: 'Total',
  已使用: 'Used',
  可用: 'Available',
  缓冲: 'Buffers',
  缓存: 'Cache',
  系统保留: 'Reserved',
  网络吞吐: 'Network throughput',
  '磁盘 IO': 'Disk I/O',
  阵列: 'Array',
  管理阵列: 'Manage array',
  '核显 · 温度': 'iGPU · temp',
  整机功耗: 'Power draw',
  '负载 1/5/15m': 'Load 1/5/15m',
  进程数: 'Processes',
  'GPU 监控 · {n}': 'GPU monitor · {n}',
  '核显 · 正常': 'iGPU · normal',
  '显存（共享）': 'VRAM (shared)',
  引擎占用: 'Engine usage',
  'GPU 频率': 'GPU frequency',
  功耗: 'Power',
  '驱动 / 转码': 'Driver / transcode',
  'GPU 使用率': 'GPU usage',
  风扇转速: 'Fan speed',
  '接管中 · {a}/{b} 运转': 'Managed · {a}/{b} spinning',
  未配置: 'Not configured',
  '风扇未配置 · 到「风扇」页添加风区并接管后此处显示实时转速':
    'No fans configured · add fan zones and take over on the Fans page to see live speeds here',
  风扇控制与曲线编辑: 'Fan control & curve editor',
  已退出: 'Exited',
  '未检测到 Docker 容器': 'No Docker containers detected',
  查看容器: 'View containers',
  硬盘温度: 'Disk temperatures',
  '{n} 盘 · 按阈值着色': '{n} disks · colored by threshold',
  无温度数据源: 'No temperature source',
  '未检测到硬盘温度传感器 · 传感器接入后此处显示各盘温度':
    'No disk temperature sensors detected · temperatures appear here once sensors are available',
  存储卷概览: 'Storage volumes',
  查看存储卷: 'View volumes',
  条: 'alerts',
  当前无活动告警: 'No active alerts',
  '后端不可达，显示演示告警': 'Backend unreachable — showing demo alerts',

  // ---- 存储卷页 ----
  '阵列设备 · 卷': 'Array devices · volumes',
  运行中: 'Running',
  无阵列: 'No array',
  阵列运行中: 'Array running',
  阵列已停止: 'Array stopped',
  '校验 Parity': 'Verify parity',
  启动阵列: 'Start array',
  停止阵列: 'Stop array',
  取消: 'Cancel',
  '确认停止阵列？将卸载所有卷并停止 {n}。':
    'Stop the array? All volumes will be unmounted and {n} will stop.',
  阵列卡: 'RAID controller',
  'HBA 直通': 'HBA passthrough',
  软阵列: 'Soft RAID',
  '内核 md (mdadm)': 'Kernel md (mdadm)',
  直连盘: 'Direct-attached disks',
  '{n} 块 · 无阵列': '{n} disks · no array',
  降级: 'Degraded',
  '型号：{v}': 'Model: {v}',
  '驱动：{v}': 'Driver: {v}',
  阵列设备: 'Array devices',
  '温度阈值：{a} °C {w} · {b} °C {h}': 'Temp thresholds: {a} °C {w} · {b} °C {h}',
  设备: 'Device',
  文件系统: 'Filesystem',
  读取: 'Read',
  写入: 'Write',
  状态: 'Status',
  '卷 {n}': 'Volume {n}',
  已挂载: 'Mounted',
  '数据卷 {n}': 'Data volume {n}',
  实时: 'Live',
  挂载点: 'Mount point',
  写满预测: 'Full-in forecast',
  存储拓扑: 'Storage topology',
  '预计剩余 {v}': '~{v} remaining',
  热备: 'Hot spare',

  // ---- 硬盘 SMART 页 ----
  '硬盘 SMART': 'Disk SMART',
  '健康状态 · 自检': 'Health · Self-test',
  '{n} 块警告': '{n} warnings',
  全部正常: 'All healthy',
  转速: 'Speed',
  通电时间: 'Power-on time',
  操作: 'Actions',
  自检: 'Self-test',
  '短自检（B · 约 2 分钟）': 'Short test (B · ~2 min)',
  '长自检（C · 约 4 小时）': 'Long test (C · ~4 h)',
  '短修复（A · 离线）': 'Conveyance (A · offline)',
  盘位: 'Slot',
  健康趋势: 'Health trend',
  磁盘: 'Disk',
  指标: 'Metric',
  '近 30 天 · 1h 桶': 'Last 30 days · 1h buckets',
  窗口变化: 'Window change',
  '该盘暂无趋势数据（—）：功能上线后按 1h 桶逐渐积累，休眠盘不采样':
    'No trend data for this disk yet (—): buckets accumulate hourly after rollout; sleeping disks are not sampled',
  进行中的自检: 'Self-test in progress',
  '自检类型：A 短修 / B 短检 / C 长检 · 完成后健康状态在本页更新':
    'Types: A conveyance / B short / C long · health status updates on this page when done',
  重映射扇区: 'Reallocated sectors',
  待定扇区: 'Pending sectors',
  不可修正扇区: 'Uncorrectable sectors',
  磨损均衡: 'Wear leveling',
  '寿命已用 %': 'Life used %',
  介质错误: 'Media errors',
  '温度 °C': 'Temp °C',
  通电小时: 'Power-on hours',

  // ---- 硬件检测页 ----
  硬件检测: 'Hardware detection',
  '系统 · 主板 · CPU · 内存 · 网络 · RAID · 硬盘':
    'System · Board · CPU · Memory · Network · RAID · Disks',
  系统信息: 'System info',
  内存: 'Memory',
  运行环境自检: 'Runtime environment check',
  '安装期自举结果 · 实时探测': 'Install-time bootstrap results · live probing',
  每核实时占用: 'Per-core live usage',
  点击格子看详情: 'Click a slot for details',

  // ---- 系统资源页 ----
  系统资源: 'System resources',
  'CPU · 内存 · 网络 · 磁盘 IO · GPU': 'CPU · Memory · Network · Disk I/O · GPU',
  网络: 'Network',
  全网聚合: 'All interfaces',
  读: 'Read',
  写: 'Write',
  'RAPL 功耗': 'RAPL power',
  合计: 'Total',
  '— % · 60s 窗口': '— % · 60s window',
  '60s 窗口': '60s window',

  // ---- Docker 页 ----
  '容器运行状态 · 资源占用': 'Container status · resource usage',
  容器: 'Container',
  网速: 'Net',
  端口映射: 'Port mapping',
  运行时长: 'Uptime',
  '演示数据（本机无 Docker 或后端不可达）': 'Demo data (no Docker on host or backend unreachable)',
  '{a} 个运行中 · {b} 已退出': '{a} running · {b} exited',
  '移动端：表格横向滚动（卡片化列入迭代评估）':
    'Mobile: the table scrolls horizontally (card layout under evaluation)',

  // ---- 事件时间线页 ----
  事件时间线: 'Event timeline',
  '告警 · 系统事件 一屏回溯': 'Alerts · system events at a glance',
  严重: 'Critical',
  信息: 'Info',
  告警: 'Alert',
  全部: 'All',
  '{n} 条活跃': '{n} active',
  全部平静: 'All quiet',
  进行中: 'Active now',
  '暂无事件记录（—）：告警触发、巡检、容器退出、端口异动、日志哨兵命中都会出现在这里':
    'No events yet (—): alert firings, inspections, container exits, port changes and log-sentinel hits appear here',

  // ---- 历史趋势页 ----
  历史趋势: 'History trends',
  '六维度历史数据回看 · 报告导出': 'Six-dimension history · report export',
  'Markdown 报告': 'Markdown report',
  'HTML 报告': 'HTML report',
  'CSV 数据': 'CSV data',
  区间统计: 'Range stats',
  均值: 'Avg',
  峰值: 'Peak',
  采样点: 'Samples',
  导出格式: 'Export format',
  立即下载: 'Download now',

  // ---- 示波器页 ----
  实时推送: 'Live push',
  轮询降级: 'Polling fallback',
  '等待实时数据流入（—）：WS 推送或轮询降级接入后开始绘制':
    'Waiting for live data (—): drawing starts once the WS push or polling connects',
  '悬停画布显示游标读数；数据源为 1s 实时快照，页面隐藏或离开本页自动停绘（零常驻开销）。':
    'Hover the canvas for cursor readouts; data source is the 1s live snapshot — drawing pauses when the page is hidden or left (zero resident cost).',

  // ---- 大屏 ----
  '网速 ↓': 'Net ↓',
  '网速 ↑': 'Net ↑',
  负载: 'Load',
  进程: 'Procs',
  运行: 'Up',
  天: 'd',
  磁盘清单不可用: 'Disk list unavailable',
  温度传感器不可用: 'Temperature sensors unavailable',
  '暂无事件（—）': 'No events (—)',
  '退出大屏（Esc）': 'Exit kiosk (Esc)',
  已暂停: 'Paused',
  屏: 'screen',

  // ---- 端口页 ----
  端口占用: 'Port occupancy',
  '监听端口 · 进程 · 可达性': 'Listening ports · processes · reachability',
  '搜索端口 / 进程 / 应用': 'Search ports / processes / apps',
  全部可达性: 'All reachability',
  可达: 'Reachable',
  受限: 'Restricted',
  不可达: 'Unreachable',
  '进程 (PID)': 'Process (PID)',
  可达性: 'Reachability',
  确认释放: 'Confirm release',
  确认: 'Confirm',
  无匹配端口: 'No matching ports',
  应用: 'App',
  协议: 'Protocol',

  // ---- 关于页 ----
  后端已连接: 'Backend connected',
  检查更新: 'Check updates',
  当前版本: 'Current version',
  最新版本: 'Latest version',
  '（已是最新）': ' (up to date)',
  更新日志: 'Changelog',
  构建信息: 'Build info',

  // ---- 花活二期 I：2.5D 硬盘舱位墙 ----
  表格: 'Table',
  舱位: 'Bays',
  硬盘舱位: 'Disk bays',
  '面板色 = 温度（{a} °C 偏高 · {b} °C 过热）· 灯 = 真实 IO · 点击翻面看 SMART 摘要':
    'Panel = temp ({a} °C warm · {b} °C hot) · LEDs = real IO · click to flip for SMART summary',
  '暂无盘位数据（—）': 'No disk bay data (—)',
  '暂无趋势数据（—）': 'No trend data yet (—)',
  '近 30 天重映射扇区 · 1h 桶': 'Reallocated sectors · last 30 days, 1h buckets',

  // ---- 花活二期 K：进程风暴榜 ----
  进程风暴榜: 'Process storm board',
  '5s 采样 · 两轮均值去抖 · 仅名称与占用': '5s sampling · 2-round smoothed · names & usage only',
  '等待采样（—）': 'Waiting for samples (—)',
  'CPU Top 8': 'CPU Top 8',
  '内存 Top 8': 'Memory Top 8',
  '暂无进程采样（—）：实时通道接入后自动出现':
    'No process samples yet (—): appears once the realtime channel connects',
  'CPU 榜首': 'Top CPU',

  // ---- 花活二期 J：硬盘健康预言 ----
  健康分: 'Score',
  健康预言: 'Health oracle',
  良好: 'Good',
  观察: 'Watch',
  异常: 'Bad',
  新盘: 'New disk',
  重映射增速: 'Realloc growth',
  温度余量: 'Temp margin',
  磨损度: 'Wear',
  寿命已用: 'Life used',
  '评分 = 五维加权（变化速率为主、绝对值为辅）':
    'Score = 5-dim weighted (growth rate primary, absolute secondary)',
  '预计 {n} 天后触及阈值 {v}': 'Hits threshold {v} in ~{n} days',
  '当前 {c} · 日增 {r}': 'now {c} · +{r}/day',
  '暂无触阈值预测（—）：拿得到 SMART 阈值且有正增速时给出':
    'No ETA yet (—): shown when a SMART threshold exists and growth is positive',
  '该盘暂无评分（—）：接入并完成 SMART 采样后自动给出':
    'No score yet (—): appears automatically after SMART sampling',

  // ---- 花活二期 O：开机自检动画 ----
  不再播放: "Don't play again",
  点击任意处跳过: 'Click anywhere to skip',

  // ---- 花活二期 N：一键体检 ----
  一键体检: 'Health checkup',
  '六维体检：预言/容量/阵列/温度/告警/端口':
    '6-dim checkup: oracle/capacity/raid/temp/alerts/ports',
  '正在体检…': 'Checking…',
  '体检不可用（—）：后端不可达，不显示假分':
    'Checkup unavailable (—): backend unreachable, no fake score',
  硬盘预言: 'Disk oracle',
  容量预测: 'Capacity forecast',
  阵列状态: 'Array status',
  '30 天告警': '30-day alerts',
  端口暴露面: 'Port exposure',
  '生成分享 PNG': 'Share PNG',
  点击任意处跳过动画: 'Click anywhere to skip animation',

  // ---- 花活二期 Q：跑分中心 ----
  跑分中心: 'Disk benchmark',
  '只读顺序读基准 · 占空比限速 · 同一时间仅一块盘':
    'Read-only sequential benchmark · duty-cycled · one disk at a time',
  开始跑分: 'Start benchmark',
  取消跑分: 'Cancel benchmark',
  占用: 'duty',
  已读: 'Read',
  '速度曲线随采样点逐步出现…': 'Speed curve builds up as samples arrive…',
  '基准期间该盘业务延迟会上升（物理规律）；休眠盘默认跳过不唤醒':
    'Disk latency will rise during the benchmark (physics); standby disks are skipped, never woken',
  '只读不写（O_DIRECT 绕页缓存）；standby 盘默认跳过不唤醒':
    'Read-only, never writes (O_DIRECT bypasses page cache); standby disks are skipped, never woken',
  上次跑分出错: 'Last benchmark failed',
  '盘与盘对比（最新成绩 · 墙钟均值含限速窗口）':
    'Disk vs disk (latest results · wall-clock average incl. duty windows)',
  历史成绩: 'History',
  '暂无成绩（—）：跑分完成后此处出榜':
    'No results yet (—): the board appears after a benchmark finishes',
  时长: 'Duration',
  平均: 'Avg',

  // ---- 花活二期 M：Docker 舰牌墙 ----
  容器舰队: 'Container fleet',
  意外退出: 'Unexpected exit',
  '↓ 读 · ↑ 写': '↓ read · ↑ write',
  '24h CPU': '24h CPU',
  '暂无 24h 趋势（1m 桶积累中）': 'No 24h trend yet (1m buckets accumulating)',
  重启: 'Restart',
  停止: 'Stop',
  启动: 'Start',
  '确认重启容器 {n}？': 'Restart container {n}?',
  '确认停止容器 {n}？': 'Stop container {n}?',
  'Docker 不可用（—）': 'Docker unavailable (—)',
};
