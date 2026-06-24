<template>
  <div class="workbench">
    <section class="overview-card">
      <div class="overview-identity">
        <div>
          <p class="eyebrow">AI 工作台</p>
          <h3>项目总览</h3>
        </div>
        <el-tag size="small" :type="overviewTagType">{{ workbench.project?.projectStatus || 'draft' }}</el-tag>
      </div>
      <div class="overview-progress">
        <div class="progress-ring" :style="{ '--progress': `${Number(workbench.chapterStatus?.progressPercent || 0) * 3.6}deg` }">
          <span>{{ Math.round(Number(workbench.chapterStatus?.progressPercent || 0)) }}%</span>
        </div>
        <div class="progress-copy">
          <strong>{{ workbench.chapterStatus?.generated || 0 }}/{{ workbench.chapterStatus?.total || 0 }}</strong>
          <span>章节已形成正文</span>
          <el-progress :percentage="Number(workbench.chapterStatus?.progressPercent || 0)" :stroke-width="8" :show-text="false" />
        </div>
      </div>
      <div class="overview-metrics">
        <article>
          <strong>{{ workbench.stats?.citationCount || 0 }}</strong>
          <span>引用</span>
        </article>
        <article>
          <strong>{{ workbench.stats?.imagePlanCount || 0 }}</strong>
          <span>配图计划</span>
        </article>
        <article>
          <strong>{{ workbench.stats?.pendingFollowupCount || 0 }}</strong>
          <span>待补资料</span>
        </article>
        <article>
          <strong>{{ workbench.stats?.pendingImagePlanCount || 0 }}</strong>
          <span>待补图片</span>
        </article>
      </div>
      <div class="overview-actions">
        <el-button
          type="primary"
          :icon="VideoPlay"
          :disabled="generating || projectRunning || !nextPendingChapter"
          :loading="projectRunning"
          @click="generateWholeProject"
        >
          批量顺序生成整本
        </el-button>
        <el-button
          plain
          :icon="VideoPlay"
          :disabled="generating || projectRunning || !nextPendingChapter"
          @click="generateNextPendingChapter"
        >
          继续生成未完成章节
        </el-button>
        <el-button
          type="success"
          plain
          :icon="DocumentChecked"
          :disabled="generating || projectRunning || exportingProject || !canExportProject"
          :loading="exportingProject"
          @click="exportWholeProject"
        >
          导出整本
        </el-button>
        <el-button :icon="Refresh" :loading="loadingChapters" @click="loadWorkbench">刷新总览</el-button>
      </div>
      <div v-if="workbench.volumes?.length" class="volume-pills">
        <span v-for="volume in workbench.volumes" :key="volume.volumeType" class="volume-pill">
          {{ volumeName(volume.volumeType) }} {{ volume.generatedCount }}/{{ volume.chapterCount }}
        </span>
      </div>
    </section>

    <aside class="chapter-panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">章节导航</p>
          <h3>章节工作台</h3>
        </div>
        <el-select v-model="chapterFilter" size="small" class="chapter-filter">
          <el-option label="全部章节" value="all" />
          <el-option label="待生成" value="pending" />
          <el-option label="已生成" value="generated" />
          <el-option label="有待办" value="attention" />
        </el-select>
      </div>

      <el-skeleton v-if="loadingChapters" :rows="6" animated />
      <el-empty v-else-if="!chapters.length" description="暂无章节，请先完成目录设计" />
      <div v-else class="chapter-list">
        <button
          v-for="chapter in filteredChapters"
          :key="chapter.id"
          class="chapter-item"
          :class="{ active: selectedChapter?.id === chapter.id }"
          @click="selectChapter(chapter)"
        >
          <span class="chapter-title">{{ chapter.title }}</span>
          <span class="chapter-meta">
            <el-tag size="small" :type="chapter.hasContent ? 'success' : 'info'">{{ chapter.hasContent ? 'ready' : chapter.status }}</el-tag>
            <span>{{ volumeLabel(chapter) }}</span>
          </span>
          <span class="chapter-stats">
            <span>{{ chapter.wordCount || 0 }} 字</span>
            <span>{{ chapter.citationCount || 0 }} 引用</span>
            <span v-if="chapter.pendingFollowupCount || chapter.pendingImagePlanCount" class="warn-text">
              {{ (chapter.pendingFollowupCount || 0) + (chapter.pendingImagePlanCount || 0) }} 待处理
            </span>
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
        <div class="floating-actions">
          <el-button :icon="Refresh" :disabled="!selectedChapter || generating" @click="reloadEditor">刷新</el-button>
          <el-button :icon="DocumentChecked" :disabled="!selectedChapter || saving" :loading="saving" @click="saveDoc">保存</el-button>
          <el-button type="primary" :icon="VideoPlay" :disabled="!selectedChapter || generating" :loading="generating" @click="generateChapter">
            生成本章
          </el-button>
        </div>
        <div
          v-if="selectionToolbar.visible"
          class="selection-toolbar"
          :style="{ left: `${selectionToolbar.x}px`, top: `${selectionToolbar.y}px` }"
        >
          <el-button size="small" :icon="EditPen" @mousedown.prevent @click="openInlineRewrite">重写</el-button>
        </div>
        <div
          v-if="inlineRewriteVisible"
          class="inline-rewrite-card"
          :style="{ left: `${selectionToolbar.x}px`, top: `${selectionToolbar.y + 38}px` }"
          @mousedown.stop
        >
          <div class="inline-rewrite-head">
            <strong>改写选区</strong>
            <el-button link size="small" @click="closeInlineRewrite">关闭</el-button>
          </div>
          <el-input
            v-model="rewriteInstruction"
            type="textarea"
            :rows="3"
            placeholder="输入改写要求，例如更正式、扩写、压缩、突出响应点"
          />
          <el-input
            v-if="rewriteSuggestion"
            v-model="rewriteSuggestion"
            class="rewrite-suggestion"
            type="textarea"
            :rows="5"
          />
          <div class="inline-rewrite-actions">
            <el-button size="small" :loading="rewriting" :disabled="!rewriteInstruction.trim()" @click="createRewriteSuggestion">
              生成建议
            </el-button>
            <el-button size="small" type="primary" :disabled="!rewriteSuggestion" :loading="saving" @click="applyRewriteSuggestion">
              替换并保存
            </el-button>
          </div>
        </div>
        <EditorContent v-if="editor" :editor="editor" class="tiptap-surface" />
      </div>
    </section>

    <aside class="inspector-panel">
      <section class="inspector-section">
        <div class="section-title">
          <h3>项目级待办</h3>
          <el-tag size="small">{{ workbench.pendingActions?.length || 0 }}</el-tag>
        </div>
        <div v-if="!workbench.pendingActions?.length" class="muted-empty">当前项目没有新的阻塞项，适合继续整本生成或直接导出。</div>
        <div v-else class="followup-list">
          <article v-for="item in workbench.pendingActions" :key="`${item.kind}-${item.chapterId || item.message}`" class="followup-item">
            <el-tag size="small" :type="item.severity === 'warning' ? 'warning' : 'info'">{{ item.kind }}</el-tag>
            <p>{{ item.message }}</p>
          </article>
        </div>
      </section>

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

      <section class="inspector-section">
        <div class="section-title">
          <h3>图片计划</h3>
          <el-tag size="small">{{ imagePlans.length }}</el-tag>
        </div>
        <div v-if="!imagePlans.length" class="muted-empty">生成时会自动判断本章是否需要配图</div>
        <div v-else class="plan-list">
          <article v-for="plan in imagePlans" :key="plan.id || `${plan.imageType}-${plan.caption}`" class="plan-item">
            <div class="plan-row">
              <strong>{{ imageTypeLabel(plan.imageType) }}</strong>
              <el-tag size="small" :type="plan.status === 'ready' ? 'success' : 'warning'">{{ plan.status }}</el-tag>
            </div>
            <p>{{ plan.caption }}</p>
            <span>{{ plan.query }}</span>
          </article>
        </div>
      </section>

      <section class="inspector-section">
        <div class="section-title">
          <h3>待办追问</h3>
          <el-tag size="small">{{ followups.length }}</el-tag>
        </div>
        <div v-if="!followups.length" class="muted-empty">资料或图片不足时会在这里形成待办</div>
        <div v-else class="followup-list">
          <article v-for="item in followups" :key="item.id || item.question" class="followup-item">
            <el-tag size="small" :type="item.severity === 'error' ? 'danger' : 'warning'">{{ actionLabel(item.action) }}</el-tag>
            <p>{{ item.question }}</p>
          </article>
        </div>
      </section>
    </aside>

  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DocumentChecked, EditPen, Refresh, VideoPlay } from '@element-plus/icons-vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import { Node } from '@tiptap/core'
