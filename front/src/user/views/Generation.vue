<template>
  <div>
    <el-steps :active="step" finish-status="success" align-center class="gen-steps">
      <el-step title="预分析" />
      <el-step title="确认事实" />
      <el-step title="格式要求" />
      <el-step title="设计目录" />
      <el-step title="生成文档" />
    </el-steps>

    <div class="step-content" v-if="step === 0">
      <el-button type="primary" :loading="loading" @click="runPreAnalysis">开始预分析</el-button>
      <p class="hint">系统将解析招标文件，提取项目事实、格式要求和评分标准</p>
    </div>

    <div class="step-content" v-if="step === 1">
      <h3>请确认以下项目事实</h3>
      <el-table :data="facts" stripe>
        <el-table-column prop="factLabel" label="事实项" width="160" />
        <el-table-column label="值">
          <template #default="{ row }">
            <el-input v-model="row.factValue" size="small" />
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="90">
          <template #default="{ row }">
            <el-progress :percentage="Math.round((row.confidence || 0) * 100)" :stroke-width="6" :show-text="false" />
          </template>
        </el-table-column>
      </el-table>
      <el-button type="primary" class="mt16" @click="confirmFacts" :loading="loading">确认事实并继续</el-button>
    </div>

    <div class="step-content" v-if="step === 2">
      <h3>投标文件格式要求</h3>
      <div class="format-switch">
        <el-switch v-model="useFormatRequirements" active-text="严格按照招标文件响应格式生成" inactive-text="由AI自由设计章节结构" />
        <p class="hint" v-if="useFormatRequirements">开启后，目录设计将严格遵循招标文件中规定的投标文件格式要求</p>
        <p class="hint" v-else>关闭后，AI将根据招标内容自主设计最优章节结构</p>
      </div>

      <template v-if="useFormatRequirements">
      <p class="hint">以下是从招标文件中提取的投标文件章节格式要求，请确认或修改。目录设计将严格遵循这些要求。</p>

      <el-card shadow="never" class="format-card" v-if="formatRequirements.document_composition">
        <template #header><span>投标文件组成</span></template>
        <el-input v-model="formatRequirements.document_composition" type="textarea" :rows="2" />
      </el-card>

      <el-card shadow="never" class="format-card">
        <template #header>
          <div class="card-header-row">
            <span>必须包含的章节（{{ formatRequirements.required_chapters?.length || 0 }} 项）</span>
            <el-button type="primary" size="small" @click="addChapter">+ 添加章节</el-button>
          </div>
        </template>
        <div v-for="(ch, idx) in formatRequirements.required_chapters" :key="idx" class="chapter-item">
          <el-row :gutter="12" align="middle">
            <el-col :span="8">
              <el-input v-model="ch.title" placeholder="章节标题" size="small" />
            </el-col>
            <el-col :span="12">
              <el-input v-model="ch.description" placeholder="要求说明" size="small" />
            </el-col>
            <el-col :span="2">
              <el-checkbox v-model="ch.is_mandatory" label="必选" size="small" />
            </el-col>
            <el-col :span="2">
              <el-button type="danger" link size="small" @click="removeChapter(idx)">删除</el-button>
            </el-col>
          </el-row>
        </div>
      </el-card>

      <el-card shadow="never" class="format-card">
        <template #header>
          <div class="card-header-row">
            <span>封面格式</span>
            <el-button type="primary" size="small" @click="addCoverLine">+ 添加行</el-button>
          </div>
        </template>
        <div class="cover-preview">
          <div v-for="(line, idx) in coverLines" :key="idx" class="cover-line-item">
            <el-row :gutter="8" align="middle">
              <el-col :span="10">
                <el-input v-model="line.text" placeholder="封面文字" size="small" />
              </el-col>
              <el-col :span="5">
                <el-select v-model="line.style" size="small" placeholder="样式">
                  <el-option label="大标题" value="title" />
                  <el-option label="副标题" value="subtitle" />
                  <el-option label="正文" value="normal" />
                </el-select>
              </el-col>
              <el-col :span="6">
                <el-select v-model="line.placeholder" size="small" placeholder="自动填充">
                  <el-option label="不自动填充" value="none" />
                  <el-option label="项目名称" value="project_name" />
                  <el-option label="投标人名称" value="bidder_name" />
                  <el-option label="招标编号" value="tender_no" />
                  <el-option label="投标日期" value="bid_date" />
                  <el-option label="采购人" value="purchaser_name" />
                </el-select>
              </el-col>
              <el-col :span="3">
                <el-button type="danger" link size="small" @click="coverLines.splice(idx, 1)">删除</el-button>
              </el-col>
            </el-row>
          </div>
          <el-input v-model="coverNotes" placeholder="封面备注（如：需加盖公章、密封等）" size="small" class="mt8" />
        </div>
      </el-card>

      <el-card shadow="never" class="format-card" v-if="formatRequirements.format_notes?.length">
        <template #header><span>格式注意事项</span></template>
        <el-tag v-for="(note, idx) in formatRequirements.format_notes" :key="idx" class="format-tag" closable @close="formatRequirements.format_notes.splice(idx, 1)">
          {{ note }}
        </el-tag>
      </el-card>
      </template>

      <el-button type="primary" class="mt16" @click="confirmFormat">确认格式要求，设计目录</el-button>
    </div>

    <div class="step-content" v-if="step === 3">
      <el-button type="primary" :loading="loading" @click="runChapterDesign">生成目录结构</el-button>
      <div v-if="outline" class="outline-preview">
        <h4>目录预览（{{ outlineTree.length }} 个一级章节）</h4>
        <el-alert
          v-if="outline.needsReview"
          type="warning"
          show-icon
          :closable="false"
          title="未识别到固定投标文件格式，请确认目录后再生成。"
        />
        <div v-if="outline.questions?.length" class="outline-questions">
          <el-tag v-for="(question, idx) in outline.questions" :key="idx" type="warning">
            {{ question }}
          </el-tag>
        </div>
        <el-tree :data="outlineTree" default-expand-all :props="{ label: 'label', children: 'children' }" />
        <div v-if="sourceChapters.length" class="source-snippets">
          <h4>格式来源</h4>
          <el-collapse>
            <el-collapse-item
              v-for="(ch, idx) in sourceChapters"
              :key="idx"
              :title="`${ch.title} - ${ch.sourceHeading || '招标文件'}`"
            >
              <pre>{{ ch.sourceText }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-button
          type="primary"
          class="mt16"
          :disabled="outline.needsReview || hasTemplateIssues || !outline.chapters?.length"
          @click="step = 4"
        >
          确认目录，开始生成
        </el-button>
      </div>
    </div>

    <div class="step-content" v-if="step === 4">
      <el-button type="success" size="large" :loading="loading" @click="runGenerate" v-if="!result && !loading">
        <el-icon><Document /></el-icon> 生成投标文档
      </el-button>
      <div v-if="loading && !result" class="generating-hint">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <p>{{ progressText }}</p>
        <el-progress v-if="progressTotal > 0" :percentage="Math.round(progressCurrent / progressTotal * 100)" :stroke-width="10" style="width: 300px;" />
        <p class="sub-hint">系统正在逐章生成内容，请勿关闭页面</p>
      </div>
      <div v-if="result" class="result-panel">
        <el-result icon="success" title="投标文档生成完成" :sub-title="`风险等级: ${result.reviewReport?.riskLevel || '低'}`">
          <template #extra>
            <el-button type="primary" @click="downloadWord" v-if="result.fileUrl">
              <el-icon><Download /></el-icon> 下载 Word 文档
            </el-button>
            <el-button @click="$router.push(`/project/${projectId}/editor`)">在线编辑</el-button>
          </template>
        </el-result>
        <el-divider />
        <div v-if="scoringReport" class="scoring-panel">
          <h4>评分点覆盖检查</h4>
          <el-progress :percentage="scoringReport.coverage_rate" :stroke-width="14" :format="() => `${scoringReport.coverage_rate}%`" />
          <p class="scoring-summary">共 {{ scoringReport.total }} 项评分点，已覆盖 {{ scoringReport.covered }} 项，未覆盖 {{ scoringReport.missing_count }} 项</p>
          <el-alert v-if="scoringReport.missing_items?.length" type="warning" :closable="false" style="margin-top: 8px;">
            <template #title>未覆盖的评分点：</template>
            <ul class="missing-list">
              <li v-for="(item, i) in scoringReport.missing_items" :key="i">{{ item }}</li>
            </ul>
          </el-alert>
        </div>
        <el-divider v-if="scoringReport" />
        <h4>文档下载</h4>
        <div class="doc-preview" v-if="result.wordFileId">
          <iframe :src="`/api/files/${result.wordFileId}/preview`" class="preview-frame" />
        </div>
        <div class="doc-preview" v-else-if="result.fileUrl">
          <el-link :href="result.fileUrl" type="primary" target="_blank">点击下载查看文档</el-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Document, Loading } from '@element-plus/icons-vue'
