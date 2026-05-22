import { computed } from 'vue'
import type { DuplicateGroup } from '@/types'
import { useSelectionStore } from '@/stores/selection'

export function useStats(visibleGroups: () => DuplicateGroup[]) {
  const selectionStore = useSelectionStore()

  // 基于当前可见列表（筛选后）的统计
  const totalGroups = computed(() => visibleGroups().length)

  // 重复副本总数（每组所有副本之和）
  const totalFiles = computed(() =>
    visibleGroups().reduce((sum, g) => sum + g.duplicate_count, 0)
  )

  // 可删除副本数 = 每组 (副本数-1)，即保留一份后可删除的数量
  const deletableFiles = computed(() =>
    visibleGroups().reduce((sum, g) => sum + Math.max(0, g.duplicate_count - 1), 0)
  )

  // 可释放空间 = 每组 (副本数-1) * 文件大小
  const totalSizeBytes = computed(() =>
    visibleGroups().reduce((sum, g) => sum + g.file_size * (g.duplicate_count - 1), 0)
  )

  // 重复文件占用的总空间（所有副本，含保留的那份）
  const totalDuplicateSizeBytes = computed(() =>
    visibleGroups().reduce((sum, g) => sum + g.file_size * g.duplicate_count, 0)
  )

  // 最大单组可释放空间（最"值钱"的重复组）
  const maxGroupSaveBytes = computed(() =>
    visibleGroups().reduce((max, g) => {
      const save = g.file_size * (g.duplicate_count - 1)
      return save > max ? save : max
    }, 0)
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
    deletableFiles,
    totalSizeBytes,
    totalDuplicateSizeBytes,
    maxGroupSaveBytes,
    selectedCount,
    selectedSizeBytes,
    formatBytes,
  }
}
