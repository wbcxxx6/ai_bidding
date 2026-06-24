<template>
  <div class="knowledge-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Knowledge Center</p>
        <h2>知识中心</h2>
      </div>
      <el-button type="primary" @click="openCreate">创建知识库</el-button>
    </div>

    <el-tabs v-model="activeType" class="knowledge-tabs">
      <el-tab-pane v-for="entry in entries" :key="entry.type" :label="entry.label" :name="entry.type">
        <section class="entry-summary">
          <div>
            <h3>{{ entry.label }}</h3>
            <p>{{ entry.description }}</p>
          </div>
          <el-tag>{{ filteredKbs(entry.type).length }} 个知识库</el-tag>
        </section>

        <section v-if="entry.type === 'image_asset'" class="image-assets">
          <div class="section-head">
            <h3>图片资产</h3>
            <el-button type="primary" plain @click="showImageAssetDialog = true">登记图片资产</el-button>
          </div>
          <el-table :data="imageAssets" stripe>
            <el-table-column prop="assetTitle" label="标题" min-width="180" />
            <el-table-column prop="imageType" label="图片类型" width="150" />
            <el-table-column prop="sourceType" label="来源" width="150" />
            <el-table-column label="状态" width="130">
              <template #default="{ row }">
                <el-tag :type="row.allowedForBid ? 'success' : 'info'">{{ row.reviewStatus }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="caption" label="说明" min-width="220" />
          </el-table>
        </section>

        <el-empty v-if="entry.type !== 'image_asset' && !filteredKbs(entry.type).length" description="暂无知识库" />
        <el-table v-else-if="entry.type !== 'image_asset'" :data="filteredKbs(entry.type)" stripe>
          <el-table-column prop="kbName" label="名称" min-width="180" />
          <el-table-column label="类型" width="130">
            <template #default="{ row }">
              <el-tag>{{ entryLabel(row.kbType) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="220" />
          <el-table-column label="处理进度" min-width="240">
            <template #default="{ row }">
              <div class="progress-cell">
                <div class="progress-line">
                  <span>{{ row.documentCount || 0 }} 个文件</span>
                  <span>{{ row.chunkCount || 0 }} 个切片</span>
                </div>
                <div class="status-tags">
                  <el-tag size="small" :type="statusTagType(row.processSummary?.parseStatus)">
                    解析{{ statusLabel(row.processSummary?.parseStatus) }}
                  </el-tag>
                  <el-tag size="small" :type="statusTagType(row.processSummary?.vectorStatus)">
                    向量{{ statusLabel(row.processSummary?.vectorStatus) }}
                  </el-tag>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="visibilityScope" label="可见范围" width="120" />
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">查看文件</el-button>
              <el-upload
                :show-file-list="false"
                :before-upload="(file) => uploadDoc(row.id, file, entry.docType)"
                accept=".pdf,.doc,.docx,.txt,.md"
              >
                <el-button link type="primary">上传{{ entry.uploadLabel }}</el-button>
              </el-upload>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showCreate" title="创建知识库" width="460px">
      <el-form :model="form" label-width="96px">
        <el-form-item label="入口类型">
          <el-select v-model="form.type">
            <el-option
              v-for="entry in documentEntries"
              :key="entry.type"
              :label="entry.label"
              :value="entry.type"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="createKb">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showImageAssetDialog" title="登记图片资产" width="520px">
      <el-form :model="imageForm" label-width="96px">
        <el-form-item label="标题"><el-input v-model="imageForm.assetTitle" /></el-form-item>
        <el-form-item label="图片类型">
          <el-select v-model="imageForm.imageType">
            <el-option label="产品图片" value="product_image" />
            <el-option label="架构图" value="architecture_diagram" />
            <el-option label="流程图" value="process_diagram" />
            <el-option label="组织架构图" value="org_chart" />
            <el-option label="证书图片" value="certificate_image" />
            <el-option label="项目案例图片" value="case_image" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="imageForm.sourceType">
            <el-option label="企业上传" value="enterprise_upload" />
            <el-option label="历史标书" value="history_bid" />
            <el-option label="AI 生成" value="ai_generated" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="imageForm.caption" type="textarea" /></el-form-item>
        <el-form-item label="检索文本"><el-input v-model="imageForm.searchableText" type="textarea" /></el-form-item>
        <el-form-item label="允许投标">
          <el-switch v-model="imageForm.allowedForBid" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showImageAssetDialog = false">取消</el-button>
        <el-button type="primary" :loading="creatingImageAsset" @click="createImageAsset">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="showDetail" :title="detailTitle" size="62%" destroy-on-close>
      <div v-loading="detailLoading" class="kb-detail">
        <section v-if="selectedKb" class="detail-summary">
          <div>
            <p class="eyebrow">Pipeline</p>
            <h3>{{ selectedKb.kbName }}</h3>
            <p>{{ selectedKb.description || '暂无说明' }}</p>
          </div>
          <div class="summary-metrics">
            <div>
              <strong>{{ detailSummary.documentCount || 0 }}</strong>
              <span>文件</span>
            </div>
            <div>
              <strong>{{ detailSummary.chunkCount || 0 }}</strong>
              <span>切片</span>
            </div>
            <div>
              <strong>{{ detailSummary.vectorizedCount || 0 }}</strong>
              <span>已向量化</span>
            </div>
          </div>
        </section>

        <el-empty v-if="!detailLoading && !detailDocuments.length" description="该知识库暂无文件" />
        <el-table v-else :data="detailDocuments" stripe>
          <el-table-column label="文件" min-width="220">
            <template #default="{ row }">
              <div class="file-title">
                <strong>{{ row.docTitle || row.originalFilename }}</strong>
                <span>{{ row.originalFilename }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="130">
            <template #default="{ row }">
              <el-tag>{{ entryLabel(row.docType) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="处理步骤" min-width="320">
            <template #default="{ row }">
              <el-steps :active="activeStep(row.pipelineSteps)" finish-status="success" align-center>
                <el-step
                  v-for="step in row.pipelineSteps"
                  :key="step.key"
                  :title="step.label"
                  :status="step.status"
                />
              </el-steps>
            </template>
          </el-table-column>
          <el-table-column label="切片" width="90" align="center">
            <template #default="{ row }">{{ row.chunkCount || 0 }}</template>
          </el-table-column>
          <el-table-column label="模型" min-width="150">
            <template #default="{ row }">{{ row.embeddingModel || '-' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.vectorStatus === 'indexed' ? 'success' : row.vectorStatus)">
                {{ documentStatusText(row) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="openChunks(row)">查看切片</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>

    <el-drawer v-model="showChunks" :title="chunkTitle" size="50%" destroy-on-close>
      <div v-loading="chunkLoading" class="chunk-list">
        <el-empty v-if="!chunkLoading && !chunks.length" description="暂无切片" />
        <article v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
          <header>
            <strong>#{{ chunk.chunkIndex + 1 }}</strong>
            <el-tag size="small" :type="chunk.status === 'indexed' ? 'success' : 'info'">{{ chunk.status }}</el-tag>
          </header>
          <p>{{ chunk.preview }}</p>
        </article>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi, v2Api } from '@/shared/api.js'

const entries = [
  {
    type: 'company_profile',
    label: '企业资信',
    uploadLabel: '资信文件',
    docType: 'company_profile',
    description: '维护企业简介、资质证书、人员证明、业绩证明、信誉承诺等可引用资料。',
  },
  {
    type: 'product_library',
    label: '产品',
    uploadLabel: '产品资料',
    docType: 'product_library',
    description: '维护产品介绍、技术参数、方案资料、产品图片说明和适用场景。',
  },
  {
    type: 'history_bid',
    label: '历史标书',
    uploadLabel: '历史标书',
    docType: 'history_bid',
    description: '沉淀历史投标文件、章节结构、项目案例和可复用表达。',
  },
  {
    type: 'image_asset',
    label: '图片资产',
    uploadLabel: '图片资产',
    docType: 'image_asset',
    description: '维护产品图、架构图、流程图、证书图、案例图等可插入投标文件的图片资产。',
  },
]

const documentEntries = computed(() => entries.filter(entry => entry.type !== 'image_asset'))
const activeType = ref('company_profile')
const kbs = ref([])
const imageAssets = ref([])
const showCreate = ref(false)
const showImageAssetDialog = ref(false)
const creating = ref(false)
const creatingImageAsset = ref(false)
const showDetail = ref(false)
const detailLoading = ref(false)
const selectedKb = ref(null)
const detailSummary = ref({})
const detailDocuments = ref([])
const showChunks = ref(false)
const chunkLoading = ref(false)
const selectedDocument = ref(null)
const chunks = ref([])
const form = ref({ name: '', type: 'company_profile', description: '' })
const imageForm = ref({
  assetTitle: '',
  imageType: 'product_image',
  sourceType: 'enterprise_upload',
  caption: '',
  searchableText: '',
  allowedForBid: true,
})

onMounted(async () => {
  await Promise.all([loadKbs(), loadImageAssets()])
})

function normalizeKb(row) {
  return {
    ...row,
    kbName: row.kbName || row.kb_name,
    kbType: row.kbType || row.kb_type,
    visibilityScope: row.visibilityScope || row.visibility_scope,
    documentCount: row.documentCount || row.document_count || 0,
    chunkCount: row.chunkCount || row.chunk_count || 0,
    processSummary: row.processSummary || row.process_summary || {},
  }
}

const detailTitle = computed(() => selectedKb.value ? `${selectedKb.value.kbName} · 文件明细` : '知识库文件')
const chunkTitle = computed(() => selectedDocument.value ? `${selectedDocument.value.docTitle || selectedDocument.value.originalFilename} · 切片` : '文档切片')

function entryLabel(type) {
  return entries.find(entry => entry.type === type)?.label || type || '通用'
}

function filteredKbs(type) {
  return kbs.value.filter(item => item.kbType === type)
}

function statusLabel(status) {
  const labels = {
    empty: '待上传',
    pending: '待处理',
    process: '处理中',
    processing: '处理中',
    partial: '部分完成',
    success: '完成',
    indexed: '完成',
    parsed: '完成',
    failed: '失败',
  }
  return labels[status] || '待处理'
}

function statusTagType(status) {
  if (['success', 'indexed', 'parsed'].includes(status)) return 'success'
  if (['failed', 'error'].includes(status)) return 'danger'
  if (['partial', 'process', 'processing'].includes(status)) return 'warning'
  return 'info'
}

function documentStatusText(row) {
  if (row.vectorStatus === 'indexed') return '可检索'
  if (row.vectorStatus === 'failed' || row.parseStatus === 'failed') return '处理失败'
  if (row.parseStatus === 'parsed') return '待向量化'
  return '待解析'
}

function activeStep(steps = []) {
  const firstUnfinished = steps.findIndex(step => step.status !== 'success')
  return firstUnfinished === -1 ? steps.length : firstUnfinished
}

function openCreate() {
  form.value = {
    name: '',
    type: activeType.value === 'image_asset' ? 'company_profile' : activeType.value,
    description: '',
  }
  showCreate.value = true
}

async function loadKbs() {
  try {
    const { data } = await knowledgeApi.list()
    kbs.value = (data.items || data || []).map(normalizeKb)
  } catch {
    kbs.value = []
  }
}

async function loadImageAssets() {
  try {
    const { data } = await v2Api.listImageAssets({ limit: 100 })
    imageAssets.value = data.items || []
  } catch {
    imageAssets.value = []
  }
}

async function createKb() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入知识库名称')
    return
  }
  creating.value = true
  try {
    await knowledgeApi.create({
      kbName: form.value.name,
      kbType: form.value.type,
      description: form.value.description,
    })
    ElMessage.success('知识库已创建')
    showCreate.value = false
    await loadKbs()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '创建失败')
  } finally {
    creating.value = false
  }
}

async function uploadDoc(kbId, file, docType) {
  try {
    await knowledgeApi.uploadDoc(kbId, file, docType)
    ElMessage.success('文档上传成功，已进入向量化处理')
    await loadKbs()
    if (selectedKb.value?.id === kbId) {
      await openDetail(selectedKb.value, false)
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '上传失败')
  }
  return false
}

async function openDetail(row, reveal = true) {
  selectedKb.value = row
  if (reveal) showDetail.value = true
  detailLoading.value = true
  try {
    const { data } = await knowledgeApi.get(row.id)
    selectedKb.value = data.kb || row
    detailSummary.value = data.summary || {}
    detailDocuments.value = data.documents || []
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载知识库文件失败')
    detailDocuments.value = []
  } finally {
    detailLoading.value = false
  }
}

async function openChunks(row) {
  selectedDocument.value = row
  showChunks.value = true
  chunkLoading.value = true
  try {
    const { data } = await knowledgeApi.listChunks(row.documentId)
    chunks.value = data.items || []
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '加载切片失败')
    chunks.value = []
  } finally {
    chunkLoading.value = false
  }
}

async function createImageAsset() {
  if (!imageForm.value.assetTitle.trim()) {
    ElMessage.warning('请输入图片资产标题')
    return
  }
  creatingImageAsset.value = true
  try {
    await v2Api.createImageAsset(imageForm.value)
    ElMessage.success('图片资产已登记')
    showImageAssetDialog.value = false
    imageForm.value = {
      assetTitle: '',
      imageType: 'product_image',
      sourceType: 'enterprise_upload',
      caption: '',
      searchableText: '',
      allowedForBid: true,
    }
    await loadImageAssets()
  } catch (error) {
    ElMessage.error(error.response?.data?.error || '保存失败')
  } finally {
    creatingImageAsset.value = false
  }
}
</script>

<style scoped>
.knowledge-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-header,
.section-head,
.entry-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.page-header h2,
.entry-summary h3,
.section-head h3 {
  margin: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: #64748b;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}

.knowledge-tabs {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px;
}

.entry-summary {
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.entry-summary p {
  margin: 6px 0 0;
  color: #64748b;
}

.image-assets {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.progress-cell,
.file-title,
.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-line {
  display: flex;
  gap: 12px;
  color: #475569;
  font-size: 13px;
}

.status-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.kb-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-summary {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  padding: 16px;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.detail-summary h3 {
  margin: 0;
}

.detail-summary p {
  margin: 6px 0 0;
  color: #64748b;
}

.summary-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(72px, 1fr));
  gap: 10px;
  min-width: 260px;
}

.summary-metrics div {
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.summary-metrics strong,
.summary-metrics span {
  display: block;
}

.summary-metrics strong {
  color: #0f172a;
  font-size: 20px;
  line-height: 1.1;
}

.summary-metrics span,
.file-title span {
  color: #64748b;
  font-size: 12px;
}

.chunk-item {
  padding: 14px 0;
  border-bottom: 1px solid #e5e7eb;
}

.chunk-item header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.chunk-item p {
  margin: 0;
  color: #334155;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .detail-summary {
    flex-direction: column;
  }

  .summary-metrics {
    width: 100%;
    min-width: 0;
  }
}
</style>
