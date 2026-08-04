<template>
  <div class="benefit-campaigns">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>客户权益 / 活动</span>
          <el-button type="primary" @click="openCreate">新建活动</el-button>
        </div>
      </template>

      <el-table :data="campaigns" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="code" label="代码" width="110" />
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="grant_scope" label="发放范围" width="110">
          <template #default="{ row }">{{ scopeLabel(row.grant_scope) }}</template>
        </el-table-column>
        <el-table-column prop="grant_mode" label="授予方式" width="110">
          <template #default="{ row }">
            <el-tag :type="row.grant_mode === 'default' ? 'success' : 'warning'" size="small">
              {{ modeLabel(row.grant_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cycle_type" label="周期" width="90">
          <template #default="{ row }">{{ cycleLabel(row.cycle_type) }}</template>
        </el-table-column>
        <el-table-column label="研报" width="70" prop="report_quota" />
        <el-table-column label="问股" width="70" prop="ask_quota" />
        <el-table-column label="推送" width="70" prop="push_quota" />
        <el-table-column label="叠加" width="70">
          <template #default="{ row }">{{ row.stackable ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column label="有效期" min-width="180">
          <template #default="{ row }">
            <span v-if="!row.start_at && !row.end_at">不限</span>
            <span v-else>{{ fmtTime(row.start_at) }} ~ {{ fmtTime(row.end_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑活动' : '新建活动'" width="640px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="代码">
          <el-input v-model="form.code" :disabled="!!editing" placeholder="如 summer_ask_2026" />
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="草稿" value="draft" />
            <el-option label="进行中" value="active" />
            <el-option label="暂停" value="paused" />
            <el-option label="结束" value="ended" />
          </el-select>
        </el-form-item>
        <el-form-item label="发放范围">
          <el-select v-model="form.grant_scope" style="width: 100%" @change="onScopeChange">
            <el-option label="指定客户（手动发放）" value="manual" />
            <el-option label="按会员等级" value="membership" />
            <el-option label="全体小程序用户" value="all" />
          </el-select>
        </el-form-item>
        <el-form-item label="授予方式">
          <el-select
            v-model="form.grant_mode"
            style="width: 100%"
            :disabled="form.grant_scope === 'manual'"
          >
            <el-option
              label="默认授予（系统自动发，不可再手动发）"
              value="default"
              :disabled="form.grant_scope === 'manual'"
            />
            <el-option label="增加授予（仅运营手动发放）" value="addon" />
          </el-select>
          <div class="hint">
            指定客户只能用增加授予；会员/全体可选默认或增加。默认由系统按范围自动发且不能再授予。
          </div>
        </el-form-item>
        <el-form-item v-if="form.grant_scope === 'membership'" label="会员等级">
          <el-select v-model="form.membership_level_id" style="width: 100%" clearable>
            <el-option v-for="lv in levels" :key="lv.id" :label="lv.name" :value="lv.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="周期类型">
          <el-select v-model="form.cycle_type" style="width: 100%">
            <el-option label="一次性" value="once" />
            <el-option label="每天刷新" value="daily" />
            <el-option label="每月刷新" value="monthly" />
          </el-select>
        </el-form-item>
        <el-form-item label="开始时间">
          <el-date-picker v-model="form.start_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="结束时间">
          <el-date-picker v-model="form.end_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="研报次数"><el-input-number v-model="form.report_quota" :min="0" /></el-form-item>
        <el-form-item label="问股次数"><el-input-number v-model="form.ask_quota" :min="0" /></el-form-item>
        <el-form-item label="推送次数"><el-input-number v-model="form.push_quota" :min="0" /></el-form-item>
        <el-form-item label="可叠加"><el-switch v-model="form.stackable" /></el-form-item>
        <el-form-item label="优先级"><el-input-number v-model="form.priority" :min="0" /><span class="hint">数字越小越先扣减</span></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { opsApi, type BenefitCampaign, type MembershipLevel } from '@/api/ops'
import { ElMessage } from 'element-plus'

const campaigns = ref<BenefitCampaign[]>([])
const levels = ref<MembershipLevel[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref<BenefitCampaign | null>(null)

const form = reactive({
  name: '',
  code: '',
  description: '',
  status: 'draft' as BenefitCampaign['status'],
  grant_scope: 'manual' as BenefitCampaign['grant_scope'],
  grant_mode: 'addon' as BenefitCampaign['grant_mode'],
  membership_level_id: '' as string | undefined,
  cycle_type: 'once' as BenefitCampaign['cycle_type'],
  start_at: '' as string | undefined,
  end_at: '' as string | undefined,
  report_quota: 0,
  ask_quota: 0,
  push_quota: 0,
  stackable: true,
  priority: 100,
})

const statusLabel = (s: string) => ({ draft: '草稿', active: '进行中', paused: '暂停', ended: '结束' }[s] || s)
const statusType = (s: string) => ({ draft: 'info', active: 'success', paused: 'warning', ended: 'danger' }[s] || 'info')
const scopeLabel = (s: string) => ({ manual: '指定客户', membership: '会员等级', all: '全体用户' }[s] || s)
const modeLabel = (s: string) => ({ default: '默认授予', addon: '增加授予' }[s] || s || '增加授予')
const cycleLabel = (s: string) => ({ once: '一次性', daily: '每天', monthly: '每月' }[s] || s)
const fmtTime = (v?: string) => (v ? String(v).replace('T', ' ').slice(0, 16) : '不限')

const onScopeChange = (scope: BenefitCampaign['grant_scope']) => {
  if (scope === 'manual') {
    form.grant_mode = 'addon'
  }
}

const resetForm = () => {
  form.name = ''
  form.code = ''
  form.description = ''
  form.status = 'draft'
  form.grant_scope = 'manual'
  form.grant_mode = 'addon'
  form.membership_level_id = undefined
  form.cycle_type = 'once'
  form.start_at = undefined
  form.end_at = undefined
  form.report_quota = 0
  form.ask_quota = 0
  form.push_quota = 0
  form.stackable = true
  form.priority = 100
}

const load = async () => {
  loading.value = true
  try {
    const [cRes, lRes] = await Promise.all([
      opsApi.listBenefitCampaigns(),
      opsApi.listMembershipLevels(),
    ])
    campaigns.value = (cRes as any)?.data?.campaigns || []
    levels.value = (lRes as any)?.data?.levels || []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  resetForm()
  dialogVisible.value = true
}

const openEdit = (row: BenefitCampaign) => {
  editing.value = row
  form.name = row.name
  form.code = row.code
  form.description = row.description || ''
  form.status = row.status
  form.grant_scope = row.grant_scope
  form.grant_mode = row.grant_mode || 'addon'
  form.membership_level_id = row.membership_level_id || undefined
  form.cycle_type = row.cycle_type
  form.start_at = row.start_at || undefined
  form.end_at = row.end_at || undefined
  form.report_quota = row.report_quota
  form.ask_quota = row.ask_quota
  form.push_quota = row.push_quota
  form.stackable = row.stackable
  form.priority = row.priority
  dialogVisible.value = true
}

const submit = async () => {
  if (!form.name || !form.code) {
    ElMessage.warning('请填写名称和代码')
    return
  }
  if (form.grant_scope === 'manual' && form.grant_mode === 'default') {
    ElMessage.warning('指定客户只能使用「增加授予」')
    return
  }
  const payload: any = {
    name: form.name,
    code: form.code,
    description: form.description,
    status: form.status,
    grant_scope: form.grant_scope,
    grant_mode: form.grant_mode,
    membership_level_id: form.grant_scope === 'membership' ? form.membership_level_id : null,
    cycle_type: form.cycle_type,
    start_at: form.start_at || null,
    end_at: form.end_at || null,
    report_quota: form.report_quota,
    ask_quota: form.ask_quota,
    push_quota: form.push_quota,
    stackable: form.stackable,
    priority: form.priority,
  }
  try {
    if (editing.value) {
      const { code, ...update } = payload
      await opsApi.updateBenefitCampaign(editing.value.id, update)
    } else {
      await opsApi.createBenefitCampaign(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

onMounted(load)
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.hint {
  margin-left: 0;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
  line-height: 1.4;
}
</style>
