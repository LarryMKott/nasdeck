# Vue Admin — 企业级 Vue 3 中后台脚手架（纯 JavaScript）

基于 **Vue 3.4 + Vite 5 + Pinia + Vue Router 4 + Element Plus + SCSS + Axios** 的领域驱动（Domain-Driven）中后台脚手架，零 TypeScript。ESM 模块天然运行于严格模式（等同 `'use strict'`），语法基线 ES2022，构建目标 `es2022`。

## 快速开始

```bash
npm install       # 安装依赖（自动初始化 husky 并修正 hooksPath）
npm run dev       # 启动开发服务器（默认 Mock 数据，开箱可用）
npm run build     # 生产构建
npm run build:test# 测试环境构建
npm run preview   # 预览构建产物
```

演示账号：`admin / 123456`（管理员，全部权限）、`editor / 123456`（仅可查看用户列表，用于验证菜单权限与按钮权限）。

## 工程规范

| 能力       | 工具                    | 说明                                                       |
| ---------- | ----------------------- | ---------------------------------------------------------- |
| 代码检查   | ESLint 9（Flat Config） | `js:recommended` + `vue:flat/recommended` + 严格自定义规则 |
| 格式化     | Prettier 3              | 单引号、分号、行宽 100                                     |
| 样式检查   | Stylelint 16            | `standard-scss` + `recommended-vue` + 属性顺序             |
| Git 钩子   | Husky 9                 | pre-commit / commit-msg，仅对本工程内暂存文件生效          |
| 提交校验   | commitlint 19           | Conventional Commits（中文 subject 友好）                  |
| 暂存区检查 | lint-staged 15          | 按文件类型执行 eslint / stylelint / prettier               |

常用命令：`npm run lint` / `lint:fix`、`npm run lint:style`、`npm run format`。

## 目录结构（领域驱动）

```
vue-admin/
├─ vite.config.js            # Vite 配置（分包/Gzip/代理/SCSS 注入）
├─ eslint.config.js          # ESLint Flat Config
├─ .eslintrc-auto-import.json# 自动导入全局清单（构建时生成，纳入版本管理）
├─ .env / .env.development / .env.test / .env.production
└─ src/
   ├─ main.js / App.vue      # 应用装配入口
   ├─ api/                   # 全局共用 API（认证域）
   ├─ assets/                # 静态资源
   ├─ components/            # 全局通用组件（自动导入，无需 import）
   ├─ composables/           # 全局组合式函数
   ├─ config/                # 应用默认配置
   ├─ constants/             # 全局常量
   ├─ directives/            # 自定义指令（v-permission）
   ├─ layouts/               # 主布局（侧边栏/导航栏/面包屑/keep-alive）
   ├─ mock/                  # 本地 Mock（adapter 级拦截，VITE_USE_MOCK 开关）
   ├─ modules/               # ★ 业务模块（领域驱动，模块内聚）
   │  ├─ dashboard/
   │  │  ├─ api/             # 模块接口
   │  │  ├─ components/      # 模块组件
   │  │  ├─ stores/          # 模块状态
   │  │  ├─ views/           # 模块页面
   │  │  └─ routes.js        # 模块路由（内聚声明）
   │  └─ system/             # 同上结构
   ├─ router/                # 路由器/守卫/静态与动态路由聚合
   ├─ stores/                # 全局 store（app / user / permission）
   ├─ styles/                # 全局样式（variables 由 vite 注入）
   └─ utils/                 # 工具（cache/auth/validate/request）
```

**新增业务模块**：在 `src/modules/<domain>/` 下建 `api / components / stores / views / routes.js`，`routes.js` 中导出路由数组（引用 `Layout` 作为容器），再到 `src/router/dynamic-routes.js` 汇总一行即可，路由懒加载、权限过滤、菜单渲染自动生效。

## 核心能力

### Axios 封装（`src/utils/request/`）

- **请求拦截**：自动附加 `Authorization: Bearer <token>`；
- **响应拦截**：统一处理业务错误码与 HTTP 状态码并提示；标准结构返回 `{ code, data, message }`，Blob 返回完整 response；
- **取消重复请求**：`AbortController` 按「方法+地址+参数」自动取消同类 pending 请求；请求级 `noCancel: true` 可跳过去重；
- **无感刷新**：401（HTTP 或业务码）时用 refreshToken 静默换新并重放，并发 401 只刷新一次、其余排队重放；刷新失败清凭证回登录页。

