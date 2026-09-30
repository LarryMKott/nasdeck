<script setup>
import { User, Lock } from '@element-plus/icons-vue';
import { useUserStore } from '@/stores/modules/user';
import { defaultSettings } from '@/config/settings';
import logoUrl from '@/assets/images/logo.svg';

defineOptions({ name: 'LoginView' });

const router = useRouter();
const route = useRoute();
const userStore = useUserStore();

const formRef = ref(null);
const loading = ref(false);
const form = reactive({
  username: 'admin',
  password: '123456',
});

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 20, message: '密码长度为 6-20 位', trigger: 'blur' },
  ],
};

/** 提交登录：成功后跳转 redirect 指定页面（守卫负责注入动态路由） */
async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;

  loading.value = true;
  try {
    await userStore.login({ ...form });
    ElMessage.success('登录成功，欢迎回来！');
    const target = route.query.redirect ? decodeURIComponent(String(route.query.redirect)) : '/';
    router.replace(target);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-view">
    <el-card class="login-view__card" shadow="always">
      <div class="login-view__head">
        <img :src="logoUrl" alt="logo" class="login-view__logo" />
        <h1 class="login-view__title">{{ defaultSettings.title }}</h1>
        <p class="login-view__subtitle">企业级中后台管理系统</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        size="large"
        @keyup.enter="handleLogin"
      >
        <el-form-item label="账号" prop="username">
          <el-input
            v-model.trim="form.username"
            :prefix-icon="User"
            placeholder="请输入账号"
            clearable
          />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input
            v-model.trim="form.password"
            :prefix-icon="Lock"
            type="password"
            placeholder="请输入密码"
            show-password
            clearable
          />
        </el-form-item>
        <el-button
          class="login-view__submit"
          type="primary"
          size="large"
          :loading="loading"
          @click="handleLogin"
        >
          登 录
        </el-button>
      </el-form>

      <el-alert
        class="login-view__tip"
        type="info"
        :closable="false"
        title="演示账号：admin / 123456（管理员） · editor / 123456（仅可查看用户列表）"
      />
    </el-card>
  </div>
</template>

<style lang="scss" scoped>
.login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background:
    radial-gradient(1200px 600px at 20% 10%, rgb(64 158 255 / 18%), transparent 60%),
    linear-gradient(160deg, #1f2d3d 0%, #001529 100%);

  &__card {
    width: 400px;
    padding: 8px 12px 4px;
    border-radius: 10px;
  }

  &__head {
    margin-bottom: 20px;
    text-align: center;
  }

  &__logo {
    width: 48px;
    height: 48px;
    margin: 0 auto 12px;
    border-radius: 12px;
  }

  &__title {
    margin: 0;
    font-size: 20px;
    color: $color-text-primary;
  }

  &__subtitle {
    margin: 6px 0 0;
    font-size: 13px;
    color: $color-text-secondary;
  }

  &__submit {
    width: 100%;
    margin-top: 4px;
  }

  &__tip {
    margin-top: 16px;
  }
}
</style>
