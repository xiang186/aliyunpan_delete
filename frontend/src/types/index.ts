export type FileType = 'video' | 'image' | 'audio' | 'document' | 'archive' | 'other'

export interface DuplicateFile {
  file_id: string
  file_name: string
  file_path: string
  file_size: number
  content_hash: string
  modified_at: string
  file_type: FileType
}

export interface DuplicateGroup {
  group_id: string
  file_name: string
  file_size: number
  content_hash: string
  duplicate_count: number
  file_type: FileType
  files: DuplicateFile[]
}

export interface TaskSummary {
  task_id: string
  delete_type: 'trash' | 'permanent'
  status: 'running' | 'completed' | 'failed'
  total_count: number
  success_count: number
  failed_count: number
  freed_bytes: number
  started_at: number
  completed_at: number | null
}
