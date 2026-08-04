<template>
  <div class="mp-users">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>用户管理</span>
          <div class="header-actions">
            <el-input
              v-model="keyword"
              placeholder="搜索昵称/openid/手机号"
              clearable
              style="width: 240px"
              @keyup.enter="applySearch"
            />
            <el-button type="primary" @click="applySearch">搜索</el-button>
          </div>
        </div>
      </template>

      <el-table :data="users" v-loading="loading" stripe>
        <el-table-column prop="nickname" label="昵称" min-width="120" />
        <el-table-column prop="openid" label="OpenID" min-width="160" show-overflow-tooltip />
        <el-table-column prop="role_name" label="角色" width="100">
          <template #default="{ row }">
            <el-tag :type="row.role === 'risk_officer' ? 'warning' : 'info'" size="small">
              {{ row.role_name || '普通' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="phone" label="手机号" width="120" />
        <el-table-column prop="balance" label="余额（元）" width="100">
          <template #default="{ row }">{{ row.balance?.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="total_analyses" label="研报数" width="80" />
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">{{ row.is_active ? '正常' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="注册时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="openManage(row)">管理</el-button>
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { opsApi, type MpUser } from '@/api/ops'
import { ElMessage } from 'element-plus'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()
const users = ref<MpUser[]>([])
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await opsApi.listMpUsers({
      keyword: keyword.value || undefined,
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    users.value = res.data.users
    total.value = res.data.total ?? res.data.users.length
  } catch {
    ElMessage.error('加载用户失败')
  } finally {
    loading.value = false
  }
}

const applySearch = () => {
  currentPage.value = 1
  loadUsers()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadUsers()
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  loadUsers()
}

const openManage = (row: MpUser) => {
  router.push({ name: 'MpUserDetail', params: { id: row.id } })
}

const formatTime = (t?: string) => (t ? formatDateTime(t) : '-')

onMounted(loadUsers)
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
}
.pagination-wrapper {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
</style>
