<template>
  <div class="workbench">
    <aside class="chapter-panel">
      <section class="overview-card">
        <div class="panel-head">
          <div>
            <p class="eyebrow">V2 P0</p>
            <h3>项目总览</h3>
          </div>
          <el-tag size="small" :type="overviewTagType">{{ workbench.project?.projectStatus || 'draft' }}</el-tag>
        </div>
        <div class="overview-progress">
          <div class="progress-copy">
            <strong>{{ workbench.chapterStatus?.generated || 0 }}/{{ workbench.chapterStatus?.total || 0 }}</strong>
            <span>章节已形成正文</span>
          </div>
          <el-progress :percentage="Number(workbench.chapterStatus?.progressPercent || 0)" :stroke-width="10" />
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
        <div v-if="workbench.volumes?.length" class="volume-pills">
          <span v-for="volume in workbench.volumes" :key="volume.volumeType" class="volume-pill">
            {{ volumeName(volume.volumeType) }} {{ volume.generatedCount }}/{{ volume.chapterCount }}
          </span>
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
      </section>

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
import { DocumentChecked, Refresh, VideoPlay } from '@element-plus/icons-vue'
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
const workbench = ref({
  project: null,
  chapterStatus: { total: 0, generated: 0, pending: 0, progressPercent: 0 },
  stats: { citationCount: 0, imagePlanCount: 0, followupCount: 0, pendingFollowupCount: 0, pendingImagePlanCount: 0 },
  volumes: [],
  chapters: [],
  recentTasks: [],
})
let renderTimer = null

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
    ElMessage.success('项目级顺序生成已完成')
  } catch (error) {
    errorText.value = error.response?.data?.error || error.message || '项目生成失败'
  } finally {
    projectRunning.value = false
  }
}

async function exportWholeProject() {
  if (exportingProject.value || generating.value || projectRunning.value) return
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
  } catch (error) {
    errorText.value = error.response?.data?.error || error.message || '项目导出失败'
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

onMounted(loadWorkbench)

onBeforeUnmount(() => {
  if (renderTimer) clearTimeout(renderTimer)
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

.overview-card {
  margin-bottom: 16px;
  padding: 14px;
  background: linear-gradient(180deg, #f8fbff 0%, #fdfefe 100%);
  border: 1px solid #dbeafe;
  border-radius: 12px;
}

.overview-progress {
  margin-top: 14px;
}

.progress-copy {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
  color: #475569;
  font-size: 13px;
}

.progress-copy strong {
  color: #0f172a;
  font-size: 22px;
}

.overview-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.overview-metrics article {
  padding: 10px;
  background: rgba(255, 255, 255, .78);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
}

.overview-metrics strong,
.overview-metrics span {
  display: block;
}

.overview-metrics strong {
  color: #0f172a;
  font-size: 18px;
  font-weight: 700;
}

.overview-metrics span {
  margin-top: 4px;
  color: #64748b;
  font-size: 12px;
}

.volume-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.volume-pill {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  color: #1d4ed8;
  font-size: 12px;
  background: #eff6ff;
  border-radius: 999px;
}

.overview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.chapter-filter {
  width: 112px;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 14px;
  max-height: calc(100vh - 470px);
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
.citation-item p,
.plan-item p,
.followup-item p {
  margin: 4px 0 0;
  color: #4b5563;
  font-size: 13px;
  line-height: 1.5;
}

.citation-list,
.plan-list,
.followup-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 300px;
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

@media (max-width: 1100px) {
  .workbench {
    grid-template-columns: 1fr;
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
