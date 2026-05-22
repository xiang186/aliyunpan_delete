<template>
  <el-dialog
    v-model="dialogVisible"
    title="选择扫描目录"
    width="520px"
    :close-on-click-modal="false"
    @open="handleOpen"
    @close="handleClose"
  >
    <div class="folder-tree-container">
      <!-- 搜索框 -->
      <div class="search-row">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索目录名称..."
          clearable
          :prefix-icon="Search"
          class="search-input"
          @input="handleSearchInput"
          @clear="handleSearchClear"
        />
        <!-- 索引状态提示 -->
        <el-tooltip :content="indexTooltip" placement="top">
          <span class="index-badge" :class="indexStatus">
            <el-icon v-if="indexStatus === 'building'" class="is-loading"><Loading /></el-icon>
            <el-icon v-else-if="indexStatus === 'ready'"><CircleCheck /></el-icon>
            <el-icon v-else><InfoFilled /></el-icon>
            <span class="badge-text">{{ indexBadgeText }}</span>
          </span>
        </el-tooltip>
      </div>

      <!-- 错误提示 -->
      <div v-if="loadError" class="load-error">
        <el-alert type="error" :title="loadError" :closable="false" show-icon />
      </div>

      <!-- 搜索结果模式 -->
      <template v-if="isSearchMode">
        <div v-if="searchLoading" class="status-placeholder">
          <el-icon class="is-loading"><Loading /></el-icon> 搜索中...
        </div>
        <div v-else-if="searchResults.length === 0" class="status-placeholder">
          未找到匹配的目录
        </div>
        <el-scrollbar v-else height="320px">
          <div
            v-for="item in searchResults"
            :key="item.file_id"
            class="search-result-item"
            :class="{ selected: selectedIds.includes(item.file_id) }"
            @click="toggleSearchResult(item)"
          >
            <el-checkbox
              :model-value="selectedIds.includes(item.file_id)"
              @change="toggleSearchResult(item)"
              @click.stop
            />
            <el-icon class="node-icon"><Folder /></el-icon>
            <div class="result-text">
              <span class="result-name" v-html="highlightMatch(item.name)" />
              <span class="result-path">{{ item.full_path }}</span>
            </div>
          </div>
        </el-scrollbar>
      </template>

      <!-- 树形浏览模式 -->
      <template v-else>
        <div v-if="treeLoading" class="status-placeholder">
          <el-icon class="is-loading"><Loading /></el-icon> 加载中...
        </div>
        <el-scrollbar v-else height="320px">
          <div v-if="treeData.length === 0 && !loadError" class="status-placeholder">
            暂无子目录
          </div>
          <el-tree
            v-else
            ref="treeRef"
            :data="treeData"
            :props="treeProps"
            :load="loadNode"
            lazy
            show-checkbox
            node-key="file_id"
            :default-checked-keys="checkedKeys"
            @check="handleCheck"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <el-icon class="node-icon"><Folder /></el-icon>
                <span class="node-label">{{ data.name }}</span>
              </span>
            </template>
          </el-tree>
        </el-scrollbar>
      </template>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="selected-hint">
          <template v-if="selectedIds.length === 0">未选择（将扫描全盘）</template>
          <template v-else>已选 {{ selectedIds.length }} 个目录</template>
        </span>
        <div class="footer-buttons">
          <el-button @click="handleClear">清除选择</el-button>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleConfirm">确定</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { Folder, Search, Loading, CircleCheck, InfoFilled } from '@element-plus/icons-vue'
import type { ElTree } from 'element-plus'
import { listFolders, getFolderIndexStatus, buildFolderIndex, searchFolders } from '@/api'

interface FolderNode {
  file_id: string
  name: string
  has_children: boolean
  full_path?: string   // computed when loaded, used as parent_path for children
  children?: FolderNode[]
}

interface SearchResult {
  file_id: string
  name: string
  full_path: string
  parent_id: string
  has_children: boolean
}

const props = defineProps<{
  visible: boolean
  sessionId?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'confirm', ids: string[], names: string[]): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

