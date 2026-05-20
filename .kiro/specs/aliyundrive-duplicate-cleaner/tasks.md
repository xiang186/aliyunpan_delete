# 实现计划：阿里云盘重复文件批量清理工具

## 概述

本计划将设计文档中的架构拆解为一系列可增量执行的编码任务，按"后端基础 → 后端核心服务 → 前端基础 → 前端核心功能 → 集成与收尾"的顺序推进，确保每一步都能独立验证，最终将所有模块串联为完整应用。

## 任务

- [x] 1. 项目初始化与基础架构搭建
  - 创建后端目录结构：`backend/app/{api,services,models,db,core}/`，添加 `pyproject.toml`（依赖：fastapi、uvicorn、sqlalchemy、pydantic、httpx、cryptography、hypothesis、pytest、pytest-asyncio）
  - 创建前端目录结构：`frontend/src/{views,components,stores,composables,api}/`，初始化 `package.json`（依赖：vue3、typescript、vite、pinia、element-plus、axios、vitest、@vue/test-utils）
  - 创建根目录 `docker-compose.yml` 与 `.env.example`，定义 `ALIYUN_CLIENT_ID`、`ALIYUN_CLIENT_SECRET`、`ENCRYPTION_KEY`、`DATABASE_URL` 等环境变量
  - _需求：1.5、8.3_

- [x] 2. 数据库模型与迁移
  - [x] 2.1 实现 SQLAlchemy ORM 模型
    - 在 `backend/app/db/models.py` 中定义 `Session`、`Task`、`TaskFile` 三张表的 ORM 类，字段与设计文档 SQL 定义完全一致
    - 在 `backend/app/db/database.py` 中实现 `get_db()` 依赖注入与数据库初始化函数 `init_db()`
    - _需求：7.1、9.9_

  - [ ]* 2.2 编写任务历史 Round-Trip 属性测试
    - **属性 10：任务历史持久化的 Round-Trip 完整性**
    - 使用 Hypothesis 生成随机 `delete_type`、计数值、时间戳，写入 SQLite 后查询，断言返回数据与写入数据完全一致
    - **验证：需求 7.1、9.9**

- [x] 3. 核心工具模块实现
  - [x] 3.1 实现文件类型分类函数
    - 在 `backend/app/core/file_type.py` 中实现 `classify_file_type(filename: str) -> FileType`，按设计文档 `FILE_TYPE_MAP` 映射扩展名，大小写不敏感，无扩展名或未知扩展名返回 `FileType.OTHER`
    - 定义 `FileType` 枚举：`VIDEO / IMAGE / AUDIO / DOCUMENT / ARCHIVE / OTHER`
    - _需求：3.8_

  - [ ]* 3.2 编写文件类型分类完备性属性测试
    - **属性 1：文件类型分类的完备性与确定性**
    - 使用 `@given(st.text())` 生成任意文件名，断言 `classify_file_type` 始终返回有效 `FileType` 枚举值，不抛出异常，且对相同输入结果一致
    - **验证：需求 3.8**

  - [x] 3.3 实现 API 频率控制器
    - 在 `backend/app/core/rate_limiter.py` 中实现 `RateLimiter` 类：`call_with_rate_limit(coro, *args)`、`_exponential_backoff(attempt: int) -> float`
    - 退避公式：`min(2 ** attempt, 60)`，最多重试 5 次，调用间隔默认 200ms，支持通过 `RateLimitConfig` 配置
    - _需求：8.1、8.2、8.3_

  - [ ]* 3.4 编写指数退避单调递增属性测试
    - **属性 9：指数退避等待时间的单调递增性与上界约束**
    - 使用 `@given(st.integers(min_value=0, max_value=4))` 生成重试次数 n，断言 `_exponential_backoff(n) <= _exponential_backoff(n+1)` 且 `_exponential_backoff(n) <= 60`
    - **验证：需求 8.2**

  - [x] 3.5 实现 Token 加密存储工具
    - 在 `backend/app/core/crypto.py` 中实现 `encrypt_token(token: str) -> str` 与 `decrypt_token(encrypted: str) -> str`，使用 `cryptography` 库的 Fernet 对称加密
    - _需求：1.5_

