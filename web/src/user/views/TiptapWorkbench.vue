<template>
  <div class="workbench">
    <aside class="chapter-panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">V2 P0</p>
          <h3>章节工作台</h3>
        </div>
        <el-button :icon="Refresh" circle size="small" :loading="loadingChapters" @click="loadChapters" />
      </div>

      <el-skeleton v-if="loadingChapters" :rows="6" animated />
      <el-empty v-else-if="!chapters.length" description="暂无章节，请先完成目录设计" />
      <div v-else class="chapter-list">
        <button
          v-for="chapter in chapters"
          :key="chapter.id"
          class="chapter-item"
          :class="{ active: selectedChapter?.id === chapter.id }"
          @click="selectChapter(chapter)"
        >
          <span class="chapter-title">{{ chapter.title }}</span>
          <span class="chapter-meta">
            <el-tag size="small" :type="chapter.status === 'generated' ? 'success' : 'info'">{{ chapter.status }}</el-tag>
            <span>{{ volumeLabel(chapter) }}</span>
          </span>
        </button>
      </div>
    </aside>

    <section class="editor-panel">
      <div class="toolbar">
        <div>
          <p class="eyebrow">{{ selectedChapter ? `章节 #${selectedChapter.id}` : '未选择章节' }}</p>
          <h2>{{ selectedChapter?.title || '选择章节开始生成' }}</h2>
        </div>
        <div class="toolbar-actions">
          <el-button :icon="Refresh" :disabled="!selectedChapter || generating" @click="reloadEditor">刷新</el-button>
          <el-button :icon="DocumentChecked" :disabled="!selectedChapter || saving" :loading="saving" @click="saveDoc">保存</el-button>
          <el-button type="primary" :icon="VideoPlay" :disabled="!selectedChapter || generating" :loading="generating" @click="generateChapter">
            生成本章
          </el-button>
        </div>
      </div>

      <el-alert
        v-if="errorText"
        class="inline-alert"
        type="error"
        :title="errorText"
        :closable="true"
        @close="errorText = ''"
      />

      <div v-if="!selectedChapter" class="empty-editor">
        <el-empty description="从左侧选择一个章节，进入 AI 流式写作" />
      </div>
      <div v-else class="editor-shell">
        <EditorContent v-if="editor" :editor="editor" class="tiptap-surface" />
      </div>
    </section>

    <aside class="inspector-panel">
      <section class="inspector-section">
        <div class="section-title">
          <h3>任务事件</h3>
          <el-tag size="small" :type="generating ? 'warning' : 'info'">{{ currentTaskId ? `#${currentTaskId}` : 'idle' }}</el-tag>
        </div>
        <div v-if="!events.length" class="muted-empty">暂无任务事件</div>
        <ol v-else class="event-list">
          <li v-for="(event, index) in events" :key="`${event.type}-${index}`">
            <span class="event-type">{{ event.type }}</span>
            <p>{{ eventText(event) }}</p>
          </li>
        </ol>
      </section>

      <section class="inspector-section">
        <div class="section-title">
          <h3>参考来源</h3>
          <el-tag size="small">{{ citations.length }}</el-tag>
        </div>
        <div v-if="!citations.length" class="muted-empty">生成后会显示进入 Prompt 的参考来源</div>
        <div v-else class="citation-list">
          <article v-for="citation in citations" :key="citation.id || citation.citationKey" class="citation-item">
            <strong>{{ citation.citationKey }}</strong>
            <span>{{ citation.sourceTitle || '参考资料' }}</span>
            <p>{{ citation.quoteText }}</p>
          </article>
        </div>
      </section>
    </aside>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentChecked, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { v2Api } from '@/shared/api.js'

const props = defineProps({ projectId: Number })

const chapters = ref([])
const selectedChapter = ref(null)
const loadingChapters = ref(false)
const saving = ref(false)
const generating = ref(false)
const errorText = ref('')
const events = ref([])
const citations = ref([])
const currentTaskId = ref(null)
const lastMarkdown = ref('')

const editor = useEditor({
  extensions: [StarterKit],
  content: '',
  editorProps: {
    attributes: {
      class: 'tiptap-content',
    },
  },
})