import { biddingApi, projectApi } from '@/shared/api.js'

const props = defineProps({ projectId: Number, biddingId: Number })
const step = ref(0)
const loading = ref(false)
const facts = ref([])
const formatRequirements = ref({ required_chapters: [], format_notes: [], document_composition: '' })
const useFormatRequirements = ref(true)
const coverLines = ref([])
const coverNotes = ref('')
const outline = ref(null)
const result = ref(null)
const progressText = ref('')
const progressCurrent = ref(0)
const progressTotal = ref(0)
const scoringReport = ref(null)

onMounted(async () => { await restoreState() })

async function restoreState() {
  try {
    const { data: proj } = await projectApi.get(props.projectId)
    const status = proj.project_status

    if (status === 'completed' && proj.biddingStatus === 'Generated') {
      const fileId = proj.generated_file_id || proj.biddingId
      result.value = {
        fileUrl: `/api/files/${fileId}/download`,
        wordFileId: fileId,
        bidDocumentId: proj.bidDocumentId,
      }
      step.value = 4
      return
    }

    if (status === 'analyzing' || status === 'generating') {
      const { data: factsData } = await projectApi.getFacts(props.projectId)
      facts.value = factsData.items || []
      if (facts.value.some(f => f.status === 'confirmed')) {
        step.value = 2
      } else if (facts.value.length > 0) {
        step.value = 1
      }
      return
    }
  } catch { /* start from step 0 */ }
}