import { v2Api } from '@/shared/api.js'

const props = defineProps({ projectId: Number })
const route = useRoute()
const activeProjectId = computed(() => Number(props.projectId || route.params.id))

const chapters = ref([])
const selectedChapter = ref(null)
const loadingChapters = ref(false)
const saving = ref(false)
const generating = ref(false)
const errorText = ref('')
const events = ref([])
const citations = ref([])
const imagePlans = ref([])
const followups = ref([])
const currentTaskId = ref(null)
const lastMarkdown = ref('')
const chapterFilter = ref('all')
const projectRunning = ref(false)
const exportingProject = ref(false)
const rewriting = ref(false)
const inlineRewriteVisible = ref(false)
const rewriteInstruction = ref('')
const rewriteSuggestion = ref('')
const rewriteSelection = ref({ from: null, to: null, text: '' })
const selectionToolbar = ref({ visible: false, x: 0, y: 0 })
const workbench = ref({
  project: null,
  chapterStatus: { total: 0, generated: 0, pending: 0, progressPercent: 0 },
  stats: { citationCount: 0, imagePlanCount: 0, followupCount: 0, pendingFollowupCount: 0, pendingImagePlanCount: 0 },
  volumes: [],
  chapters: [],
  recentTasks: [],
})
let renderTimer = null
let autostartConsumed = false

