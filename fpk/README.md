# fpk/ — nasdeck 飞牛（fnOS）应用打包层

把 nasdeck（FastAPI 后端 + Vue3 前端）打成标准 FPK 应用包。对齐 fnOS FPK 应用开发标准
（目录结构 / 配置文件格式 / 打包规范 / 权限声明 / 日志规范），并保留旧版（Flask 时代）
在真机上用血泪换来的接线方式。

## 一键打包

```bash
# Windows 开发机（Git Bash）
backend/.venv/Scripts/python.exe scripts/build_fpk.py
# 产物：build/fpk/nasdeck-fnpack-<版本>.fpk
```

脚本自动完成：前端 `vite build --mode fpk` → Python 依赖交叉安装为
**Linux x86_64 cp312** site-packages（离线随包）→ 组包 → 按 fnpack 1.2.3 检查项校验
→ 出 `.fpk`。版本号唯一来源是 `backend/pyproject.toml`（注入 manifest 的 `@VERSION@`）。

`--builder manual` 可跳过官方 fnpack 强制用手工 tar 打包（默认 auto：fnpack 优先、
产物丢可执行位时自动回退——Windows 构建机的已知坑）。

## 包结构（fnpack 标准布局）

```
fpk/                        # 打包源（本目录）
├── manifest                # 元数据（INI 风格；version 由构建脚本注入）
├── config/
│   ├── privilege           # 权限：run-as root（见下「权限决策」）
│   └── resource            # usr-local-linker: server/bin/storcli64 → /usr/local/bin
├── cmd/                    # 生命周期脚本（可重复执行）
│   ├── main                # start/stop/status（退出码 0/1/3，官方约定）
│   ├── install_callback    # 系统工具自举 + 可执行位兜底 + 用户配置还原
│   ├── uninstall_callback  # 按向导选择保留/清除 @appdata（有路径安全护栏）
│   └── *_init/*_callback   # 占位（exit 0）
├── wizard/
│   ├── install             # 安装说明页
│   └── uninstall           # 卸载页：用户选是否删除配置数据
└── app/                    # 应用内容（安装后与系统层合并到应用根目录）
    ├── app.py              # 健康检 shim：飞牛经 /app/app.py 软链探活（真机实测，勿删）
    ├── ui/
    │   ├── config          # 桌面入口（iframe → /cgi/ThirdParty/.../index.cgi/）
    │   ├── index.cgi       # CGI 反代 → 127.0.0.1:9800（fnpackup 同款）
    │   └── images/icon-{64,256}.png
    └── server/             # 构建脚本生成
        ├── main.py + app/          # FastAPI 后端
        ├── site-packages/          # 离线依赖（Linux x86_64 cp312）
        ├── bin/storcli64           # 随包 LSI 工具
        └── web/dist/               # 前端产物（后端 SPA 托管）

build/fpk/pkg/              # staging（组装产物，可删）
build/fpk/nasdeck-fnpack-*.fpk  # 最终交付物
```

## 运行时接线（真机验证过的设计，改动前先读）

| 主题 | 决策 | 原因 |
|---|---|---|
| 访问模型 | **CGI 反代**（iframe → index.cgi → 127.0.0.1:9800），不用统一网关 | 飞牛会周期性清空第三方 `entry.gateway_socket` 导致网关 404（2026-08 真机实测，看门狗方案已废弃） |
| 端口 | 9800 **仅绑 127.0.0.1**；`service_port=9800 + checkport=true` | 只服务本机反代，不向局域网暴露管理面板；飞牛照常能探活 |
| 权限 | `run-as: root` | SMART / storcli / hwmon PWM 写入 / systemctl 全部需要 root；面板本身在飞牛登录态之后 |
| Python | `install_dep_apps=python312` 提供解释器；依赖离线打进 site-packages | 不联网、不 pip 装系统（旧 `--break-system-packages` 方案废弃）；`PYTHONPATH` 注入 |
| 前端 | `.env.fpk`：base=完整 cgi 前缀，history 路由刷新不丢资源；SPA 回退由后端承担（`NASDECK_STATIC_DIR`） | nas 数据层自带 index.cgi 前缀自适应；WS 经代理不可用 → 前端自动降级 2s 轮询 |
| 数据 | DB 落 `TRIM_PKGVAR`（@appdata，重启/升级保留）；日志落 `TRIM_PKGVAR/app.log` | 遵循 TRIM_* 环境变量，代码零硬编码路径 |
| 健康检 | `app/app.py` shim + cmd/main 重建 `/app/app.py` 软链 | 飞牛靠该软链探活第三方应用，uninstall 会删软链而 install 不重建（不补则 start 报 10500） |

## cmd/main 里的环境变量约定

```bash
export PATH=/var/apps/python312/target/bin:$PATH   # 运行时解释器
export NASDECK_PORT=9800  NASDECK_HOST=127.0.0.1   # 回环反代
export NASDECK_DB_URL="sqlite+aiosqlite://${TRIM_PKGVAR}/nasdeck.db"
export NASDECK_STORCLI_PATH="${SERVER_DIR}/bin/storcli64"
export NASDECK_STATIC_DIR="${SERVER_DIR}/web/dist" # 后端托管 SPA
export PYTHONPATH="${SERVER_DIR}/site-packages"
```

## 安装与真机验证

1. 应用中心 → 手动安装 → 选 `.fpk`（官方注明仅限本地测试；分发走应用中心/GitHub Release）。
2. 验证清单：
   - 安装成功、桌面出现「NAS硬件监控」图标、点击打开面板（需先登录飞牛）
   - `cmd/main status` 退出码 0；`curl 127.0.0.1:9800/health` 返回 healthy
   - 面板各页数据正常（CPU/硬盘 SMART/阵列卡/风扇），风扇控制可写 PWM
   - 停止/启动/升级各一遍；升级后 @appdata 数据仍在
   - 卸载 → 选「保留配置」→ 重装 → 配置还原（config_backup 镜像生效）
3. 从旧版（Flask/2.3.3 及更早）升级：appname 未变（`com.dashboard.nasdeck`），直接
   覆盖安装即走升级流程；历史数据库统一迁到 @appdata。

## 已知限制

- 实时推送（WebSocket）经 CGI 反代不可用，前端自动降级为 2s 轮询（设计内行为）。
- `platform=x86`：随包 storcli64 为 x86_64 ELF；ARM 机器缺少阵列卡功能（其余正常降级）。
- 健康报告 HTML 写在应用 target 目录（升级会清），历史数据本体在 @appdata 不受影响。
