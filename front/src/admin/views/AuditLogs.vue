<template>
  <div>
    <h2 class="page-title">审计日志</h2>
    <el-table :data="logs" stripe>
      <el-table-column prop="provider_code" label="提供商" width="120" />
      <el-table-column prop="model_name" label="模型" width="160" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'succeeded' ? 'success' : 'danger'" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="latency_ms" label="耗时(ms)" width="100" />
      <el-table-column prop="created_at" label="时间" />
    </el-table>
    <el-empty v-if="!logs.length" description="暂无调用记录" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const logs = ref([])

onMounted(async () => {
  try {
    const { data } = await axios.get('/api/settings/model-logs')
    logs.value = data.items || data || []
  } catch { /* empty */ }
})
</script>

<style scoped>
.page-title { margin: 0 0 20px; font-size: 20px; }
</style>
