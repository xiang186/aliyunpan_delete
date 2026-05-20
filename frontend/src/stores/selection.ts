import { defineStore } from 'pinia'

export const useSelectionStore = defineStore('selection', {
  state: () => ({
    selectedIds: new Set<string>(),
  }),
  getters: {
    selectedCount: (state) => state.selectedIds.size,
    selectedIdsArray: (state) => Array.from(state.selectedIds),
  },
  actions: {
    toggle(fileId: string) {
      if (this.selectedIds.has(fileId)) this.selectedIds.delete(fileId)
      else this.selectedIds.add(fileId)
    },
    select(fileId: string) {
      this.selectedIds.add(fileId)
    },
    deselect(fileId: string) {
      this.selectedIds.delete(fileId)
    },
    selectAll(fileIds: string[]) {
      fileIds.forEach((id) => this.selectedIds.add(id))
    },
    clear() {
      this.selectedIds.clear()
    },
    isSelected(fileId: string) {
      return this.selectedIds.has(fileId)
    },
  },
})
