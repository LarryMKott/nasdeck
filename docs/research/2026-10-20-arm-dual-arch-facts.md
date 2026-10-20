# ARM 双架构外部事实核查（2026-10-20）

> 对应票：https://github.com/LarryMKott/nasdeck/issues/10
> 范围：fnOS ARM 现状、manifest `platform` 语义、ARM 上的 `python312` 运行时、fnpack 双架构交付、storcli 的 aarch64 版本、CPython 3.12 aarch64 wheel、ARM 系统能力。
> 证据分级：**已核实**（有官方文档或一手仓库实证）、**未核实**（无直接证据，按最坏情况设计）、**无法确认**（官方沉默或零证据）。

## 1. ARM 版 fnOS 与 `platform`

| # | 结论 | 状态 |
|---|---|---|
| 1.1 | fnOS ARM 公测版 2026-02-10 发布，官网独立镜像入口 <https://www.fnnas.com/download-arm>（UEFI ARM ISO + 数十款设备固件） | 已核实 |
| 1.2 | ARM 版当前版本号 1.2.0701（2026-10-12），与 x86 同为 4 段版本格式，`os_min_version` 可用同一门槛 | 已核实（下载页） |
| 1.3 | 官方 ARM 公测声明：公测、不建议生产、需备份，BUG 反馈至社区 ARM 版块 | 已核实 <https://help.fnnas.com/articles/v1/contact/disclaimers> |
| 1.4 | `platform` 仅允许 `x86` / `arm` / `all` 三个值；旧字段 `arch` 已废弃 | 已核实 <https://developer.fnnas.com/docs/core-concepts/manifest/> |
| 1.5 | `platform=all` 官方语义：同时支持 x86 和 ARM 设备，**仅当应用包不包含特定架构二进制时使用** | 已核实（同上，官方原话） |
| 1.6 | 官方文档落实 `all` 的实例：纯 Python 标准库网关代理写 `platform = all`，单包同时支持 x86_64/ARM64 | 已核实（社区实证）<https://github.com/techysy/deepseek-harness-fnos> |

## 2. ARM 上的 `python312` 运行时

| # | 结论 | 状态 |
|---|---|---|
| 2.1 | 官方 runtime 文档仅写 `install_dep_apps=python312` + `export PATH=/var/apps/python312/target/bin:$PATH`，全文未区分 x86/ARM | 已核实（文档未分架构）<https://developer.fnnas.com/docs/core-concepts/runtime/> |
| 2.2 | 依赖应用机制在 ARM 上确实工作：有项目在 ARM fpk 中用 `install_dep_apps=nodejs_v24` + `bunjs` 成功 | 已核实（社区实证）<https://github.com/techysy/deepseek-harness-fnos> |
| 2.3 | ARM 上是否存在同名 `python312` 应用、解释器是否同为 `/var/apps/python312/target/bin` | **未核实**（无官方说明、未找到 ARM 设备实证）→ 按「可能不存在」设计 |

## 3. fnpack 与双架构交付形态

| # | 结论 | 状态 |
|---|---|---|
| 3.1 | fnpack 官方提供 Linux ARM 构建（`fnpack-1.2.3-linux-arm64`），最新 1.2.3 | 已核实 <https://developer.fnnas.com/docs/cli/fnpack/> |
| 3.2 | fnpack 构建前检查项仅有 manifest / privilege / resource / ICON / app / cmd / wizard 等，文档未列任何 `platform` 与包内容一致性校验 | 未核实（文档未列 ≠ 一定不校验；需二进制实测） |
| 3.3 | 官方文档没有「一个 fpk 同时含 x86 与 arm 产物」的机制说明，也未规定双架构交付形态 | 无法确认（官方沉默） |
| 3.4 | 官方只要求「在计划支持的 fnOS 版本和硬件架构上测试应用」 | 已核实 <https://developer.fnnas.com/docs/quick-started/publish-application> |
| 3.5 | 社区通行做法：按架构各出一个 fpk（`<app>_<ver>_x86.fpk` / `_arm.fpk`），sed 改 manifest 的 `platform` 后分别 `fnpack build`；纯无二进制包才用 `all` 单包 | 已核实（多例）<https://github.com/conversun/fnos-store/blob/main/build.sh> <https://github.com/kci-lnk/fn-fpk-builder-skill/blob/main/SKILL.md> |
| 3.6 | fnpack 已知限制：不支持包内 symlink（打包前须删除） | 已核实（社区实证）<https://github.com/techysy/deepseek-harness-fnos> |

