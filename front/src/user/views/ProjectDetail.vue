<template>
  <div v-if="project" class="project-detail" :class="{ 'editor-mode': activeTab === 'editor' }">
    <div class="page-header">
      <el-page-header @back="$router.push('/')">
        <template #content>
          <span class="project-title">{{ project.project_name }}</span>
          <el-tag :type="statusType(project.project_status)" class="ml12">{{ project.project_status }}</el-tag>
        </template>
      </el-page-header>
    </div>
    <el-tabs v-model="activeTab" class="project-tabs">
      <el-tab-pane label="生成流程" name="generate">
        <Generation :project-id="id" :bidding-id="project.biddingId" />
      </el-tab-pane>
      <el-tab-pane label="AI 工作台" name="workbench">
        <TiptapWorkbench :project-id="id" />
      </el-tab-pane>
      <el-tab-pane label="联网研究" name="research">
        <Research :project-id="id" />
      </el-tab-pane>
      <el-tab-pane label="在线编辑" name="editor">
        <Editor v-if="activeTab === 'editor'" :project-id="id" />
      </el-tab-pane>
    </el-tabs>
  </div>
  <div v-else class="loading-state">
    <el-skeleton :rows="6" animated />
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { projectApi } from '@/shared/api.js'
import Generation from './Generation.vue'
import Research from './Research.vue'
import Editor from './Editor.vue'
import TiptapWorkbench from './TiptapWorkbench.vue'

const route = useRoute()
const id = Number(route.params.id)
const project = ref(null)
const activeTab = ref(route.query.tab || 'generate')

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

watch(() => route.query.tab, (tab) => {
  if (tab) activeTab.value = tab
})
</script>

<style scoped>
.project-detail {
  min-height: calc(100vh - 104px);
}

.project-detail.editor-mode {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 104px);
  min-height: 720px;
}

.page-header { margin-bottom: 20px; }
.project-title { font-size: 18px; font-weight: 600; }
.ml12 { margin-left: 12px; }
.loading-state { padding: 40px 0; }

.project-tabs {
  display: flex;
  flex-direction: column;
}

.editor-mode .project-tabs {
  flex: 1;
  min-height: 0;
}

.editor-mode .project-tabs :deep(.el-tabs__content),
.editor-mode .project-tabs :deep(.el-tab-pane) {
  flex: 1;
  min-height: 0;
}
</style>