const MarkdownTable = Node.create({
  name: 'markdownTable',
  group: 'block',
  atom: true,
  addAttributes() {
    return {
      markdown: {
        default: '',
        parseHTML: element => element.getAttribute('data-markdown-table') || '',
      },
    }
  },
  parseHTML() {
    return [{ tag: 'div[data-markdown-table]' }]
  },
  renderHTML({ node }) {
    return markdownTableToDomSpec(node.attrs.markdown || '')
  },
})

const editor = useEditor({
  extensions: [StarterKit, MarkdownTable],
  content: '',
  onSelectionUpdate: ({ editor: activeEditor }) => updateSelectionToolbar(activeEditor),
  onBlur: () => {
    if (!inlineRewriteVisible.value) {
      selectionToolbar.value.visible = false
    }
  },
  editorProps: {
    attributes: {
      class: 'tiptap-content',
    },
  },
})

function volumeLabel(chapter) {
  return volumeName(chapter.volumeType || inferVolumeType(chapter))
}

function inferVolumeType(chapter) {
  const title = `${chapter.title || ''} ${chapter.type || ''}`
  if (title.includes('报价') || title.includes('价格')) return 'pricing'
  if (title.includes('资格') || title.includes('资质')) return 'qualification'
  if (title.includes('商务') || title.includes('合同')) return 'business'
  return 'technical'
}

function volumeName(type) {
  const labels = {
    technical: '技术',
    business: '商务',
    qualification: '资格',
    pricing: '报价',
  }
  return labels[type] || '技术'
}

function eventText(event) {
  return event.text || event.message || event.error || event.sourceTitle || event.citationKey || ''
}

function imageTypeLabel(type) {
  const labels = {
    architecture_diagram: '架构图',
    process_diagram: '流程图',
    org_chart: '组织架构图',
    product_image: '产品图',
  }
  return labels[type] || type || '图片'
}

function actionLabel(action) {
  const labels = {
    upload_knowledge: '补资料',
    upload_image_asset: '补图片',
    rewrite_chapter: '改写',
  }
  return labels[action] || action || '待办'
}

const overviewTagType = computed(() => {
  const status = workbench.value.project?.projectStatus
  if (status === 'completed') return 'success'
  if (status === 'generating' || generating.value) return 'warning'
  return 'info'
})

const filteredChapters = computed(() => {
  if (chapterFilter.value === 'generated') return chapters.value.filter(chapter => chapter.hasContent)
  if (chapterFilter.value === 'pending') return chapters.value.filter(chapter => !chapter.hasContent)
  if (chapterFilter.value === 'attention') {
    return chapters.value.filter(chapter => (chapter.pendingFollowupCount || 0) > 0 || (chapter.pendingImagePlanCount || 0) > 0)
  }
  return chapters.value
})

const nextPendingChapter = computed(() => chapters.value.find(chapter => !chapter.hasContent))
const canExportProject = computed(() => {
  const status = workbench.value.chapterStatus || {}
  return (status.total || 0) > 0 && (status.pending || 0) === 0
})

function setEditorMarkdown(markdown) {
  lastMarkdown.value = markdown || ''
  renderEditorMarkdown()
}

function getSelectedText() {
  if (!editor.value) return { from: null, to: null, text: '' }
  const { from, to, empty } = editor.value.state.selection
  if (empty || from === to) return { from, to, text: '' }
  const text = editor.value.state.doc.textBetween(from, to, '\n\n').trim()
  const contextBefore = editor.value.state.doc.textBetween(Math.max(0, from - 700), from, '\n\n')
  const contextAfter = editor.value.state.doc.textBetween(to, Math.min(editor.value.state.doc.content.size, to + 700), '\n\n')
  return { from, to, text, contextBefore, contextAfter }
}

function updateSelectionToolbar(activeEditor = editor.value) {
  if (!activeEditor || !selectedChapter.value || generating.value) {
    selectionToolbar.value.visible = false
    return
  }
  const { from, to, empty } = activeEditor.state.selection
  if (empty || from === to) {
    if (!inlineRewriteVisible.value) {
      selectionToolbar.value.visible = false
    }
    return
  }
  const text = activeEditor.state.doc.textBetween(from, to, '\n\n').trim()
  if (!text) {
    selectionToolbar.value.visible = false
    return
  }
  const start = activeEditor.view.coordsAtPos(from)
  const shell = activeEditor.view.dom.closest('.editor-shell')
  const shellRect = shell?.getBoundingClientRect()
  if (!shellRect) return
  const x = Math.max(8, Math.min(start.left - shellRect.left, shellRect.width - 400))
  selectionToolbar.value = {
    visible: true,
    x,
    y: Math.max(8, start.top - shellRect.top - 42 + (shell?.scrollTop || 0)),
  }
  if (!inlineRewriteVisible.value) {
    rewriteSelection.value = getSelectedText()
  }
}