// ── Tree state ────────────────────────────────────────────────────────────────
const treeRef = ref<InstanceType<typeof ElTree>>()
const treeData = ref<FolderNode[]>([])
const treeLoading = ref(false)
const loadError = ref<string | null>(null)
const checkedKeys = ref<string[]>([])

const treeProps = {
  label: 'name',
  children: 'children',
  isLeaf: (data: FolderNode) => !data.has_children,
}

// ── Selection state ───────────────────────────────────────────────────────────
const selectedIds = ref<string[]>([])
const selectedNames = ref<string[]>([])

// ── Search state ──────────────────────────────────────────────────────────────
const searchKeyword = ref('')
const searchResults = ref<SearchResult[]>([])
const searchLoading = ref(false)
const isSearchMode = computed(() => searchKeyword.value.trim().length > 0)

// ── Index status ──────────────────────────────────────────────────────────────
const indexStatus = ref<'idle' | 'building' | 'ready'>('idle')
const indexTotalFolders = ref(0)
let pollTimer: ReturnType<typeof setInterval> | null = null
let searchDebounce: ReturnType<typeof setTimeout> | null = null

const indexBadgeText = computed(() => {
  if (indexStatus.value === 'ready') return `索引就绪 (${indexTotalFolders.value})`
  if (indexStatus.value === 'building') return '索引构建中...'
  return '索引未就绪'
})

const indexTooltip = computed(() => {
  if (indexStatus.value === 'ready') return '目录索引已就绪，可搜索所有层级目录'
  if (indexStatus.value === 'building') return '正在后台构建目录索引，完成后可搜索所有层级目录'
  return '目录索引尚未构建，搜索仅限已加载的目录'
})

// ── Open / Close ──────────────────────────────────────────────────────────────
async function handleOpen() {
  loadError.value = null
  treeData.value = []
  selectedIds.value = []
  selectedNames.value = []
  checkedKeys.value = []
  searchKeyword.value = ''
  searchResults.value = []

  // Load root folders (lazy tree)
  treeLoading.value = true
  try {
    const res = await listFolders('root', props.sessionId, '')
    treeData.value = res.data.folders.map((f) => ({
      ...f,
      full_path: f.name,
      children: f.has_children ? undefined : [],
    }))
  } catch (err: any) {
    loadError.value = err?.response?.data?.detail ?? '加载目录失败，请重试'
  } finally {
    treeLoading.value = false
  }

  // Check index status and trigger build if needed
  await checkAndStartIndex()
}

function handleClose() {
  stopPolling()
}

