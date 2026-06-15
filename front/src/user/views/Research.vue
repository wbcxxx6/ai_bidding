<template>
  <div>
    <div class="page-header">
      <h3>联网研究报告</h3>
      <el-button type="primary" :loading="loading" @click="startResearch">发起研究</el-button>
    </div>
    <el-table :data="reports" stripe v-if="reports.length">
      <el-table-column prop="report_title" label="报告标题" />
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="primary" @click="viewReport(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-else description="暂无研究报告" />

    <el-dialog v-model="dialogVisible" title="研究报告详情" width="700px">
      <div v-if="currentReport">
        <h4>发现</h4>
        <ul><li v-for="(f, i) in findings" :key="i">{{ f }}</li></ul>
        <h4>风险提示</h4>
        <ul><li v-for="(r, i) in risks" :key="i" class="risk-item">{{ r }}</li></ul>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { researchApi } from '@/shared/api.js'

const props = defineProps({ projectId: Number })
const loading = ref(false)
const reports = ref([])
const dialogVisible = ref(false)
const currentReport = ref(null)

const findings = computed(() => {
  const json = currentReport.value?.findings_json
  if (!json) return []
  return typeof json === 'string' ? JSON.parse(json) : json
})
const risks = computed(() => {
  const json = currentReport.value?.risk_flags_json
  if (!json) return []
  return typeof json === 'string' ? JSON.parse(json) : json
})

onMounted(loadReports)

async function loadReports() {
  try {
    const { data } = await researchApi.listReports(props.projectId)
    reports.value = data.items || []
  } catch { /* empty */ }
}

async function startResearch() {
  loading.value = true
  try {
    await researchApi.create(props.projectId, { query: '招投标法规政策' })
    ElMessage.success('研究任务已提交')
    await loadReports()
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '研究失败')
  } finally { loading.value = false }
}

function viewReport(row) {
  currentReport.value = row
  dialogVisible.value = true
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.risk-item { color: #e53e3e; }
</style>
