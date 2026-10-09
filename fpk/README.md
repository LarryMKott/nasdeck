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
│   ├── install_callback    # 监听端口落盘 + 系统工具自举 + 可执行位兜底 + 用户配置还原
│   ├── upgrade_callback    # 还原端口镜像（升级整体替换包文件后从 var 恢复）
│   ├── config_callback     # 运行配置落盘（端口/日志级别/保留时长）+ 条件重启
│   ├── uninstall_callback  # 按向导选择保留/清除 @appdata（有路径安全护栏）
│   └── *_init/*_callback   # 占位（exit 0）
├── wizard/
│   ├── install             # 安装说明页 + 监听端口向导（wizard_port，默认 9800）
│   ├── uninstall           # 卸载页：用户选是否删除配置数据
│   └── config              # 配置页：端口（0=不变）/日志级别/原始数据保留时长
└── app/                    # 应用内容（安装后与系统层合并到应用根目录）
    ├── app.py              # 健康检 shim：飞牛经 /app/app.py 软链探活（真机实测，勿删）
    ├── ui/
│   ├── config          # 桌面入口（生效副本，缺省 = config.cgi；cmd/main 按访问模型自愈切换）
│   ├── config.cgi      # CGI 反代形态入口变体（iframe → /cgi/ThirdParty/.../index.cgi/）
│   ├── config.gateway  # 统一网关形态入口变体（gatewayPrefix=/app/{appname} + gatewaySocket）
│   ├── index.cgi       # CGI 反代 → 本机回环端口（默认 9800，读同目录 ui/port 镜像；网关形态不使用但随包保留）
│   └── images/icon_{64,256}.png
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
| 访问模型 | **安装/配置向导可选 CGI 反代（缺省）或统一网关**；CGI = iframe → index.cgi → 本机回环端口（WebSocket 不可用，前端 2s 轮询），网关 = uvicorn 监听 `${TRIM_APPDEST}/app.sock`（WebSocket 实时推送）。权威选择落 `${TRIM_PKGVAR}/access_mode`，**cmd/main start 时应用**：按形态导出 `NASDECK_UDS/GATEWAY_PREFIX/PUBLIC_PATH`、把 `ui/config.{cgi,gateway}` 变体应用为生效入口（升级打回后自愈）；**index.cgi 按形态分派转发目标**（gateway → `--unix-socket app.sock`），桌面入口 URL 注册滞后于形态切换时旧图标 URL 依旧可达（0.2.17 真机实测教训：入口注册不热更新，图标仍指 CGI URL） | 网关 2026-08 真机教训（入口被清）在现行 ui/config 声明方式下未复现（gwprobe 48h 观察见下），故恢复为可选项、CGI 仍缺省；前缀剥离中间件对「网关剥/不剥前缀」两种转发行为均正确；网关形态鉴权信任边界 = app.sock 文件权限（`require_trim_auth` 按 NASDECK_UDS 跳过 proxy_token） |
| 端口 | 回环端口**默认 9800，安装向导可自定义、应用「配置」可随时修改**（`wizard_port` → 校验+占用预检 → 落盘 `${TRIM_PKGVAR}/port`，镜像 `ui/port`）；manifest 按 CGI 规范省略 `service_port`、`checkport=false` | cmd/main 与 index.cgi 从同一落盘文件读端口（非法值回退 9800）；仅绑 127.0.0.1，不向局域网暴露管理面板 |
| 运行参数 | 日志级别 / 原始数据保留时长经**配置向导**落盘 `${TRIM_PKGVAR}/runtime.env`，cmd/main 启动时 source | `NASDECK_LOG_LEVEL` 仅在用户显式选过时落盘导出，缺省由后端按版本通道判定：**dev- 前缀包 DEBUG**（真机排查采集链路）、正式包 INFO；`NASDECK_RAW_KEEP_MINUTES`（默认 120）；后端 pydantic-settings 前缀映射零改动 |
| 鉴权 | `NASDECK_TRIM_AUTH=true`：读=飞牛登录（X-Trim-Userid），写=管理员（X-Trim-Isadmin） | index.cgi 转发的可信身份头在后端强制校验（`require_trim_auth`）；桌面入口 `allUsers=true` 全员可见（普通用户只读，前端屏蔽设置按钮）；`/health` 探针除外 |
| 权限 | `run-as: root` | SMART / storcli / hwmon PWM 写入 / systemctl 全部需要 root；面板本身在飞牛登录态 + 分级鉴权之后 |
| Python | `install_dep_apps=python312` 提供解释器；依赖离线打进 site-packages | 不联网、不 pip 装系统（旧 `--break-system-packages` 方案废弃）；`PYTHONPATH` 注入 |
| 前端 | `.env.fpk`：base=完整 cgi 前缀，history 路由刷新不丢资源；SPA 回退由后端承担（`NASDECK_STATIC_DIR`） | nas 数据层自带 index.cgi 前缀自适应；WS 经代理不可用 → 前端自动降级 2s 轮询 |
| 数据 | DB 落 `TRIM_PKGVAR`（@appdata，重启/升级保留）；日志落 `TRIM_PKGVAR/app.log` | 遵循 TRIM_* 环境变量，代码零硬编码路径 |
| 健康检 | `app/app.py` shim + cmd/main 重建 `/app/app.py` 软链 | 飞牛靠该软链探活第三方应用，uninstall 会删软链而 install 不重建（不补则 start 报 10500） |

## cmd/main 里的环境变量约定

```bash
export PATH=/var/apps/python312/target/bin:$PATH   # 运行时解释器
export NASDECK_PORT="$(head -n 1 "${TRIM_PKGVAR}/port")"  # 向导落盘端口，缺省回退 9800
export NASDECK_HOST=127.0.0.1   # 回环反代
. "${TRIM_PKGVAR}/runtime.env"  # 配置向导落盘：LOG_LEVEL（显式配置才有）/ RAW_KEEP_MINUTES（缺省 120）
export NASDECK_DB_URL="sqlite+aiosqlite:///${TRIM_PKGVAR}/nasdeck.db"  # 四斜杠=绝对路径，三斜杠是相对路径
export NASDECK_STORCLI_PATH="${SERVER_DIR}/bin/storcli64"
export NASDECK_STATIC_DIR="${SERVER_DIR}/web/dist" # 后端托管 SPA（挂载时按 PUBLIC_PATH 替换 index.html 资源基址占位符）
export NASDECK_TRIM_AUTH=true                      # 分级鉴权：读=飞牛登录用户，写=管理员
export NASDECK_PUBLIC_PATH="/cgi/ThirdParty/com.dashboard.nasdeck/index.cgi"  # CGI 形态；网关形态=/app/com.dashboard.nasdeck
# 以下仅网关形态导出（CGI 形态缺省）：
# export NASDECK_UDS="${TRIM_APPDEST}/app.sock"                # uvicorn 监听 Unix Socket（TCP 不生效）
# export NASDECK_GATEWAY_PREFIX="/app/com.dashboard.nasdeck"   # 前缀剥离中间件
# 网关形态不导出 NASDECK_PROXY_TOKEN（无 index.cgi，信任边界=app.sock 文件权限）
export PYTHONPATH="${SERVER_DIR}/site-packages"
```

## 安装与真机验证

1. 应用中心 → 手动安装 → 选 `.fpk`（官方注明仅限本地测试；分发走应用中心/GitHub Release）。
2. 验证清单：
   - 安装成功、桌面出现「NAS硬件监控」图标（所有用户可见）、点击打开面板（需登录飞牛）
   - `cmd/main status` 退出码 0；`curl 127.0.0.1:9800/health` 返回 healthy
   - 面板各页数据正常（CPU/硬盘 SMART/阵列卡/风扇），风扇控制可写 PWM
   - 硬件检测页「运行环境自检」分区如实反映自举结果：工具缺哪个、驱动加载没、生效配置
   - 鉴权：管理员读写正常；普通用户可看面板、写操作 403 且无设置按钮；直连 9800 无身份头返回 403
   - 停止/启动/升级各一遍；升级后 @appdata 数据仍在
   - 卸载 → 选「保留配置」→ 重装 → 配置还原（config_backup 镜像生效）
3. 自定义端口验证（第二次装机时做）：
   - 向导改端口（如 9801）安装：`cat @appdata/.../var/port` 为 9801，面板可打开，
     `curl 127.0.0.1:9801/health` 返回 healthy
   - 向导填已占用端口 → 安装失败并弹「端口已被占用」提示；换端口后可装
   - 升级一次 → 端口镜像 `ui/port` 被还原，面板仍走 9801
4. 配置向导验证（应用中心 → 应用设置 → 配置）：
   - dev 包未配置过日志级别时 `var/runtime.env` 无 `NASDECK_LOG_LEVEL` 键，app.log 启动行显示 `log_level=DEBUG` 且有工具调用/采集明细（`工具 smartctl … → rc=0 …`）
   - 改日志级别为 DEBUG 保存 → `var/runtime.env` 更新，app.log 出现 DEBUG 记录；改回 INFO 后采集明细消失（启动行 `log_level=INFO`）
   - 改端口（如 9802）保存 → 服务自动重启，面板经 9802 可访问；改回 9801 同理
   - 全部选「保持不变/0」保存 → 服务不重启，runtime.env 不变
   - 保留时长改 240 → 数据库原始表保留窗口变化（降采样任务按新值裁剪）
5. 从旧版（Flask/2.3.3 及更早）升级：appname 未变（`com.dashboard.nasdeck`），直接
   覆盖安装即走升级流程；历史数据库统一迁到 @appdata。

## 已知限制

- 实时推送（WebSocket）经 CGI 反代不可用，前端自动降级为 2s 轮询（设计内行为）。
- `platform=x86`：随包 storcli64 为 x86_64 ELF；ARM 机器缺少阵列卡功能（其余正常降级）。
- 健康报告 HTML 写在应用 target 目录（升级会清），历史数据本体在 @appdata 不受影响。

## 真机形态事实（fnOS 1.2.0701，2026-10-08/09 gwprobe 试验实测）

试验包 `scripts/gwprobe/`（应用 `com.test.gatewayprobe`，独立于生产包，验证完卸载）。
以下事实影响所有 FPK 包与「访问模型」选型：

- **生命周期回调在下载暂存目录执行**（`/vol2/appcenter-downloads/...-tpk`，升级后即清）：
  `TRIM_APPDEST` 不注入、`TRIM_PKGVAR` 正常。回调里禁止用脚本自身位置反推目标路径写
  长期存活文件，一律走 `/var/apps/{appname}` 稳定前门。生产包 `install_callback` 的
  `ui/port`、`ui/proxy_token` 镜像因此落不进 target/ui/——**功能无损**：index.cgi 有
  var 权威副本回退链，且 fnOS 维护 `/var/apps/{app}/var → @appdata` 符号链接；镜像由
  cmd/main start 自愈（2026-10-09 起）。安装向导「自定义端口」真机验证仍是待办。
- **appcenter-cli 无升级命令**：install-fpk 对已装应用一律拒绝（同版本跳过、新版本也拒），
  升级 = uninstall + install；uninstall 不清 @appdata。
- fnpack 设备端校验 `config/resource` 必需（缺则装机失败 code 10111），最小合法内容
  `{"data-share":{"shares":[]}}`。
- **网关鉴权先于路由**：未登录 curl 对存在/不存在的网关入口一律 `200 "invalid token"`，
  HTTP 层无判别力；入口存活性只能看存储层——`/var/apps_ui/{app}` 符号链接（安装时
  创建，指向 target/ui）+ config 的 `gatewaySocket` 字段（系统不改写 ui/config 内容）。
  网关路由由 `trim_http_cgi`（Go）服务读取。

## 网关模式复核试验（进行中，结论待 48h watch.log）

「安装时让用户选访问模型（index.cgi / 统一网关）」的前置验证：2026-08 的
「飞牛周期性清空第三方 gateway 入口」缺陷在当前版本是否仍复现。探针 root cron
每 10 分钟采样落 `/vol2/@appdata/com.test.gatewayprobe/watch.log`，判据：
`ALIVE` 全链路健康 / `ENTRY_CLEARED` 入口被清（缺陷复现）/ `SVC_DOWN`、`SOCK_DEAD`
非入口问题。2026-10-08 23:02 部署起持续 ALIVE（截至 10-09 上午无复现）。
结论出来后更新「访问模型」决策行；若缺陷已消失，网关模式的价值是 WS 实时推送
（省掉 2s 轮询降级），届时再做安装/配置向导的模型切换（判据走存储层，不带登录态即可监控）。
