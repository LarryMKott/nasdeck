<script setup>
/** 操作手册：prose 排版 + 目录抽屉（本地 mock） */
import { ref } from 'vue';
import { manual as d } from '../mock';
import UPageHeader from '../components/UPageHeader.vue';
import UDrawer from '../components/UDrawer.vue';

defineOptions({ name: 'NasManual' });

const tocOpen = ref(false);
</script>

<template>
  <section>
    <u-page-header title="操作手册" sub="快速上手 · 页面说明 · 常见问题">
      <template #right>
        <button class="btn" @click="tocOpen = true"><u-icon name="menu" />目录</button>
      </template>
    </u-page-header>

    <div class="wg" style="margin-bottom: 0">
      <div class="wg-b prose">
        <h2>快速上手</h2>
        <p>
          nasdeck 安装后自动开始采集硬件数据，无需额外配置。打开面板即见「总览」；顶部页签按「阵列 /
          监控 / 服务 / 系统」组织 13 个页面。
        </p>
        <div class="note">
          <u-icon name="info" />
          <span>
            数据管道保持后端 <code>/manual?embed=1</code> 不变，仅外壳与排版套用本稿令牌（prose
            类）；开发阶段以示意文案占位。
          </span>
        </div>
        <h2>页面说明</h2>
        <p>
          「系统 / 温度」提供秒级实时刷新与温度墙分档着色；「趋势」支持 24h / 7d / 30d
          回看、六维度切换与框选缩放，并可导出 Markdown / HTML / CSV 健康报告。
        </p>
        <p>
          「硬盘」提供健康分级、在线自检与盘定位灯；「存储卷」展示阵列设备与卷映射拓扑；「风扇」需先开启接管总开关，再按传感器绑定温控曲线。
        </p>
        <h2>常见问题</h2>
        <p>
          <b>风扇接管后声音变大？</b
          >接管瞬间会按当前温度重新计算占空比，可在曲线编辑器里把低温段压低，或将规则切换到「静音优先」曲线。
        </p>
        <p>
          <b>反代后部分图标 302？</b>静态资源由 FastAPI 直出，无旧路径 302
          问题；若使用第三方反代请关闭对 <code>/static</code> 的改写。
        </p>
      </div>
    </div>

    <!-- 目录抽屉 -->
    <u-drawer v-model="tocOpen" title="目录" icon="book">
      <div
        v-for="item in d.toc"
        :key="item.text"
        class="toc-item"
        :class="{ lv2: item.lv2 }"
        @click="tocOpen = false"
      >
        {{ item.text }}
      </div>
    </u-drawer>
  </section>
</template>
