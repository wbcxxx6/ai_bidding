<template>
  <div>
    <div class="page-header">
      <h2>知识库管理</h2>
      <el-button type="primary" @click="showCreate = true">创建知识库</el-button>
    </div>
    <el-table :data="kbs" stripe>
      <el-table-column prop="kb_name" label="名称" />
      <el-table-column prop="kb_type" label="类型" width="120" />
      <el-table-column prop="visibility_scope" label="可见范围" width="120" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-upload :show-file-list="false" :before-upload="(f) => uploadDoc(row.id, f)" accept=".pdf,.doc,.docx,.txt,.md">
            <el-button link type="primary">上传文档</el-button>
          </el-upload>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showCreate" title="创建知识库" width="400px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type">
            <el-option label="企业级" value="enterprise" />
            <el-option label="部门级" value="department" />
            <el-option label="项目级" value="project" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="createKb">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi } from '@/shared/api.js'

const kbs = ref([])
const showCreate = ref(false)
const form = ref({ name: '', type: 'enterprise', description: '' })

onMounted(loadKbs)

async function loadKbs() {
  try {
    const { data } = await knowledgeApi.list()
    kbs.value = data.items || data || []
  } catch { /* empty */ }
}

async function createKb() {
  try {
    await knowledgeApi.create({ name: form.value.name, kbType: form.value.type, description: form.value.description })
    ElMessage.success('知识库已创建')
    showCreate.value = false
    await loadKbs()
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '创建失败')
  }
}

async function uploadDoc(kbId, file) {
  try {
    await knowledgeApi.uploadDoc(kbId, file, 'history_bid')
    ElMessage.success('文档上传成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '上传失败')
  }
  return false
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