- [x] 4. 阿里云盘 API 客户端实现
  - [x] 4.1 实现 `AliyunDriveClient`
    - 在 `backend/app/services/aliyun_client.py` 中实现：`get_duplicate_files(access_token, marker)`、`batch_trash(access_token, file_ids)`、`batch_delete_permanently(access_token, file_ids)`、`refresh_token(refresh_token)`
    - 使用 `httpx.AsyncClient`，超时 30s，所有调用经过 `RateLimiter`
    - _需求：2.1、5.2、8.1、9.5_

  - [ ]* 4.2 编写批量分批完备性属性测试
    - **属性 6：批量删除分批的完备性与边界约束**
    - 使用 `@given(st.lists(st.text(), min_size=0, max_size=10000))` 生成任意文件 ID 列表，断言分批后每批 ≤ 100，所有批次并集等于原始集合，批次间无重复
    - **验证：需求 5.2、9.5**

- [x] 5. 认证服务实现
  - [x] 5.1 实现 `AuthService`
    - 在 `backend/app/services/auth_service.py` 中实现：`generate_auth_url()`、`exchange_code_for_token(code)`、`refresh_access_token(session_id)`、`get_valid_access_token(session_id)`（自动刷新）、`revoke_session(session_id)`、`is_authenticated(session_id)`
    - Token 使用 `crypto.py` 加密后存入 `sessions` 表
    - _需求：1.1、1.2、1.3、1.4、1.5_

  - [x] 5.2 实现认证 API 路由
    - 在 `backend/app/api/auth.py` 中实现：`GET /api/auth/login-url`、`GET /api/auth/callback`、`GET /api/auth/status`、`POST /api/auth/logout`
    - _需求：1.1、1.2、1.4_

  - [ ]* 5.3 编写认证服务单元测试
    - 测试 Token 刷新逻辑（Access Token 过期时自动刷新）、Refresh Token 失效时通知前端、Session 管理与加密存储
    - _需求：1.3、1.4、1.5_

- [x] 6. 扫描服务实现
  - [x] 6.1 实现 `ScanService` 与后台任务
    - 在 `backend/app/services/scan_service.py` 中实现：`start_scan(session_id) -> str`（创建任务、启动后台任务）、`_fetch_all_duplicates(session_id, task_id)`（分页拉取、构建 `DuplicateGroup`、推送 SSE 进度事件）
    - 使用 `asyncio.Queue` 在后台任务与 SSE 生成器之间传递事件
    - _需求：2.1、2.2、2.3、2.4、2.5_

  - [x] 6.2 实现扫描 SSE 生成器
    - 在 `backend/app/api/scan.py` 中实现：`POST /api/scan/start`、`GET /api/scan/progress/{task_id}`（返回 `EventSourceResponse`）
    - SSE 事件格式遵循设计文档：`ScanProgressEvent`、`ScanCompleteEvent`、`ScanErrorEvent`
    - _需求：2.2、2.3、2.5_

  - [ ]* 6.3 编写扫描服务单元测试
    - 测试分页拉取逻辑、SSE 事件序列化、扫描中断时返回部分数据
    - _需求：2.2、2.5_

