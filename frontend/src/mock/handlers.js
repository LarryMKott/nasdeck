'use strict';

/** Mock 数据与路由表：仅用于本地开发联调（VITE_USE_MOCK=true 时启用） */

/** 内置演示账号 → 角色/权限 */
const ACCOUNTS = {
  admin: {
    nickname: '超级管理员',
    roles: ['admin'],
    permissions: [
      'system:user:list',
      'system:user:add',
      'system:user:edit',
      'system:user:delete',
      'system:role:list',
    ],
  },
  editor: {
    nickname: '内容编辑',
    roles: ['editor'],
    permissions: ['system:user:list'],
  },
};

/** 构造模拟用户列表 */
function buildUsers() {
  const roleNames = ['admin', 'editor', 'viewer'];
  const nicknames = [
    '张伟',
    '王芳',
    '李娜',
    '刘强',
    '陈静',
    '杨洋',
    '赵敏',
    '黄磊',
    '周杰',
    '吴敏',
    '徐峥',
    '孙俪',
    '马超',
    '朱婷',
    '胡军',
    '郭涛',
    '林心如',
    '何炅',
    '高圆圆',
    '罗成',
  ];
  const depts = ['研发部', '产品部', '运营部', '财务部'];
  return nicknames.map((nickname, index) => ({
    id: index + 1,
    username:
      index === 0 ? 'admin' : index === 1 ? 'editor' : `user${String(index + 1).padStart(3, '0')}`,
    nickname,
    mobile: `138${String(10000000 + index * 137).slice(0, 8)}`,
    dept: depts[index % depts.length],
    roles: [roleNames[index % roleNames.length]],
    status: index % 7 === 5 ? 0 : 1,
    remark: '',
    createdAt: `2025-0${(index % 9) + 1}-1${index % 9} 10:3${index % 10}:00`,
  }));
}

/** 模拟数据集（模块内可变，供增删改演示） */
const users = buildUsers();

/** @type {Array<{method: string, path: string | RegExp, handler: Function}>} */
export const mockRoutes = [
  {
    method: 'post',
    path: '/auth/login',
    handler({ body }) {
      const { username, password } = body ?? {};
      const account = username ? ACCOUNTS[username] : null;
      if (!account || password !== '123456') {
        return { code: 1001, message: '用户名或密码错误', data: null };
      }
      return {
        code: 200,
        message: '登录成功',
        data: {
          accessToken: `mock-access-${username}-${Date.now()}`,
          refreshToken: `mock-refresh-${username}-${Date.now()}`,
        },
      };
    },
  },
  {
    method: 'get',
    path: '/auth/user/info',
    handler({ headers }) {
      // 依据访问令牌反查账号（仅演示：mock-access-admin-* → admin）
      const auth = headers?.authorization ?? headers?.Authorization ?? '';
      const username = String(auth).includes('-admin-')
        ? 'admin'
        : String(auth).includes('-editor-')
          ? 'editor'
          : 'admin';
      const account = ACCOUNTS[username];
      return {
        code: 200,
        message: 'ok',
        data: { userId: 1, username, avatar: '', ...account },
      };
    },
  },
  {
    method: 'post',
    path: '/auth/refresh',
    handler() {
      return {
        code: 200,
        message: 'ok',
        data: {
          accessToken: `mock-access-refreshed-${Date.now()}`,
          refreshToken: `mock-refresh-refreshed-${Date.now()}`,
        },
      };
    },
  },
  {
    method: 'post',
    path: '/auth/logout',
    handler() {
      return { code: 200, message: 'ok', data: null };
    },
  },
  {
    method: 'get',
    path: '/system/user/page',
    handler({ query }) {
      const page = Number(query.page ?? 1);
      const pageSize = Number(query.pageSize ?? 10);
      const keyword = String(query.keyword ?? '').trim();
      const status =
        query.status === '' || query.status === undefined ? null : Number(query.status);

      const filtered = users.filter(
        (user) =>
          (!keyword || user.username.includes(keyword) || user.nickname.includes(keyword)) &&
          (status === null || user.status === status)
      );
      return {
        code: 200,
        message: 'ok',
        data: {
          list: filtered.slice((page - 1) * pageSize, page * pageSize),
          total: filtered.length,
          page,
          pageSize,
        },
      };
    },
  },
  {
    method: 'post',
    path: '/system/user',
    handler({ body }) {
      const user = {
        id: Math.max(...users.map((item) => item.id), 0) + 1,
        status: 1,
        remark: '',
        roles: ['viewer'],
        createdAt: new Date().toLocaleString('zh-CN', { hour12: false }),
        ...body,
      };
      users.unshift(user);
      return { code: 200, message: '创建成功', data: user };
    },
  },
  {
    method: 'put',
    path: /\/system\/user\/(\d+)$/,
    handler({ body, match }) {
      const id = Number(match?.[1]);
      const index = users.findIndex((item) => item.id === id);
      if (index < 0) return { code: 404, message: '用户不存在', data: null };
      users[index] = { ...users[index], ...body };
      return { code: 200, message: '更新成功', data: users[index] };
    },
  },
  {
    method: 'delete',
    path: /\/system\/user\/(\d+)$/,
    handler({ match }) {
      const id = Number(match?.[1]);
      const index = users.findIndex((item) => item.id === id);
      if (index < 0) return { code: 404, message: '用户不存在', data: null };
      users.splice(index, 1);
      return { code: 200, message: '删除成功', data: null };
    },
  },
  {
    method: 'get',
    path: '/system/role/list',
    handler() {
      return {
        code: 200,
        message: 'ok',
        data: [
          {
            id: 1,
            name: '超级管理员',
            code: 'admin',
            remark: '拥有系统全部权限',
            status: 1,
            createdAt: '2025-01-01 00:00:00',
          },
          {
            id: 2,
            name: '内容编辑',
            code: 'editor',
            remark: '仅可查看用户列表',
            status: 1,
            createdAt: '2025-02-11 09:20:00',
          },
          {
            id: 3,
            name: '访客',
            code: 'viewer',
            remark: '只读访问',
            status: 0,
            createdAt: '2025-03-15 14:05:00',
          },
        ],
      };
    },
  },
  {
    method: 'get',
    path: '/dashboard/overview',
    handler() {
      return {
        code: 200,
        message: 'ok',
        data: {
          summary: [
            { label: '总用户数', value: 1286, icon: 'User', trend: 12.4 },
            { label: '今日活跃', value: 328, icon: 'View', trend: 8.2 },
            { label: '订单总数', value: 9621, icon: 'TrendCharts', trend: -2.5 },
            { label: '系统消息', value: 42, icon: 'Bell', trend: 3.7 },
          ],
          logs: [
            { id: 1, content: '管理员 admin 登录系统', time: '2026-09-29 09:30:12', type: '登录' },
            { id: 2, content: '新增用户 user021', time: '2026-09-29 10:02:45', type: '操作' },
            { id: 3, content: '角色 editor 权限变更', time: '2026-09-29 10:41:08', type: '操作' },
            {
              id: 4,
              content: '系统定时任务：数据备份完成',
              time: '2026-09-29 12:00:00',
              type: '系统',
            },
            {
              id: 5,
              content: '用户 user007 修改了登录密码',
              time: '2026-09-29 13:26:51',
              type: '操作',
            },
            {
              id: 6,
              content: '检测到异常登录尝试（IP 10.0.3.44）',
              time: '2026-09-29 14:15:33',
              type: '告警',
            },
          ],
        },
      };
    },
  },
];
