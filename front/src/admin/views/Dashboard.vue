<template>
  <div>
    <h2 class="page-title">系统概览</h2>
    <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="dashboard-alert" />
    <el-row v-loading="loading" :gutter="16">
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="投标项目" :value="stats.projects" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="知识库文档" :value="stats.documents" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="模型调用次数" :value="stats.modelCalls" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { settingsApi } from '@/shared/api.js'

const stats = ref({ projects: 0, documents: 0, modelCalls: 0 })
const loading = ref(false)
const error = ref('')

async function loadStats() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await settingsApi.getDashboardStats()
    stats.value = {
      projects: Number(data.projects || 0),
      documents: Number(data.documents || 0),
      modelCalls: Number(data.modelCalls || 0),
    }
  } catch {
    error.value = '系统概览加载失败，请确认后端服务和数据库连接正常'
  } finally {
    loading.value = false
  }
}

onMounted(loadStats)
</script>

<style scoped>
.page-title { margin: 0 0 20px; font-size: 20px; }
.stat-card { border-radius: 12px; }
.dashboard-alert { margin-bottom: 16px; }
</style>
