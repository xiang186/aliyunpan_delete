<template>
  <div class="history-view">
    <el-container>
      <el-header class="page-header">
        <el-button :icon="ArrowLeft" @click="router.back()">返回</el-button>
        <h1 class="page-title">任务历史记录</h1>
      </el-header>

      <el-main v-loading="loading">
        <el-empty v-if="!loading && taskStore.tasks.length === 0" description="暂无历史记录" />

        <el-table
          v-else
          :data="sortedTasks"
          border
          stripe
          style="width: 100%"
          @row-click="handleRowClick"
          row-class-name="clickable-row"
        >
          <el-table-column label="操作类型" width="160" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.delete_type === 'trash'" type="warning">移至回收站</el-tag>
              <el-tag v-else type="danger">永久删除 ⚠️不可恢复</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.status === 'completed'" type="success">已完成</el-tag>
              <el-tag v-else-if="row.status === 'running'" type="primary">进行中</el-tag>
              <el-tag v-else type="danger">失败</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="文件数" prop="total_count" width="90" align="right" />

          <el-table-column label="成功 / 失败" width="120" align="center">
            <template #default="{ row }">
              <span class="count-success">{{ row.success_count }}</span>
              <span class="count-sep"> / </span>
              <span class="count-failed">{{ row.failed_count }}</span>
            </template>
          </el-table-column>

          <el-table-column label="释放空间" width="120" align="right">
            <template #default="{ row }">
              {{ formatBytes(row.freed_bytes) }}
            </template>
          </el-table-column>

          <el-table-column label="开始时间" min-width="160">
            <template #default="{ row }">
              {{ formatTime(row.started_at) }}
            </template>
          </el-table-column>
        </el-table>
      </el-main>
    </el-container>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="任务详情"
      size="60%"
      direction="rtl"
      :before-close="handleDrawerClose"
    >
      <div v-loading="detailLoading" class="drawer-content">
        <TaskHistoryDetail
          v-if="taskStore.currentTask"
          :task="taskStore.currentTask"
          :files="taskStore.currentTaskFiles"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useTaskStore } from '@/stores/task'
import { listTasks, getTask } from '@/api'
import TaskHistoryDetail from '@/components/TaskHistoryDetail.vue'

const router = useRouter()
const taskStore = useTaskStore()

const loading = ref(false)
const detailLoading = ref(false)
const drawerVisible = ref(false)

const sortedTasks = computed(() =>
  [...taskStore.tasks].sort((a, b) => b.started_at - a.started_at),
)

onMounted(async () => {
  loading.value = true
  try {
    const res = await listTasks()
    taskStore.setTasks(res.data.tasks)
  } catch {
    ElMessage.error('加载任务列表失败')
  } finally {
    loading.value = false
  }
})

async function handleRowClick(row: any) {
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const res = await getTask(row.task_id)
    taskStore.setCurrentTask(res.data.task, res.data.files)
  } catch {
    ElMessage.error('加载任务详情失败')
    drawerVisible.value = false
  } finally {
    detailLoading.value = false
  }
}

function handleDrawerClose() {
  drawerVisible.value = false
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}
</script>

<style scoped>
.history-view {
  min-height: 100vh;
  background: #f5f7fa;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  background-color: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 60px;
  padding: 0 20px;
}

.page-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #303133;
}

.el-main {
  padding: 20px;
}

.count-success {
  color: #67c23a;
  font-weight: 600;
}

.count-sep {
  color: #c0c4cc;
}

.count-failed {
  color: #f56c6c;
  font-weight: 600;
}

.drawer-content {
  padding: 0 4px;
  min-height: 200px;
}

:deep(.clickable-row) {
  cursor: pointer;
}

:deep(.clickable-row:hover td) {
  background-color: #ecf5ff !important;
}
</style>
