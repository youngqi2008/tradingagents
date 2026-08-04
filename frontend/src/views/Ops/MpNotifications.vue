<template>
  <div class="mp-notifications">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>小程序站内通知</span>
          <el-button type="primary" @click="openCreate">发送通知</el-button>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="target_type" label="发送范围" width="110">
          <template #default="{ row }">{{ targetText(row) }}</template>
        </el-table-column>
        <el-table-column prop="recipient_count" label="触达人数" width="90" />
        <el-table-column prop="read_count" label="已读" width="70" />
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : 'info'">
              {{ row.status === 'published' ? '已发布' : '已撤回' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="发送人" width="100" />
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">详情</el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="row.status !== 'published'"
              @click="revoke(row)"
            >
              撤回
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" title="发送站内通知" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="标题" required>
          <el-input v-model="form.title" maxlength="128" show-word-limit />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input v-model="form.content" type="textarea" :rows="6" />
        </el-form-item>
        <el-form-item label="发送范围" required>
          <el-select v-model="form.target_type" style="width: 100%">
            <el-option label="全部小程序用户" value="all" />
            <el-option label="指定会员等级" value="membership" />
            <el-option label="指定用户 ID" value="users" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.target_type === 'membership'" label="会员等级" required>
          <el-select v-model="form.target_membership_level_id" placeholder="选择等级" style="width: 100%">
            <el-option v-for="l in levels" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.target_type === 'users'" label="用户 ID" required>
          <el-input
            v-model="form.target_user_ids_text"
            type="textarea"
            :rows="3"
            placeholder="多个用户 ID 用英文逗号分隔，如 1,2,3"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">发送</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="通知详情" width="520px">
      <template v-if="detail">
        <p><strong>标题：</strong>{{ detail.title }}</p>
        <p><strong>范围：</strong>{{ targetText(detail) }}</p>
        <p><strong>触达/已读：</strong>{{ detail.recipient_count }} / {{ detail.read_count }}</p>
        <el-divider />
        <div class="detail-content">{{ detail.content }}</div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { opsApi, type MpNotification, type MembershipLevel } from '@/api/ops'
import { ElMessage, ElMessageBox } from 'element-plus'

const items = ref<MpNotification[]>([])
const levels = ref<MembershipLevel[]>([])
const loading = ref(false)
const submitting = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const dialogVisible = ref(false)
const detailVisible = ref(false)
const detail = ref<MpNotification | null>(null)

const form = reactive({
  title: '',
  content: '',
  target_type: 'all' as string,
  target_membership_level_id: '',
  target_user_ids_text: '',
})

const formatTime = (t?: string) => (t ? new Date(t).toLocaleString('zh-CN') : '-')

const targetText = (row: MpNotification) => {
  if (row.target_type === 'all') return '全部用户'
  if (row.target_type === 'membership') return `会员等级 #${row.target_membership_level_id || '-'}`
  if (row.target_type === 'users') return `指定用户 (${row.target_user_ids?.length || 0}人)`
  return row.target_type
}

const loadLevels = async () => {
  const res = await opsApi.listMembershipLevels()
  levels.value = res.data.levels
}

const load = async () => {
  loading.value = true
  try {
    const res = await opsApi.listMpNotifications({
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    items.value = res.data.notifications
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  Object.assign(form, {
    title: '',
    content: '',
    target_type: 'all',
    target_membership_level_id: '',
    target_user_ids_text: '',
  })
  dialogVisible.value = true
}

const submit = async () => {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('请填写标题和内容')
    return
  }
  const payload: Record<string, unknown> = {
    title: form.title.trim(),
    content: form.content.trim(),
    target_type: form.target_type,
  }
  if (form.target_type === 'membership') {
    if (!form.target_membership_level_id) {
      ElMessage.warning('请选择会员等级')
      return
    }
    payload.target_membership_level_id = form.target_membership_level_id
  }
  if (form.target_type === 'users') {
    const ids = form.target_user_ids_text
      .split(/[,，\s]+/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (!ids.length) {
      ElMessage.warning('请填写用户 ID')
      return
    }
    payload.target_user_ids = ids
  }
  submitting.value = true
  try {
    const res = await opsApi.createMpNotification(payload as Parameters<typeof opsApi.createMpNotification>[0])
    ElMessage.success(res.message || '发送成功')
    dialogVisible.value = false
    load()
  } catch {
    ElMessage.error('发送失败')
  } finally {
    submitting.value = false
  }
}

const viewDetail = (row: MpNotification) => {
  detail.value = row
  detailVisible.value = true
}

const revoke = async (row: MpNotification) => {
  await ElMessageBox.confirm(`确定撤回「${row.title}」？撤回后用户将不再看到此消息。`, '确认')
  try {
    await opsApi.revokeMpNotification(row.id)
    ElMessage.success('已撤回')
    load()
  } catch {
    ElMessage.error('操作失败')
  }
}

onMounted(async () => {
  await loadLevels()
  await load()
})
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
.detail-content {
  white-space: pre-wrap;
  line-height: 1.6;
}
</style>
