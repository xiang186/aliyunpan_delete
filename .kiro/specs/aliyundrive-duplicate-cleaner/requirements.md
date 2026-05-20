# 需求文档

## 简介

本项目是一个前后端分离的 Web 应用，用于批量删除阿里云盘中的重复文件。阿里云盘官方界面的"重复文件清理"功能每次仅能筛选并操作几百个文件，对于拥有几十万重复文件的用户而言效率极低。本应用通过调用阿里云盘官方 API，突破官方界面的批量限制，支持一次性获取全量重复文件列表并进行批量删除（移至回收站），显著提升清理效率。

## 词汇表

- **System**：本 Web 应用整体系统
- **Frontend**：前端 Vue/React 单页应用，运行于用户浏览器
- **Backend**：后端服务，负责与阿里云盘 API 通信及业务逻辑处理
- **AliyunDrive_API**：阿里云盘官方开放 API
- **User**：使用本应用的阿里云盘 VIP 会员用户
- **Duplicate_File**：在阿里云盘中内容完全相同（通过文件哈希值判断）的多个文件中，除保留一份外的其余副本
- **Duplicate_Group**：一组内容相同的重复文件集合
- **Access_Token**：用于调用阿里云盘 API 的身份认证令牌
- **Refresh_Token**：用于刷新 Access_Token 的长效令牌
- **Recycle_Bin**：阿里云盘回收站，被删除的文件将移入此处
- **Task**：后端执行的一次批量删除操作任务
- **File_Type**：文件的媒体类型分类，包括：视频（video）、图片（image）、音频（audio）、文档（document）、压缩包（archive）、其他（other）

---

## 需求

### 需求 1：用户身份认证

**用户故事：** 作为阿里云盘 VIP 用户，我希望通过安全的方式登录本应用，以便应用能够代表我调用阿里云盘 API。

#### 验收标准

1. THE Frontend SHALL 提供阿里云盘 OAuth 授权登录入口，引导用户完成授权流程。
2. WHEN 用户完成 OAuth 授权后，THE Backend SHALL 获取并安全存储该用户的 Access_Token 与 Refresh_Token。
3. WHEN Access_Token 过期时，THE Backend SHALL 使用 Refresh_Token 自动刷新 Access_Token，无需用户重新登录。
4. IF Refresh_Token 失效或刷新失败，THEN THE Backend SHALL 通知 Frontend 要求用户重新授权。
5. THE Backend SHALL 将 Token 信息仅存储于服务端 Session 或加密存储中，不在前端明文暴露。

---

### 需求 2：获取全量重复文件列表

**用户故事：** 作为用户，我希望一次性获取网盘中所有重复文件的完整列表，而不受官方界面每次几百条的限制，以便我能全面了解重复文件情况。

#### 验收标准

1. WHEN 用户触发"扫描重复文件"操作，THE Backend SHALL 调用 AliyunDrive_API 的重复文件查询接口，分页获取所有重复文件数据，直至获取完整列表。
2. WHILE 扫描任务进行中，THE Backend SHALL 向 Frontend 实时推送当前已获取的文件数量与扫描进度百分比。
3. WHEN 扫描完成后，THE Backend SHALL 将所有 Duplicate_Group 及其包含的 Duplicate_File 信息返回给 Frontend。
4. THE Backend SHALL 对每个 Duplicate_Group 返回以下信息：文件名、文件大小、文件哈希值、重复数量、各副本的文件 ID 与所在路径。
5. IF AliyunDrive_API 返回错误或超时，THEN THE Backend SHALL 记录错误详情并向 Frontend 返回包含错误原因的响应，不中断已获取的数据。

---

### 需求 3：重复文件列表展示与筛选

**用户故事：** 作为用户，我希望在界面上清晰地浏览、搜索和筛选重复文件列表，以便我能快速定位需要删除的文件。

#### 验收标准