- [x] 7. 删除服务实现
  - [x] 7.1 实现 `DeleteService` 与后台任务
    - 在 `backend/app/services/delete_service.py` 中实现：`start_delete(session_id, file_ids, delete_type) -> str`、`_execute_batch_delete(session_id, task_id, ...)`（分批调用 API、幂等处理、推送 SSE 进度事件）
    - 幂等处理：文件不存在（API 返回特定错误码）时计入成功
    - _需求：5.1、5.2、5.3、5.4、5.5、5.6、9.4、9.5、9.6、9.7、9.8、9.10_

  - [x] 7.2 实现删除 SSE 生成器
    - 在 `backend/app/api/delete.py` 中实现：`POST /api/delete/start`、`GET /api/delete/progress/{task_id}`（返回 `EventSourceResponse`）
    - SSE 事件格式：`DeleteProgressEvent`、`DeleteCompleteEvent`
    - _需求：5.3、5.4、9.6、9.7_

  - [ ]* 7.3 编写删除结果摘要不变量属性测试
    - **属性 7：删除结果摘要的数量不变量**
    - 使用 Hypothesis 生成随机成功/失败分布的批次结果，断言 `success_count + failed_count == total_requested`，且每个文件 ID 在结果中有且仅有一个状态
    - **验证：需求 5.4、9.7**

  - [ ]* 7.4 编写删除幂等性属性测试
    - **属性 8：删除操作的幂等性**
    - 使用 Hypothesis 生成含已删除文件 ID 的请求，断言不存在的文件 ID 被计入成功数量，不影响其他文件处理结果
    - **验证：需求 5.6、9.10**

- [x] 8. 任务历史仓库与 API 实现
  - [x] 8.1 实现 `TaskRepository`
    - 在 `backend/app/db/task_repository.py` 中实现：`create_task`、`update_task`、`get_task`、`list_tasks`、`get_task_files`
    - `list_tasks` 按 `started_at` 倒序排列，区分 `delete_type`（trash/permanent）
    - _需求：7.1、7.2、9.9_

  - [x] 8.2 实现任务历史 API 路由
    - 在 `backend/app/api/tasks.py` 中实现：`GET /api/tasks`、`GET /api/tasks/{task_id}`
    - _需求：7.2、7.3_

- [x] 9. 后端集成检查点
  - 确保所有后端测试通过，ask the user if questions arise.
  - 验证 FastAPI 应用可正常启动，所有路由注册正确，数据库初始化无误

- [x] 10. 前端基础架构搭建
  - [x] 10.1 配置 Vite + Vue 3 + TypeScript 项目
    - 配置 `vite.config.ts`（代理 `/api` 到后端）、`tsconfig.json`、Element Plus 按需引入
    - 在 `src/api/client.ts` 中实现 Axios 实例，配置 baseURL、请求拦截器（注入 session_id）、响应拦截器（处理 401 跳转登录）
    - _需求：1.1、1.4_

  - [x] 10.2 配置 Pinia stores
    - 实现 `stores/auth.ts`（登录状态、session_id）、`stores/scan.ts`（扫描结果、进度）、`stores/selection.ts`（选中文件集合）、`stores/task.ts`（任务历史列表）
    - _需求：3.1、4.6、7.2_

  - [x] 10.3 实现 `useSSE` composable
    - 在 `composables/useSSE.ts` 中封装 `EventSource`，支持自动重连、事件类型分发（progress/complete/error）、连接状态管理
    - _需求：2.2、5.3、9.6_

- [x] 11. 前端筛选与选择逻辑实现
  - [x] 11.1 实现 `useFileFilter` composable
    - 在 `composables/useFileFilter.ts` 中实现：按文件名关键词过滤（大小写不敏感）、按 `FileType` 过滤、按文件大小/重复数量排序，多条件取交集，返回响应式计算属性
    - _需求：3.2、3.3、3.6、3.7、3.9_

  - [ ]* 11.2 编写多条件筛选交集语义属性测试（Vitest）
    - **属性 2：多条件筛选的正确性与交集语义**
    - 使用随机 `DuplicateGroup` 列表与随机类型/关键词/排序组合，断言结果满足交集语义，排序不改变元素集合
    - **验证：需求 3.2、3.6、3.7、3.9**

  - [x] 11.3 实现 `useSelection` composable
    - 在 `composables/useSelection.ts` 中实现：单文件勾选/取消、全选（每组保留一个）、取消全选、"保留最新/最早"策略选择
    - 防误删保护：当某组所有副本均被选中时，自动取消最后一个并提示
    - _需求：4.1、4.2、4.3、4.4、4.5、4.7_

  - [ ]* 11.4 编写防误删全组保护属性测试（Vitest）
    - **属性 4：防误删全组保护的不变性**
    - 使用随机文件组与随机选择操作序列，断言任意操作后每组未选中副本数量 ≥ 1
    - **验证：需求 4.3、4.7**

  - [ ]* 11.5 编写保留策略选择正确性属性测试（Vitest）
    - **属性 5：保留策略选择的正确性**
    - 使用随机文件组（含随机修改时间），断言"保留最新"后选中集合等于除最新文件外的所有副本，"保留最早"同理
    - **验证：需求 4.1、4.2**