function openInlineRewrite() {
  const selection = getSelectedText()
  if (!selection.text) {
    ElMessage.warning('请先在正文中选中需要改写的一段内容')
    return
  }
  rewriteSelection.value = selection
  rewriteInstruction.value = ''
  rewriteSuggestion.value = ''
  inlineRewriteVisible.value = true
  selectionToolbar.value.visible = true
}

function closeInlineRewrite() {
  inlineRewriteVisible.value = false
  rewriteInstruction.value = ''
  rewriteSuggestion.value = ''
  selectionToolbar.value.visible = false
}

async function createRewriteSuggestion() {
  if (!selectedChapter.value || !rewriteSelection.value.text || !rewriteInstruction.value.trim()) return
  rewriting.value = true
  errorText.value = ''
  try {
    const { data } = await v2Api.rewriteSelection(selectedChapter.value.id, {
      selectedText: rewriteSelection.value.text,
      instruction: rewriteInstruction.value.trim(),
      contextBefore: rewriteSelection.value.contextBefore || '',
      contextAfter: rewriteSelection.value.contextAfter || '',
    })
    rewriteSuggestion.value = data.newText || ''
    if (!rewriteSuggestion.value) {
      ElMessage.warning('未生成可替换内容，请调整改写要求后重试')
    }
  } catch (error) {
    errorText.value = error.response?.data?.error || '改写建议生成失败'
  } finally {
    rewriting.value = false
  }
}

async function applyRewriteSuggestion() {
  if (!editor.value || !rewriteSuggestion.value || rewriteSelection.value.from == null || rewriteSelection.value.to == null) return
  const { from, to, text } = rewriteSelection.value
  const currentText = editor.value.state.doc.textBetween(from, to, '\n\n').trim()
  if (currentText !== text) {
    ElMessage.warning('选区内容已经变化，请重新选择后再替换')
    return
  }
  editor.value
    .chain()
    .focus()
    .insertContentAt({ from, to }, rewriteSuggestion.value)
    .run()
  closeInlineRewrite()
  await saveDoc({ silent: true })
  ElMessage.success('选中内容已替换并保存')
}

function renderEditorMarkdown() {
  if (!editor.value) return
  const html = markdownToHtml(lastMarkdown.value || '')
  editor.value.commands.setContent(html || '<p></p>', { emitUpdate: false })
  if (typeof document === 'undefined') return
  requestAnimationFrame(() => {
    const surface = document.querySelector('.editor-shell')
    if (surface) surface.scrollTop = surface.scrollHeight
  })
}

function appendToken(text) {
  lastMarkdown.value += text
  scheduleMarkdownRender()
}

function scheduleMarkdownRender(force = false) {
  if (renderTimer) {
    clearTimeout(renderTimer)
    renderTimer = null
  }
  if (force) {
    renderEditorMarkdown()
    return
  }
  renderTimer = setTimeout(() => {
    renderTimer = null
    renderEditorMarkdown()
  }, 160)
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderInlineMarkdown(value) {
  return escapeHtml(String(value || '').replace(/<br\s*\/?>/gi, '\n'))
    .replace(/\n/g, '<br>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
}

function renderImagePlaceholder(line) {
  const match = line.match(/^!\[([^\]]*)\]\((image-plan:\/\/[^)\s]+)\)\s*$/)
  if (!match) return null
  const caption = renderInlineMarkdown(match[1] || '章节配图')
  return `<figure class="image-plan-placeholder"><div>图片待补充</div><figcaption>${caption}</figcaption></figure>`
}

function renderFlowchartPlaceholder(code, lang) {
  let caption = lang === 'mermaid' ? '流程图' : '结构化流程图'
  try {
    const parsed = JSON.parse(code)
    caption = parsed.title || caption
  } catch {
    // Mermaid or incomplete JSON is still rendered as a chart placeholder.
  }
  return `<figure class="flowchart-placeholder"><div>流程图将在导出时渲染</div><figcaption>${renderInlineMarkdown(caption)}</figcaption></figure>`
}

function isTableDivider(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
}

function parseTableRow(line) {
  if (!line.trim().includes('|')) return null
  const cells = line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())
  return cells.length >= 2 ? cells : null
}

function normalizeTableCells(cells, colCount) {
  if (cells.length === colCount) return cells
  if (cells.length < colCount) return [...cells, ...Array(colCount - cells.length).fill('')]
  return [...cells.slice(0, colCount - 1), cells.slice(colCount - 1).join(' | ')]
}

function parseMarkdownTableBlock(markdown) {
  const tableLines = String(markdown || '').split('\n').filter(line => line.trim())
  if (tableLines.length < 2) return null
  const header = parseTableRow(tableLines[0])
  if (!header || !isTableDivider(tableLines[1])) return null
  const rows = []
  for (const line of tableLines.slice(2)) {
    if (isTableDivider(line)) continue
    const row = parseTableRow(line)
    if (row) rows.push(normalizeTableCells(row, header.length))
  }
  return { header, rows }
}

function tableCellDomSpec(cell) {
  const parts = String(cell || '').split(/<br\s*\/?>|\n/gi)
  const children = []
  parts.forEach((part, index) => {
    if (index > 0) children.push(['br'])
    children.push(part)
  })
  return children.length ? children : ['']
}