function volumeLabel(chapter) {
  const title = `${chapter.title || ''} ${chapter.type || ''}`
  if (title.includes('报价') || title.includes('价格')) return '报价'
  if (title.includes('资格') || title.includes('资质')) return '资格'
  if (title.includes('商务') || title.includes('合同')) return '商务'
  return '技术'
}

function eventText(event) {
  return event.text || event.message || event.error || event.sourceTitle || event.citationKey || ''
}

function setEditorMarkdown(markdown) {
  lastMarkdown.value = markdown || ''
  if (!editor.value) return
  const html = markdownToHtml(markdown || '')
  editor.value.commands.setContent(html || '<p></p>')
}

function appendToken(text) {
  lastMarkdown.value += text
  if (!editor.value) return
  editor.value.commands.insertContent(escapeHtml(text).replace(/\n/g, '<br>'))
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function markdownToHtml(markdown) {
  const lines = String(markdown || '').split('\n')
  const html = []
  let paragraph = []
  const flushParagraph = () => {
    if (!paragraph.length) return
    html.push(`<p>${paragraph.map(escapeHtml).join('<br>')}</p>`)
    paragraph = []
  }
  for (const line of lines) {
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      const level = Math.min(heading[1].length, 4)
      html.push(`<h${level}>${escapeHtml(heading[2])}</h${level}>`)
      continue
    }
    if (!line.trim()) {
      flushParagraph()
      continue
    }
    paragraph.push(line)
  }
  flushParagraph()
  return html.join('')
}

function nodeText(node) {
  if (!node) return ''
  if (node.type === 'text') return node.text || ''
  return (node.content || []).map(nodeText).join('')
}

function editorJsonToMarkdown(doc) {
  const blocks = []
  for (const node of doc?.content || []) {
    if (node.type === 'heading') {
      blocks.push(`${'#'.repeat(node.attrs?.level || 2)} ${nodeText(node)}`.trim())
    } else if (node.type === 'bulletList') {
      for (const item of node.content || []) {
        blocks.push(`- ${nodeText(item)}`.trim())
      }
    } else if (node.type === 'orderedList') {
      ;(node.content || []).forEach((item, index) => blocks.push(`${index + 1}. ${nodeText(item)}`.trim()))
    } else if (node.type === 'paragraph') {
      blocks.push(nodeText(node))
    } else {
      const text = nodeText(node)
      if (text) blocks.push(text)
    }
  }
  return blocks.filter(block => block.trim()).join('\n\n')
}

async function loadChapters() {
  loadingChapters.value = true
  errorText.value = ''
  try {
    const { data } = await v2Api.listChapters(props.projectId)
    chapters.value = data.items || []
    if (!selectedChapter.value && chapters.value.length) {
      await selectChapter(chapters.value[0])
    }
  } catch (error) {
    errorText.value = error.response?.data?.error || '章节加载失败'
  } finally {
    loadingChapters.value = false
  }
}

async function selectChapter(chapter) {
  selectedChapter.value = chapter
  events.value = []
  currentTaskId.value = null
  await reloadEditor()
  await loadCitations()
}

async function reloadEditor() {
  if (!selectedChapter.value) return
  try {
    const { data } = await v2Api.getEditorDoc(selectedChapter.value.id)
    setEditorMarkdown(data.markdown || '')
  } catch (error) {
    errorText.value = error.response?.data?.error || '正文加载失败'
  }
}

async function loadCitations() {
  if (!selectedChapter.value) return
  try {
    const { data } = await v2Api.listCitations(selectedChapter.value.id)
    citations.value = data.items || []
  } catch {
    citations.value = []
  }
}

async function saveDoc() {
  if (!selectedChapter.value || !editor.value) return
  saving.value = true
  try {
    await v2Api.saveEditorDoc(selectedChapter.value.id, {
      markdown: editorJsonToMarkdown(editor.value.getJSON()),
      tiptapJson: editor.value.getJSON(),
    })
    ElMessage.success('正文已保存')
    await loadChapters()
  } catch (error) {
    errorText.value = error.response?.data?.error || '保存失败'
  } finally {
    saving.value = false
  }
}

async function generateChapter() {
  if (!selectedChapter.value || generating.value) return
  generating.value = true
  errorText.value = ''
  events.value = []
  citations.value = []
  setEditorMarkdown('')
  try {
    const { data } = await v2Api.createTask({
      taskType: 'chapter_generate',
      projectId: props.projectId,
      chapterId: selectedChapter.value.id,
    })
    currentTaskId.value = data.task.id
    await consumeTaskStream(data.task.id)
    await loadCitations()
    await loadChapters()
  } catch (error) {
    errorText.value = error.response?.data?.error || error.message || '生成失败'
  } finally {
    generating.value = false
  }
}

