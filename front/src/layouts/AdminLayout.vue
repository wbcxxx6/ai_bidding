<template>
  <el-container class="app-container">
    <el-aside width="200px" class="admin-aside">
      <div class="brand">
        <el-icon :size="24"><Setting /></el-icon>
        <span>管理后台</span>
      </div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item index="/admin">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/admin/knowledge">
          <el-icon><Collection /></el-icon>
          <span>知识库</span>
        </el-menu-item>
        <el-menu-item index="/admin/models">
          <el-icon><Cpu /></el-icon>
          <span>模型配置</span>
        </el-menu-item>
        <el-menu-item index="/admin/audit">
          <el-icon><List /></el-icon>
          <span>审计日志</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="admin-header">
        <span class="header-title">系统管理</span>
        <el-button link @click="$router.push('/')">返回用户端</el-button>
      </el-header>
      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style scoped>
.app-container { height: 100vh; }
.admin-aside { background: #1e293b; }
.brand { display: flex; align-items: center; gap: 8px; padding: 18px 16px; color: #f1f5f9; font-size: 15px; font-weight: 600; }
.aside-menu { border-right: none; background: transparent; }
.aside-menu :deep(.el-menu-item) { color: #94a3b8; margin: 2px 6px; border-radius: 6px; }
.aside-menu :deep(.el-menu-item:hover),
.aside-menu :deep(.el-menu-item.is-active) { background: rgba(99, 102, 241, 0.2); color: #fff; }
.admin-header { display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #e2e8f0; height: 52px; padding: 0 20px; }
.header-title { font-weight: 600; font-size: 15px; }
.admin-main { background: #f8fafc; padding: 24px; overflow-y: auto; }
</style>
