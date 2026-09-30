<script setup>
/** 404 页面 */
defineOptions({ name: 'NotFoundView' });

const router = useRouter();
</script>

<template>
  <div class="error-view">
    <el-result icon="warning" title="404" sub-title="抱歉，您访问的页面不存在">
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
