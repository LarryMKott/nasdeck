# 文档 vs 实现 偏差审计（2026-10-20）

> 范围：`backend/`、`frontend/`、`fpk/`、`prototype/` 与 `README.md`、`docs/wiki/*`、`docs/*.md`、`REVIEW-2026-10-19.md`。
> 方法：静态逐行对照（每条结论带 `文件:行号`）+ 硬验证（后端 pytest、前端 build）。
> 判定口径：文档写死的**契约**（接口路径/字段、端口、鉴权、权限、wizard、打包步骤）以文档为准，实现偏离即缺陷；**架构/目录/演进描述**以实现为准，文档过时即改文档。
> 基线：commit `7de22e1`，版本 `0.1.0`。

## 结论

**实现基本符合文档，未发现"文档契约要求而实现缺失"的功能缺口。** 绝大多数偏差是文档过时、文档内部自相矛盾，或旧蓝本未标注"已被后续决策推翻"。真正"实现偏离最新文档"的只有 1 处：前端路由模式（history vs hash），且实现自洽（后端有 SPA 回退），已按"实现为准"修正文档。

## 偏差清单

### A. 契约过时 / 自相矛盾（已改文档）

| ID | 文档位置 | 文档断言 | 实现证据 | 判定与处置 |
|---|---|---|---|---|
| D1 | `docs/前后端数据接口约定.md` §1.1:29；§7.1:493 | Vite 代理 target 指向 `127.0.0.1:9800`，与后端 8766 不一致，"联调前需对齐" | `frontend/.env.development:8` `VITE_PROXY_TARGET=http://127.0.0.1:8766`；`frontend/vite.config.js:22,76` 读该变量；`backend/app/core/config.py:29` `port: int = 8766` | 文档过时 → 已改 |
| D1b | 同上 §1.1:29 | dev server 端口 `5273` | `frontend/.env.development:5` `VITE_PORT=5173` | 文档过时 → 已改 |
| D2 | 同上 §1.4:73；§4:420 | WebSocket"当前无鉴权"，列入豁免 | `backend/app/api/ws/realtime.py:49-65` `_ws_authorized()`＋`:70-71` 未授权 `close(1008)`；`docs/wiki/06` 与 manifest changelog 均写"WS 鉴权" | **安全口径错误** → 已改为"WS 走握手鉴权" |
| D3 | 同上 §1.1:29 | `vite.config.ts` | 实际 `frontend/vite.config.js`（无 .ts） | 已改 |
| D4 | 同上 §1.1:27 | `api_prefix` 见 `backend/app/core/config.py` | `config.py` 无此字段；实际挂载 `backend/main.py:90` `app.include_router(api_router, prefix="/api/v1")` | 已改 |
| D12 | 同上 §1.1 部署形态表 | 只列"后端直连 8766"与"网关挂载"，未提 FPK 内部反代端口 | FPK 形态：`fpk/cmd/main:23-27`、`fpk/app/app.py:18` 默认 `NASDECK_PORT=9800`（wizard 可改，落 `TRIM_PKGVAR/port`）；`fpk/app/ui/index.cgi:12-18` 反代到 `http://127.0.0.1:${port}` | 形态交代不全 → 已补 |
| C-M1 | 同上 §1.1:33 | "后端不托管前端静态资源" | `backend/main.py:94-100` 在 `NASDECK_STATIC_DIR` 存在时 `mount_spa` 托管；契约 §5/§6 亦写"托管已实现"；`backend/app/core/statics.py:15-26` 有 SPA 回退 | 契约内部矛盾 → 已改为"FPK 形态由后端托管" |
| C-H5 | 同上 §1.2:51 | — | `backend/app/core/exceptions.py` `_envelope` 只返回 `{code,message,data}`；`timestamp` 仅成功信封由 `main.py` 注入 | 复核：**文档正确**，非矛盾（原"内部矛盾"判断不成立） |

### B. 旧蓝本 / 历史记录未标注（已加指针）

