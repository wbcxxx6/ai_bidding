<template>
  <div>
    <h2 class="page-title">模型配置</h2>
    <el-card shadow="never" class="settings-card">
      <el-form :model="form" label-width="120px">
        <el-form-item label="模型提供商">
          <el-select v-model="form.provider" @change="onProviderChange" placeholder="选择模型提供商">
            <el-option v-for="p in providers" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="currentProvider">
          <el-alert :title="currentProvider.model_hint" type="info" :closable="false" show-icon />
        </el-form-item>
        <el-form-item label="模型 ID">
          <el-input v-model="form.model" :placeholder="currentProvider?.default_model || '输入模型名称'" />
        </el-form-item>
        <el-form-item label="API Base URL">
          <el-input v-model="form.baseUrl" disabled />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.apiKey" type="password" show-password placeholder="输入 API Key" />
          <div class="field-hint" v-if="apiKeySet">当前已配置 API Key（{{ apiKeyMasked }}）</div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save" :loading="saving">保存配置</el-button>
          <el-button @click="testConnection" :loading="testing">测试连接</el-button>
          <el-link v-if="currentProvider?.official_docs" :href="currentProvider.official_docs" target="_blank" type="primary" class="doc-link">
            查看官方文档 ↗
          </el-link>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="providers-card">
      <template #header><span>支持的模型提供商</span></template>
      <el-table :data="providers" stripe size="small">
        <el-table-column prop="name" label="名称" width="160" />
        <el-table-column prop="base_url" label="Base URL" />
        <el-table-column prop="default_model" label="默认模型" width="160" />
        <el-table-column label="文档" width="80">
          <template #default="{ row }">
            <el-link :href="row.official_docs" target="_blank" type="primary">文档</el-link>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { settingsApi } from '@/shared/api.js'

const form = ref({ provider: '', model: '', baseUrl: '', apiKey: '' })
const providers = ref([])
const saving = ref(false)
const testing = ref(false)
const apiKeySet = ref(false)
const apiKeyMasked = ref('')

const currentProvider = computed(() => providers.value.find(p => p.id === form.value.provider))

onMounted(async () => {
  try {
    const [settingsRes, providersRes] = await Promise.all([settingsApi.get(), settingsApi.getProviders()])
    const s = settingsRes.data
    form.value = {
      provider: s.activeProvider || '',
      model: s.model || '',
      baseUrl: s.baseUrl || '',
      apiKey: ''
    }
    apiKeySet.value = s.apiKeySet || false
    apiKeyMasked.value = s.apiKeyMasked || ''
    providers.value = providersRes.data.providers || []
  } catch { /* empty */ }
})

function onProviderChange() {
  const p = providers.value.find(x => x.id === form.value.provider)
  if (p) {
    form.value.baseUrl = p.base_url
    form.value.model = p.default_model || ''
  }
}

async function save() {
  saving.value = true
  try {
    await settingsApi.update(form.value)
    ElMessage.success('配置已保存')
    apiKeySet.value = !!form.value.apiKey || apiKeySet.value
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '保存失败')
  } finally { saving.value = false }
}

async function testConnection() {
  testing.value = true
  try {
    const { data } = await settingsApi.test()
    ElMessage.success(data.message || '连接成功')
  } catch (e) {
    ElMessage.error(e.response?.data?.error || '连接失败')
  } finally { testing.value = false }
}
</script>

<style scoped>
.page-title { margin: 0 0 20px; font-size: 20px; }
.settings-card { max-width: 640px; border-radius: 12px; margin-bottom: 24px; }
.providers-card { border-radius: 12px; }
.field-hint { font-size: 12px; color: #909399; margin-top: 4px; }
.doc-link { margin-left: 12px; }
</style>
