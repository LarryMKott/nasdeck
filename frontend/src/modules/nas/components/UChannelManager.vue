<script setup>
/** 通知渠道管理（共享组件）：列表/启停/测试/增删改弹窗。
 * AutomationView（告警规则与通知页签）与 SettingsView（头像设置页）共用——
 * 渠道逻辑单源，两处入口零复制。数据由父组件拉取，写操作后 emit refresh 回拉。 */
import { computed, reactive, ref } from 'vue';
import { createChannel, deleteChannel, testChannel, updateChannel } from '../api/endpoints/alert';
import UModal from './UModal.vue';
import UPop from './UPop.vue';
import UIcon from '@/modules/nas/components/UIcon.vue';

const props = defineProps({
  /** 渠道清单（脱敏形态，含 config_masked） */
  channels: { type: Array, default: () => [] },
  /** 写操作开关（权限铁律：非管理员仅渲染不渲染写控件） */
  canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(['refresh']);

/** 通知渠道类型与各类型配置字段（与后端 channels/*.required_fields 对齐；
 * secret 字段以 password 框呈现，编辑时回显掩码串，原样保存=保留旧凭据） */
const CHANNEL_TYPES = [
  {
    value: 'telegram',
    label: 'Telegram',
    fields: [
      { key: 'bot_token', label: 'Bot Token', secret: true, required: true },
      { key: 'chat_id', label: 'Chat ID', required: true },
    ],
  },
  {
    value: 'bark',
    label: 'Bark (iOS)',
    fields: [
      { key: 'device_key', label: 'Device Key', secret: true, required: true },
      { key: 'server', label: '自建服务器（可选）', placeholder: 'https://api.day.app' },
    ],
  },
  {
    value: 'email',
    label: '邮件 SMTP',
    fields: [
      { key: 'host', label: 'SMTP 服务器', required: true, placeholder: 'smtp.example.com' },
      { key: 'port', label: '端口', required: true, placeholder: '587' },
      { key: 'username', label: '账号', required: true },
      { key: 'password', label: '密码 / 授权码', secret: true, required: true },
      { key: 'to', label: '收件邮箱', required: true },
    ],
  },
  {
    value: 'webhook',
    label: 'Webhook',
    fields: [{ key: 'url', label: 'URL', required: true, placeholder: 'https://example.com/hook' }],
  },
];
const TYPE_LABELS = Object.fromEntries(CHANNEL_TYPES.map((t) => [t.value, t.label]));
const typeMeta = computed(() => CHANNEL_TYPES.find((t) => t.value === chanForm.value.type));

function configSummary(cfg) {
  return (
    Object.values(cfg ?? {})
      .filter((v) => v !== '' && v != null)
      .join(' · ') || '—'
  );
}

/** 渠道编辑弹窗：新建空表单 / 编辑回填脱敏配置（掩码串原样回传，后端合并旧凭据） */
const chanModalOpen = ref(false);
const chanSaving = ref(false);
const chanForm = ref({ id: null, name: '', type: 'bark', enabled: true, config: {} });

function openChannelCreate() {
  chanForm.value = { id: null, name: '', type: 'bark', enabled: true, config: {} };
  chanModalOpen.value = true;
}

function openChannelEdit(c) {
  chanForm.value = {
    id: c.id,
    name: c.name,
    type: c.type,
    enabled: c.enabled,
    config: { ...c.config_masked },
  };
  chanModalOpen.value = true;
}

/** 切换类型：各类型配置字段不同，清空避免残留其它类型的键 */
function onChanTypeChange() {
  chanForm.value.config = {};
}

async function saveChannel() {
  if (!props.canWrite || chanSaving.value) return;
  const f = chanForm.value;
  if (!f.name.trim()) return;
  chanSaving.value = true;
  try {
    const body = { name: f.name.trim(), type: f.type, config: { ...f.config }, enabled: f.enabled };
    if (f.id == null) await createChannel(body);
    else await updateChannel(f.id, body);
    chanModalOpen.value = false;
    emit('refresh');
  } catch {
    /* 校验失败（缺字段 / url 非法 → 1002）静默，弹窗留在原地可改 */
  } finally {
    chanSaving.value = false;
  }
}

/** 渠道启停：掩码配置原样回传（后端合并旧凭据） */
async function toggleChannel(c) {
  if (!props.canWrite) return;
  const next = !c.enabled;
  const prev = c.enabled;
  c.enabled = next;
  try {
    await updateChannel(c.id, {
      name: c.name,
      type: c.type,
      config: { ...c.config_masked },
      enabled: next,
    });
  } catch {
    c.enabled = prev;
  }
}

async function deleteChan(c) {
  try {
    await deleteChannel(c.id);
  } catch {
    /* 静默，刷新以实际为准 */
  }
  emit('refresh');
}

/** 渠道连通性测试：逐渠道行内按钮（发送真实测试通知） */
const chanTestState = reactive({});
async function testChan(c) {
  if (!props.canWrite || chanTestState[c.id] === 'sending') return;
  chanTestState[c.id] = 'sending';
  try {
    const result = await testChannel(c.id);
    chanTestState[c.id] = result?.success ? 'ok' : 'fail';
  } catch {
    chanTestState[c.id] = 'fail';
  }
}
</script>

<template>
  <div>
    <div class="small" style="margin-bottom: 8px; font-weight: 600">通知渠道</div>
    <table v-if="channels?.length" class="u" style="margin-bottom: 10px">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>配置</th>
          <th>启用</th>
          <th class="r">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in channels" :key="c.id">
          <td>{{ c.name }}</td>
          <td class="small">{{ TYPE_LABELS[c.type] ?? c.type }}</td>
          <td
            class="small muted num"
            style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap"
            :title="configSummary(c.config_masked)"
          >
            {{ configSummary(c.config_masked) }}
          </td>
          <td>
            <label class="switch" :class="{ on: c.enabled }" @click="toggleChannel(c)">
              <span class="tr" />
            </label>
          </td>
          <td class="r" style="white-space: nowrap">
            <button
              class="btn sm"
              :disabled="chanTestState[c.id] === 'sending'"
              :title="`发送测试通知到「${c.name}」`"
              @click="testChan(c)"
            >
              <u-icon name="send" />{{
                chanTestState[c.id] === 'sending'
                  ? '发送中'
                  : chanTestState[c.id] === 'ok'
                    ? '已送达'
                    : chanTestState[c.id] === 'fail'
                      ? '失败'
                      : '测试'
              }}
            </button>
            <button class="btn sm" @click="openChannelEdit(c)">编辑</button>
            <u-pop ok-text="删除" cancel-text="取消" danger @confirm="deleteChan(c)">
              <template #trigger>
                <button class="btn sm">删除</button>
              </template>
              删除渠道「{{ c.name }}」？引用它的规则将不再经它推送。
            </u-pop>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else class="small muted" style="margin-bottom: 10px">
      尚未配置通知渠道——先添加一个（Telegram / Bark / 邮件 / Webhook），才能在规则中勾选推送目标
    </div>
    <button v-if="canWrite" class="btn sm" @click="openChannelCreate">
      <u-icon name="plus" />添加渠道
    </button>

    <!-- 渠道编辑弹窗 -->
    <u-modal
      v-model="chanModalOpen"
      :title="chanForm.id == null ? '添加通知渠道' : `编辑渠道 · ${chanForm.name}`"
      icon="send"
    >
      <div class="frm">
        <label>名称</label>
        <input v-model="chanForm.name" type="text" maxlength="64" placeholder="如 手机 Bark" />
        <label>类型</label>
        <select v-model="chanForm.type" @change="onChanTypeChange">
          <option v-for="t in CHANNEL_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <template v-for="f in typeMeta?.fields ?? []" :key="f.key">
          <label>{{ f.label }}</label>
          <input
            v-model="chanForm.config[f.key]"
            :type="f.secret ? 'password' : 'text'"
            :placeholder="f.placeholder ?? ''"
            autocomplete="off"
            spellcheck="false"
          />
        </template>
        <label>启用</label>
        <label
          class="switch"
          :class="{ on: chanForm.enabled }"
          style="align-self: center"
          @click.prevent="chanForm.enabled = !chanForm.enabled"
        >
          <span class="tr" />
        </label>
      </div>
      <div class="small muted" style="margin-top: 10px">
        编辑时带 ****
        的掩码值原样保存即保留旧凭据；保存后点列表「测试」验证连通性。规则触发时按所选渠道逐个推送。
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px">
        <button class="btn" @click="chanModalOpen = false">取消</button>
        <button class="btn pri" :disabled="chanSaving" @click="saveChannel">
          <u-icon name="check" />{{ chanSaving ? '保存中…' : '保存渠道' }}
        </button>
      </div>
    </u-modal>
  </div>
</template>