// ── Index management ──────────────────────────────────────────────────────────
async function checkAndStartIndex() {
  try {
    const res = await getFolderIndexStatus(props.sessionId)
    indexStatus.value = res.data.status
    indexTotalFolders.value = res.data.total_folders

    if (res.data.status === 'idle') {
      // Trigger background build
      await buildFolderIndex(props.sessionId)
      indexStatus.value = 'building'
      startPolling()
    } else if (res.data.status === 'building') {
      startPolling()
    }
    // 'ready' — nothing to do
  } catch {
    // Non-critical — index is optional
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await getFolderIndexStatus(props.sessionId)
      indexStatus.value = res.data.status
      indexTotalFolders.value = res.data.total_folders
      if (res.data.status !== 'building') {
        stopPolling()
      }
    } catch {
      stopPolling()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(() => {
  stopPolling()
  if (searchDebounce) clearTimeout(searchDebounce)
})

// ── Lazy load tree ────────────────────────────────────────────────────────────
async function loadNode(node: any, resolve: (data: FolderNode[]) => void) {
  if (node.level === 0) {
    resolve(treeData.value)
    return
  }
  const data: FolderNode = node.data
  const parentPath = data.full_path ?? data.name
  try {
    const res = await listFolders(data.file_id, props.sessionId, parentPath)
    resolve(
      res.data.folders.map((f) => ({
        ...f,
        full_path: parentPath ? `${parentPath}/${f.name}` : f.name,
        children: f.has_children ? undefined : [],
      })),
    )
  } catch {
    resolve([])
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
function handleSearchInput() {
  if (searchDebounce) clearTimeout(searchDebounce)
  if (!searchKeyword.value.trim()) {
    searchResults.value = []
    return
  }
  searchDebounce = setTimeout(doSearch, 300)
}

function handleSearchClear() {
  searchResults.value = []
  if (searchDebounce) clearTimeout(searchDebounce)
}

async function doSearch() {
  const kw = searchKeyword.value.trim()
  if (!kw) return

  searchLoading.value = true
  try {
    const res = await searchFolders(kw, props.sessionId)
    searchResults.value = res.data.folders
  } catch {
    searchResults.value = []
  } finally {
    searchLoading.value = false
  }
}

function highlightMatch(name: string): string {
  const kw = searchKeyword.value.trim()
  if (!kw) return escapeHtml(name)
  const idx = name.toLowerCase().indexOf(kw.toLowerCase())
  if (idx === -1) return escapeHtml(name)
  return (
    escapeHtml(name.slice(0, idx)) +
    `<mark class="hl">${escapeHtml(name.slice(idx, idx + kw.length))}</mark>` +
    escapeHtml(name.slice(idx + kw.length))
  )
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// ── Selection (search results) ────────────────────────────────────────────────
function toggleSearchResult(item: SearchResult) {
  const idx = selectedIds.value.indexOf(item.file_id)
  if (idx === -1) {
    selectedIds.value.push(item.file_id)
    selectedNames.value.push(item.name)
  } else {
    selectedIds.value.splice(idx, 1)
    selectedNames.value.splice(idx, 1)
  }
}

// ── Selection (tree) ──────────────────────────────────────────────────────────
function handleCheck(_data: FolderNode, state: { checkedNodes: FolderNode[] }) {
  // Merge tree selections with any search-result selections
  const treeIds = state.checkedNodes.map((n) => n.file_id)
  const treeNames = state.checkedNodes.map((n) => n.name)

  // Keep search-result selections that are not in the tree
  const searchOnlyIds = selectedIds.value.filter((id) => !treeIds.includes(id))
  const searchOnlyNames = selectedNames.value.filter(
    (_, i) => !treeIds.includes(selectedIds.value[i]),
  )

  selectedIds.value = [...treeIds, ...searchOnlyIds]
  selectedNames.value = [...treeNames, ...searchOnlyNames]
}

function handleClear() {
  treeRef.value?.setCheckedKeys([])
  selectedIds.value = []
  selectedNames.value = []
}

function handleConfirm() {
  emit('confirm', [...selectedIds.value], [...selectedNames.value])
  dialogVisible.value = false
}
</script>

<style scoped>
.folder-tree-container {
  min-height: 200px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.search-input {
  flex: 1;
}

.index-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  white-space: nowrap;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: default;
  flex-shrink: 0;
}

.index-badge.idle {
  color: #909399;
  background: #f4f4f5;
}

.index-badge.building {
  color: #e6a23c;
  background: #fdf6ec;
}

.index-badge.ready {
  color: #67c23a;
  background: #f0f9eb;
}

.badge-text {
  font-size: 12px;
}

.load-error {
  margin-bottom: 12px;
}

.status-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 120px;
  color: #909399;
  font-size: 14px;
}

/* Search results */
.search-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s;
}

.search-result-item:hover {
  background: #f5f7fa;
}

.search-result-item.selected {
  background: #ecf5ff;
}

.result-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.result-name {
  font-size: 14px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.result-path {
  font-size: 12px;
  color: #909399;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Tree */
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.node-icon {
  color: #e6a23c;
  flex-shrink: 0;
}

.node-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Footer */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.selected-hint {
  font-size: 13px;
  color: #606266;
}

.footer-buttons {
  display: flex;
  gap: 8px;
}
</style>

<style>
/* Global: highlight mark inside v-html */
.hl {
  background-color: #fef08a;
  color: #1a1a1a;
  border-radius: 2px;
  padding: 0 1px;
}
</style>