function markdownTableToDomSpec(markdown) {
  const parsed = parseMarkdownTableBlock(markdown)
  if (!parsed) {
    return ['div', { 'data-markdown-table': markdown }, markdown || '']
  }
  return [
    'div',
    { 'data-markdown-table': markdown },
    [
      'table',
      { class: 'md-table' },
      ['thead', ['tr', ...parsed.header.map(cell => ['th', ...tableCellDomSpec(cell)])]],
      ['tbody', ...parsed.rows.map(row => ['tr', ...row.map(cell => ['td', ...tableCellDomSpec(cell)])])],
    ],
  ]
}

function renderMarkdownTable(header, rows) {
  const colCount = header.length
  const normalizedRows = rows.map(row => normalizeTableCells(row, colCount))
  const markdown = [
    `| ${header.join(' | ')} |`,
    `| ${header.map(() => '---').join(' | ')} |`,
    ...normalizedRows.map(row => `| ${row.join(' | ')} |`),
  ].join('\n')
  return [
    `<div data-markdown-table="${escapeHtml(markdown)}">`,
    '<table class="md-table">',
    `<thead><tr>${header.map(cell => `<th>${renderInlineMarkdown(cell)}</th>`).join('')}</tr></thead>`,
    `<tbody>${normalizedRows.map(row => `<tr>${row.map(cell => `<td>${renderInlineMarkdown(cell)}</td>`).join('')}</tr>`).join('')}</tbody>`,
    '</table>',
    '</div>',
  ].join('')
}

