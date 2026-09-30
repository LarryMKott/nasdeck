<script setup>
/** 403 无权限页面 */
defineOptions({ name: 'ForbiddenView' });

const router = useRouter();
</script>

<template>
  <div class="error-view">
    <el-result icon="error" title="403" sub-title="抱歉，您没有权限访问该页面">
      <template #extra>
        <el-button type="primary" @click="router.replace('/')">返回首页</el-button>
      </template>
    </el-result>
  </div>
</template>

<style lang="scss" scoped>
.error-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  background-color: $bg-page;
}
</style>
