# 湖北恩施水利配套制造 AI 标书系统---后端

基于大语言模型 (LLM) 与检索增强生成 (RAG) 技术的内网智能标书编制系统。本项目面向湖北恩施水利配套制造企业，围绕三峡集团及相关水利工程供应链业务，覆盖涡片、螺母、紧固件、金属结构件、设备配套加工、质量检验、交付保障和现场服务等投标场景，通过结合本地知识库高精度检索与大模型文本生成能力，实现招投标文件的自动化分析、撰写、排版、在线编辑与导出。

> 本项目为恩施水利配套制造企业内网部署的 AI 标书系统，核心链路包括招标文件解析、企业知识库检索、投标章节设计、投标正文生成、Word 排版导出与 OnlyOffice 在线编辑。

---

## 🛠️ 技术栈 (Tech Stack)

* **核心语言:** Python 3.9+
* **Web 框架:** 详见 `main.py` 与 `routes.py` (核心路由设计)
* **大语言模型:** 通义千问 (Qwen)
* **向量数据库:** ChromaDB (本地化运行)
* **关系型数据库:** SQLite
* **文档处理:** `python-docx` / Markdown 解析库

## 📁 核心目录结构

```text
ai_bidding/
├── main.py                # 后端服务入口文件
├── routes.py              # 核心业务路由及 API 接口定义
├── users.py               # 用户认证与权限管理模块
├── qwen_client.py         # 大模型 API 封装与调用链路
├── file_to_chroma.py      # 知识库文档解析与 Chroma 向量化持久化
├── md_to_word.py          # Markdown 转 Word (.docx) 排版导出引擎
├── bidding_workbench.html # 内网标书工作台页面
├── chroma_db/             # ChromaDB 向量数据库本地存储目录
├── bidding.db             # SQLite 关系型数据库文件
└── .env                   # 环境变量与敏感配置 (API Keys 等)
```

# AI招投标项目使用说明

## 💻 环境依赖与前置软件 (Prerequisites)

为了完整运行本项目，你需要在本地或服务器上安装以下基础软件：

* Python 3.9+
* Docker（用于部署 ONLYOFFICE 和独立的向量数据库服务）

## 🐳 Docker 部署必需服务

### 1. 部署 ONLYOFFICE 文档服务器 (必须)

系统依赖 ONLYOFFICE 实现文档的在线预览和编辑。请运行以下命令启动服务（此处传入的 `JWT_SECRET` 必须与下方 `.env` 配置文件中的保持一致）：

```bash
docker run -i -t -d -p 80:80 \
  --restart=always \
  -e JWT_SECRET=fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue \
  onlyoffice/documentserver
```

### 2. 部署 ChromaDB 向量数据库 (可选)

注意：当前后端代码默认使用了 Chroma 的本地持久化客户端（数据保存在本地 `chroma_db/` 目录），因此无需额外部署即可运行。

如果你希望将向量数据库作为独立服务运行以提升性能和解耦，可以使用以下 Docker 命令启动：

```bash
docker run -d -p 8000:8000 \
  -v ./chroma_data:/chroma/chroma \
  --name chromadb \
  chromadb/chroma
```

(如使用独立服务，请相应修改代码中的 Chroma 客户端连接方式)

## 快速开始 (Quick Start)

### 1. 克隆项目

```bash
git clone <内网代码仓库地址>
cd ai_bidding
```

### 2. 安装 Python 依赖

建议使用虚拟环境：

```bash
# 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建或修改 `.env` 文件，配置以下核心参数：

```ini
# 阿里云百炼 (通义千问) API Key
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# ONLYOFFICE 配置 (需与 Docker 启动时传入的密钥一致)
ONLYOFFICE_JWT_SECRET=fsdftertrt34768586sfhjsdhfjhhjfsuhaiubue

# 宿主机与 Docker 容器间的通信地址配置
BACKEND_URL_FOR_DOCKER=host.docker.internal:3012
APP_HOST=localhost:3012
```

### 4. 启动后端服务

```bash
python main.py
```

服务启动后，可以通过后端暴露的 API 接口进行联调和验收（默认运行在 3012 端口）。

### 5. 访问内网标书工作台

后端启动后，浏览器访问：

```text
http://localhost:3012/bidding
```

工作台提供完整业务闭环：

```text
上传招标文件 -> AI 预分析 -> 提取章节格式 -> 生成章节设计 -> 生成 Word -> OnlyOffice 在线编辑
```

本地 Docker 部署 OnlyOffice 时，建议 `.env` 保持以下配置：

```ini
BACKEND_URL_FOR_DOCKER=host.docker.internal:3012
APP_PUBLIC_BASE_URL=http://host.docker.internal:3012
```

其中 `APP_PUBLIC_BASE_URL` 必须是 OnlyOffice Document Server 能访问到的后端地址。若部署在内网服务器，应改为真实内网可访问地址，例如：

```ini
APP_PUBLIC_BASE_URL=http://内网服务器地址:3012
```

若现场 OnlyOffice 服务暂不可用，工作台仍提供 Word 下载链接，可保障“AI 生成 Word 并下载”的主业务链路可用。

## 备注

前端方向

* 根据客户内网部署规范完善前端工程。
* 实现用户登录、知识库上传管理界面。
* 实现与大模型的交互对话、章节设计界面。
* 集成 ONLYOFFICE 实现生成文档的在线编辑与预览。

### 后端/AI 方向

* 优化复杂文档解析策略（如针对 PDF 的表格提取）。
* 优化 RAG 检索算法（混合检索、重排序 Rerank）。
* 完善 API 接口文档 (Swagger/OpenAPI)。
* 增加对内网私有化模型服务的适配能力。