function markdownToHtml(markdown) {
  const lines = String(markdown || '').split('\n')
  const html = []
  let paragraph = []
  let list = null
  let blockquote = []
  const flushParagraph = () => {
    if (!paragraph.length) return
    html.push(`<p>${paragraph.map(renderInlineMarkdown).join('<br>')}</p>`)
    paragraph = []
  }
  const flushList = () => {
    if (!list) return
    html.push(`<${list.type}>${list.items.map(item => `<li>${renderInlineMarkdown(item)}</li>`).join('')}</${list.type}>`)
    list = null
  }
  const flushBlockquote = () => {
    if (!blockquote.length) return
    html.push(`<blockquote>${blockquote.map(item => `<p>${renderInlineMarkdown(item)}</p>`).join('')}</blockquote>`)
    blockquote = []
  }
  const flushAll = () => {
    flushParagraph()
    flushList()
    flushBlockquote()
  }
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const flowchartFence = line.match(/^```(flowchart-json|flowchart|mermaid)\s*$/)
    if (flowchartFence) {
      flushAll()
      const chartLines = []
      index += 1
      while (index < lines.length && !lines[index].trim().startsWith('```')) {
        chartLines.push(lines[index])
        index += 1
      }
      html.push(renderFlowchartPlaceholder(chartLines.join('\n'), flowchartFence[1]))
      continue
    }

    const imagePlaceholder = renderImagePlaceholder(line)
    if (imagePlaceholder) {
      flushAll()
      html.push(imagePlaceholder)
      continue
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushAll()
      const level = Math.min(heading[1].length, 4)
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`)
      continue
    }

    const quote = line.match(/^>\s?(.*)$/)
    if (quote) {
      flushParagraph()
      flushList()
      blockquote.push(quote[1])
      continue
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/)
    if (unordered) {
      flushParagraph()
      flushBlockquote()
      if (!list || list.type !== 'ul') {
        flushList()
        list = { type: 'ul', items: [] }
      }
      list.items.push(unordered[1])
      continue
    }

    const ordered = line.match(/^\s*\d+[.)、]\s+(.+)$/)
    if (ordered) {
      flushParagraph()
      flushBlockquote()
      if (!list || list.type !== 'ol') {
        flushList()
        list = { type: 'ol', items: [] }
      }
      list.items.push(ordered[1])
      continue
    }

    const tableHeader = parseTableRow(line)
    if (tableHeader && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      flushAll()
      const rows = []
      index += 2
      while (index < lines.length) {
        const row = parseTableRow(lines[index])
        if (isTableDivider(lines[index])) {
          index += 1
          continue
        }
        if (!row) {
          index -= 1
          break
        }
        rows.push(row)
        index += 1
      }
      html.push(renderMarkdownTable(tableHeader, rows))
      continue
    }

    if (!line.trim()) {
      flushAll()
      continue
    }
    flushList()
    flushBlockquote()
    paragraph.push(line)
  }
  flushAll()
  return html.join('')
}

function nodeText(node) {
  if (!node) return ''
  if (node.type === 'text') return node.text || ''
  return (node.content || []).map(nodeText).join('')
}

function markdownTableNodeToMarkdown(node) {
  if (node.attrs?.markdown) return node.attrs.markdown
  const rows = []
  for (const row of node.content || []) {
    rows.push((row.content || []).map(nodeText))
  }
  if (!rows.length) return ''
  const header = rows[0]
  return [`| ${header.join(' | ')} |`, `| ${header.map(() => '---').join(' | ')} |`, ...rows.slice(1).map(row => `| ${row.join(' | ')} |`)].join('\n')
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
    } else if (node.type === 'markdownTable' || node.attrs?.markdown) {
      blocks.push(markdownTableNodeToMarkdown(node))
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
    const { data } = await v2Api.getWorkbench(activeProjectId.value)
    workbench.value = data || workbench.value
    chapters.value = data.chapters || []
    if (selectedChapter.value) {
      const freshSelected = chapters.value.find(item => item.id === selectedChapter.value.id)
      if (freshSelected) {
        selectedChapter.value = freshSelected
      } else {
        selectedChapter.value = null
      }
    }
    if (!selectedChapter.value && chapters.value.length) {
      await selectChapter(chapters.value[0])
    }
  } catch (error) {
    errorText.value = error.response?.data?.error || '章节加载失败'
  } finally {
    loadingChapters.value = false
  }
}

async function loadWorkbench() {
  await loadChapters()
}

async function selectChapter(chapter) {
  selectedChapter.value = chapter
  events.value = []
  currentTaskId.value = null
  await reloadEditor()
  await Promise.all([loadCitations(), loadImagePlans(), loadFollowups()])
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

async function loadImagePlans() {
  if (!selectedChapter.value) return
  try {
    const { data } = await v2Api.listImagePlans(selectedChapter.value.id)
    imagePlans.value = data.items || []
  } catch {
    imagePlans.value = []
  }
}

async function loadFollowups() {
  if (!selectedChapter.value) return
  try {
    const { data } = await v2Api.listFollowups(selectedChapter.value.id)
    followups.value = data.items || []
  } catch {
    followups.value = []
  }
}

async function saveDoc(options = {}) {
  if (!selectedChapter.value || !editor.value) return
  saving.value = true
  try {
    await v2Api.saveEditorDoc(selectedChapter.value.id, {
      markdown: editorJsonToMarkdown(editor.value.getJSON()),
      tiptapJson: editor.value.getJSON(),
    })
    if (!options.silent) {
      ElMessage.success('正文已保存')
    }
    await loadChapters()
  } catch (error) {
    errorText.value = error.response?.data?.error || '保存失败'
  } finally {
    saving.value = false
  }
}

async function generateChapter() {
  if (!selectedChapter.value || generating.value) return
  await runChapterGeneration(selectedChapter.value)
}

async function generateNextPendingChapter() {
  if (!nextPendingChapter.value || generating.value) return
  await selectChapter(nextPendingChapter.value)
  await runChapterGeneration(nextPendingChapter.value)
}

async function generateWholeProject() {
  if (projectRunning.value || generating.value) return
  projectRunning.value = true
  errorText.value = ''
  events.value = []
  currentTaskId.value = null
  try {
    const { data } = await v2Api.createProjectTask(activeProjectId.value, { includeExisting: false })
    currentTaskId.value = data.task.id
    await consumeProjectTaskStream(data.task.id)
    await loadWorkbench()
    if (canExportProject.value) {
      const exported = await runProjectExportTask()
      if (exported) {
        ElMessage.success('项目级顺序生成并导出 Word 已完成')
      }
    } else {
      ElMessage.success('项目级顺序生成已完成')
    }
  } catch (error) {
    errorText.value = error.response?.data?.error || error.message || '项目生成失败'
  } finally {
    projectRunning.value = false
  }
}

async function exportWholeProject() {
  if (exportingProject.value || generating.value || projectRunning.value) return
  await runProjectExportTask()
}

async function runProjectExportTask() {
  exportingProject.value = true
  errorText.value = ''
  events.value = []
  currentTaskId.value = null
  try {
    const { data } = await v2Api.createExportTask(activeProjectId.value)
    currentTaskId.value = data.task.id
    await consumeProjectTaskStream(data.task.id)
    await loadWorkbench()
    ElMessage.success('整本导出完成，可在在线编辑中查看 Word')
    return true
  } catch (error) {
    errorText.value = error.response?.data?.error || error.message || '项目导出失败'
    return false
  } finally {
    exportingProject.value = false
  }
}

async function runChapterGeneration(chapter) {
  generating.value = true
  errorText.value = ''
  events.value = []
  citations.value = []
  imagePlans.value = []
  followups.value = []
  setEditorMarkdown('')
  try {
    const { data } = await v2Api.createTask({
      taskType: 'chapter_generate',
      projectId: activeProjectId.value,
      chapterId: chapter.id,
    })
    currentTaskId.value = data.task.id
    await consumeTaskStream(data.task.id)
    await Promise.all([loadCitations(), loadImagePlans(), loadFollowups()])
    await loadWorkbench()
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
  const decoder = new TextDecoder('utf-8')
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
      } else if (event.type === 'image_plan') {
        imagePlans.value.push(event)
      } else if (event.type === 'followup') {
        followups.value.push(event)
      } else if (event.type === 'done') {
        scheduleMarkdownRender(true)
      } else if (event.type === 'error') {
        throw new Error(event.error || '生成任务失败')
      }
    }
  }
  scheduleMarkdownRender(true)
}

async function consumeProjectTaskStream(taskId) {
  const response = await fetch(v2Api.streamTaskUrl(taskId))
  if (!response.ok) {
    throw new Error('项目任务流连接失败')
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
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
      if (event.type === 'chapter_token') {
        if (!selectedChapter.value || selectedChapter.value.id !== event.chapterId) {
          const targetChapter = chapters.value.find(item => item.id === event.chapterId)
          if (targetChapter) {
            selectedChapter.value = targetChapter
            setEditorMarkdown('')
          }
        }
        if (selectedChapter.value?.id === event.chapterId) {
          appendToken(event.text || '')
          await nextTick()
        }
      } else if (event.type === 'chapter_done') {
        if (selectedChapter.value?.id === event.chapterId) {
          scheduleMarkdownRender(true)
          await Promise.all([loadCitations(), loadImagePlans(), loadFollowups()])
        }
        await loadWorkbench()
      } else if (event.type === 'export_done' || event.type === 'done') {
        scheduleMarkdownRender(true)
        await loadWorkbench()
      } else if (event.type === 'error' || event.type === 'chapter_error' || event.type === 'export_error') {
        throw new Error(event.error || '项目任务失败')
      }
    }
  }
  scheduleMarkdownRender(true)
}

watch(activeProjectId, () => loadWorkbench())

onMounted(async () => {
  await loadWorkbench()
  if (route.query.autostart === 'project-generate' && !autostartConsumed) {
    autostartConsumed = true
    await generateWholeProject()
  }
})

onBeforeUnmount(() => {
  if (renderTimer) clearTimeout(renderTimer)
  editor.value?.destroy()
})
</script>

<style scoped>
.workbench {
  display: grid;
  grid-template-columns: 260px minmax(420px, 1fr) 320px;
  grid-template-rows: auto minmax(640px, 1fr);
  align-items: start;
  gap: 16px;
  min-height: calc(100vh - 112px);
  overflow: hidden;
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
  height: 100%;
  min-height: 0;
  padding: 14px;
  overflow: hidden;
}

.panel-head,
.toolbar,
.overview-identity,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-head h3,
.section-title h3,
.overview-identity h3,
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

.overview-card {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(150px, 190px) minmax(240px, 340px) minmax(320px, 1fr) auto;
  align-items: center;
  column-gap: 18px;
  row-gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border: 1px solid #dfe7f2;
  border-radius: 10px;
  box-shadow: 0 8px 20px rgba(15, 23, 42, .045);
}

.overview-identity {
  justify-content: flex-start;
  padding-right: 12px;
  border-right: 1px solid #e5eaf2;
}

.overview-progress {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  margin-top: 0;
}

.progress-ring {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border-radius: 999px;
  background:
    conic-gradient(#2f7eea var(--progress), #e9eef6 0),
    #fff;
}

.progress-ring span {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  color: #111827;
  font-size: 13px;
  font-weight: 750;
  background: #fff;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px #e5eaf2;
}

.progress-copy {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  column-gap: 10px;
  row-gap: 6px;
  color: #475569;
  font-size: 13px;
}

.progress-copy strong {
  color: #0f172a;
  font-size: 24px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.progress-copy .el-progress {
  grid-column: 1 / -1;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin-top: 0;
}

.overview-metrics article {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2px;
  min-height: 48px;
  padding: 8px 10px;
  background: #f8fafc;
  border: 1px solid #edf2f7;
  border-radius: 8px;
}

.overview-metrics strong,
.overview-metrics span {
  display: inline;
}

.overview-metrics strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.overview-metrics span {
  color: #64748b;
  font-size: 12px;
}

.volume-pills {
  grid-column: 2 / 4;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 0;
}

.volume-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 9px;
  color: #1d4ed8;
  font-size: 12px;
  background: rgba(219, 234, 254, .82);
  border-radius: 999px;
}

.overview-actions {
  grid-column: 4;
  grid-row: 1 / span 2;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  align-content: center;
  margin-top: 0;
  max-width: 430px;
}

.overview-actions :deep(.el-button) {
  min-height: 32px;
  margin-left: 0;
  border-radius: 7px;
}

.chapter-filter {
  width: 112px;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
  max-height: calc(100% - 58px);
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

.chapter-stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
  color: #64748b;
  font-size: 12px;
}

.warn-text {
  color: #b45309;
  font-weight: 600;
}

.editor-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  height: 100%;
  min-height: 0;
}

.toolbar {
  position: sticky;
  top: 0;
  z-index: 3;
  padding: 14px 16px;
  background: #fff;
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
  position: relative;
  flex: 1;
  min-height: 0;
  padding: 16px;
  overflow: auto;
}

.floating-actions {
  position: sticky;
  top: 0;
  z-index: 4;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  margin: -16px -16px 12px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, .94);
  border-bottom: 1px solid #e5e7eb;
  backdrop-filter: blur(8px);
}

.selection-toolbar {
  position: absolute;
  z-index: 8;
  padding: 4px;
  background: #111827;
  border-radius: 8px;
  box-shadow: 0 10px 24px rgba(15, 23, 42, .22);
}

.selection-toolbar :deep(.el-button) {
  color: #fff;
  background: transparent;
  border-color: transparent;
}

.inline-rewrite-card {
  position: absolute;
  z-index: 9;
  width: min(380px, calc(100% - 32px));
  padding: 12px;
  background: #fff;
  border: 1px solid #dbe4f0;
  border-radius: 8px;
  box-shadow: 0 18px 40px rgba(15, 23, 42, .18);
}

.inline-rewrite-head,
.inline-rewrite-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.inline-rewrite-head {
  margin-bottom: 8px;
  color: #111827;
}

.rewrite-suggestion {
  margin-top: 8px;
}

.inline-rewrite-actions {
  justify-content: flex-end;
  margin-top: 10px;
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

:deep(.tiptap-content h1),
:deep(.tiptap-content h2),
:deep(.tiptap-content h3),
:deep(.tiptap-content h4) {
  margin: 18px 0 10px;
  color: #111827;
  font-weight: 700;
  line-height: 1.35;
}

:deep(.tiptap-content h1) {
  font-size: 24px;
}

:deep(.tiptap-content h2) {
  font-size: 22px;
}

:deep(.tiptap-content h3) {
  font-size: 19px;
}

:deep(.tiptap-content h4) {
  font-size: 16px;
}

:deep(.tiptap-content ul),
:deep(.tiptap-content ol) {
  margin: 0 0 12px 22px;
  padding: 0;
}

:deep(.tiptap-content li) {
  margin: 4px 0;
}

:deep(.tiptap-content blockquote) {
  margin: 12px 0;
  padding: 8px 12px;
  color: #4b5563;
  background: #f8fafc;
  border-left: 3px solid #94a3b8;
}

:deep(.tiptap-content [data-markdown-table]) {
  margin: 14px 0 18px;
  overflow-x: auto;
}

:deep(.tiptap-content table.md-table) {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  background: #fff;
}

:deep(.tiptap-content table.md-table th),
:deep(.tiptap-content table.md-table td) {
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  vertical-align: top;
  color: #111827;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

:deep(.tiptap-content table.md-table th) {
  text-align: center;
  font-weight: 700;
  background: #f1f5f9;
}

:deep(.tiptap-content code) {
  padding: 2px 5px;
  color: #334155;
  background: #eef2f7;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: .92em;
}

:deep(.tiptap-content .image-plan-placeholder) {
  margin: 16px 0;
  padding: 18px;
  text-align: center;
  color: #475569;
  background: #f8fafc;
  border: 1px dashed #94a3b8;
  border-radius: 8px;
}

:deep(.tiptap-content .image-plan-placeholder div) {
  font-size: 13px;
  font-weight: 700;
}

:deep(.tiptap-content .image-plan-placeholder figcaption) {
  margin-top: 8px;
  color: #111827;
  font-size: 13px;
}

:deep(.tiptap-content .flowchart-placeholder) {
  margin: 16px 0;
  padding: 18px;
  text-align: center;
  color: #475569;
  background: #f8fbff;
  border: 1px dashed #60a5fa;
  border-radius: 8px;
}

:deep(.tiptap-content .flowchart-placeholder div) {
  font-size: 13px;
  font-weight: 700;
}

:deep(.tiptap-content .flowchart-placeholder figcaption) {
  margin-top: 8px;
  color: #111827;
  font-size: 13px;
}

.inspector-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
}

.inspector-section {
  flex: 0 0 auto;
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
  min-height: 44px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.6;
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
.citation-item p,
.plan-item p,
.followup-item p {
  margin: 4px 0 0;
  color: #4b5563;
  font-size: 13px;
  line-height: 1.65;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.citation-list,
.plan-list,
.followup-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 220px;
  overflow-y: auto;
}

.citation-item,
.plan-item,
.followup-item {
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #edf2f7;
  border-radius: 8px;
}

.citation-item strong,
.plan-item strong {
  display: inline-block;
  margin-right: 8px;
  color: #111827;
}

.citation-item span {
  color: #374151;
  font-size: 13px;
}

.plan-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.plan-item span {
  display: block;
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
}

@media (max-width: 1180px) {
  .workbench {
    grid-template-columns: 220px minmax(360px, 1fr);
    height: auto;
    overflow: visible;
  }

  .overview-card {
    grid-template-columns: 1fr;
  }

  .overview-actions,
  .volume-pills {
    grid-column: auto;
    grid-row: auto;
    justify-content: flex-start;
    max-width: none;
  }

  .overview-identity {
    border-right: none;
    padding-right: 0;
  }

  .inspector-panel {
    grid-column: 1 / -1;
    height: auto;
  }
}

@media (max-width: 860px) {
  .workbench {
    grid-template-columns: 1fr;
  }

  .chapter-panel,
  .inspector-panel {
    height: auto;
  }

  .overview-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chapter-list,
  .event-list,
  .citation-list,
  .plan-list,
  .followup-list {
    max-height: none;
  }
}
</style>