```js
import { get, post, download } from '@/utils/request';
const res = await get('/system/user/page', { page: 1 }); // res: { code, data, message }
await post('/system/user', form, { noCancel: true }); // 关闭重复请求取消
```

### 路由体系（`src/router/`）

- 页面全部路由懒加载（动态 `import()`）；
- `beforeEach` 全局守卫：白名单放行 → 登录校验 → 拉取用户信息 → **动态路由注入**（按角色/权限过滤后 `router.addRoute`）→ 重放当前导航；404 兜底路由最后注册；
- 路由 `meta`：`title / icon / hidden / keepAlive / roles / permissions`；
- 刷新页面自动重建动态路由（`permission.isGenerated` 为内存态）。

### 状态管理（`src/stores/`）

- 按领域拆分：`app`（侧边栏/尺寸）、`user`（用户/角色/权限）、`permission`（动态路由/菜单/缓存名单），业务模块自带 `stores/`；
- `pinia-plugin-persistedstate` 按 store 配置持久化字段（`persist.paths`）。

### 自动导入

- API：`vue` / `vue-router` / `pinia` 全量 API 及 `ElMessage` 等消息类 API 直接使用，无需 import（`ref`、`computed`、`useRouter`、`defineStore`…）；
- 组件：`src/components/` 下的全局组件与 Element Plus 组件在模板中直接使用（模板统一 kebab-case），样式按需注入；
- `.eslintrc-auto-import.json` 在首次构建/dev 时生成并自动更新，ESLint 据此识别全局 API。

### 多环境与构建优化

| 变量                  | 说明                         |
| --------------------- | ---------------------------- |
| `VITE_APP_TITLE`      | 页面标题                     |
| `VITE_APP_BASE_API`   | 接口基础路径（dev 自动代理） |
| `VITE_USE_MOCK`       | 是否启用本地 Mock            |
| `VITE_PROXY_TARGET`   | dev 代理目标后端             |
| `VITE_BUILD_GZIP`     | 构建是否输出 `.gz`           |
| `VITE_STORAGE_PREFIX` | 本地存储 key 前缀            |

构建优化：第三方库手动分包（vue-vendor / element-vendor / vendor-misc）、Gzip 压缩（>10KB）、`sourcemap: false`、生产移除 `console.log/info/debug` 与 `debugger`（保留 `warn/error` 便于排障）。

## 权限模型

- **菜单/路由级**：路由 `meta.roles`（角色编码）或 `meta.permissions`（权限标识），未配置默认放行；递归过滤后注入；
- **按钮/元素级**：`v-permission="['system:user:add']"`，无权限时移除元素；逻辑中可用 `usePermission().hasPermission([...])`；
- 演示：`editor` 登录后无「角色管理」菜单，直接访问 `/system/role` 落入 404；用户管理页的新增/编辑/删除按钮全部隐藏。

## Git 钩子说明（重要）

本工程位于 nasdeck 仓库子目录，`npm install` 时已将 `core.hooksPath` 指向 `vue-admin/.husky`。钩子内置范围守卫：**只有暂存文件包含 `vue-admin/` 内文件时才执行 lint-staged 与 commitlint**，仓库其他目录（如 `prototype/`、`frontend/`）的提交不受影响。

如需临时跳过校验：`git commit --no-verify`；如需彻底停用：`git config --unset core.hooksPath`。

## FAQ

- **连接真实后端**：`.env.development` 中设 `VITE_USE_MOCK=false`，后端按「统一响应结构 `{code, data, message}` + `POST /auth/login | POST /auth/refresh | GET /auth/user/info`」实现即可；
- **部署刷新 404**：history 路由需服务端回退，Nginx 示例：`location / { try_files $uri $uri/ /index.html; }`；
- **SCSS 变量**：`styles/variables.scss` 由 vite 注入所有样式编译入口，`.vue` 内直接使用 `$color-primary` 等，**不要**在 `.vue` 中再 `@use` 它（会重复加载报错）。