1. WHEN 扫描完成后，THE Frontend SHALL 以分组方式展示所有 Duplicate_Group，每组显示文件名、文件大小、重复副本数量。
2. THE Frontend SHALL 支持按文件名关键词对 Duplicate_Group 列表进行实时过滤。
3. THE Frontend SHALL 支持按文件大小（升序/降序）和重复数量（升序/降序）对列表进行排序。
4. WHEN 用户展开某个 Duplicate_Group 时，THE Frontend SHALL 显示该组内每个副本的完整路径、文件大小与最后修改时间。
5. THE Frontend SHALL 在页面顶部展示汇总统计信息，包括：重复文件组总数、重复副本总数、可释放空间总量（字节）。
6. THE Frontend SHALL 提供按 File_Type 筛选的选项，支持的类型包括：视频、图片、音频、文档、压缩包、其他，以及"全部"选项。
7. WHEN 用户选择某个 File_Type 筛选条件时，THE Frontend SHALL 仅展示文件扩展名归属于该类型的 Duplicate_Group，并实时更新汇总统计信息以反映当前筛选结果。
8. THE Backend SHALL 在返回 Duplicate_Group 信息时，为每个文件附带其 File_Type 分类标签，分类规则基于文件扩展名：视频（mp4/mkv/avi/mov/wmv/flv/webm 等）、图片（jpg/jpeg/png/gif/bmp/webp/heic 等）、音频（mp3/flac/wav/aac/ogg/m4a 等）、文档（pdf/doc/docx/xls/xlsx/ppt/pptx/txt/md 等）、压缩包（zip/rar/7z/tar/gz/bz2 等），其余扩展名归类为其他。
9. THE Frontend SHALL 支持 File_Type 筛选与文件名关键词搜索、排序条件同时生效，多个筛选条件取交集。

---

### 需求 4：批量选择重复文件

**用户故事：** 作为用户，我希望灵活地批量选择要删除的重复文件副本，以便我能精确控制删除范围。

#### 验收标准

1. THE Frontend SHALL 为每个 Duplicate_Group 提供"保留最新版本，删除其余副本"的一键选择操作。
2. THE Frontend SHALL 为每个 Duplicate_Group 提供"保留最早版本，删除其余副本"的一键选择操作。
3. THE Frontend SHALL 提供"全选所有重复副本（每组保留一个）"的全局操作按钮。
4. THE Frontend SHALL 提供"取消全选"的全局操作按钮。
5. THE Frontend SHALL 允许用户在 Duplicate_Group 展开视图中手动勾选或取消勾选单个文件副本。
6. WHILE 用户进行选择操作时，THE Frontend SHALL 实时更新已选文件数量与预计可释放空间的统计显示。
7. THE Frontend SHALL 确保每个 Duplicate_Group 中至少保留一个文件副本，当用户尝试选中某组全部副本时，THE Frontend SHALL 自动取消选中该组中最后一个被选中的副本并提示用户。

---

### 需求 5：批量删除重复文件（移至回收站）

**用户故事：** 作为用户，我希望将选中的重复文件批量移至回收站，以便释放网盘空间，同时保留恢复的可能性。

#### 验收标准

1. WHEN 用户确认执行删除操作，THE Frontend SHALL 向 Backend 提交包含所有选中文件 ID 的删除请求。
2. THE Backend SHALL 将删除请求拆分为每批不超过 100 个文件 ID 的子批次，依次调用 AliyunDrive_API 的批量移至回收站接口。
3. WHILE 删除任务执行中，THE Backend SHALL 向 Frontend 实时推送当前已处理文件数、总文件数与任务进度百分比。
4. WHEN 删除任务完成后，THE Backend SHALL 向 Frontend 返回操作结果摘要，包括：成功删除数量、失败数量及失败文件的 ID 与错误原因。
5. IF 某个子批次调用 AliyunDrive_API 失败，THEN THE Backend SHALL 记录该批次的错误信息并继续处理后续批次，不中断整体任务。
6. THE Backend SHALL 对删除操作进行幂等处理：IF 某文件 ID 已不存在或已在回收站中，THEN THE Backend SHALL 将其计入成功数量，不视为错误。

---

### 需求 6：操作安全确认

