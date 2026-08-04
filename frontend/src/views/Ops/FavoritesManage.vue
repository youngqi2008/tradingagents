<template>
  <div class="ops-favorites">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>自选股订阅管理</span>
          <div>
            <el-button @click="runMarketReview" :loading="reviewLoading">推送大盘复盘</el-button>
            <el-button @click="runDigest" :loading="digestLoading">立即推送自选日报</el-button>
            <el-button type="primary" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-form :inline="true" class="filter-row">
        <el-form-item label="用户ID">
          <el-input v-model="filterUserId" clearable placeholder="小程序用户 ID" style="width: 160px" />
        </el-form-item>
        <el-form-item label="股票代码">
          <el-input v-model="filterCode" clearable placeholder="如 600519" style="width: 140px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
        title="大盘复盘：工作日 18:00 推送全体用户；自选日报：18:05 按每人自选定向推送（均进小程序消息中心）。"
      />

      <el-table :data="items" v-loading="loading" stripe>
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="nickname" label="昵称" min-width="100" />
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" min-width="120" />
        <el-table-column prop="market" label="市场" width="80" />
        <el-table-column prop="notes" label="备注" min-width="120" />
        <el-table-column prop="added_at" label="加入时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.added_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="goUser(row.user_id)">用户</el-button>
            <el-button size="small" link @click="pushOne(row.user_id)">推送此人</el-button>
            <el-button size="small" link type="danger" @click="remove(row)">移除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="load"
        />
      </div>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>为用户添加自选</template>
      <el-form :inline="true">
        <el-form-item label="用户ID">
          <el-input v-model="addForm.user_id" style="width: 140px" />
        </el-form-item>
        <el-form-item label="代码">
          <el-input v-model="addForm.stock_code" style="width: 120px" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="addForm.stock_name" style="width: 140px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="addFavorite">添加</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { opsApi, type OpsFavoriteItem } from '@/api/ops'

const router = useRouter()
const loading = ref(false)
const digestLoading = ref(false)
const reviewLoading = ref(false)
const items = ref<OpsFavoriteItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const filterUserId = ref('')
const filterCode = ref('')

const addForm = reactive({
  user_id: '',
  stock_code: '',
  stock_name: '',
})

const fmtTime = (v?: string) => (v ? String(v).replace('T', ' ').slice(0, 19) : '-')

const load = async () => {
  loading.value = true
  try {
    const res = await opsApi.listOpsFavorites({
      user_id: filterUserId.value || undefined,
      stock_code: filterCode.value || undefined,
      mp_only: true,
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    items.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const goUser = (id: string) => {
  router.push(`/ops/users/${id}`)
}

const remove = async (row: OpsFavoriteItem) => {
  await ElMessageBox.confirm(`移除用户 ${row.user_id} 的自选 ${row.stock_code}？`, '确认')
  try {
    await opsApi.removeUserFavorite(row.user_id, row.stock_code)
    ElMessage.success('已移除')
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '移除失败')
  }
}

const addFavorite = async () => {
  if (!addForm.user_id || !addForm.stock_code) {
    ElMessage.warning('请填写用户ID和股票代码')
    return
  }
  try {
    await opsApi.addUserFavorite(addForm.user_id, {
      stock_code: addForm.stock_code,
      stock_name: addForm.stock_name || undefined,
    })
    ElMessage.success('已添加')
    addForm.stock_code = ''
    addForm.stock_name = ''
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '添加失败')
  }
}

const runDigest = async () => {
  digestLoading.value = true
  try {
    const res = await opsApi.runFavoritesDigest()
    ElMessage.success(res.message || `已推送 ${(res as any).data?.sent ?? 0} 人`)
  } catch (e: any) {
    ElMessage.error(e?.message || '推送失败')
  } finally {
    digestLoading.value = false
  }
}

const runMarketReview = async () => {
  reviewLoading.value = true
  try {
    const res = await opsApi.runMarketReview()
    ElMessage.success(res.message || '大盘复盘已推送')
  } catch (e: any) {
    ElMessage.error(e?.message || '大盘复盘失败')
  } finally {
    reviewLoading.value = false
  }
}

const pushOne = async (userId: string) => {
  try {
    const res = await opsApi.runFavoritesDigest(userId)
    ElMessage.success(res.message || '已推送')
  } catch (e: any) {
    ElMessage.error(e?.message || '推送失败')
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
.filter-row {
  margin-bottom: 8px;
}
.pager {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