| ID | 文档位置 | 文档断言 | 实现证据 | 判定与处置 |
|---|---|---|---|---|
| C-H2 | `docs/前端架构迁移说明.md:20` | `createWebHashHistory` | `frontend/src/router/index.js:4,9` `createWebHistory`；`backend/app/core/statics.py:15-26` SPA 回退支撑 history 深链 | 实现为准（history 自洽）→ 已改迁移说明口径 + `wiki/04` 补"路由形态" |
| C-H3 | `docs/NasDash前端Vue3架构重构方案.md:27` | "保留 vite-plugin-singlefile" | `frontend/vite.config.js:27-55` 无 singlefile；迁移说明:71-77 记录"去 singlefile" | 蓝本过时（方案.md:7 自己已划掉）→ 已加历史说明 |
| C-M2 | 方案:56,167；迁移说明:22 | axios + TypeScript | `frontend/src/modules/nas/api/client.js:39` 原生 fetch；src 全 JS 无 tsconfig；迁移说明:54 明确"不引入 axios" | 蓝本过时，现实现与最新决策一致 → 已加指针 |
| C-M3 | 迁移说明:19-25；重构说明:43 | `src/api/*.ts`、`views/<Name>/index.vue`、12 模块 | 实际 `src/modules/nas/{views,components,api,composables,stores,mock,routes}`（13 视图，`backend/app/api/v1` 7 域） | 旧架构已再重写 → 已加"历史记录"指针，现状以 `wiki/04` 为准 |
| C-M4 | `frontend/src/modules/nas/routes.js:3` 注释 | "界面阶段全部使用本地 mock" | `data.js` 仅在后端不可达（`resp===null`）才回退 mock（`data.js:273,400,447,632,757,784,812,857`），空列表当真值（`:401,650,772`）；`wiki/04:39-41` 已定义该语义 | 口径未对齐（注释 vs 铁律）→ 语义已在 wiki/04 写清，注释属实现内部说明，不改代码 |
| C-L2 | 无 | 文档未区分两种 layout | `frontend/src/router/static-routes.js:8` 用 `@/layouts/index.vue`；`frontend/src/modules/nas/routes.js:4` 用 `@/layouts/UnraidLayout.vue` | 实现无文档 → `wiki/04:17` 已列两种 layout，非缺口 |

### C. wiki 摘要偏差（已改）

| ID | 文档位置 | 文档断言 | 实现证据 | 处置 |
|---|---|---|---|---|
| D5 | `docs/wiki/06-接口与数据模型.md:26` | `curve/preview` | `backend/app/api/v1/control.py:99` `@router.get("/curves/preview")` | 已改为 `curves/preview` |
| D6 | 同上 :26 | 未列 hwmon 通道 | `control.py:26` `@router.get("/hwmon/channels")` | 已补 |
| D7 | 同上 :9-17 | 错误码表无 1000 | `backend/app/core/exceptions.py:13` `code = 1000`（业务基类，契约 §1.3 有） | 已补 |
| D8 | `docs/wiki/05-打包与部署.md:37` | `frontend mock.js about` | 实际 `frontend/src/modules/nas/mock.js` | 已改 |

### D. 已核对一致（代表性）

| 项 | 文档 | 实现 |
|---|---|---|
| 统一前缀 | 契约 §3:31 | `backend/main.py:90` `prefix="/api/v1"` |
| 路由聚合 7 域 | 契约 §3.0-3.7、wiki/06:21-30 | `backend/app/api/v1/__init__.py:5-14` include 7 路由 |
| 信封 `{code,message,data,timestamp}` | 契约 §1.2 | `backend/main.py:28-46` `envelope_middleware` |
| `/health` 无前缀无鉴权 | 契约 §3.0:315 | `backend/main.py:89` |
| DB 默认路径 | wiki/03:6 | `backend/app/core/config.py:43` |
| wizard_port 默认 9800 | wiki/05:55 | `fpk/wizard/install`、`fpk/cmd/main:23-27` |
| 13 视图 | wiki/01、契约 §2 | `frontend/src/modules/nas/routes.js` 13 子路由 |
| CGI 反代路径剥离 | 契约 §1.1:28、§7.1:490 | `frontend/src/modules/nas/api/client.js:20-25`；`fpk/app/ui/index.cgi:21-40` |
| 空列表为真值 | wiki/04:39-41 | `frontend/src/modules/nas/api/data.js:401,650,772` |

## 硬验证结果

| 项 | 命令 | 结果 |
|---|---|---|
| 后端测试 | `uv run pytest -q`（`uv sync --extra dev` 后，Python 3.13.16） | 全绿，exit 0 |
| 前端构建 | `corepack pnpm install --frozen-lockfile && corepack pnpm build` | 成功，产出 `dist/assets/js/*` 分包，exit 0 |

