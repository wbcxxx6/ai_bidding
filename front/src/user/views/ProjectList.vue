<template>
  <div class="project-center">
    <section class="hero-panel">
      <div>
        <p class="eyebrow">Project Center</p>
        <h2>项目中心</h2>
        <p>集中管理投标项目、招标文件、解析进度和生成结果</p>
      </div>
      <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".pdf,.doc,.docx,.txt,.md">
        <el-button type="primary" :icon="Upload">上传招标文件</el-button>
      </el-upload>
    </section>

    <section v-if="projects.length" class="project-grid">
      <button v-for="project in projects" :key="project.id" class="project-card" @click="$router.push(`/project/${project.id}`)">
        <span class="status-pill" :class="statusClass(project)">
          {{ statusLabel(project) }}
        </span>
        <strong>{{ projectTitle(project) }}</strong>
        <span class="filename">招标文件：{{ maskedFilename(project) }}</span>
        <div class="progress-track">
          <span class="progress-fill" :class="statusClass(project)" :style="{ width: `${progressPercent(project)}%` }" />
        </div>
        <div class="card-foot">
          <span>{{ progressPercent(project) }}%</span>
          <span>{{ taskSummary(project) }}</span>
        </div>
      </button>
    </section>

    <el-empty v-else description="暂无项目，请上传招标文件创建项目" />

    <section class="task-panel">
      <div class="section-head">
        <h3>最近任务</h3>
        <el-tag>{{ recentTasks.length }}</el-tag>
      </div>
      <div v-if="recentTasks.length" class="task-list">
        <article v-for="task in recentTasks" :key="task.key" class="task-row">
          <span>{{ task.typeLabel }}</span>
          <span>{{ task.projectName }}</span>
          <span>{{ task.description }}</span>
          <el-tag :type="task.tagType">{{ task.statusLabel }}</el-tag>
        </article>
      </div>
      <div v-else class="empty-task">暂无任务进度</div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { biddingApi, projectApi } from '@/shared/api.js'

const router = useRouter()
const projects = ref([])

const statusMeta = {
  draft: { label: '待上传', percent: 10, className: 'draft', task: '等待上传或确认资料' },
  analyzing: { label: '解析中', percent: 35, className: 'analyzing', task: '正在解析招标文件' },
  generating: { label: '生成中', percent: 65, className: 'generating', task: '正在生成章节正文' },
  completed: { label: '已完成', percent: 100, className: 'completed', task: '投标文件已生成' },
}

const taskTypeLabels = {
  pre_analysis: '文件解析',
  chapter_design: '章节规划',
  generate_document: '整本生成',
  chapter_generate: '章节生成',
  project_generate: '整本生成',
  project_export: '整本导出',
}

const taskStatusLabels = {
  queued: '排队中',
  pending: '待处理',
  running: '处理中',
  succeeded: '完成',
  failed: '失败',
  cancelled: '已取消',
}

const recentTasks = computed(() => projects.value
  .map(project => {
    const agentTaskId = project.latest_agent_task_id || project.latestAgentTaskId
    const legacyTaskId = project.latest_generation_task_id || project.latestGenerationTaskId
    const taskType = project.latest_agent_task_type || project.latestAgentTaskType || project.latest_generation_task_type || project.latestGenerationTaskType
    const taskStatus = project.latest_agent_task_status || project.latestAgentTaskStatus || project.latest_generation_task_status || project.latestGenerationTaskStatus || projectStatus(project)
    if (!agentTaskId && !legacyTaskId && projectStatus(project) === 'draft') return null
    return {
      key: `${project.id}-${agentTaskId || legacyTaskId || projectStatus(project)}`,
      typeLabel: taskTypeLabels[taskType] || statusMeta[projectStatus(project)]?.task || '项目任务',
      projectName: projectTitle(project),
      description: taskSummary(project),
      statusLabel: taskStatusLabels[taskStatus] || statusLabel(project),
      tagType: taskTagType(taskStatus),
    }
  })
  .filter(Boolean)
  .slice(0, 8))

async function loadProjects() {
  try {
    const { data } = await projectApi.list()
    projects.value = data.items || data || []
  } catch {
    projects.value = []
  }
}

onMounted(loadProjects)
onActivated(loadProjects)

function projectStatus(project) {
  return project.project_status || project.projectStatus || 'draft'
}

function projectTitle(project) {
  return project.project_name || project.projectName || `项目 #${project.id}`
}

function statusLabel(project) {
  return statusMeta[projectStatus(project)]?.label || projectStatus(project)
}

