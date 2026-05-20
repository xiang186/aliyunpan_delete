<template>
  <div class="duplicate-group-list">
    <el-scrollbar v-if="groups.length > 0" class="list-scrollbar">
      <div class="list-inner">
        <DuplicateGroupItem
          v-for="group in groups"
          :key="group.group_id"
          :group="group"
        />
      </div>
    </el-scrollbar>

    <el-empty v-else description="暂无重复文件" class="empty-state" />
  </div>
</template>

<script setup lang="ts">
import type { DuplicateGroup } from '@/types'
import DuplicateGroupItem from './DuplicateGroupItem.vue'

defineProps<{
  groups: DuplicateGroup[]
}>()
</script>

<style scoped>
.duplicate-group-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.list-scrollbar {
  flex: 1;
  min-height: 0;
}

.list-inner {
  padding: 4px 2px;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}
</style>
