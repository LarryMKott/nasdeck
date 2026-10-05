# nasdeck

**0.1.0**（正式版） · 飞牛OS（fnOS）NAS 硬件监控面板

把原本要 SSH 敲命令才能看到的硬件状态——CPU、内存、温度、风扇、硬盘 SMART、阵列卡、存储卷、Docker、端口占用——装进一块 UNRAID 风格的网页面板。FastAPI 采集、Vue 3 展示，标准 FPK 包装，打开即用。

![总览](docs/screenshots/01-overview.png)

## 功能一览

- **监控**：总览仪表盘（秒级推送）、硬件检测（主板/CPU/内存/网卡/阵列卡三形态识别 + 运行环境自检）、温度墙、系统资源、历史趋势（秒级→分钟→10 分钟三级粒度，2h/30d/90d 保留）
- **存储**：真实层级存储拓扑树（控制器→阵列→成员盘→分区/挂载点）、硬盘 SMART 健康分级与在线自检、NVMe 健康温度接入
- **控制**：风扇 hwmon PWM 接管 + 温度→占空比曲线编辑器 + 失控保护；告警阈值规则 + Bark/Telegram/邮件/Webhook 通知；健康报告导出（可脱敏）
- **安全**：面板仅绑回环，经飞牛 cgi 反代持登录态；普通用户只读，写操作仅管理员（后端强校验）

## 安装

1. 下载 [最新版 fpk](https://github.com/LarryMKott/nasdeck/releases/latest)
2. 飞牛应用中心 → 手动安装（Python 依赖随包离线内置，无需联网）
3. 桌面点开「NAS硬件监控」图标即用；详细说明见[操作手册](https://github.com/LarryMKott/nasdeck/wiki/%E6%93%8D%E4%BD%9C%E6%89%8B%E5%86%8C)

## 文档

- [操作手册（Wiki）](https://github.com/LarryMKott/nasdeck/wiki) · [前后端接口约定](docs/前后端数据接口约定.md) · [FPK 打包说明](fpk/README.md)

## 开发

```bash
cd backend && python main.py                          # 后端 127.0.0.1:8766
cd frontend && pnpm dev                               # 前端 5173（代理后端，演示数据兜底）
cd backend && python -m pytest tests/ -q              # 测试 139 项
python scripts/build_fpk.py --python <解释器路径>       # 打 FPK 包
```

架构设计、编码约定、打包细节与运维排障见[项目 Wiki](docs/wiki/Home.md)。

## License

[MIT](LICENSE)
