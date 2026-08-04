<template>
  <div class="mp-user-detail" v-loading="pageLoading">
    <div class="page-header">
      <el-button link @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        返回用户列表
      </el-button>
      <h2>{{ user?.nickname || '用户详情' }}</h2>
    </div>

    <el-row :gutter="16" class="summary-row" v-if="detail">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">账户余额</div>
          <div class="stat-value">¥{{ (user?.balance ?? 0).toFixed(2) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">会员等级</div>
          <div class="stat-value sm">{{ detail.membership_level_name }}</div>
          <div class="stat-sub" v-if="detail.monthly_fee > 0">
            月费 ¥{{ detail.monthly_fee.toFixed(2) }}
            <el-tag size="small" :type="detail.membership_fee_paid ? 'success' : 'danger'" style="margin-left: 6px">
              {{ detail.membership_fee_paid ? '已扣' : '未扣' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">本月免费研报</div>
          <div class="stat-value sm">
            {{ detail.report_free_remaining }} / {{ detail.report_free_limit }}
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-label">本月免费问股</div>
          <div class="stat-value sm">
            {{ detail.ask_free_remaining }} / {{ detail.ask_free_limit }}
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="main-card">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="账户管理" name="account" />
        <el-tab-pane label="充值管理" name="recharge" />
        <el-tab-pane label="消费流水" name="billing" />
        <el-tab-pane label="研报管理" name="reports" />
      </el-tabs>

      <!-- 账户管理 -->
      <div v-show="activeTab === 'account'" class="tab-panel">
        <el-descriptions :column="2" border v-if="user">
          <el-descriptions-item label="用户ID">{{ user.id }}</el-descriptions-item>
          <el-descriptions-item label="昵称">{{ user.nickname || '-' }}</el-descriptions-item>
          <el-descriptions-item label="OpenID" :span="2">{{ user.openid || '-' }}</el-descriptions-item>
          <el-descriptions-item label="手机号">{{ user.phone || '-' }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag :type="user.role === 'risk_officer' ? 'warning' : 'info'" size="small">
              {{ user.role_name || '普通' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="user.is_active ? 'success' : 'danger'">
              {{ user.is_active ? '正常' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">{{ formatTime(user.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="最近登录">{{ formatTime(user.last_login) }}</el-descriptions-item>
          <el-descriptions-item label="分析次数">{{ user.total_analyses }}</el-descriptions-item>
          <el-descriptions-item label="当前余额">¥{{ user.balance?.toFixed(2) }}</el-descriptions-item>
        </el-descriptions>

        <el-divider>账户操作</el-divider>
        <el-form :inline="true" label-width="80px">
          <el-form-item label="用户角色">
            <el-select
              v-model="userRole"
              placeholder="选择角色"
              style="width: 160px"
              @change="updateRole"
            >
              <el-option v-for="r in roles" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
          </el-form-item>
          <el-form-item label="会员等级">
            <el-select
              v-model="membershipLevelId"
              placeholder="选择等级"
              style="width: 160px"
              @change="updateMembership"
            >
              <el-option v-for="l in levels" :key="l.id" :label="l.name" :value="l.id" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button :type="user?.is_active ? 'danger' : 'success'" @click="toggleActive">
              {{ user?.is_active ? '禁用账户' : '启用账户' }}
            </el-button>
          </el-form-item>
        </el-form>
        <div class="hint">角色与会员等级独立：默认「普通」，可授予「风控专员」。</div>

        <el-divider>手动调账</el-divider>
        <el-form :inline="true" @submit.prevent="submitAdjust">
          <el-form-item label="金额">
            <el-input-number v-model="adjustAmount" :precision="2" :step="10" />
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="adjustRemark" style="width: 200px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="submitAdjust" :disabled="adjustAmount === 0">确认调账</el-button>
          </el-form-item>
        </el-form>
        <div class="hint">正数增加余额，负数减少余额</div>

        <el-divider>客户权益</el-divider>
        <div class="benefit-summary" v-if="detail">
          <el-tag type="warning">活动研报剩余 {{ detail.report_benefit_remaining || 0 }}</el-tag>
          <el-tag type="warning" style="margin-left: 8px">活动问股剩余 {{ detail.ask_benefit_remaining || 0 }}</el-tag>
          <el-tag type="warning" style="margin-left: 8px">活动推送剩余 {{ detail.push_benefit_remaining || 0 }}</el-tag>
        </div>
        <el-table :data="benefitGrants" size="small" stripe style="margin-top: 12px" empty-text="暂无活动权益">
          <el-table-column prop="campaign_name" label="活动" min-width="120" />
          <el-table-column label="研报" width="90">
            <template #default="{ row }">{{ row.report_remaining }}/{{ row.report_limit }}</template>
          </el-table-column>
          <el-table-column label="问股" width="90">
            <template #default="{ row }">{{ row.ask_remaining }}/{{ row.ask_limit }}</template>
          </el-table-column>
          <el-table-column label="推送" width="90">
            <template #default="{ row }">{{ row.push_remaining }}/{{ row.push_limit }}</template>
          </el-table-column>
          <el-table-column prop="cycle_key" label="周期" width="100" />
          <el-table-column prop="status" label="状态" width="80" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'active'"
                size="small"
                type="danger"
                link
                @click="revokeBenefit(row.id)"
              >撤销</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-form :inline="true" style="margin-top: 12px" @submit.prevent="assignBenefit">
          <el-form-item label="增加授予">
            <el-select v-model="assignCampaignId" placeholder="选择可增加授予的活动" style="width: 260px" filterable>
              <el-option
                v-for="c in addonCampaigns"
                :key="c.id"
                :label="`${c.name} (${c.code})`"
                :value="c.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="备注">
            <el-input v-model="assignRemark" style="width: 160px" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :disabled="!assignCampaignId" @click="assignBenefit">发放权益</el-button>
          </el-form-item>
        </el-form>
        <div class="hint">默认授予由系统自动发放且不可再手动发；此处仅可选择「增加授予」类活动。</div>
      </div>

      <!-- 充值管理 -->
      <div v-show="activeTab === 'recharge'" class="tab-panel">
        <h4>充值订单</h4>
        <el-table :data="orders" v-loading="ordersLoading" stripe size="small">
          <el-table-column prop="order_no" label="订单号" min-width="180" show-overflow-tooltip />
          <el-table-column prop="amount" label="金额" width="100">
            <template #default="{ row }">¥{{ row.amount?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'paid' ? 'success' : 'info'">{{ orderStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="140" show-overflow-tooltip />
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="paid_at" label="支付时间" width="170">
            <template #default="{ row }">{{ formatTime(row.paid_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="ordersPage"
            :page-size="pageSize"
            :total="ordersTotal"
            layout="total, prev, pager, next"
            @current-change="loadOrders"
          />
        </div>

        <h4 style="margin-top: 24px">充值与调账流水</h4>
        <el-table :data="rechargeRecords" v-loading="rechargeLoading" stripe size="small">
          <el-table-column prop="created_at" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" label="类型" width="100">
            <template #default="{ row }">{{ billingTypeText(row.action_type) }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="100">
            <template #default="{ row }">
              <span :class="row.amount >= 0 ? 'amount-plus' : 'amount-minus'">
                {{ row.amount >= 0 ? '+' : '' }}{{ row.amount?.toFixed(2) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="balance_after" label="余额" width="100">
            <template #default="{ row }">{{ row.balance_after?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="order_no" label="订单号" min-width="160" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        </el-table>
      </div>

      <!-- 消费流水 -->
      <div v-show="activeTab === 'billing'" class="tab-panel">
        <el-form :inline="true" class="filter-form">
          <el-form-item label="类型">
            <el-select v-model="billingTypeFilter" clearable placeholder="全部" style="width: 120px" @change="loadBilling">
              <el-option label="研报生成" value="generate" />
              <el-option label="充值" value="recharge" />
              <el-option label="调账" value="adjust" />
              <el-option label="退款" value="refund" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button @click="loadBilling">刷新</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="billingRecords" v-loading="billingLoading" stripe>
          <el-table-column prop="created_at" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="action_type" label="类型" width="100">
            <template #default="{ row }">{{ billingTypeText(row.action_type) }}</template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" width="100">
            <template #default="{ row }">
              <span :class="row.amount >= 0 ? 'amount-plus' : 'amount-minus'">
                {{ row.amount >= 0 ? '+' : '' }}{{ row.amount?.toFixed(2) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="balance_before" label="变动前" width="90">
            <template #default="{ row }">{{ row.balance_before?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="balance_after" label="变动后" width="90">
            <template #default="{ row }">{{ row.balance_after?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="is_free" label="免费" width="70">
            <template #default="{ row }">{{ row.is_free ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column prop="stock_code" label="股票" width="90" />
          <el-table-column prop="task_id" label="任务ID" min-width="140" show-overflow-tooltip />
          <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        </el-table>
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="billingPage"
            :page-size="pageSize"
            :total="billingTotal"
            layout="total, prev, pager, next"
            @current-change="loadBilling"
          />
        </div>
      </div>

      <!-- 研报管理 -->
      <div v-show="activeTab === 'reports'" class="tab-panel">
        <el-form :inline="true" class="filter-form">
          <el-form-item label="状态">
            <el-select v-model="taskStatusFilter" clearable placeholder="全部" style="width: 120px" @change="loadTasks">
              <el-option label="进行中" value="processing" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
            </el-select>
          </el-form-item>
          <el-form-item>
            <el-button @click="loadTasks">刷新</el-button>
          </el-form-item>
        </el-form>
        <el-table :data="tasks" v-loading="tasksLoading" stripe>
          <el-table-column prop="task_id" label="任务ID" min-width="180" show-overflow-tooltip />
          <el-table-column prop="stock_code" label="股票代码" width="100" />
          <el-table-column prop="stock_name" label="股票名称" width="120" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="taskStatusType(row.status)">{{ taskStatusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="120">
            <template #default="{ row }">
              <el-progress
                :percentage="row.progress || 0"
                :status="row.status === 'failed' ? 'exception' : row.status === 'completed' ? 'success' : undefined"
              />
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button v-if="row.status === 'completed'" type="primary" link size="small" @click="openReport(row)">
                查看报告
              </el-button>
              <el-button
                v-if="isRunning(row.status)"
                type="warning"
                link
                size="small"
                @click="markFailed(row)"
              >标记失败</el-button>
              <el-button type="danger" link size="small" @click="deleteTask(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrapper">
          <el-pagination
            v-model:current-page="tasksPage"
            :page-size="pageSize"
            :total="tasksTotal"
            layout="total, prev, pager, next"
            @current-change="loadTasks"
          />
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft } from '@element-plus/icons-vue'
import {
  opsApi,
  type MpUser,
  type MpUserDetail,
  type MembershipLevel,
  type BillingRecord,
  type PaymentOrder,
  type MpAnalysisTask,
  type BenefitCampaign,
  type UserBenefitGrant,
  type UserRole,
} from '@/api/ops'
import { formatDateTime } from '@/utils/datetime'

const route = useRoute()
const router = useRouter()
const userId = computed(() => String(route.params.id || ''))

const pageLoading = ref(false)
const detail = ref<MpUserDetail | null>(null)
const user = computed(() => detail.value?.user ?? null)
const levels = ref<MembershipLevel[]>([])
const membershipLevelId = ref('')
const roles = ref<UserRole[]>([])
const userRole = ref('normal')
const activeTab = ref('account')

const adjustAmount = ref(0)
const adjustRemark = ref('管理员调账')

const benefitGrants = ref<UserBenefitGrant[]>([])
const benefitCampaigns = ref<BenefitCampaign[]>([])
/** 仅「增加授予」可手动发放；默认授予不可选 */
const addonCampaigns = computed(() =>
  benefitCampaigns.value.filter((c) => (c.grant_mode || 'addon') === 'addon')
)
const assignCampaignId = ref('')
const assignRemark = ref('')

const pageSize = 20
const orders = ref<PaymentOrder[]>([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersLoading = ref(false)

const rechargeRecords = ref<BillingRecord[]>([])
const rechargeLoading = ref(false)

const billingRecords = ref<BillingRecord[]>([])
const billingTotal = ref(0)
const billingPage = ref(1)
const billingTypeFilter = ref('')
const billingLoading = ref(false)

const tasks = ref<MpAnalysisTask[]>([])
const tasksTotal = ref(0)
const tasksPage = ref(1)
const taskStatusFilter = ref('')
const tasksLoading = ref(false)

const loadDetail = async () => {
  pageLoading.value = true
  try {
    const res = await opsApi.getMpUserDetail(userId.value)
    detail.value = res.data
    membershipLevelId.value = res.data.user.membership_level_id || ''
    userRole.value = res.data.user.role || 'normal'
    benefitGrants.value = res.data.benefit_grants || []
  } catch {
    ElMessage.error('加载用户信息失败')
    goBack()
  } finally {
    pageLoading.value = false
  }
}

const loadLevels = async () => {
  const res = await opsApi.listMembershipLevels()
  levels.value = res.data.levels
}

const loadRoles = async () => {
  const res = await opsApi.listUserRoles({ active_only: true })
  roles.value = res.data.roles
}

const loadBenefitCampaigns = async () => {
  try {
    const res = await opsApi.listBenefitCampaigns({ status: 'active' })
    benefitCampaigns.value = res.data.campaigns || []
  } catch {
    benefitCampaigns.value = []
  }
}

const assignBenefit = async () => {
  if (!assignCampaignId.value) return
  try {
    await opsApi.assignUserBenefit(userId.value, {
      campaign_id: assignCampaignId.value,
      remark: assignRemark.value || undefined,
    })
    ElMessage.success('已发放权益')
    assignCampaignId.value = ''
    assignRemark.value = ''
    await loadDetail()
  } catch (e: any) {
    ElMessage.error(e?.message || '发放失败')
  }
}

const revokeBenefit = async (grantId: string) => {
  await ElMessageBox.confirm('确定撤销该权益？', '确认')
  try {
    await opsApi.revokeUserBenefit(grantId)
    ElMessage.success('已撤销')
    await loadDetail()
  } catch {
    ElMessage.error('撤销失败')
  }
}

const loadOrders = async () => {
  ordersLoading.value = true
  try {
    const res = await opsApi.listPaymentOrders({
      user_id: userId.value,
      skip: (ordersPage.value - 1) * pageSize,
      limit: pageSize,
    })
    orders.value = res.data.orders
    ordersTotal.value = res.data.total ?? res.data.orders.length
  } catch {
    ElMessage.error('加载充值订单失败')
  } finally {
    ordersLoading.value = false
  }
}

const loadRechargeRecords = async () => {
  rechargeLoading.value = true
  try {
    const [rechargeRes, adjustRes] = await Promise.all([
      opsApi.listBillingRecords({ user_id: userId.value, action_type: 'recharge', limit: 50 }),
      opsApi.listBillingRecords({ user_id: userId.value, action_type: 'adjust', limit: 50 }),
    ])
    const merged = [...rechargeRes.data.records, ...adjustRes.data.records]
    merged.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))
    rechargeRecords.value = merged
  } catch {
    ElMessage.error('加载充值流水失败')
  } finally {
    rechargeLoading.value = false
  }
}

const loadBilling = async () => {
  billingLoading.value = true
  try {
    const res = await opsApi.listBillingRecords({
      user_id: userId.value,
      action_type: billingTypeFilter.value || undefined,
      skip: (billingPage.value - 1) * pageSize,
      limit: pageSize,
    })
    billingRecords.value = res.data.records
    billingTotal.value = res.data.total ?? res.data.records.length
  } catch {
    ElMessage.error('加载消费流水失败')
  } finally {
    billingLoading.value = false
  }
}

const loadTasks = async () => {
  tasksLoading.value = true
  try {
    const res = await opsApi.listAnalysisTasks({
      user_id: userId.value,
      status: taskStatusFilter.value || undefined,
      skip: (tasksPage.value - 1) * pageSize,
      limit: pageSize,
    })
    tasks.value = res.data.tasks
    tasksTotal.value = res.data.total
  } catch {
    ElMessage.error('加载研报任务失败')
  } finally {
    tasksLoading.value = false
  }
}

const onTabChange = (tab: string | number) => {
  if (tab === 'recharge') {
    loadOrders()
    loadRechargeRecords()
  } else if (tab === 'billing') {
    loadBilling()
  } else if (tab === 'reports') {
    loadTasks()
  }
}

const updateMembership = async (levelId: string) => {
  try {
    await opsApi.updateUserMembership(userId.value, levelId)
    ElMessage.success('会员等级已更新')
    await loadDetail()
  } catch {
    ElMessage.error('更新失败')
    await loadDetail()
  }
}

const updateRole = async (role: string) => {
  try {
    await opsApi.updateUserRole(userId.value, role)
    ElMessage.success('角色已更新')
    await loadDetail()
  } catch {
    ElMessage.error('更新角色失败')
    await loadDetail()
  }
}

const toggleActive = async () => {
  if (!user.value) return
  try {
    await opsApi.setUserActive(userId.value, !user.value.is_active)
    ElMessage.success('状态已更新')
    await loadDetail()
  } catch {
    ElMessage.error('操作失败')
  }
}

const submitAdjust = async () => {
  if (adjustAmount.value === 0) return
  try {
    await opsApi.adjustBalance(userId.value, adjustAmount.value, adjustRemark.value)
    ElMessage.success('调账成功')
    adjustAmount.value = 0
    await loadDetail()
    if (activeTab.value === 'recharge') {
      loadRechargeRecords()
    }
  } catch {
    ElMessage.error('调账失败')
  }
}

const openReport = (row: MpAnalysisTask) => {
  router.push({ name: 'ReportDetail', params: { id: row.task_id } })
}

const markFailed = async (row: MpAnalysisTask) => {
  try {
    await ElMessageBox.confirm(`确定将任务「${row.stock_name || row.stock_code}」标记为失败？`, '确认', { type: 'warning' })
    await opsApi.markTaskFailed(row.task_id)
    ElMessage.success('已标记为失败')
    loadTasks()
    loadDetail()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

const deleteTask = async (row: MpAnalysisTask) => {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.stock_name || row.stock_code}」？`, '确认删除', { type: 'error' })
    await opsApi.deleteTask(row.task_id)
    ElMessage.success('已删除')
    loadTasks()
    loadDetail()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

const goBack = () => router.push({ name: 'MpUsers' })

const formatTime = (t?: string) => (t ? formatDateTime(t) : '-')
const billingTypeText = (t: string) =>
  ({
    generate: '研报生成',
    ask: '问股',
    membership_fee: '会员月费',
    recharge: '充值',
    adjust: '调账',
    refund: '退款',
    download: '下载',
  } as Record<string, string>)[t] || t
const orderStatusText = (s: string) =>
  ({ paid: '已支付', pending: '待支付', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] || s
const isRunning = (s: string) => ['pending', 'processing', 'running'].includes(s)
const taskStatusType = (s: string): 'success' | 'info' | 'warning' | 'danger' => {
  const m: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info', processing: 'warning', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info',
  }
  return m[s] || 'info'
}
const taskStatusText = (s: string) =>
  ({ pending: '排队中', processing: '生成中', running: '生成中', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[s] || s

onMounted(async () => {
  await Promise.all([loadLevels(), loadRoles(), loadBenefitCampaigns()])
  await loadDetail()
})
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.benefit-summary {
  margin-bottom: 4px;
}
.page-header h2 {
  margin: 0;
  font-size: 20px;
}
.summary-row {
  margin-bottom: 16px;
}
.stat-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  margin-top: 8px;
}
.stat-value.sm {
  font-size: 18px;
}
.stat-sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
.main-card {
  margin-top: 0;
}
.tab-panel {
  padding-top: 8px;
}
.tab-panel h4 {
  margin: 0 0 12px;
  font-size: 15px;
}
.filter-form {
  margin-bottom: 12px;
}
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}
.amount-plus {
  color: var(--el-color-success);
}
.amount-minus {
  color: var(--el-color-danger);
}
</style>