function statusClass(project) {
  return statusMeta[projectStatus(project)]?.className || 'draft'
}

function progressPercent(project) {
  const status = projectStatus(project)
  const total = Number(project.total_chapters || project.totalChapters || 0)
  const generated = Number(project.generated_chapters || project.generatedChapters || 0)
  if (status === 'completed') return 100
  if (status === 'generating' && total > 0) {
    return Math.max(45, Math.min(98, Math.round((generated / total) * 100)))
  }
  return statusMeta[status]?.percent || 10
}

function maskedFilename(project) {
  const filename = project.bidding_filename || project.biddingFilename || '待上传'
  if (filename === '待上传') return filename
  const dotIndex = filename.lastIndexOf('.')
  const ext = dotIndex > -1 ? filename.slice(dotIndex) : ''
  const stem = dotIndex > -1 ? filename.slice(0, dotIndex) : filename
  if (stem.length <= 4) return `${stem[0] || ''}***${ext}`
  return `${stem.slice(0, 2)}***${stem.slice(-2)}${ext}`
}

function taskSummary(project) {
  const status = projectStatus(project)
  const total = Number(project.total_chapters || project.totalChapters || 0)
  const generated = Number(project.generated_chapters || project.generatedChapters || 0)
  if (status === 'generating' && total > 0) return `章节 ${generated}/${total}`
  if (status === 'completed') return '已进入 AI 工作台'
  return statusMeta[status]?.task || '等待处理'
}

function taskTagType(status) {
  if (status === 'succeeded' || status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running' || status === 'generating') return 'primary'
  return 'warning'
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
.project-center {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.hero-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  min-height: 132px;
  padding: 28px 34px;
  background: #fff;
  border: 1px solid #dce6f3;
  border-radius: 18px;
}

.hero-panel h2,
.section-head h3 {
  margin: 0;
  color: #182235;
}

.hero-panel p:last-child {
  margin: 10px 0 0;
  color: #64748b;
}

.eyebrow {
  margin: 0 0 4px;
  color: #64748b;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 20px;
}

.project-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  min-height: 184px;
  padding: 28px 30px;
  background: #fff;
  border: 1px solid #dce6f3;
  border-radius: 16px;
  cursor: pointer;
  text-align: left;
  transition: transform 0.18s ease, border-color 0.18s ease;
}

.project-card:hover {
  border-color: #9db7e8;
  transform: translateY(-2px);
}

.project-card:active {
  transform: translateY(0);
}

.project-card strong {
  color: #182235;
  font-size: 20px;
}

.filename {
  max-width: 100%;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 18px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 700;
}

.status-pill.draft,
.progress-fill.draft {
  color: #64748b;
  background: #e8eef7;
}

.status-pill.analyzing,
.progress-fill.analyzing {
  color: #b45309;
  background: #fff0d5;
}

.status-pill.generating,
.progress-fill.generating {
  color: #1d4ed8;
  background: #dbeafe;
}

.status-pill.completed,
.progress-fill.completed {
  color: #15803d;
  background: #dcfce7;
}

.progress-track {
  position: relative;
  width: 100%;
  height: 10px;
  margin-top: auto;
  overflow: hidden;
  background: #e8eef7;
  border-radius: 999px;
}

.progress-fill {
  position: absolute;
  inset: 0 auto 0 0;
  border-radius: inherit;
}

.progress-fill.draft { background: #94a3b8; }
.progress-fill.analyzing { background: #f59e0b; }
.progress-fill.generating { background: #3b82f6; }
.progress-fill.completed { background: #22a35a; }

.card-foot {
  display: flex;
  justify-content: space-between;
  width: 100%;
  color: #64748b;
  font-size: 13px;
}

.task-panel {
  padding: 26px 34px;
  background: #fff;
  border: 1px solid #dce6f3;
  border-radius: 18px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}

.task-list {
  border-top: 1px solid #e5edf7;
}

.task-row {
  display: grid;
  grid-template-columns: 1fr 1.4fr 2fr 100px;
  gap: 18px;
  align-items: center;
  min-height: 58px;
  border-bottom: 1px solid #e5edf7;
  color: #182235;
}

.task-row span:nth-child(2),
.task-row span:nth-child(3) {
  color: #64748b;
}

.empty-task {
  padding: 28px 0;
  color: #64748b;
  text-align: center;
}

@media (max-width: 768px) {
  .hero-panel {
    align-items: flex-start;
    flex-direction: column;
    padding: 22px;
  }

  .task-row {
    grid-template-columns: 1fr;
    gap: 6px;
    padding: 14px 0;
  }
}
</style>
