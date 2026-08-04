<template>
  <div class="role-manage">
    <el-card>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="角色管理" name="roles" />
        <el-tab-pane label="角色授予" name="grant" />
      </el-tabs>

      <!-- 角色管理 -->
      <div v-show="activeTab === 'roles'">
        <div class="header-row">
          <span class="hint">管理小程序业务角色（与会员等级独立）。内置：普通、风控专员。</span>
          <el-button type="primary" @click="openCreate">新增角色</el-button>
        </div>

        <el-table :data="roles" v-loading="rolesLoading" stripe>
          <el-table-column prop="name" label="名称" width="120" />
          <el-table-column prop="code" label="编码" width="140" />
          <el-table-column prop="description" label="说明" min-width="200" />
          <el-table-column prop="user_count" label="用户数" width="90" />
          <el-table-column prop="is_default" label="默认" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_default" type="warning" size="small">默认</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEdit(row)">编辑</el-button>
              <el-button
                size="small"
                type="danger"
                :disabled="row.is_default || !row.is_active"
                @click="deactivate(row)"
              >
                停用
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 角色授予 -->
      <div v-show="activeTab === 'grant'">
        <div class="header-row">
          <div class="filters">
            <el-input
              v-model="keyword"
              placeholder="搜索昵称/openid/手机号"
              clearable
              style="width: 220px"
              @keyup.enter="applySearch"
            />
            <el-select v-model="filterRole" placeholder="按角色筛选" clearable style="width: 160px" @change="applySearch">
              <el-option v-for="r in activeRoles" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
            <el-button type="primary" @click="applySearch">搜索</el-button>
          </div>
          <div class="grant-actions">
            <el-select v-model="grantRole" placeholder="授予角色" style="width: 160px">
              <el-option v-for="r in activeRoles" :key="r.code" :label="r.name" :value="r.code" />
            </el-select>
            <el-button
              type="warning"
              :disabled="!selectedIds.length || !grantRole"
              :loading="granting"
              @click="grantSelected"
            >
              授予选中（{{ selectedIds.length }}）
            </el-button>
          </div>
        </div>

        <el-table
          :data="users"
          v-loading="usersLoading"
          stripe
          @selection-change="onSelectionChange"
        >
          <el-table-column type="selection" width="48" />
          <el-table-column prop="nickname" label="昵称" min-width="120" />
          <el-table-column prop="openid" label="OpenID" min-width="160" show-overflow-tooltip />
          <el-table-column prop="role_name" label="当前角色" width="110">
            <template #default="{ row }">
              <el-tag :type="row.role === 'risk_officer' ? 'warning' : 'info'" size="small">
                {{ row.role_name || '普通' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="is_active" label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                {{ row.is_active ? '正常' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-select
                :model-value="row.role || 'normal'"
                size="small"
                style="width: 120px"
                @change="(v) => grantOne(row, String(v))"
              >
                <el-option v-for="r in activeRoles" :key="r.code" :label="r.name" :value="r.code" />
              </el-select>
              <el-button link type="primary" size="small" @click="goUser(row.id)">详情</el-button>
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
            @size-change="loadUsers"
            @current-change="loadUsers"
          />
        </div>
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑角色' : '新增角色'" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：风控专员" />
        </el-form-item>
        <el-form-item label="编码" required>
          <el-input
            v-model="form.code"
            :disabled="!!editing"
            placeholder="如 risk_officer（字母数字下划线）"
          />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" />
        </el-form-item>
        <el-form-item label="默认角色">
          <el-switch v-model="form.is_default" />
        </el-form-item>
        <el-form-item v-if="editing" label="启用">
          <el-switch v-model="form.is_active" :disabled="!!editing?.is_default" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { opsApi, type MpUser, type UserRole } from '@/api/ops'

const router = useRouter()
const activeTab = ref('roles')

const roles = ref<UserRole[]>([])
const rolesLoading = ref(false)
const dialogVisible = ref(false)
const editing = ref<UserRole | null>(null)
const form = reactive({
  name: '',
  code: '',
  description: '',
  sort_order: 0,
  is_default: false,
  is_active: true,
})

const users = ref<MpUser[]>([])
const usersLoading = ref(false)
const keyword = ref('')
const filterRole = ref('')
const grantRole = ref('')
const granting = ref(false)
const selectedIds = ref<string[]>([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const activeRoles = computed(() => roles.value.filter((r) => r.is_active !== false))

const loadRoles = async () => {
  rolesLoading.value = true
  try {
    const res = await opsApi.listUserRoles()
    roles.value = res.data.roles || []
    if (!grantRole.value && activeRoles.value.length) {
      const risk = activeRoles.value.find((r) => r.code === 'risk_officer')
      grantRole.value = risk?.code || activeRoles.value[0].code
    }
  } finally {
    rolesLoading.value = false
  }
}

const loadUsers = async () => {
  usersLoading.value = true
  try {
    const res = await opsApi.listMpUsers({
      keyword: keyword.value || undefined,
      role: filterRole.value || undefined,
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value,
    })
    users.value = res.data.users || []
    total.value = res.data.total || 0
  } finally {
    usersLoading.value = false
  }
}

const applySearch = () => {
  currentPage.value = 1
  loadUsers()
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, {
    name: '',
    code: '',
    description: '',
    sort_order: 0,
    is_default: false,
    is_active: true,
  })
  dialogVisible.value = true
}

const openEdit = (row: UserRole) => {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    code: row.code,
    description: row.description || '',
    sort_order: row.sort_order ?? 0,
    is_default: !!row.is_default,
    is_active: row.is_active !== false,
  })
  dialogVisible.value = true
}

const submitRole = async () => {
  if (!form.name.trim() || !form.code.trim()) {
    ElMessage.warning('请填写名称和编码')
    return
  }
  try {
    if (editing.value?.id) {
      await opsApi.updateUserRoleDef(editing.value.id, {
        name: form.name,
        description: form.description,
        sort_order: form.sort_order,
        is_default: form.is_default,
        is_active: form.is_active,
      })
    } else {
      await opsApi.createUserRole({
        name: form.name,
        code: form.code,
        description: form.description,
        sort_order: form.sort_order,
        is_default: form.is_default,
      })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await loadRoles()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

const deactivate = async (row: UserRole) => {
  if (!row.id) return
  await ElMessageBox.confirm(`确定停用角色「${row.name}」？已授予该角色的用户不会自动变更。`, '确认')
  try {
    await opsApi.deactivateUserRole(row.id)
    ElMessage.success('已停用')
    await loadRoles()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

const onSelectionChange = (rows: MpUser[]) => {
  selectedIds.value = rows.map((r) => r.id)
}

const grantOne = async (row: MpUser, role: string) => {
  try {
    await opsApi.updateUserRole(row.id, role)
    ElMessage.success('角色已更新')
    await loadUsers()
    await loadRoles()
  } catch {
    ElMessage.error('更新失败')
    await loadUsers()
  }
}

const grantSelected = async () => {
  if (!selectedIds.value.length || !grantRole.value) return
  const roleName = activeRoles.value.find((r) => r.code === grantRole.value)?.name || grantRole.value
  await ElMessageBox.confirm(
    `将选中的 ${selectedIds.value.length} 名用户授予「${roleName}」？`,
    '批量授予'
  )
  granting.value = true
  try {
    const res = await opsApi.grantUserRoles(selectedIds.value, grantRole.value)
    ElMessage.success(res.message || '授予完成')
    selectedIds.value = []
    await loadUsers()
    await loadRoles()
  } catch (e: any) {
    ElMessage.error(e?.message || '批量授予失败')
  } finally {
    granting.value = false
  }
}

const goUser = (id: string) => router.push({ name: 'MpUserDetail', params: { id } })

onMounted(async () => {
  await loadRoles()
  await loadUsers()
})
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.filters,
.grant-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.hint {
  color: #909399;
  font-size: 13px;
}
.pagination-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
