<template>
  <div class="membership-levels">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>会员等级配置</span>
          <el-button type="primary" @click="openCreate">新增等级</el-button>
        </div>
      </template>

      <el-table :data="levels" v-loading="loading" stripe>
        <el-table-column prop="name" label="名称" width="110" />
        <el-table-column prop="code" label="代码" width="90" />
        <el-table-column prop="monthly_price" label="月费（元）" width="100" />
        <el-table-column prop="monthly_free_generations" label="免费研报/月" width="110" />
        <el-table-column prop="per_generation_price" label="研报单价" width="90" />
        <el-table-column prop="monthly_free_asks" label="免费问股/月" width="110" />
        <el-table-column prop="per_ask_price" label="问股单价" width="90" />
        <el-table-column prop="description" label="说明" min-width="180" />
        <el-table-column prop="is_default" label="默认" width="70">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="warning">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">{{ row.is_active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" :disabled="row.is_default" @click="removeLevel(row)">停用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑等级' : '新增等级'" width="520px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="代码"><el-input v-model="form.code" :disabled="!!editing" placeholder="如 normal / vip / vvip" /></el-form-item>
        <el-form-item label="月会员费（元）"><el-input-number v-model="form.monthly_price" :min="0" :precision="2" :step="1" /></el-form-item>
        <el-form-item label="月免费研报次数"><el-input-number v-model="form.monthly_free_generations" :min="0" /></el-form-item>
        <el-form-item label="研报超限单价"><el-input-number v-model="form.per_generation_price" :min="0" :precision="2" :step="1" /></el-form-item>
        <el-form-item label="月免费问股次数"><el-input-number v-model="form.monthly_free_asks" :min="0" /></el-form-item>
        <el-form-item label="问股超限单价"><el-input-number v-model="form.per_ask_price" :min="0" :precision="2" :step="0.1" :step-strictly="false" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
        <el-form-item label="默认等级"><el-switch v-model="form.is_default" /></el-form-item>
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
import { opsApi, type MembershipLevel } from '@/api/ops'
import { ElMessage, ElMessageBox } from 'element-plus'

const levels = ref<MembershipLevel[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref<MembershipLevel | null>(null)
const form = reactive({
  name: '',
  code: '',
  monthly_price: 0,
  monthly_free_generations: 0,
  per_generation_price: 9.9,
  monthly_free_asks: 0,
  per_ask_price: 1.9,
  description: '',
  is_default: false,
})

const load = async () => {
  loading.value = true
  try {
    const res = await opsApi.listMembershipLevels()
    levels.value = res.data.levels
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, {
    name: '',
    code: '',
    monthly_price: 0,
    monthly_free_generations: 0,
    per_generation_price: 9.9,
    monthly_free_asks: 0,
    per_ask_price: 1.9,
    description: '',
    is_default: false,
  })
  dialogVisible.value = true
}

const openEdit = (row: MembershipLevel) => {
  editing.value = row
  Object.assign(form, {
    name: row.name,
    code: row.code,
    monthly_price: row.monthly_price ?? 0,
    monthly_free_generations: row.monthly_free_generations,
    per_generation_price: row.per_generation_price,
    monthly_free_asks: row.monthly_free_asks ?? 0,
    per_ask_price: row.per_ask_price ?? row.per_generation_price,
    description: row.description,
    is_default: row.is_default,
  })
  dialogVisible.value = true
}

const submit = async () => {
  try {
    if (editing.value) {
      await opsApi.updateMembershipLevel(editing.value.id, { ...form })
    } else {
      await opsApi.createMembershipLevel({ ...form })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
  } catch {
    ElMessage.error('保存失败')
  }
}

const removeLevel = async (row: MembershipLevel) => {
  await ElMessageBox.confirm(`确定停用等级「${row.name}」？`, '确认')
  try {
    await opsApi.deleteMembershipLevel(row.id)
    ElMessage.success('已停用')
    load()
  } catch {
    ElMessage.error('操作失败')
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
</style>