## 4. storcli 的 aarch64 版本

| # | 结论 | 状态 |
|---|---|---|
| 4.1 | Broadcom Unified StorCLI 包内含 ARM 分支：`Unified_storcli_all_os/ARM/Linux/storcli64_007.2705.0000.0000_arm64.deb` | 已核实（第三方资源说明引用 Broadcom docs 1232743397）<https://charmhub.io/hardware-observer/resources/storcli-deb> |
| 4.2 | AUR `storcli` PKGBUILD 声明 `arch=('x86_64' 'aarch64')`，aarch64 取 `ARM/Linux` 分支 | 已核实 <https://aurwatch.org/package/storcli> |
| 4.3 | 安装落点同 x86：`/opt/MegaRAID/storcli/`（aarch64 rpm 路径官方文档示例） | 已核实 <https://support.huawei.com/enterprise/en/doc/EDOC1100048773/177cf185/downloading-and-installing-storcli> |
| 4.4 | ARM 上非 MegaRAID 场景（HBA/JBOD/SATA）替代：`lspci` + `/sys/class/scsi_host`/`/sys/block` + `smartctl -d megaraid,N` 或 `-d sat`；MegaRAID 专有 ioctl 无用户态替代 | 部分核实（工具路径通用，fnOS ARM 实测未取证） |

## 5. manylinux + CPython 3.12 aarch64 wheel

| 包 | aarch64 cp312 wheel | 状态 |
|---|---|---|
| uvloop | `uvloop-0.23.0-cp312-cp312-manylinux2014_aarch64.manylinux_2_17_aarch64.manylinux_2_28_aarch64.whl` | 已核实 <https://pypi.org/pypi/uvloop/0.23.0/json> |
| greenlet | `greenlet-3.5.6-cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl` —— **只有 2_24/2_28，没有 manylinux2014(2_17)** | 已核实 <https://pypi.org/pypi/greenlet/3.5.6/json> |
| watchfiles | 1.2.0 有 `cp312-manylinux_2_17_aarch64.manylinux2014_aarch64`；最新 1.3.0 同类发布 | 已核实（1.2.0 文件页；1.3.0 未逐文件核） |
| pydantic-core | 多个版本有 `cp312-cp312-manylinux_2_17_aarch64.manylinux2014_aarch64` | 已核实（索引镜像）<https://dl.espressif.com/pypi/pydantic-core> |
| psutil | 以 `cp36-abi3-manylinux_2_17_aarch64.manylinux2014_aarch64` 发布，abi3 覆盖 3.12 | 已核实 <https://dl.espressif.com/pypi/psutil> |
| httptools / websockets / SQLAlchemy / pyyaml | 未逐文件核 | 未核实（需 CI 门禁实测） |
| fastapi / uvicorn / aiosqlite / apscheduler / pydantic | 纯 Python 包，理论上 `py3-none-any` | 未核实（建议门禁命令验证） |

门禁命令（不安装、只解析）：

```bash
pip download --no-deps --only-binary=:all: \
  --platform manylinux2014_aarch64 --platform manylinux_2_28_aarch64 \
  --python-version 3.12 --implementation cp \
  -r requirements.txt -d /tmp/x
```

## 6. ARM fnOS 的系统能力

| # | 结论 | 状态 |
|---|---|---|
| 6.1 | dmidecode 读 SMBIOS/DMI 表；上游明确只在 x86 上扫 `/dev/mem` 找入口点，arm64 有专门处理——即 ARM 仅在固件提供 SMBIOS 时可用 | 已核实 <https://github.com/acidanthera/dmidecode/blob/master/NEWS> |
| 6.2 | RK3xxx / Amlogic / 全志等 device-tree 板（fnOS ARM 首批主力）无 DMI → `/sys/class/dmi` 不存在、`dmidecode` 报 "No SMBIOS nor DMI entry point found" | 未核实（逻辑推断，未在 fnOS ARM 实测） |
| 6.3 | devicetree 路径 `/proc/device-tree/model`、`/sys/firmware/devicetree/base`（`model` / `compatible`）可作主板标识；内存信息走 `/proc/meminfo`，非 devicetree | 未核实（标准内核接口，fnOS ARM 未实测） |
| 6.4 | ARM64 也存在 ACPI 模式（UEFI 服务器如鲲鹏/飞腾），此时 DMI 可能可用——同一份代码需运行时探测 | 已核实（ACPI/DT 双模式存在）<https://github.com/Sky1-Linux/acpi-to-dts-tools> |
| 6.5 | `lspci` / `smartctl` / `mdadm` / hwmon 风扇 PWM 在 fnOS ARM 上是否正常 | **无法确认**（零直接证据；hwmon PWM 还取决于板级 DTS 是否暴露 `pwm-fan`） |
| 6.6 | fnOS ARM 设备为 Debian 12 / glibc 2.36 | 已核实（社区实证）<https://github.com/techysy/deepseek-harness-fnos> |

