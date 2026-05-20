import { computed } from 'vue'
import type { DuplicateGroup } from '@/types'
import { useSelectionStore } from '@/stores/selection'

export function useStats(visibleGroups: () => DuplicateGroup[]) {
  const selectionStore = useSelectionStore()

  // 基于当前可见列表（筛选后）的统计
  const totalGroups = computed(() => visibleGroups().length)

  const totalFiles = computed(() =>
    visibleGroups().reduce((sum, g) => sum + g.duplicate_count, 0)
  )

  // 可释放空间 = 每组 (副本数-1) * 文件大小
  const totalSizeBytes = computed(() =>
    visibleGroups().reduce((sum, g) => sum + g.file_size * (g.duplicate_count - 1), 0)
  )

  // 已选文件数（仅统计可见列表中的已选文件）
  const selectedCount = computed(() => {
    let count = 0
    for (const group of visibleGroups()) {
      for (const file of group.files) {
        if (selectionStore.isSelected(file.file_id)) count++
      }
    }
    return count
  })

  // 已选文件预计释放空间
  const selectedSizeBytes = computed(() => {
    let total = 0
    for (const group of visibleGroups()) {
      for (const file of group.files) {
        if (selectionStore.isSelected(file.file_id)) total += file.file_size
      }
    }
    return total
  })

  // 格式化字节数为人类可读字符串
  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return `${(bytes / Math.pow(1024, i)).toFixed(2)} ${units[i]}`
  }

  return {
    totalGroups,
    totalFiles,
    totalSizeBytes,
    selectedCount,
    selectedSizeBytes,
    formatBytes,
  }
}
