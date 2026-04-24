# Notes: 本地带图片标书 MVP

## Existing Project Findings
- `main.py` 使用 Flask，上传目录为 `uploads`，输出目录为 `outputs`，关系库为 `bidding.db`。
- `routes.py` 当前支持招标文件上传、预分析、章节生成、OnlyOffice 回调等标书流程。
- `file_to_chroma.py` 当前将 PDF/DOCX/TXT 抽取为文本 chunk，并用 DashScope `text-embedding-v3` 写入 ChromaDB。
- `md_to_word.py` 当前支持标题、段落、列表、Markdown 表格和 Mermaid 图片，但尚不支持普通 Markdown 图片语法。
- `requirements.txt` 已包含 Flask、ChromaDB、OpenAI client、PyPDF2、python-docx 等基础依赖。

## MVP Direction
- 保持现有架构，新增“素材库”能力。
- PDF 产品手册解析后形成两类数据：
  - 文本 chunk：用于 RAG 生成产品说明、技术响应。
  - 图片 asset：用于按产品型号、章节、图注、附近文本检索并插入 Word。
- 图片检索第一版不依赖视觉模型，先用图片附近文本、章节标题、页码、人工标签做检索。
- 输出 Word 的最小做法是让 AI 生成 Markdown，其中包含图片占位语法，再由 `md_to_word.py` 插入真实图片。

## Mac M1 Local Dependencies
- `PyMuPDF` 用于 PDF 文本和图片抽取。
- `Pillow` 用于图片格式检查和缩放。
- `python-docx` 已存在，用于 Word 插图。
- SQLite 可继续作为 MVP 关系数据库。
- ChromaDB 可继续作为 MVP 向量库。

## Suggested New Files
- `asset_store.py`: 素材库数据库表、写入、查询。
- `pdf_asset_parser.py`: 产品 PDF 手册解析，抽文字、图片、页码、上下文。
- `asset_retriever.py`: 按章节需求检索图片素材。
- `scripts/ingest_product_manual.py`: 命令行导入产品手册。
- `scripts/generate_image_bid_demo.py`: 生成带图片 Word 的端到端 demo。
