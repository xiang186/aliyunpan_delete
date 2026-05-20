import { defineStore } from 'pinia'
import type { TaskSummary } from '@/types'

export const useTaskStore = defineStore('task', {
  state: () => ({
    tasks: [] as TaskSummary[],
    currentTask: null as any,
    currentTaskFiles: [] as any[],
  }),
  actions: {
    setTasks(tasks: TaskSummary[]) {
      this.tasks = tasks
    },
    setCurrentTask(task: any, files: any[]) {
      this.currentTask = task
      this.currentTaskFiles = files
    },
  },
})