## 7. ARM 安装目录与环境变量一致性

| # | 结论 | 状态 |
|---|---|---|
| 7.1 | `/var/apps/{appname}` 目录结构（cmd/config/manifest/target/etc/var/tmp/home/meta）官方文档未区分架构 | 已核实（文档 arch 无关）<https://developer.fnnas.com/docs/core-concepts/framework> |
| 7.2 | `TRIM_*` 变量集合同样 arch 无关；官方提供 `TRIM_SYS_ARCH` 供运行时判架构，并明确「行为不得与 manifest 声明的支持范围冲突」 | 已核实 <https://developer.fnnas.com/docs/core-concepts/environment-variables/> |
| 7.3 | ARM 专属限制：x86→ARM 存储盘可迁移，应用数据不跨架构兼容；建议空盘或先备份 | 已核实（第三方报道转述官方口径）<https://dt.zol.com.cn/1133/11330822.html> |
| 7.4 | 除上述外是否有 ARM 专属限制（如平台级 docker、网关限制） | 无法确认 |

## 对 nasdeck 的直接影响

1. **依赖（`scripts/build_fpk.py:49`）**：`TARGET_PLATFORMS` 现为 `manylinux2014_x86_64` + `manylinux_2_28_x86_64`；ARM 必须同时传 `manylinux2014_aarch64` 与 `manylinux_2_28_aarch64`——greenlet 只有 `manylinux_2_28_aarch64`，只给 manylinux2014 会导致 ARM 交叉安装直接失败。glibc 2.36 满足 2_28。
2. **manifest（`fpk/manifest:8`）**：`platform = x86` 必须按架构各出一包并改成 `platform = arm`（包内含 `storcli64` x86_64 ELF，永远不能写 `all`）；`os_min_version = 1.2.0` 对 ARM 可用同一门槛，但需真机实测才算声明成立。
3. **硬件采集（`backend/app/services/hardware/policy.py`）**：`/sys/class/dmi` + `dmidecode` 在 device-tree ARM 板上不存在，需加 devicetree（`/proc/device-tree/model`、`compatible`）兜底分支，否则 ARM 上主板/型号字段全空；风扇 PWM 依赖板级 hwmon，不可假定存在。
4. **打包脚本 + 发布流程**：`bin/storcli64` 与 `EXEC_FILES` 的 ELF 校验（`build_fpk.py:428-429`）在 ARM 上必须可跳过/替换（可换 Broadcom `storcli64_*_arm64.deb`，或直接不随包并降级阵列卡功能）；产物命名与 Release 资产需 `_x86` / `_arm` 双份，不能单包覆盖。
5. **解释器探测**：`install_dep_apps=python312` 在 ARM 上是否存在同名运行时**未核实**，`cmd/main` 与 `cmd/install_callback` 中 `/var/apps/python312/target/bin` 的定位需带 fallback + 人话报错（`TRIM_TEMP_LOGFILE`），否则 ARM 装机即失败且用户看不到原因。

## 仍未知（需真机或 CI 实测）

- ARM 上 `python312` 应用是否存在、解释器路径是否一致。
- fnpack 是否校验 `platform` 与包内容一致性（文档未列，需二进制实测）。
- fnOS ARM 上 `lspci` / `smartctl` / `mdadm` / hwmon PWM 的真实可用性（`.fpk` 真机验证）。
- QEMU 通用 virt 能否启动完整 fnOS ARM 机型镜像（本期验收不依赖，见 #18）。
- ARM 应用数据不跨架构兼容的具体范围（数据库/配置/缓存）。