- [x] 12. 前端统计汇总逻辑实现
  - [x] 12.1 实现统计汇总计算逻辑
    - 在 `stores/scan.ts` 或独立 composable 中实现：基于当前可见列表（筛选后）计算组总数、副本总数、可释放空间字节数，选择状态变化时实时更新
    - _需求：3.5、3.7、4.6_

  - [ ]* 12.2 编写统计与可见列表一致性属性测试（Vitest）
    - **属性 3：汇总统计与当前可见列表的一致性**
    - 使用随机文件组列表与随机筛选条件，断言统计值等于可见列表字段的精确聚合值
    - **验证：需求 3.5、3.7、4.6**

- [x] 13. 前端核心视图与组件实现
  - [x] 13.1 实现 `LoginView.vue`
    - 展示"阿里云盘 OAuth 登录"按钮，调用 `GET /api/auth/login-url` 后跳转授权页
    - 处理 OAuth 回调（从 URL 参数读取 session_id），更新 `auth` store，跳转主页
    - _需求：1.1_

  - [x] 13.2 实现 `FilterBar.vue` 与 `StatsSummary.vue`
    - `FilterBar`：文件名搜索输入框、FileType 筛选标签、文件大小/重复数量排序选择器，绑定 `useFileFilter`
    - `StatsSummary`：展示组总数、副本总数、可释放空间，数据来自 `scan` store 的计算属性
    - _需求：3.2、3.3、3.5、3.6、3.9_

  - [x] 13.3 实现 `DuplicateGroupItem.vue` 与 `DuplicateGroupList.vue`
    - `DuplicateGroupItem`：展示文件名、大小、副本数，可展开显示每个副本的路径、大小、修改时间，提供"保留最新/最早"按钮，绑定 `useSelection`
    - `DuplicateGroupList`：虚拟滚动列表（使用 Element Plus `el-virtual-list` 或 `vue-virtual-scroller`），渲染所有可见分组
    - _需求：3.1、3.4、4.1、4.2、4.5_

  - [x] 13.4 实现 `SelectionToolbar.vue`
    - 展示已选文件数量与预计释放空间，提供"全选（每组保留一个）"、"取消全选"按钮，以及"移至回收站"与"永久删除"两个独立操作入口
    - _需求：4.3、4.4、4.6、9.1_

  - [x] 13.5 实现 `DeleteConfirmDialog.vue`
    - 弹窗展示：将删除文件总数、预计释放空间、"文件将移至回收站"说明
    - 确认/取消按钮，执行期间禁用确认按钮
    - _需求：6.1、6.2、6.3、6.4_

  - [x] 13.6 实现 `PermanentDeleteDialog.vue`
    - 弹窗展示：永久删除警告、不可撤销说明，要求用户输入"确认永久删除"文本后激活确认按钮
    - _需求：9.2、9.3_

  - [ ]* 13.7 编写永久删除确认文本精确匹配属性测试（Vitest）
    - **属性 11：永久删除确认文本的精确匹配验证**
    - 使用 `fc.string()` 或随机字符串生成任意输入，断言仅当输入与"确认永久删除"完全相同时按钮激活，其他任何字符串（含前缀、后缀、大小写变体）均不激活
    - **验证：需求 9.3**

  - [x] 13.8 实现 `ProgressPanel.vue`
    - 展示实时进度条（已处理/总数/百分比），绑定 `useSSE` 接收 progress/complete/error 事件，complete 后展示结果摘要（成功数、失败数、释放空间、失败文件列表）
    - _需求：2.2、5.3、5.4、9.6、9.7_

  - [x] 13.9 实现 `ScanView.vue` 主页
    - 组合 `FilterBar`、`StatsSummary`、`DuplicateGroupList`、`SelectionToolbar`、`ProgressPanel`
    - 扫描按钮触发 `POST /api/scan/start`，然后通过 `useSSE` 订阅进度
    - _需求：2.1、2.2、2.3、3.1_

