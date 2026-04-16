# 🚀 AI智能招投标文档生成系统---后端

基于大语言模型 (LLM) 与检索增强生成 (RAG) 技术的智能辅助编写系统。本项目旨在解决传统招投标文件编写耗时长、历史资料利用率低等痛点，通过结合本地知识库高精度检索与大模型文本生成能力，实现招投标模块的自动化撰写、排版与导出。

> 目前本项目仅开源了**核心后端业务逻辑与 AI 链路的开发，前端部分（UI/UX）可基于客户的要求和视觉效果自行定制开发！**

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

## 🚀 快速开始 (Quick Start)

### 1. 克隆项目

```bash
git clone https://github.com/你的用户名/ai_bidding.git
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

服务启动后，可以通过后端暴露的 API 接口进行调试和测试（默认运行在 3012 端口）。

## 🤝 参与贡献 (Contributing)

本项目正处于快速迭代阶段，这是一个绝佳的参与 AI 落地开源项目的机会！我们期待你的 PR：

### 💻 前端方向 (Urgent!)

* 从 0 到 1 搭建前端工程。
* 实现用户登录、知识库上传管理界面。
* 实现与大模型的交互对话、章节设计界面。
* 集成 ONLYOFFICE 实现生成文档的在线编辑与预览。

### ⚙️ 后端/AI 方向

* 优化复杂文档解析策略（如针对 PDF 的表格提取）。
* 优化 RAG 检索算法（混合检索、重排序 Rerank）。
* 完善 API 接口文档 (Swagger/OpenAPI)。
* 增加对其他开源模型（如 Ollama 本地模型）的支持。

## 🙏 致谢 (Acknowledgments)

本项目在开发与架构设计过程中，部分思路与实现借鉴了开源项目 `xiaodingfeng/contract-review`，特此对原作者的开源精神与优秀代码表示感谢！

## 📄 许可证 (License)

本项目采用 MIT License 开源许可证。