const typeLabel = (type) => {
  if (type === 'locked_template') return '模板锁定'
  if (type === 'locked_outline') return '目录锁定'
  if (type === 'free_content') return '自由内容'
  if (type === 'table') return '模板表单'
  return type || '未分类'
}

const sourceChapters = computed(() => {
  if (!outline.value?.chapters) return []
  return outline.value.chapters.filter(ch => ch.sourceText)
})

const hasTemplateIssues = computed(() => {
  if (!outline.value?.chapters) return false
  return outline.value.chapters.some(ch => ['toc_only', 'missing'].includes(ch.templateStatus))
})

const outlineTree = computed(() => {
  if (!outline.value?.chapters) return []
  return outline.value.chapters.map(ch => ({
    label: `${ch.title}（${typeLabel(ch.type)}${ch.templateStatus ? `｜模板:${ch.templateStatus}` : ''}${ch.lockTitle ? '｜标题锁定' : ''}${ch.sourceHeading ? `｜${ch.sourceHeading}` : ''}${ch.target_words ? `｜${ch.target_words}字` : ''}）`,
    children: (ch.sections || []).map(s => ({
      label: s.title,
      children: (s.subsections || []).map(sub => ({
        label: sub.title + (sub.describe ? ` — ${sub.describe}` : '')
      }))
    }))
  }))
})

async function runPreAnalysis() {
  loading.value = true
  try {
    const { data: analysisResult } = await biddingApi.preAnalysis(props.biddingId)
    const { data: factsData } = await projectApi.getFacts(props.projectId)
    facts.value = factsData.items || []

    if (analysisResult.bid_document_format) {
      formatRequirements.value = {
        required_chapters: analysisResult.bid_document_format.required_chapters || [],
        format_notes: analysisResult.bid_document_format.format_notes || [],
        document_composition: analysisResult.bid_document_format.document_composition || '',
      }
      const cover = analysisResult.bid_document_format.cover_page
      if (cover && cover.cover_lines) {
        coverLines.value = cover.cover_lines
        coverNotes.value = cover.cover_notes || ''
      } else {
        coverLines.value = [
          { text: '投 标 文 件', style: 'title', placeholder: 'none' },
          { text: '', style: 'subtitle', placeholder: 'project_name' },
          { text: '', style: 'normal', placeholder: 'bidder_name' },
          { text: '', style: 'normal', placeholder: 'bid_date' },
        ]
      }
    }

    step.value = 1
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '预分析失败')
  } finally { loading.value = false }
}

async function confirmFacts() {
  loading.value = true
  try {
    const payload = facts.value.map(f => ({ factKey: f.factKey, factValue: f.factValue, status: 'confirmed' }))
    await projectApi.confirmFacts(props.projectId, payload)
    ElMessage.success('事实已确认')
    step.value = 2
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '确认失败')
  } finally { loading.value = false }
}