- [x] 14. 前端任务历史页面实现
  - [x] 14.1 实现 `TaskHistoryDetail.vue` 与 `HistoryView.vue`
    - `HistoryView`：调用 `GET /api/tasks`，展示历史任务摘要列表（时间倒序），区分"移至回收站"与"永久删除"类型
    - `TaskHistoryDetail`：点击任务后调用 `GET /api/tasks/{task_id}`，展示每个文件的文件名、路径、操作结果
    - _需求：7.2、7.3、9.9_

- [x] 15. 前端集成检查点
  - 确保所有前端测试通过，ask the user if questions arise.
  - 验证前端开发服务器可正常启动，各页面路由跳转正确，API 代理配置有效

- [ ] 16. 后端集成测试
  - [ ] 16.1 编写 OAuth 回调流程集成测试
    - 使用 `pytest + httpx.AsyncClient` 测试完整 OAuth 回调流程，Mock 阿里云盘 API 的 Token 换取接口
    - _需求：1.1、1.2_

  - [ ]* 16.2 编写扫描任务 SSE 集成测试
    - 测试 `POST /api/scan/start` → `GET /api/scan/progress/{task_id}` 完整流程，验证 SSE 事件序列（progress → complete）
    - _需求：2.1、2.2、2.3_

  - [ ]* 16.3 编写删除任务集成测试
    - 测试 trash 与 permanent 两种删除类型的完整流程，验证分批逻辑、幂等处理、任务历史持久化
    - _需求：5.1、5.2、5.4、5.6、9.4、9.5、9.9_

  - [ ]* 16.4 编写 API 限流重试集成测试
    - Mock 阿里云盘 API 返回 429，验证指数退避重试行为（等待时间递增、最多重试 5 次）
    - _需求：8.2_

- [x] 17. 部署配置
  - [x] 17.1 编写后端 `Dockerfile`
    - 基于 `python:3.11-slim`，安装依赖，暴露 8000 端口，入口命令 `uvicorn app.main:app`
    - _需求：8.3_

  - [x] 17.2 编写前端 `Dockerfile` 与 Nginx 配置
    - 多阶段构建：`node:20-alpine` 构建，`nginx:alpine` 服务静态文件，配置 `/api` 反向代理到后端
    - _需求：1.1_

  - [x] 17.3 完善 `docker-compose.yml`
    - 定义 `backend`、`frontend` 两个服务，挂载 SQLite 数据卷，注入环境变量
    - _需求：8.3_

- [ ] 18. 最终集成检查点
  - 确保所有测试（后端 pytest + 前端 Vitest）全部通过，ask the user if questions arise.
  - 验证 docker-compose 可完整启动，前后端联调 OAuth 登录 → 扫描 → 删除 → 历史查看全流程

## 备注

- 标有 `*` 的子任务为可选测试任务，可在 MVP 阶段跳过以加快交付
- 每个任务均引用了具体需求条款，确保可追溯性
- 属性测试（Hypothesis / Vitest）与单元测试互补，属性测试验证普遍性质，单元测试验证具体示例与边界值
- 检查点任务确保每个阶段完成后系统处于可验证状态
