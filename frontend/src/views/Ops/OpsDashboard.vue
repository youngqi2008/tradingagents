<template>
  <div class="ops-dashboard">
    <el-row :gutter="16">
      <el-col :span="6" v-for="item in statCards" :key="item.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-label">{{ item.label }}</div>
          <div class="stat-value">{{ item.value }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { opsApi, type OpsStatistics } from '@/api/ops'
import { ElMessage } from 'element-plus'

const stats = ref<OpsStatistics | null>(null)

const statCards = computed(() => {
  const s = stats.value
  if (!s) return []
  return [
    { label: '小程序用户', value: s.mp_user_count },
    { label: '研报生成总数', value: s.total_generations },
    { label: '问股总次数', value: s.total_asks ?? 0 },
    { label: '会员月费收入（元）', value: (s.membership_fee_revenue ?? 0).toFixed(2) },
    { label: '生成收入（元）', value: s.generation_revenue.toFixed(2) },
    { label: '问股收入（元）', value: (s.ask_revenue ?? 0).toFixed(2) },
    { label: '充值总额（元）', value: s.total_recharge.toFixed(2) },
  ]
})

onMounted(async () => {
  try {
    const res = await opsApi.getStatistics()
    stats.value = res.data
  } catch {
    ElMessage.error('加载运营统计失败')
  }
})
</script>

<style scoped>
.stat-card {
  margin-bottom: 16px;
}
.stat-label {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  margin-top: 8px;
}
</style>
