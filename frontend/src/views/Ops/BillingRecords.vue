<template>
  <div class="billing-records">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="消费流水" name="billing">
        <el-table :data="records" v-loading="loadingBilling" stripe>
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column prop="user_id" label="用户ID" width="120" show-overflow-tooltip />
          <el-table-column prop="action_type" label="类型" width="90" />
          <el-table-column prop="amount" label="金额" width="90">
            <template #default="{ row }">{{ row.amount?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="is_free" label="免费" width="70">
            <template #default="{ row }">{{ row.is_free ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column prop="stock_code" label="股票" width="90" />
          <el-table-column prop="remark" label="备注" min-width="160" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="充值订单" name="orders">
        <el-table :data="orders" v-loading="loadingOrders" stripe>
          <el-table-column prop="order_no" label="订单号" min-width="180" />
          <el-table-column prop="user_id" label="用户ID" width="120" show-overflow-tooltip />
          <el-table-column prop="amount" label="金额" width="90">
            <template #default="{ row }">{{ row.amount?.toFixed(2) }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 'paid' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="170" />
          <el-table-column prop="paid_at" label="支付时间" width="170" />
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { opsApi, type BillingRecord, type PaymentOrder } from '@/api/ops'
import { ElMessage } from 'element-plus'

const activeTab = ref('billing')
const records = ref<BillingRecord[]>([])
const orders = ref<PaymentOrder[]>([])
const loadingBilling = ref(false)
const loadingOrders = ref(false)

const loadBilling = async () => {
  loadingBilling.value = true
  try {
    const res = await opsApi.listBillingRecords({ limit: 100 })
    records.value = res.data.records
  } catch {
    ElMessage.error('加载流水失败')
  } finally {
    loadingBilling.value = false
  }
}

const loadOrders = async () => {
  loadingOrders.value = true
  try {
    const res = await opsApi.listPaymentOrders({ limit: 100 })
    orders.value = res.data.orders
  } catch {
    ElMessage.error('加载订单失败')
  } finally {
    loadingOrders.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'billing') loadBilling()
  else loadOrders()
})

onMounted(loadBilling)
</script>