function addChapter() {
  formatRequirements.value.required_chapters.push({ title: '', description: '', is_mandatory: true })
}

function removeChapter(idx) {
  formatRequirements.value.required_chapters.splice(idx, 1)
}

function addCoverLine() {
  coverLines.value.push({ text: '', style: 'normal', placeholder: 'none' })
}

function confirmFormat() {
  formatRequirements.value.cover_page = {
    has_cover_requirement: coverLines.value.length > 0,
    cover_lines: coverLines.value,
    cover_notes: coverNotes.value,
  }
  ElMessage.success('格式要求已确认')
  step.value = 3
}

async function runChapterDesign() {
  loading.value = true
  try {
    const reqs = useFormatRequirements.value ? formatRequirements.value : null
    const { data } = await biddingApi.chapterDesign(props.biddingId, reqs)
    outline.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '目录设计失败')
  } finally { loading.value = false }
}

async function runGenerate() {
  if (outline.value?.needsReview || hasTemplateIssues.value || !outline.value?.chapters?.length) {
    ElMessage.warning('请先确认有效目录后再生成')
    return
  }
  loading.value = true
  progressText.value = '正在启动生成任务...'
  progressCurrent.value = 0
  progressTotal.value = 0
  try {
    const response = await biddingApi.generateSSE(props.biddingId, outline.value)
    if (!response.ok) {
      const err = await response.json()
      const blockers = (err.templateBlockers || []).map(item => `${item.title}: ${item.reason}`).join('；')
      ElMessage.error(blockers ? `${err.error || '生成失败'} ${blockers}` : (err.error || '生成失败'))
      loading.value = false
      return
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
        try {
          const msg = JSON.parse(line.slice(6))
          if (msg.type === 'start') {
            progressTotal.value = msg.total
            progressText.value = `共 ${msg.total} 个章节，开始生成...`
          } else if (msg.type === 'progress') {
            progressCurrent.value = msg.current
            progressTotal.value = msg.total
            progressText.value = `正在生成 (${msg.current}/${msg.total}): ${msg.chapter}`
          } else if (msg.type === 'done') {
            result.value = msg
            ElMessage.success('投标文档生成完成')
          } else if (msg.type === 'scoring') {
            scoringReport.value = msg.report
          } else if (msg.type === 'error') {
            ElMessage.error(msg.error || '生成过程出错')
          }
        } catch { /* skip malformed lines */ }
      }
    }
  } catch (e) {
    ElMessage.error('网络连接中断，请刷新页面查看结果')
  } finally {
    loading.value = false
  }
}

function downloadWord() {
  if (result.value?.fileUrl) {
    window.open(result.value.fileUrl, '_blank')
  }
}
</script>

<style scoped>
.gen-steps { margin-bottom: 32px; }
.step-content { padding: 20px 0; }
.hint { color: #718096; margin-top: 8px; font-size: 13px; }
.outline-preview { margin-top: 16px; }
.outline-questions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.source-snippets { margin-top: 16px; }
.source-snippets pre { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.6; color: #334155; }
.mt16 { margin-top: 16px; }
.result-panel { margin-top: 16px; }
.generating-hint { display: flex; flex-direction: column; align-items: center; padding: 40px 0; gap: 12px; }
.generating-hint p { margin: 0; font-size: 15px; color: #4a5568; }
.generating-hint .sub-hint { font-size: 13px; color: #a0aec0; }
.doc-preview { margin-top: 16px; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; min-height: 200px; }
.preview-frame { width: 100%; height: 600px; border: none; border-radius: 4px; }
.scoring-panel { margin-top: 8px; }
.scoring-summary { font-size: 13px; color: #718096; margin-top: 8px; }
.missing-list { margin: 8px 0 0; padding-left: 20px; font-size: 13px; }
.missing-list li { margin: 4px 0; }
.format-card { margin-bottom: 12px; border-radius: 8px; }
.format-switch { margin-bottom: 16px; padding: 12px 16px; background: #f7fafc; border-radius: 8px; }
.card-header-row { display: flex; justify-content: space-between; align-items: center; }
.chapter-item { margin-bottom: 8px; }
.format-tag { margin: 4px 6px 4px 0; }
.cover-preview { padding: 8px 0; }
.cover-line-item { margin-bottom: 8px; }
.mt8 { margin-top: 8px; }
</style>
