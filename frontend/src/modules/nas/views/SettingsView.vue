<script setup>
/** 设置（管理员）：头像入口的快捷管理页——告警阈值（规则）+ 消息推送渠道。
 * 与「控制与自动化」页共用 UChannelManager/URuleEditor 组件（逻辑单源零复制）；
 * 非管理员只读提示（权限铁律：设置类操作仅管理员）。 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { useViewData } from '../composables/useViewData';
import { useIdentityStore } from '../stores/identity';
import { fetchAlertSettings } from '../services/automation';
import UPageHeader from '../components/UPageHeader.vue';
import UChannelManager from '../components/UChannelManager.vue';
import URuleEditor from '../components/URuleEditor.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

defineOptions({ name: 'NasSettings' });

const identity = useIdentityStore();
identity.ensure();

// 头像入口页不在导航页签内：微应用 iframe 里没有浏览器后退，须给显式退出路径
const router = useRouter();
function goBack() {
  if (window.history.state?.back) router.back();
  else router.push('/nasdeck/dash');
}

const {
  data: d,
  live,
  refresh,
  lastUpdated,
} = useViewData(fetchAlertSettings, { channels: [], rules: [] });

const headerTag = computed(() => {
  if (!live.value) return { type: 'acc', text: '演示数据' };
  const firing = d.value.rules.filter((r) => r.enabled).length;
  return { type: 'ok', text: `${d.value.channels.length} 渠道 · ${firing} 规则启用` };
});
</script>

<template>
  <section>
    <u-page-header
      title="设置"
      :sub="t('告警阈值 · 推送渠道')"
      :tag="headerTag"
      :updated="lastUpdated"
    >
      <template #right>
        <button class="btn sm" @click="goBack">{{ t('返回') }}</button>
      </template>
    </u-page-header>

    <div class="wg" style="margin-bottom: 0">
      <div class="wg-b" style="padding-bottom: 15px">
        <template v-if="identity.canWrite">
          <u-channel-manager
            :channels="d.channels"
            :can-write="identity.canWrite"
            @refresh="refresh"
          />
          <div style="margin-top: 18px">
            <u-rule-editor
              :rules="d.rules"
              :channels="d.channels"
              :can-write="identity.canWrite"
              @refresh="refresh"
            />
          </div>
          <div class="small muted" style="margin-top: 18px">
            更多管理项（SMART 周期巡检、周报推送、配置备份等）在
            <router-link to="/nasdeck/automation" style="color: var(--acc)"
              >控制与自动化</router-link
            >
            页。
          </div>
        </template>
        <div v-else class="small muted" style="padding: 8px 0">
          <u-icon name="shield" style="margin-right: 6px" />告警阈值与推送渠道为管理员设置项 ·
          如需调整请联系管理员
        </div>
      </div>
    </div>
  </section>
</template>
