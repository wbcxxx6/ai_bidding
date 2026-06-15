<template>
  <div>
    <div class="page-header">
      <h2>项目中心</h2>
      <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".pdf,.doc,.docx,.txt,.md">
        <el-button type="primary" :icon="Upload">上传招标文件</el-button>
      </el-upload>
    </div>
    <el-row :gutter="16" v-if="projects.length">
      <el-col :xs="24" :sm="12" :lg="8" v-for="p in projects" :key="p.id">
        <el-card shadow="hover" class="project-card" @click="$router.push(`/project/${p.id}`)">
          <template #header>
            <div class="card-header">
              <span class="project-name">{{ p.project_name || p.projectName }}</span>
              <el-tag :type="statusType(p.project_status || p.projectStatus)" size="small">
                {{ p.project_status || p.projectStatus || 'draft' }}
              </el-tag>
            </div>
          </template>
          <div class="card-meta">
            <p><el-icon><Calendar /></el-icon> {{ p.created_at || p.createdAt }}</p>
            <p v-if="p.purchaser_name"><el-icon><OfficeBuilding /></el-icon> {{ p.purchaser_name }}</p>
          </div>
        </el-card>
      </el-col>
    </el-row>
    <el-empty v-else description="暂无项目，请上传招标文件创建项目" />
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { biddingApi, projectApi } from '@/shared/api.js'

const router = useRouter()
const projects = ref([])

async function loadProjects() {
  try {
    const { data } = await projectApi.list()
    projects.value = data.items || data || []
  } catch { /* empty */ }
}

onMounted(loadProjects)
onActivated(loadProjects)

function statusType(s) {
  const map = { draft: 'info', analyzing: 'warning', generating: '', completed: 'success' }
  return map[s] || 'info'
}

async function handleUpload(file) {
  try {
    const { data } = await biddingApi.upload(file)
    ElMessage.success('上传成功，项目已创建')
    await loadProjects()
    router.push(`/project/${data.projectId}`)
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '上传失败')
  }
  return false
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; color: #1a202c; }
.project-card { cursor: pointer; transition: transform 0.2s; border-radius: 12px; }
.project-card:hover { transform: translateY(-2px); }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.project-name { font-weight: 600; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.card-meta p { margin: 6px 0; font-size: 13px; color: #718096; display: flex; align-items: center; gap: 6px; }
</style>
