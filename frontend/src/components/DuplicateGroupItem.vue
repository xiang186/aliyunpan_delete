<template>
  <div class="duplicate-group-item">
    <!-- 折叠头部 -->
    <div class="group-header" @click="toggleExpand">
      <div class="header-left">
        <el-icon class="expand-icon" :class="{ expanded: isExpanded }">
          <ArrowRight />
        </el-icon>
        <span class="file-name" :title="group.file_name">{{ group.file_name }}</span>
        <el-tag :type="fileTypeTagType(group.file_type)" size="small" class="type-tag">
          {{ fileTypeLabel(group.file_type) }}
        </el-tag>
      </div>
      <div class="header-right">
        <span class="file-size">{{ formatBytes(group.file_size) }}</span>
        <el-tag type="danger" size="small" class="count-tag">
          {{ group.duplicate_count }} 个副本
        </el-tag>
      </div>
    </div>

    <!-- 展开内容 -->
    <div v-if="isExpanded" class="group-body">
      <!-- 操作按钮 -->
      <div class="group-actions">
        <el-button size="small" @click.stop="handleKeepNewest">保留最新</el-button>
        <el-button size="small" @click.stop="handleKeepOldest">保留最早</el-button>
      </div>

      <!-- 文件列表 -->
      <div class="file-list">
        <div
          v-for="file in group.files"
          :key="file.file_id"
          class="file-item"
          :class="{ selected: isSelected(file.file_id) }"
        >
          <el-checkbox
            :model-value="isSelected(file.file_id)"
            @change="handleToggle(file.file_id)"
          />
          <div class="file-info">
            <div class="file-name-row">
              <span class="file-item-name" :title="file.file_name">{{ file.file_name }}</span>
            </div>
            <div class="file-row">
              <span class="file-size-inline">{{ formatBytes(file.file_size) }}</span>
              <span class="meta-sep">·</span>
              <span class="file-path-full" :title="formatPath(file.file_path)">
                {{ formatPath(file.file_path) || '根目录' }}
              </span>
              <el-icon class="info-icon" @click.stop="openDetail(file)"><InfoFilled /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 文件详情弹窗 -->
    <el-dialog
      v-model="detailVisible"
      :title="detailFile?.file_name"
      width="420px"
      destroy-on-close
    >
      <div v-if="detailFile" class="detail-content">
        <!-- 文件图标 -->
        <div class="detail-icon">
          <el-icon :size="64" :color="fileTypeColor(detailFile.file_type)">
            <component :is="fileTypeIcon(detailFile.file_type)" />
          </el-icon>
        </div>

        <div class="detail-section">
          <div class="detail-label">详细信息</div>
          <div class="detail-filename">{{ detailFile.file_name }}</div>
          <div class="detail-size">{{ formatBytes(detailFile.file_size) }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">文件位置</div>
          <div class="detail-path">{{ formatPath(detailFile.file_path) }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">最后修改时间</div>
          <div class="detail-value">{{ formatDate(detailFile.modified_at) }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">内容哈希</div>
          <div class="detail-hash">{{ detailFile.content_hash }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  ArrowRight, InfoFilled,
  VideoCamera, Picture, Headset, Document, Files, Folder,
} from '@element-plus/icons-vue'
import type { DuplicateFile, DuplicateGroup } from '@/types'
import { useSelection } from '@/composables/useSelection'
import { useScanStore } from '@/stores/scan'

const props = defineProps<{ group: DuplicateGroup }>()

const scanStore = useScanStore()
const { isSelected, toggleFile, selectGroupKeepNewest, selectGroupKeepOldest } = useSelection(
  () => scanStore.groups
)

const isExpanded = ref(false)
const detailVisible = ref(false)
const detailFile = ref<DuplicateFile | null>(null)

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

function openDetail(file: DuplicateFile) {
  detailFile.value = file
  detailVisible.value = true
}

function handleToggle(fileId: string) {
  const result = toggleFile(props.group, fileId)
  if (result.blocked) {
    ElMessage.warning('每组至少保留一个文件')
  }
}

function handleKeepNewest() {
  selectGroupKeepNewest(props.group)
}

function handleKeepOldest() {
  selectGroupKeepOldest(props.group)
}

/** Shorten a long path for inline display, keeping the last segment. */
function shortenPath(path: string): string {
  if (!path) return '根目录'
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  if (parts.length === 0) return '根目录'
  if (parts.length <= 2) return parts.join(' › ')
  return `...› ${parts[parts.length - 1]}`
}

/** Format path as breadcrumb-style string. */
function formatPath(path: string): string {
  if (!path) return '全部文件'
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  return ['全部文件', ...parts].join(' › ')
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fileTypeLabel(type: string): string {
  const map: Record<string, string> = {
    video: '视频', image: '图片', audio: '音频',
    document: '文档', archive: '压缩包', other: '其他',
  }
  return map[type] ?? '其他'
}

function fileTypeTagType(type: string): 'success' | 'warning' | 'info' | 'danger' | '' {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger' | ''> = {
    video: 'danger', image: 'success', audio: 'warning',
    document: '', archive: 'info', other: 'info',
  }
  return map[type] ?? 'info'
}

function fileTypeIcon(type: string) {
  const map: Record<string, any> = {
    video: VideoCamera, image: Picture, audio: Headset,
    document: Document, archive: Files, other: Folder,
  }
  return map[type] ?? Folder
}

function fileTypeColor(type: string): string {
  const map: Record<string, string> = {
    video: '#f56c6c', image: '#67c23a', audio: '#e6a23c',
    document: '#409eff', archive: '#909399', other: '#909399',
  }
  return map[type] ?? '#909399'
}
</script>

<style scoped>
.duplicate-group-item {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin-bottom: 8px;
  background: #fff;
  overflow: hidden;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.group-header:hover {
  background: #f5f7fa;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.expand-icon {
  flex-shrink: 0;
  color: #909399;
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.file-name {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 400px;
}

.type-tag { flex-shrink: 0; }

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  margin-left: 12px;
}

.file-size {
  font-size: 13px;
  color: #606266;
}

.count-tag { flex-shrink: 0; }

.group-body {
  border-top: 1px solid #e4e7ed;
  padding: 10px 14px;
}

.group-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.file-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
  background: #fafafa;
  transition: background 0.15s;
}

.file-item.selected {
  background: #ecf5ff;
  border-color: #b3d8ff;
}

.file-info {
  flex: 1;
  min-width: 0;
}

.file-name-row {
  margin-bottom: 3px;
}

.file-item-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
}

.file-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.file-size-inline {
  font-size: 12px;
  color: #909399;
  flex-shrink: 0;
  white-space: nowrap;
}

.meta-sep {
  font-size: 12px;
  color: #c0c4cc;
  flex-shrink: 0;
}

.file-path-full {
  font-size: 12px;
  color: #909399;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-icon {
  font-size: 14px;
  color: #c0c4cc;
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s;
}

.info-icon:hover {
  color: #409eff;
}

/* Detail dialog */
.detail-content {
  padding: 4px 0;
}

.detail-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 20px;
}

.detail-section {
  margin-bottom: 16px;
}

.detail-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.detail-filename {
  font-size: 15px;
  font-weight: 500;
  color: #303133;
  word-break: break-all;
}

.detail-size {
  font-size: 13px;
  color: #606266;
  margin-top: 2px;
}

.detail-path {
  font-size: 13px;
  color: #409eff;
  word-break: break-all;
  line-height: 1.6;
}

.detail-value {
  font-size: 13px;
  color: #303133;
}

.detail-hash {
  font-size: 11px;
  color: #909399;
  font-family: monospace;
  word-break: break-all;
}
</style>
