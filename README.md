# AI 招投标文档生成系统

面向企业投标场景的 AI 文档生成系统。项目支持招标文件上传与解析、企业知识库入库、历史投标文件 RAG 检索、多模型提供商配置、投标书章节生成、Word 导出和 OnlyOffice 在线编辑。

当前项目处于原型向企业级架构演进阶段，后端已接入 MySQL 作为业务数据底座，并保留 ChromaDB/Milvus 向量存储适配。

## 功能特性

- 招标文件上传：支持 Word、PDF、文本文件上传与解析。
- 企业知识库：支持上传历史投标文件、企业资料、项目资料，并写入向量库。
- RAG 检索：生成章节时结合当前项目资料和企业历史标书内容。
- 多模型配置：支持 DeepSeek、通义千问、火山方舟、Moonshot/Kimi、OpenAI、小米 MiMo 等 OpenAI 兼容接口。
- MySQL 数据底座：保存项目、文件元数据、知识库、切片、任务、生成标书等业务数据。
- 向量库适配：默认 ChromaDB，本地开发友好；可通过配置切换到 Milvus。
- Word 导出：将 Markdown 内容转换为 `.docx`。
- OnlyOffice 集成：返回 `editorConfig`，支持在线预览和编辑。
- 前端工作台：提供基础项目工作台、知识库、模型配置和生成流程页面。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端框架 | Flask |
| 业务数据库 | MySQL 8.x + PyMySQL |
| 向量数据库 | ChromaDB / Milvus |
| 大模型接口 | OpenAI-compatible Chat Completions |
| Embedding | OpenAI-compatible Embeddings，默认 DashScope `text-embedding-v3` |
| 文档解析 | Mammoth、PyPDF2 |
| Word 导出 | python-docx、Markdown |
| 在线编辑 | OnlyOffice Document Server |
| 前端 | Vue 3 + Vite + Element Plus |

## 项目结构

```text
ai_bidding/
├── api/                  # Flask 蓝图与 HTTP 接口
│   ├── bidding.py        # 招标文件上传、分析、生成、导出
│   ├── knowledge.py      # 知识库、企业文档入库、RAG 检索
│   ├── settings.py       # 模型提供商设置
│   └── users.py          # 用户识别
├── core/                 # 核心基础设施
│   ├── db.py             # MySQL 连接、兼容封装、表结构初始化
│   └── llm_providers.py  # 模型提供商定义与配置读写
├── services/             # 业务服务
│   ├── ingestion_service.py
│   ├── qwen_client.py
│   └── file_to_chroma.py
├── storage/              # 存储适配
│   └── vector_store.py
├── export/               # Word 导出能力
│   └── md_to_word.py
├── front/                # Vue 前端（用户端 + 后台管理）
├── frontend/             # 历史静态前端，已冻结
├── docs/                 # 设计文档
├── legacy/               # 历史代码备份
├── main.py               # Flask 应用入口
├── requirements.txt
├── .env.example          # 环境变量模板，可提交
└── .gitignore
```

## 环境要求

- Python 3.9+
- MySQL 8.x
- Docker，可选，用于运行 OnlyOffice、MySQL、Milvus
- 至少一个大模型 API Key
- Embedding API Key，如果启用知识库向量化

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-org/ai_bidding.git
cd ai_bidding/ai_bidding
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

安装依赖：

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

