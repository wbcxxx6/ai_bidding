# AI 招投标文档生成系统

AI 招投标文档生成系统面向企业投标场景，围绕“招标文件解析、项目资料沉淀、章节生成、AI 改写、在线编辑、Word 导出”形成一条完整工作流。系统支持企业知识库和历史标书检索，生成内容时可结合当前项目资料、企业资料和投标经验，帮助团队更快完成投标文件初稿与后续修订。

> 下方产品截图中的项目名称、招标文件名称和客户信息均已脱敏。

## 产品截图

### 项目中心

![项目中心](docs/assets/project-center.svg)

### AI 工作台

![AI 工作台](docs/assets/ai-workbench.svg)

### 管理后台

![管理后台](docs/assets/admin-dashboard.svg)

## 核心功能

| 模块 | 能力 |
| --- | --- |
| 项目中心 | 创建投标项目、上传招标文件、查看项目进度、恢复上次生成状态 |
| 招标文件解析 | 支持 Word、PDF、文本文件上传，提取项目信息、评分点、章节结构和关键要求 |
| 生成流程 | 按“上传文件、文件解析、章节规划、生成投标文件”推进，已完成步骤可回看和修改 |
| AI 工作台 | 三栏式章节编辑、章节导航、项目总览、待办提醒、正文编辑和章节级重写 |
| 选区改写 | 在正文中选中一段内容后，可直接针对选区发起 AI 改写，不必重写整章 |
| 企业知识库 | 上传企业资料、历史标书、项目材料，解析后写入向量库用于 RAG 检索 |
| 多模型配置 | 支持 DeepSeek、通义千问、火山方舟、Moonshot/Kimi、OpenAI、小米 MiMo 等 OpenAI 兼容接口 |
| Word 导出 | 将生成内容导出为 `.docx`，并支持接入 OnlyOffice 在线预览与编辑 |
| 管理后台 | 管理模型配置、知识库资料、项目文件和系统基础数据 |

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、Vite、Element Plus、Pinia、Vue Router、Tiptap |
| 后端 | Flask、Flask-CORS、PyMySQL |
| 数据库 | MySQL 8.x |
| RAG 检索 | PostgreSQL + PGVector + FTS + Rerank，ChromaDB/Milvus 作为开发降级 |
| 文档解析 | Mammoth、PyPDF2 |
| 文档导出 | python-docx、Markdown |
| 在线编辑 | OnlyOffice Document Server，可选 |
| 模型接口 | OpenAI-compatible Chat Completions / Embeddings |

## 项目结构

```text
ai_bidding/
├── api/                  # Flask 蓝图与 HTTP 接口
│   ├── bidding.py        # 招标文件上传、解析、生成、导出
│   ├── files.py          # 项目文件接口
│   ├── generation.py     # 生成任务接口
│   ├── knowledge.py      # 知识库与 RAG 检索
│   ├── settings.py       # 模型配置
│   └── v2/               # V2 项目、章节、工作台接口
├── core/                 # 数据库、模型提供商等基础设施
├── services/             # 文档入库、模型调用、文件处理服务
├── storage/              # 向量库适配
├── export/               # Word 导出能力
├── front/                # Vue 前端应用
├── docs/                 # 产品与架构文档
├── scripts/              # 维护脚本
├── tests/                # 自动化测试
├── main.py               # Flask 应用入口
├── requirements.txt      # Python 依赖
└── .env.example          # 环境变量模板
```

## 本地开发部署

### 1. 克隆项目

```bash
git clone https://github.com/NewbieCoderLab/ai_bidding.git
cd ai_bidding
```

### 2. 准备 Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填写 MySQL、模型 API Key、Embedding 和可选的 OnlyOffice 配置。不要将 `.env` 提交到仓库。

常用配置项：

```ini
PORT=3012

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=bidding

VECTOR_STORE=chroma
VECTOR_COLLECTION=document_embeddings

EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024
```

### 4. 准备 MySQL

创建数据库：

