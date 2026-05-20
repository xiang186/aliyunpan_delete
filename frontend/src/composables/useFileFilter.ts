import { computed, ref } from 'vue'
import type { DuplicateGroup, FileType } from '@/types'

export type SortField = 'file_size' | 'duplicate_count'
export type SortOrder = 'asc' | 'desc'

export function useFileFilter(groups: () => DuplicateGroup[]) {
  const keyword = ref('')
  const selectedFileType = ref<FileType | 'all'>('all')
  const sortField = ref<SortField>('file_size')
  const sortOrder = ref<SortOrder>('desc')

  const filteredGroups = computed(() => {
    let result = groups()

    // 1. 按文件类型筛选
    if (selectedFileType.value !== 'all') {
      result = result.filter(g => g.file_type === selectedFileType.value)
    }

    // 2. 按关键词筛选（大小写不敏感）
    if (keyword.value.trim()) {
      const kw = keyword.value.trim().toLowerCase()
      result = result.filter(g => g.file_name.toLowerCase().includes(kw))
    }

    // 3. 排序（不改变元素集合，只改变顺序）
    result = [...result].sort((a, b) => {
      const va = a[sortField.value]
      const vb = b[sortField.value]
      return sortOrder.value === 'asc' ? va - vb : vb - va
    })

    return result
  })

  return {
    keyword,
    selectedFileType,
    sortField,
    sortOrder,
    filteredGroups,
  }
}