async function consumeTaskStream(taskId) {
  const response = await fetch(v2Api.streamTaskUrl(taskId))
  if (!response.ok) {
    throw new Error('流式任务连接失败')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const event = JSON.parse(line.slice(6))
      events.value.push(event)
      if (event.type === 'token') {
        appendToken(event.text || '')
        await nextTick()
      } else if (event.type === 'citation') {
        citations.value.push(event)
      } else if (event.type === 'done') {
        setEditorMarkdown(lastMarkdown.value)
      } else if (event.type === 'error') {
        throw new Error(event.error || '生成任务失败')
      }
    }
  }
}

watch(() => props.projectId, () => loadChapters())

onMounted(loadChapters)

onBeforeUnmount(() => {
  editor.value?.destroy()
})
</script>

<style scoped>
.workbench {
  display: grid;
  grid-template-columns: 260px minmax(420px, 1fr) 320px;
  gap: 16px;
  min-height: calc(100vh - 112px);
}

.chapter-panel,
.editor-panel,
.inspector-panel {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.chapter-panel,
.inspector-panel {
  padding: 14px;
  overflow: hidden;
}

.panel-head,
.toolbar,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h3,
.section-title h3,
.toolbar h2 {
  margin: 0;
  color: #111827;
}

.toolbar h2 {
  font-size: 20px;
  font-weight: 650;
}

.eyebrow {
  margin: 0 0 4px;
  color: #6b7280;
  font-size: 12px;
  letter-spacing: 0;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
  max-height: calc(100vh - 190px);
  overflow-y: auto;
}

.chapter-item {
  width: 100%;
  padding: 10px;
  text-align: left;
  background: #f9fafb;
  border: 1px solid transparent;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color .2s ease, background .2s ease, transform .2s ease;
}

.chapter-item:hover,
.chapter-item.active {
  background: #fff;
  border-color: #2563eb;
}

.chapter-item:active {
  transform: scale(.99);
}

.chapter-title {
  display: block;
  color: #111827;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
}

.chapter-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
  color: #6b7280;
  font-size: 12px;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.toolbar {
  padding: 14px 16px;
  border-bottom: 1px solid #e5e7eb;
}

.toolbar-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.inline-alert {
  margin: 12px 16px 0;
}

.empty-editor {
  display: grid;
  place-items: center;
  min-height: 420px;
}

.editor-shell {
  flex: 1;
  min-height: 520px;
  padding: 16px;
  overflow: auto;
}

.tiptap-surface {
  min-height: 100%;
}

:deep(.tiptap-content) {
  min-height: 500px;
  padding: 20px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  outline: none;
  color: #111827;
  background: #fcfcfd;
  line-height: 1.75;
}

:deep(.tiptap-content p) {
  margin: 0 0 12px;
}

.inspector-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.inspector-section {
  min-height: 0;
  padding-bottom: 14px;
  border-bottom: 1px solid #edf2f7;
}

.inspector-section:last-child {
  border-bottom: none;
}

.muted-empty {
  margin-top: 12px;
  padding: 14px;
  color: #6b7280;
  font-size: 13px;
  background: #f9fafb;
  border-radius: 8px;
}

.event-list {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  max-height: 260px;
  overflow-y: auto;
}

.event-list li {
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
}

.event-type {
  color: #2563eb;
  font-size: 12px;
  font-weight: 700;
}

.event-list p,
.citation-item p {
  margin: 4px 0 0;
  color: #4b5563;
  font-size: 13px;
  line-height: 1.5;
}

.citation-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 360px;
  overflow-y: auto;
}

.citation-item {
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #edf2f7;
  border-radius: 8px;
}

.citation-item strong {
  display: inline-block;
  margin-right: 8px;
  color: #111827;
}

.citation-item span {
  color: #374151;
  font-size: 13px;
}

@media (max-width: 1100px) {
  .workbench {
    grid-template-columns: 1fr;
  }

  .chapter-list,
  .event-list,
  .citation-list {
    max-height: none;
  }
}
</style>