**用户故事：** 作为用户，我希望在执行批量删除前有明确的确认步骤，以防止误操作导致重要文件被删除。

#### 验收标准

1. WHEN 用户点击"执行删除"按钮时，THE Frontend SHALL 弹出确认对话框，显示本次将删除的文件总数与预计释放空间。
2. THE Frontend SHALL 在确认对话框中明确说明文件将被移至回收站而非永久删除。
3. WHEN 用户在确认对话框中点击"取消"时，THE Frontend SHALL 关闭对话框并保持当前选择状态不变。
4. THE Frontend SHALL 在删除任务执行期间禁用"执行删除"按钮，防止重复提交。

---

### 需求 7：任务历史记录

**用户故事：** 作为用户，我希望查看历次删除操作的记录，以便追溯操作历史和核查删除结果。

#### 验收标准

1. THE Backend SHALL 在每次删除任务完成后，将任务记录持久化存储，包括：任务执行时间、删除文件总数、成功数量、失败数量、释放空间大小。
2. THE Frontend SHALL 提供任务历史页面，展示所有历史删除任务的摘要列表，按执行时间倒序排列。
3. WHEN 用户点击某条历史任务时，THE Frontend SHALL 展示该任务的详细信息，包括每个被删除文件的文件名、路径与操作结果。

---

### 需求 8：API 调用频率控制

**用户故事：** 作为系统，我希望对阿里云盘 API 的调用频率进行控制，以避免触发官方的限流机制导致账号异常。

#### 验收标准

1. THE Backend SHALL 在连续 API 调用之间保持不低于 100 毫秒的间隔，避免触发 AliyunDrive_API 的频率限制。
2. IF AliyunDrive_API 返回频率限制错误（HTTP 429），THEN THE Backend SHALL 按指数退避策略暂停调用，初始等待时间为 1 秒，最大等待时间为 60 秒，最多重试 5 次。
3. THE Backend SHALL 支持通过配置文件调整 API 调用间隔参数，默认值为 200 毫秒。

---

### 需求 9：永久删除功能

**用户故事：** 作为用户，我希望能够选择永久删除重复文件（不经过回收站），以便在确认不需要恢复的情况下彻底释放网盘空间。

#### 验收标准

1. THE Frontend SHALL 在批量选择完成后，同时提供"移至回收站"与"永久删除"两个独立的操作入口，两者互斥，用户每次只能选择其中一种方式执行。
2. WHEN 用户点击"永久删除"按钮时，THE Frontend SHALL 弹出二次确认对话框，明确告知用户：本次操作将永久删除所选文件，操作不可撤销，文件无法从回收站恢复。
3. THE Frontend SHALL 在永久删除确认对话框中要求用户主动输入指定确认文本（如"确认永久删除"）后，方可激活最终确认按钮，防止误操作。
4. WHEN 用户完成二次确认后，THE Frontend SHALL 向 Backend 提交包含所有选中文件 ID 的永久删除请求，请求中须包含操作类型标识以区别于移至回收站操作。
5. THE Backend SHALL 将永久删除请求拆分为每批不超过 100 个文件 ID 的子批次，依次调用 AliyunDrive_API 的批量永久删除接口。
6. WHILE 永久删除任务执行中，THE Backend SHALL 向 Frontend 实时推送当前已处理文件数、总文件数与任务进度百分比。
7. WHEN 永久删除任务完成后，THE Backend SHALL 向 Frontend 返回操作结果摘要，包括：成功永久删除数量、失败数量及失败文件的 ID 与错误原因。
8. IF 某个子批次调用 AliyunDrive_API 永久删除接口失败，THEN THE Backend SHALL 记录该批次的错误信息并继续处理后续批次，不中断整体任务。
9. THE Backend SHALL 在任务历史记录中区分"移至回收站"与"永久删除"两种操作类型，永久删除记录须附加不可恢复标识。
10. THE Backend SHALL 对永久删除操作进行幂等处理：IF 某文件 ID 已不存在，THEN THE Backend SHALL 将其计入成功数量，不视为错误。
