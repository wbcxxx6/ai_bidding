<template>
  <div>
    <h2 class="page-title">系统概览</h2>
    <el-row :gutter="16">
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="投标项目" :value="stats.projects" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="知识库文档" :value="stats.documents" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="stat-card">
          <el-statistic title="模型调用次数" :value="stats.modelCalls" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const stats = ref({ projects: 0, documents: 0, modelCalls: 0 })
</script>

<style scoped>
.page-title { margin: 0 0 20px; font-size: 20px; }
.stat-card { border-radius: 12px; }
</style>