> 观察（非缺陷）：Windows 下 `vite-plugin-compression` 会把 `.gz` 写到错误的嵌套路径（`dist/D:/Project/nasdeck/frontend/assets/...`），未压缩产物落在 `dist/assets/` 正常。属打包侧小坑，未在本轮处理。

## 开放风险（非文档偏差，已单独建 issue）

来自 `REVIEW-2026-10-19.md`，均"已记录、未闭环"：

- **P0-1**：admin 判定依赖客户端可达的 `X-Trim-Isadmin` 头；`fpk/app/ui/index.cgi:58` 无条件转发。
- **P0-6**：`fpk/config/privilege:3` `run-as=root` 运行 Web 服务。
- **P1-16**：`fpk/cmd/main:41` 无 `TRIM_PKGVAR` 空值护栏。

## 本次改动的文档

- `docs/前后端数据接口约定.md`：版本头 v1.0→v1.1、§1.1 部署形态表、§1.2 信封说明、§1.4 豁免、§4 WS 鉴权、§7 现状路径、§7.1 开发端口、§7.4 类型层现状。
- `docs/wiki/06-接口与数据模型.md`：错误码补 1000；control 端点补 hwmon/channels、改 curves/preview。
- `docs/wiki/05-打包与部署.md`：mock 路径。
- `docs/wiki/04-前端开发指南.md`：补"路由形态（history + SPA 回退）"与"开发端口 5173 → 8766 代理"。
- `docs/前端架构迁移说明.md`、`docs/NasDash前端Vue3架构重构方案.md`、`docs/前端重构说明.md`：顶部加"历史记录/蓝本，现状以 wiki/04 为准"指针，并修正 hash/12 页等过时表述。

## 未覆盖 / 建议后续

- 契约 §4.1 WS 帧类型清单未与 `backend/app/api/ws/realtime.py` 逐帧比对（鉴权分支已核对：`realtime.py:49-65`）。
- `frontend/src/modules/nas/api/data.js` / `ws.js` 的逐函数形状未全量比对（仅抽样核对回退语义）。
- `REVIEW-2026-10-19.md` 的 P0/P1/P2 其余项未逐条复核实现状态。
- 正式部署前建议用 Alembic 替换 `init_db` 整库重建（wiki/06 已记）。
- 观察（非文档偏差，建议随 REVIEW P2 一并处理）：未处理异常把内部异常文本回显进 `message`（`backend/app/core/exceptions.py:60`，`f"internal error: {exc}"`），可能泄露路径/堆栈信息。

## 已建票（按类型）

| 类型 | Issue | 标题 |
|---|---|---|
| BUG | [#6](https://github.com/LarryMKott/nasdeck/issues/6) | P0-1（安全）：admin 判定信任客户端可达的 X-Trim-Isadmin 头 |
| BUG | [#7](https://github.com/LarryMKott/nasdeck/issues/7) | P0-6（安全）：FPK 以 run-as=root 运行 Web 服务 |
| BUG | [#8](https://github.com/LarryMKott/nasdeck/issues/8) | P1-16：fpk/cmd/main 未对 TRIM_PKGVAR 空值做护栏 |
| BUG | [#11](https://github.com/LarryMKott/nasdeck/issues/11) | Windows 下前端构建的 .gz 产物落到错误的嵌套路径 |
| BUG | [#12](https://github.com/LarryMKott/nasdeck/issues/12) | 5000 兜底响应把内部异常文本回显给客户端 |
| 需求 | [#14](https://github.com/LarryMKott/nasdeck/issues/14) | 正式部署前用 Alembic 迁移替换 init_db 整库重建 |
| 需求 | [#17](https://github.com/LarryMKott/nasdeck/issues/17) | 收口前端类型层决策（src/types/api/*.types.ts 落地或删除） |
| 需求 | [#19](https://github.com/LarryMKott/nasdeck/issues/19) | 补查审计未覆盖项（WS 帧类型、data.js/ws.js 逐函数、REVIEW 其余项） |
| 需求 | [#20](https://github.com/LarryMKott/nasdeck/issues/20) | 清理旧蓝本正文残留的过时表述（文档 + 代码注释） |
