<template>
  <div class="mp-chat-sessions">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>小程序问股会话</span>
          <div class="header-actions">
            <el-input
              v-model="keyword"
              placeholder="会话ID/标题/股票/用户"
              clearable
              style="width: 240px"
              @keyup.enter="applyFilters"
            />
            <el-select v-model="statusFilter" placeholder="状态" clearable style="width: 120px">
              <el-option label="正常" value="active" />
              <el-option label="已禁用" value="disabled" />
            </el-select>
            <el-button type="primary" @click="applyFilters">查询</el-button>
            <el-button @click="refreshList" :loading="loading">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="sessions" v-loading="loading" stripe>
        <el-table-column prop="session_id" label="会话ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user_nickname" label="用户" width="120" />
        <el-table-column prop="user_openid" label="OpenID" min-width="140" show-overflow-tooltip />
        <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
        <el-table-column prop="stock_code" label="股票" width="90" />
        <el-table-column prop="strategy_id" label="策略" width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">{{ getStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message_count" label="消息数" width="80" />
        <el-table-column prop="updated_at" label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'active'"
              type="warning"
              link
              size="small"
              @click="disableSession(row)"
            >禁用</el-button>
            <el-button
              v-if="row.status === 'disabled'"
              type="success"
              link
              size="small"
              @click="enableSession(row)"
            >启用</el-button>
            <el-button type="danger" link size="small" @click="deleteSession(row)">删除</el-button>
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

    <el-dialog v-model="detailVisible" title="问股会话详情" width="760px">
      <el-descriptions v-if="currentSession" :column="2" border class="mb-16">
        <el-descriptions-item label="会话ID" :span="2">{{ currentSession.session_id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ currentSession.user_nickname }} ({{ currentSession.user_id }})</el-descriptions-item>
        <el-descriptions-item label="OpenID">{{ currentSession.user_openid || '-' }}</el-descriptions-item>
        <el-descriptions-item label="标题">{{ currentSession.title }}</el-descriptions-item>
        <el-descriptions-item label="股票">{{ currentSession.stock_code || '-' }}</el-descriptions-item>
        <el-descriptions-item label="策略">{{ currentSession.strategy_id }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ getStatusText(currentSession.status) }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="currentSession?.messages?.length" class="messages-box">
        <div
          v-for="msg in currentSession.messages"
          :key="msg.id"
          class="message-item"
          :class="msg.role"
        >
          <div class="message-meta">
            <el-tag size="small" :type="msg.role === 'user' ? 'primary' : 'success'">
              {{ msg.role === 'user' ? '用户' : 'AI' }}
            </el-tag>
            <span class="time">{{ formatTime(msg.created_at) }}</span>
            <el-tag v-if="msg.status === 'failed'" size="small" type="danger">失败</el-tag>
          </div>
          <pre class="message-content">{{ msg.content }}</pre>
        </div>
      </div>
      <el-empty v-else description="暂无消息" />
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { opsApi, type MpChatSession } from '@/api/ops'
import { formatDateTime } from '@/utils/datetime'

const loading = ref(false)
const sessions = ref<MpChatSession[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref('')
const detailVisible = ref(false)
const currentSession = ref<MpChatSession | null>(null)

const loadList = async () => {
  loading.value = true
  try {
    const res = await opsApi.listChatSessions({
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
      status: statusFilter.value || undefined,
      keyword: keyword.value || undefined,
    })
    sessions.value = res.data.sessions
    total.value = res.data.total
  } catch {
    ElMessage.error('加载问股会话失败')
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

const openDetail = async (row: MpChatSession) => {
  try {
    const res = await opsApi.getChatSession(row.session_id)
    currentSession.value = res.data
    detailVisible.value = true
  } catch {
    ElMessage.error('获取会话详情失败')
  }
}

const disableSession = async (row: MpChatSession) => {
  try {
    await ElMessageBox.confirm(`确定禁用会话「${row.title}」吗？用户将无法继续问股。`, '确认禁用', {
      type: 'warning',
    })
    await opsApi.updateChatSessionStatus(row.session_id, 'disabled')
    ElMessage.success('已禁用')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '操作失败')
  }
}

const enableSession = async (row: MpChatSession) => {
  try {
    await opsApi.updateChatSessionStatus(row.session_id, 'active')
    ElMessage.success('已启用')
    await loadList()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

const deleteSession = async (row: MpChatSession) => {
  try {
    await ElMessageBox.confirm(`确定删除会话「${row.title}」吗？`, '确认删除', { type: 'error' })
    await opsApi.deleteChatSession(row.session_id)
    ElMessage.success('已删除')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '删除失败')
  }
}

const getStatusType = (status: string): 'success' | 'info' | 'warning' | 'danger' => {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    active: 'success',
    disabled: 'warning',
    deleted: 'info',
  }
  return map[status] || 'info'
}

const getStatusText = (status: string) =>
  ({ active: '正常', disabled: '已禁用', deleted: '已删除' })[status] || status

const formatTime = (value?: string) => (value ? formatDateTime(value) : '-')

onMounted(loadList)
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.mb-16 {
  margin-bottom: 16px;
}
.messages-box {
  max-height: 420px;
  overflow-y: auto;
}
.message-item {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 8px;
  background: #f8f9fb;
}
.message-item.user {
  background: #eef5ff;
}
.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.message-meta .time {
  color: #999;
  font-size: 12px;
}
.message-content {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
</style>