复制模板：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`，填入你自己的数据库、模型和向量库配置。不要把 `.env` 提交到 GitHub。

### 4. 准备 MySQL

创建数据库用户和权限，或使用已有 MySQL。应用启动时会根据 `core/db.py` 中的 schema 初始化所需表。

示例配置见 `.env.example`：

```ini
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=your_mysql_user
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=bidding
MYSQL_CHARSET=utf8mb4
```

### 5. 启动后端 API

```bash
python main.py
```

后端默认地址：

```text
http://localhost:3012
```

### 6. 启动前端开发环境

```bash
cd front
npm install
npm run dev
```

前端默认地址：

```text
http://localhost:5173
```

Vite 开发服务器会把 `/api` 代理到 Flask，因此本地开发时前后端是分离运行的。

### 7. 构建前端产物

```bash
cd front
npm run build
```

构建完成后，Flask 会自动托管 `front/dist/`，此时访问下面地址即可：

```bash
http://localhost:3012
```

用户端与后台管理会共用同一个 SPA 入口：

```text
http://localhost:3012/
http://localhost:3012/admin
```

## 模型与 Embedding 配置

### 聊天模型

启动后可以在前端“模型设置”中配置模型提供商和 API Key。当前支持：

| 提供商 | Base URL |
| --- | --- |
| DeepSeek | `https://api.deepseek.com/v1` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` |
| 小米 MiMo | `https://token-plan-cn.xiaomimimo.com/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Moonshot/Kimi | `https://api.moonshot.cn/v1` |

### Embedding

Milvus/ChromaDB 只负责存储向量，不负责生成向量。真正需要 API Key 的是 Embedding 模型。

默认配置使用 DashScope OpenAI 兼容 Embeddings：

```ini
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIM=1024
```

如果没有单独设置 `EMBEDDING_API_KEY`，代码会回退读取 `DASHSCOPE_API_KEY`。

## 向量库配置

本地开发默认使用 ChromaDB：

```ini
VECTOR_STORE=chroma
VECTOR_COLLECTION=document_embeddings
```

使用 Milvus：

```ini
VECTOR_STORE=milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_METRIC_TYPE=COSINE
MILVUS_INDEX_TYPE=AUTOINDEX
VECTOR_COLLECTION=document_embeddings
```

如果 Milvus 连接失败，当前代码会回退到 ChromaDB，便于开发调试。

## OnlyOffice，可选

如需在线预览和编辑生成的 Word 文件，可以启动 OnlyOffice Document Server：

```bash
docker run -d \
  --name onlyoffice-documentserver \
  -p 80:80 \
  --restart=always \
  -e JWT_SECRET=fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue \
  onlyoffice/documentserver
```

`.env` 中的 `ONLYOFFICE_JWT_SECRET` 需要与容器中的 `JWT_SECRET` 保持一致。

## 主要接口

| 模块 | 前缀 | 说明 |
| --- | --- | --- |
| 招投标文档 | `/api/bidding` | 上传招标文件、预分析、章节设计、生成投标书 |
| 用户 | `/api/users` | 轻量用户识别 |
| 模型设置 | `/api/settings` | 模型提供商列表、模型配置、模型连接测试 |
| 知识库 | `/api` | 知识库管理、文档入库、RAG 检索 |
| 前端 | `/` | 用户端工作台 |
| 管理端 | `/admin` | 后台管理页面，当前先与用户端合并在同一个前端应用内 |

## 当前存储说明

当前项目已经使用 MySQL 保存文件元数据、项目、知识库、文档切片和生成记录，但真实文件仍保存到本地目录：

- `uploads/`：用户上传的招标文件、企业知识库文件、项目资料。
- `outputs/`：生成的章节、Markdown、Word 文件。
- `chroma_db/`：本地 ChromaDB 向量库数据。

这些目录已被 `.gitignore` 忽略，不应提交到 GitHub。生产环境建议后续迁移到 MinIO/OSS/S3。

## 安全注意事项

- 不要提交 `.env`、API Key、数据库密码、JWT Secret。
- 不要提交上传的招标文件、历史投标文件、企业资质、生成的 Word。
- 不要提交本地数据库、向量库、日志、缓存和虚拟环境。
- 上传 GitHub 前建议执行：

```bash
git status --short
```



## 开发说明

- `core/db.py` 会在应用启动时初始化 MySQL 表结构。
- `storage/vector_store.py` 根据 `VECTOR_STORE` 选择 ChromaDB 或 Milvus。
- `services/ingestion_service.py` 负责文档解析、切片、向量化和切片元数据入库。
- `services/qwen_client.py` 通过模型配置调用 OpenAI 兼容 Chat Completions。
- `export/md_to_word.py` 将 Markdown 转换为 Word。

## 许可证

本项目基于 MIT License 开源，详见 [LICENSE](LICENSE)。
