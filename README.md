# 阿里云盘重复文件清理工具

扫描阿里云盘中的重复文件，支持批量删除（移至回收站或永久删除），帮助释放云盘空间。

## 功能特性

- **扫描重复文件**：递归遍历整个云盘，按文件内容哈希（SHA1）和大小识别重复文件
- **实时进度**：扫描过程中实时显示已发现的重复文件列表，无需等待扫描完成
- **暂停 / 继续 / 停止**：扫描过程中可随时暂停或停止，使用已扫描出的结果进行删除
- **批量删除**：支持移至回收站（可恢复）和永久删除两种方式
- **智能默认勾选**：扫描完成后自动勾选每组重复文件中的副本（保留最新版本）
- **文件详情**：点击文件可查看完整路径、大小、修改时间、内容哈希等信息
- **筛选与排序**：按文件类型（视频、图片、音频、文档等）筛选，支持多种排序方式
- **分页显示**：支持每页 20 / 50 / 100 条显示
- **历史记录**：查看所有删除任务的详细记录，包含每个文件的操作结果
- **刷新恢复**：页面刷新后自动恢复扫描进度和已发现的文件列表
- **QR 码登录**：扫描二维码登录阿里云盘，无需输入账号密码

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + Pinia |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy + aiosqlite |
| 通信 | SSE（Server-Sent Events）实时推送扫描/删除进度 |
| 部署 | Docker + Docker Compose + Nginx |

## 快速开始

### 方式一：Docker Compose（推荐）

**1. 克隆项目**

```bash
git clone <repo-url>
cd aliyun
```

**2. 配置环境变量**

```bash
cp .env.example .env
```

编辑 `.env` 文件，填写以下必填项：

```env
# 阿里云盘开放平台应用凭证（在 https://open.alipan.com/ 创建应用获取）
ALIYUN_CLIENT_ID=your_client_id
ALIYUN_CLIENT_SECRET=your_client_secret

# Token 加密密钥（用以下命令生成）
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your_fernet_key
```

**3. 启动服务**

```bash
docker-compose up -d --build
```

**4. 访问**

打开浏览器访问 `http://localhost`，扫描二维码登录阿里云盘即可使用。

---

### 方式二：本地开发

**后端**

```bash
cd backend

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -e .

# 配置环境变量
cp ../.env.example .env
# 编辑 .env 填写 ALIYUN_CLIENT_ID、ALIYUN_CLIENT_SECRET、ENCRYPTION_KEY

# 启动后端
uvicorn app.main:app --reload
# 后端运行在 http://localhost:8000
```

**前端**

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（自动代理 /api 到后端 8000 端口）
npm run dev
# 前端运行在 http://localhost:5173
```

## 环境变量说明

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `ALIYUN_CLIENT_ID` | ✅ | — | 阿里云盘开放平台应用 Client ID |
| `ALIYUN_CLIENT_SECRET` | ✅ | — | 阿里云盘开放平台应用 Client Secret |
| `ENCRYPTION_KEY` | ✅ | — | Fernet 对称加密密钥，用于加密存储 Token |
| `DATABASE_URL` | — | `sqlite:///./data/app.db` | SQLite 数据库路径 |
| `API_CALL_INTERVAL_MS` | — | `200` | API 调用间隔（毫秒），避免触发限流 |
| `CORS_ORIGINS` | — | `["http://localhost:5173","http://localhost:80"]` | 允许跨域的前端地址 |
| `OAUTH_REDIRECT_URI` | — | `http://localhost:8000/api/auth/callback` | OAuth 回调地址 |

生成 `ENCRYPTION_KEY`：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 使用说明

### 登录

打开页面后会显示二维码，使用阿里云盘 App 扫码登录。

### 扫描重复文件

1. 点击「扫描重复文件」按钮开始扫描
2. 扫描过程中实时显示已发现的重复文件组
3. 可点击「暂停」暂停扫描，点击「继续」恢复
4. 点击「停止并使用当前结果」可提前结束扫描，使用已发现的结果

### 删除文件

1. 扫描完成后，系统自动勾选每组中的副本文件（保留最新版本）
2. 可手动调整勾选，或使用「保留最新」/「保留最早」快速选择
3. 点击底部「移至回收站」或「永久删除」执行删除
   - **移至回收站**：文件可从阿里云盘回收站恢复（注意：回收站文件仍占用空间）
   - **永久删除**：不可恢复，请谨慎操作

### 查看历史记录

点击右上角「历史记录」可查看所有删除任务，包含每个文件的操作结果和错误信息。

## 项目结构

```
aliyun/
├── backend/                  # Python FastAPI 后端
│   ├── app/
│   │   ├── api/              # 路由（auth、scan、delete、tasks）
│   │   ├── core/             # 工具（加密、文件类型、限流）
│   │   ├── db/               # 数据库模型和仓库
│   │   ├── models/           # Pydantic 数据模型
│   │   ├── services/         # 业务逻辑（扫描、删除、阿里云客户端）
│   │   ├── config.py         # 配置管理
│   │   └── main.py           # FastAPI 应用入口
│   ├── tests/                # 单元测试
│   └── pyproject.toml
├── frontend/                 # Vue 3 前端
│   ├── src/
│   │   ├── api/              # HTTP 客户端和接口定义
│   │   ├── components/       # 通用组件
│   │   ├── composables/      # 组合式函数（SSE、筛选、选择等）
│   │   ├── router/           # 路由配置
│   │   ├── stores/           # Pinia 状态管理
│   │   ├── types/            # TypeScript 类型定义
│   │   └── views/            # 页面视图
│   └── package.json
├── docker-compose.yml
└── .env.example
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/qrcode` | 获取登录二维码 |
| `POST` | `/api/auth/qrcode/poll` | 轮询二维码扫描状态 |
| `GET` | `/api/auth/status` | 获取当前登录状态 |
| `POST` | `/api/auth/logout` | 退出登录 |
| `POST` | `/api/scan/start` | 开始扫描重复文件 |
| `GET` | `/api/scan/progress/{task_id}` | SSE 流：扫描进度 |
| `POST` | `/api/scan/pause/{task_id}` | 暂停扫描 |
| `POST` | `/api/scan/resume/{task_id}` | 继续扫描 |
| `POST` | `/api/scan/stop/{task_id}` | 停止扫描并返回当前结果 |
| `POST` | `/api/delete/start` | 开始批量删除 |
| `GET` | `/api/delete/progress/{task_id}` | SSE 流：删除进度 |
| `GET` | `/api/tasks` | 获取删除任务历史列表 |
| `GET` | `/api/tasks/{task_id}` | 获取任务详情及文件列表 |

## 注意事项

- 移至回收站的文件**仍然占用云盘空间**，需要手动清空回收站才能释放
- 后端使用内存存储扫描任务状态，**重启后端服务会导致进行中的扫描任务丢失**
- 扫描大量文件时建议使用暂停功能分批处理，避免一次性等待时间过长
- 阿里云盘 API 有调用频率限制，`API_CALL_INTERVAL_MS` 建议不低于 200ms

## License

MIT
