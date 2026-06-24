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
    <div v-else class="editor-shell">
      <div class="editor-toolbar">
        <el-button type="primary" size="small" @click="download">
          <el-icon><Download /></el-icon> 下载 Word
        </el-button>
        <el-tag type="success" size="small" v-if="editorReady">编辑器已就绪</el-tag>
        <el-tag type="warning" size="small" v-else-if="!editorError">正在加载编辑器...</el-tag>
        <el-tag type="danger" size="small" v-if="editorError">{{ editorError }}</el-tag>
      </div>
      <div class="editor-frame-wrap">
        <div :id="editorElementId" class="editor-frame"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { projectApi } from '@/shared/api.js'

const props = defineProps({ projectId: Number })

const loading = ref(true)
const error = ref(null)
const fileUrl = ref(null)
const fileId = ref(null)
const editorReady = ref(false)
const editorError = ref(null)
const editorElementId = `onlyoffice-editor-${props.projectId}-${Date.now()}`

let editorInstance = null
let editorReadyTimer = null

const ONLYOFFICE_URL = window.__ONLYOFFICE_URL__ || import.meta.env.VITE_ONLYOFFICE_URL || 'http://localhost'

onMounted(() => { loadDocument() })

onBeforeUnmount(() => {
  clearEditorReadyTimer()
  if (editorInstance?.destroyEditor) {
    editorInstance.destroyEditor()
    editorInstance = null
  }
})

async function loadDocument() {
  loading.value = true
  error.value = null
  editorReady.value = false
  editorError.value = null
  clearEditorReadyTimer()
  try {
    const { data: editorData } = await projectApi.getEditorConfig(props.projectId)
    loading.value = false
    await nextTick()
    if (editorData.config) {
      fileId.value = editorData.generatedFileId
      fileUrl.value = `/api/files/${editorData.generatedFileId}/download`
      await initEditorWithConfig(editorData.config)
    } else {
      fileUrl.value = null
      error.value = editorData.error || '暂无可在线编辑的 Word 文档，请先在 AI 工作台导出整本。'
    }
  } catch (e) {
    error.value = e.response?.data?.error || '加载文档信息失败'
    loading.value = false
  }
}

function clearEditorReadyTimer() {
  if (editorReadyTimer) {
    clearTimeout(editorReadyTimer)
    editorReadyTimer = null
  }
}

function markEditorReady() {
  clearEditorReadyTimer()
  editorReady.value = true
}

function markEditorError(message) {
  clearEditorReadyTimer()
  editorError.value = message
}

function startEditorReadyTimer() {
  clearEditorReadyTimer()
  editorReadyTimer = setTimeout(() => {
    if (!editorReady.value && !editorError.value) {
      editorError.value = 'OnlyOffice 编辑器初始化超时，请检查 Document Server 是否能访问后端文档地址'
    }
  }, 15000)
}

function ensureEditorContainer() {
  const element = document.getElementById(editorElementId)
  if (!element) {
    throw new Error('OnlyOffice 编辑器容器未渲染，请重试')
  }
  const rect = element.getBoundingClientRect()
  if (rect.width < 320 || rect.height < 480) {
    throw new Error('OnlyOffice 编辑器容器尺寸异常，请刷新后重试')
  }
}

async function waitForEditorContainer() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await nextTick()
    await new Promise(resolve => requestAnimationFrame(resolve))
    const element = document.getElementById(editorElementId)
    if (!element) continue
    const rect = element.getBoundingClientRect()
    if (rect.width >= 320 && rect.height >= 480) return
  }
  ensureEditorContainer()
}

async function initEditorWithConfig(config) {
  try {
    await loadOnlyOfficeScript()
    await waitForEditorContainer()
    ensureEditorContainer()

    if (editorInstance?.destroyEditor) {
      editorInstance.destroyEditor()
    }

    config.events = {
      onAppReady: markEditorReady,
      onError: (e) => { markEditorError(`编辑器错误: ${e?.data?.errorDescription || '未知'}`) },
    }

    startEditorReadyTimer()
    editorInstance = new window.DocsAPI.DocEditor(editorElementId, config)
  } catch (e) {
    markEditorError(e.message || 'OnlyOffice 加载失败')
  }
}

function loadOnlyOfficeScript() {
  if (window.DocsAPI) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const existingScript = document.querySelector('script[data-onlyoffice-api="true"]')
    if (existingScript) {
      existingScript.addEventListener('load', resolve, { once: true })
      existingScript.addEventListener('error', () => reject(new Error(`OnlyOffice 文档服务不可用，请确认 Document Server 已启动：${ONLYOFFICE_URL}`)), { once: true })
      return
    }
    const script = document.createElement('script')
    script.dataset.onlyofficeApi = 'true'
    script.src = `${ONLYOFFICE_URL}/web-apps/apps/api/documents/api.js`
    script.onload = resolve
    script.onerror = () => reject(new Error(`OnlyOffice 文档服务不可用，请确认 Document Server 已启动：${ONLYOFFICE_URL}`))
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
.editor-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 640px;
}

.editor-shell {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 12px;
  padding: 8px 0 12px;
}

.editor-frame-wrap {
  flex: 1;
  height: min(820px, calc(100vh - 230px));
  min-height: 680px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #dfe7f2;
  border-radius: 8px;
}

.editor-frame {
  width: 100%;
  height: 100%;
  min-height: 680px;
}

.loading-state,
.error-state,
.empty-state {
  padding: 40px 0;
}
</style>
