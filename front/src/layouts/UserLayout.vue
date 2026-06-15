<template>
  <el-container class="app-container">
    <el-aside width="220px" class="app-aside">
      <div class="brand">
        <el-icon :size="28"><Document /></el-icon>
        <span>AI 招投标平台</span>
      </div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item index="/">
          <el-icon><FolderOpened /></el-icon>
          <span>项目中心</span>
        </el-menu-item>
        <el-menu-item index="/admin">
          <el-icon><Setting /></el-icon>
          <span>后台管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.params.id">项目 #{{ route.params.id }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => {
  if (route.path.startsWith('/admin')) return '/admin'
  return '/'
})
</script>

<style scoped>
.app-container { height: 100vh; }
.app-aside { background: linear-gradient(180deg, #1a1f36 0%, #0f1629 100%); border-right: none; overflow: hidden; }
.brand { display: flex; align-items: center; gap: 10px; padding: 20px 16px; color: #fff; font-size: 16px; font-weight: 600; }
.aside-menu { border-right: none; background: transparent; }
.aside-menu :deep(.el-menu-item) { color: #a0aec0; margin: 4px 8px; border-radius: 8px; }
.aside-menu :deep(.el-menu-item:hover),
.aside-menu :deep(.el-menu-item.is-active) { background: rgba(99, 102, 241, 0.15); color: #fff; }
.app-header { display: flex; align-items: center; background: #fff; border-bottom: 1px solid #edf2f7; height: 56px; }
.app-main { background: #f7f8fc; padding: 24px; overflow-y: auto; }
</style>
