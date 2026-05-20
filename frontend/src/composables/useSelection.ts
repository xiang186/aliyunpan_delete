import { computed } from 'vue'
import { useSelectionStore } from '@/stores/selection'
import type { DuplicateGroup } from '@/types'

export function useSelection(groups: () => DuplicateGroup[]) {
  const store = useSelectionStore()

  // 全选（每组保留一个，按修改时间最新保留）
  function selectAllKeepOne() {
    store.clear()
    for (const group of groups()) {
      if (group.files.length <= 1) continue
      // 按 modified_at 降序排列，保留最新的（index 0），选中其余
      const sorted = [...group.files].sort(
        (a, b) => new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
      )
      sorted.slice(1).forEach(f => store.select(f.file_id))
    }
  }

  // 对某组：保留最新版本，选中其余
  function selectGroupKeepNewest(group: DuplicateGroup) {
    const sorted = [...group.files].sort(
      (a, b) => new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()
    )
    // 先取消该组所有选中
    group.files.forEach(f => store.deselect(f.file_id))
    // 选中除最新外的所有
    sorted.slice(1).forEach(f => store.select(f.file_id))
  }

  // 对某组：保留最早版本，选中其余
  function selectGroupKeepOldest(group: DuplicateGroup) {
    const sorted = [...group.files].sort(
      (a, b) => new Date(a.modified_at).getTime() - new Date(b.modified_at).getTime()
    )
    group.files.forEach(f => store.deselect(f.file_id))
    sorted.slice(1).forEach(f => store.select(f.file_id))
  }

  // 切换单个文件选中状态，带防误删保护
  function toggleFile(group: DuplicateGroup, fileId: string): { blocked: boolean } {
    const isCurrentlySelected = store.isSelected(fileId)
    if (!isCurrentlySelected) {
      // 检查：选中后该组是否全部被选中
      const otherFiles = group.files.filter(f => f.file_id !== fileId)
      const allOthersSelected = otherFiles.every(f => store.isSelected(f.file_id))
      if (allOthersSelected && group.files.length > 1) {
        // 防误删：不允许选中最后一个
        return { blocked: true }
      }
      store.select(fileId)
    } else {
      store.deselect(fileId)
    }
    return { blocked: false }
  }

  // 计算已选文件的预计释放空间
  const selectedSizeBytes = computed(() => {
    let total = 0
    for (const group of groups()) {
      for (const file of group.files) {
        if (store.isSelected(file.file_id)) {
          total += file.file_size
        }
      }
    }
    return total
  })

  return {
    selectedCount: computed(() => store.selectedCount),
    selectedIdsArray: computed(() => store.selectedIdsArray),
    selectedSizeBytes,
    isSelected: (fileId: string) => store.isSelected(fileId),
    selectAllKeepOne,
    clearAll: () => store.clear(),
    selectGroupKeepNewest,
    selectGroupKeepOldest,
    toggleFile,
  }
}