```sql
CREATE DATABASE bidding DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

确认 `.env` 中的账号具备该数据库的读写权限。后端启动时会执行 `core/db.py` 中的表结构初始化逻辑。

### 5. 准备 PostgreSQL RAG

RAG 主路径使用 PostgreSQL + PGVector + Full Text Search。创建数据库并执行迁移：

```bash
psql "$POSTGRES_DSN" -f migrations/postgres/001_rag_pgvector.sql
```

`.env` 至少需要配置：

```ini
POSTGRES_DSN=postgresql://postgres:password@127.0.0.1:5432/ai_bidding
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024
```

如果未配置 PostgreSQL，系统会退回 MySQL 文本检索降级路径；上传入库仍保留 Chroma/Milvus 兼容写入，便于迁移期回滚。

### 6. 启动后端

```bash
python main.py
```

默认地址：

```text
http://localhost:3012
```

### 7. 启动前端

```bash
cd front
npm install
npm run dev
```

默认地址：

```text
http://localhost:5173
```

开发环境下，Vite 会将 `/api` 请求代理到 Flask 后端。

## 生产构建部署

### 1. 构建前端

```bash
cd front
npm install
npm run build
```

构建产物会生成到 `front/dist/`。

### 2. 启动 Flask 托管 SPA

回到项目根目录：

```bash
python main.py
```

当 `front/dist/` 存在时，Flask 会托管前端构建产物：

```text
http://localhost:3012/
http://localhost:3012/admin
```

### 3. 可选：启动 OnlyOffice

如果需要在线预览和编辑 Word 文件，可启动 OnlyOffice Document Server：

```bash
docker run -d \
  --name onlyoffice-documentserver \
  -p 80:80 \
  --restart=always \
  -e JWT_SECRET=fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue \
  onlyoffice/documentserver
```

`.env` 中的 `ONLYOFFICE_JWT_SECRET` 需要与容器 `JWT_SECRET` 保持一致。
前端默认从 `http://localhost` 加载 OnlyOffice 插件脚本；如果你把容器映射到其他端口，例如 `-p 8081:80`，请在前端环境变量中设置：

```ini
VITE_ONLYOFFICE_URL=http://localhost:8081
```

### 4. 可选：旧向量库降级

PostgreSQL + PGVector 是当前 RAG 主路径。ChromaDB/Milvus 仅作为开发和迁移期降级。如果要使用 Milvus 兼容写入：

```ini
VECTOR_STORE=milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_METRIC_TYPE=COSINE
MILVUS_INDEX_TYPE=AUTOINDEX
VECTOR_COLLECTION=document_embeddings
```

如果 Milvus 不可用，兼容写入会回退到 ChromaDB，便于开发调试。

## 主要接口

| 模块 | 前缀 | 说明 |
| --- | --- | --- |
| 招投标流程 | `/api/bidding` | 招标文件上传、解析、生成、导出 |
| 项目文件 | `/api/files`、`/api` | 项目文件、知识库文件、预览下载 |
| 生成任务 | `/api/generation` | 生成记录与任务状态 |
| 用户 | `/api/users` | 轻量用户识别 |
| 模型设置 | `/api/settings` | 模型提供商、API Key、连接测试 |
| V2 工作台 | `/api/v2` | 项目、章节、章节内容、选区改写 |
| 前端应用 | `/` | 用户端 |
| 管理后台 | `/admin` | 管理端 |

## 常用工作流

1. 在项目中心创建项目并上传招标文件。
2. 系统解析招标文件，提取项目概况、评分要求、章节目录和关键约束。
3. 确认或调整章节结构，进入投标文件生成。
4. 在 AI 工作台查看项目总览、章节列表、正文和待办事项。
5. 对整章或选中的段落进行 AI 改写，必要时返回上一步修改信息。
6. 导出 Word 文件，或通过 OnlyOffice 在线编辑。

## 数据与安全

- `.env`、API Key、数据库密码、JWT Secret 不应提交到 Git。
- 上传的招标文件、历史投标文件、企业资料和生成结果默认存储在本地目录，应按部署环境做好访问控制和备份策略。
- `uploads/`、`outputs/`、`chroma_db/` 等运行时目录已被 `.gitignore` 忽略。
- 对外展示截图或演示数据前，应先脱敏项目名称、招标文件名称、客户名称、联系人、金额、地址等信息。

## 开发校验

后端语法检查：

```bash
python3 -m py_compile api/bidding.py api/v2/chapters.py
```

前端构建：

```bash
cd front
npm run build
```

提交前建议检查：

```bash
git status --short
git diff --stat
```

## 许可证

本项目基于 MIT License 开源，详见 [LICENSE](LICENSE)。
