<template>
  <div class="mp-analysis-tasks">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>小程序研报任务</span>
          <div class="header-actions">
            <el-input
              v-model="keyword"
              placeholder="任务ID/股票/用户"
              clearable
              style="width: 220px"
              @keyup.enter="applyFilters"
            />
            <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 120px">
              <el-option label="进行中" value="processing" />
              <el-option label="已完成" value="completed" />
              <el-option label="失败" value="failed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
            <el-button type="primary" @click="applyFilters">查询</el-button>
            <el-button @click="refreshList" :loading="loading">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-tabs v-model="activeTab" @tab-click="onTabChange">
        <el-tab-pane label="进行中" name="processing" />
        <el-tab-pane label="已完成" name="completed" />
        <el-tab-pane label="失败" name="failed" />
        <el-tab-pane label="全部" name="all" />
      </el-tabs>

      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="task_id" label="任务ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user_nickname" label="用户" width="120" />
        <el-table-column prop="user_openid" label="OpenID" min-width="140" show-overflow-tooltip />
        <el-table-column prop="stock_code" label="股票代码" width="100" />
        <el-table-column prop="stock_name" label="股票名称" width="120" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
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
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'completed'"
              type="primary"
              link
              size="small"
              @click="openReport(row)"
            >报告</el-button>
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
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="任务详情" width="640px">
      <el-descriptions v-if="currentTask" :column="1" border>
        <el-descriptions-item label="任务ID">{{ currentTask.task_id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ currentTask.user_nickname }} ({{ currentTask.user_id }})</el-descriptions-item>
        <el-descriptions-item label="OpenID">{{ currentTask.user_openid || '-' }}</el-descriptions-item>
        <el-descriptions-item label="股票">{{ currentTask.stock_name }} ({{ currentTask.stock_code }})</el-descriptions-item>
        <el-descriptions-item label="状态">{{ getStatusText(currentTask.status) }}</el-descriptions-item>
        <el-descriptions-item label="进度">{{ currentTask.progress }}%</el-descriptions-item>
        <el-descriptions-item label="消息">{{ currentTask.message || '-' }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(currentTask.created_at) }}</el-descriptions-item>
        <el-descriptions-item v-if="currentTask.summary" label="摘要">{{ currentTask.summary }}</el-descriptions-item>
        <el-descriptions-item v-if="currentTask.error_message" label="错误">{{ currentTask.error_message }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button v-if="currentTask?.status === 'completed'" type="primary" @click="openReport(currentTask)">
          查看报告
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { opsApi, type MpAnalysisTask } from '@/api/ops'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()
const loading = ref(false)
const tasks = ref<MpAnalysisTask[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref('')
const activeTab = ref<'processing' | 'completed' | 'failed' | 'all'>('processing')
const detailVisible = ref(false)
const currentTask = ref<MpAnalysisTask | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null

const tabStatus = () => {
  if (statusFilter.value) return statusFilter.value
  if (activeTab.value === 'all') return undefined
  return activeTab.value
}

const loadList = async () => {
  loading.value = true
  try {
    const res = await opsApi.listAnalysisTasks({
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
      status: tabStatus(),
      keyword: keyword.value || undefined,
    })
    tasks.value = res.data.tasks
    total.value = res.data.total
  } catch {
    ElMessage.error('加载任务列表失败')
  } finally {
    loading.value = false
  }
}

const applyFilters = () => {
  currentPage.value = 1
  loadList()
}

const refreshList = () => loadList()
const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadList()
}
const handleCurrentChange = (page: number) => {
  currentPage.value = page
  loadList()
}

const onTabChange = () => {
  nextTick(() => {
    currentPage.value = 1
    loadList()
    setupPolling()
  })
}

const setupPolling = () => {
  if (pollTimer) clearInterval(pollTimer)
  if (activeTab.value === 'processing' && !statusFilter.value) {
    pollTimer = setInterval(loadList, 5000)
  }
}

const openDetail = async (row: MpAnalysisTask) => {
  try {
    const res = await opsApi.getAnalysisTask(row.task_id)
    currentTask.value = res.data
    detailVisible.value = true
  } catch {
    ElMessage.error('获取任务详情失败')
  }
}

const openReport = (row: MpAnalysisTask) => {
  const id = row.task_id
  if (!id) return ElMessage.warning('未找到报告ID')
  router.push({ name: 'ReportDetail', params: { id } })
}

const markFailed = async (row: MpAnalysisTask) => {
  try {
    await ElMessageBox.confirm(
      `确定将任务「${row.stock_name || row.stock_code}」标记为失败吗？`,
      '确认操作',
      { type: 'warning' }
    )
    await opsApi.markTaskFailed(row.task_id)
    ElMessage.success('已标记为失败')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '操作失败')
  }
}

const deleteTask = async (row: MpAnalysisTask) => {
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${row.stock_name || row.stock_code}」吗？此操作不可恢复！`,
      '确认删除',
      { type: 'error' }
    )
    await opsApi.deleteTask(row.task_id)
    ElMessage.success('任务已删除')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

const isRunning = (status: string) =>
  ['pending', 'processing', 'running'].includes(status)

const getStatusType = (status: string): 'success' | 'info' | 'warning' | 'danger' => {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info',
    processing: 'warning',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) =>
  ({
    pending: '排队中',
    processing: '生成中',
    running: '生成中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  } as Record<string, string>)[status] || status

const formatTime = (t: string) => (t ? formatDateTime(t) : '-')

onMounted(() => {
  loadList()
  setupPolling()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
