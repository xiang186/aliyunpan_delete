<template>
  <div class="filter-bar">
    <!-- 文件名搜索 -->
    <div class="filter-row">
      <el-input
        :model-value="keyword"
        placeholder="搜索文件名"
        clearable
        prefix-icon="Search"
        style="width: 260px"
        @update:model-value="emit('update:keyword', $event)"
      />
    </div>

    <!-- 文件类型筛选 -->
    <div class="filter-row">
      <span class="filter-label">文件类型：</span>
      <el-radio-group
        :model-value="selectedFileType"
        @update:model-value="emit('update:selectedFileType', $event as FileType | 'all')"
      >
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="video">视频</el-radio-button>
        <el-radio-button value="image">图片</el-radio-button>
        <el-radio-button value="audio">音频</el-radio-button>
        <el-radio-button value="document">文档</el-radio-button>
        <el-radio-button value="archive">压缩包</el-radio-button>
        <el-radio-button value="other">其他</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 排序选项 -->
    <div class="filter-row">
      <span class="filter-label">排序：</span>
      <el-select
        :model-value="sortField"
        style="width: 140px"
        @update:model-value="emit('update:sortField', $event as SortField)"
      >
        <el-option label="按文件大小" value="file_size" />
        <el-option label="按重复数量" value="duplicate_count" />
      </el-select>
      <el-select
        :model-value="sortOrder"
        style="width: 100px; margin-left: 8px"
        @update:model-value="emit('update:sortOrder', $event as SortOrder)"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FileType } from '@/types'
import type { SortField, SortOrder } from '@/composables/useFileFilter'

const props = defineProps<{
  keyword: string
  selectedFileType: FileType | 'all'
  sortField: SortField
  sortOrder: SortOrder
}>()

const emit = defineEmits<{
  'update:keyword': [value: string]
  'update:selectedFileType': [value: FileType | 'all']
  'update:sortField': [value: SortField]
  'update:sortOrder': [value: SortOrder]
}>()
</script>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
}

.filter-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: #606266;
  white-space: nowrap;
}
</style>
