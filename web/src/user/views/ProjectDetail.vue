<template>
  <div v-if="project">
    <div class="page-header">
      <el-page-header @back="$router.push('/')">
        <template #content>
          <span class="project-title">{{ project.project_name }}</span>
          <el-tag :type="statusType(project.project_status)" class="ml12">{{ project.project_status }}</el-tag>
        </template>
      </el-page-header>
    </div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="生成流程" name="generate">
        <Generation :project-id="id" :bidding-id="project.biddingId" />
      </el-tab-pane>
      <el-tab-pane label="联网研究" name="research">
        <Research :project-id="id" />
      </el-tab-pane>
      <el-tab-pane label="在线编辑" name="editor">
        <Editor :project-id="id" />
      </el-tab-pane>
    </el-tabs>
  </div>
  <div v-else class="loading-state">
    <el-skeleton :rows="6" animated />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { projectApi } from '@/shared/api.js'
import Generation from './Generation.vue'
import Research from './Research.vue'
import Editor from './Editor.vue'

const route = useRoute()
const id = Number(route.params.id)
const project = ref(null)
const activeTab = ref('generate')

function statusType(s) {
  const map = { draft: 'info', analyzing: 'warning', generating: '', completed: 'success' }
  return map[s] || 'info'
}

onMounted(async () => {
  try {
    const { data } = await projectApi.get(id)
    project.value = data
  } catch { /* empty */ }
})
</script>

<style scoped>
.page-header { margin-bottom: 20px; }
.project-title { font-size: 18px; font-weight: 600; }
.ml12 { margin-left: 12px; }
.loading-state { padding: 40px 0; }
</style>
