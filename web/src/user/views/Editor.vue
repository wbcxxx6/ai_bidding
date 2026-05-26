<template>
  <div class="editor-container">
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="8" animated />
    </div>
    <div v-else-if="error" class="error-state">
      <el-result icon="warning" :title="error">
        <template #extra>
          <el-button type="primary" @click="loadDocument">重试</el-button>
          <el-button v-if="fileUrl" @click="download">下载文档</el-button>
        </template>
      </el-result>
    </div>
    <div v-else-if="!fileUrl" class="empty-state">
      <el-empty description="暂无生成文档，请先完成投标文档生成" />
    </div>
    <div v-else>
      <div class="editor-toolbar">
        <el-button type="primary" size="small" @click="download">
          <el-icon><Download /></el-icon> 下载 Word
        </el-button>
        <el-tag type="success" size="small" v-if="editorReady">编辑器已就绪</el-tag>
        <el-tag type="warning" size="small" v-else-if="!editorError">正在加载编辑器...</el-tag>
        <el-tag type="danger" size="small" v-if="editorError">{{ editorError }}</el-tag>
      </div>
      <div id="onlyoffice-editor" class="editor-frame"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { projectApi } from '@/shared/api.js'

const props = defineProps({ projectId: Number })

const loading = ref(true)
const error = ref(null)
const fileUrl = ref(null)
const fileId = ref(null)
const editorReady = ref(false)
const editorError = ref(null)

let editorInstance = null

const ONLYOFFICE_URL = window.__ONLYOFFICE_URL__ || 'http://localhost:8081'

onMounted(() => { loadDocument() })

onBeforeUnmount(() => {
  if (editorInstance?.destroyEditor) {
    editorInstance.destroyEditor()
    editorInstance = null
  }
})

async function loadDocument() {
  loading.value = true
  error.value = null
  try {
    const { data } = await projectApi.get(props.projectId)
    if (data.generated_file_id) {
      fileId.value = data.generated_file_id
      fileUrl.value = `/api/files/${data.generated_file_id}/download`

      const { data: editorData } = await projectApi.getEditorConfig(props.projectId)
      if (editorData.config) {
        await initEditorWithConfig(editorData.config)
      } else {
        editorError.value = editorData.error || '无法获取编辑器配置'
      }
    } else {
      fileUrl.value = null
    }
  } catch (e) {
    error.value = '加载文档信息失败'
  } finally {
    loading.value = false
  }
}

async function initEditorWithConfig(config) {
  try {
    await loadOnlyOfficeScript()

    if (editorInstance?.destroyEditor) {
      editorInstance.destroyEditor()
    }

    config.events = {
      onAppReady: () => { editorReady.value = true },
      onError: (e) => { editorError.value = `编辑器错误: ${e?.data?.errorDescription || '未知'}` },
    }

    editorInstance = new window.DocsAPI.DocEditor('onlyoffice-editor', config)
  } catch (e) {
    editorError.value = e.message || 'OnlyOffice 加载失败'
  }
}

function loadOnlyOfficeScript() {
  if (window.DocsAPI) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = `${ONLYOFFICE_URL}/web-apps/apps/api/documents/api.js`
    script.onload = resolve
    script.onerror = () => reject(new Error('OnlyOffice 文档服务不可用，请确认 Document Server 已启动（端口 8081）'))
    document.head.appendChild(script)
  })
}

function download() {
  if (fileUrl.value) {
    window.open(fileUrl.value, '_blank')
  }
}
</script>

<style scoped>
.editor-container { height: calc(100vh - 180px); display: flex; flex-direction: column; }
.editor-toolbar { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
.editor-frame { flex: 1; width: 100%; min-height: 500px; border: 1px solid #e2e8f0; border-radius: 8px; }
.loading-state, .error-state, .empty-state { padding: 40px 0; }
</style>
