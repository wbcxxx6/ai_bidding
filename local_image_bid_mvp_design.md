# 本地带图片标书 MVP 设计

## 目标

在 Mac M1 本地跑通一个最小闭环：

```text
上传/导入产品 PDF 手册
  -> 抽取文本、表格、图片
  -> 图片和文本入库
  -> 生成标书章节 Markdown
  -> 自动选择合适图片
  -> 导出带图片的 Word
```

这个 MVP 先不做复杂前端、不上多模态向量、不上 PostgreSQL。直接沿用当前项目的 Flask、SQLite、ChromaDB、通义千问、python-docx。

## 最小架构

```text
uploads/manuals/            产品手册 PDF
uploads/assets/             抽取出来的图片
bidding.db                  素材元数据
chroma_db/                  文本向量库
outputs/                    生成的 Markdown / Word

pdf_asset_parser.py         PDF 解析
asset_store.py              素材元数据存取
asset_retriever.py          图片检索
md_to_word.py               Markdown 转 Word，新增图片支持
```

## 数据表设计

在现有 `bidding.db` 里新增三张表即可：

```sql
CREATE TABLE IF NOT EXISTS source_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL,
    product_model TEXT,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER NOT NULL,
    page_no INTEGER,
    section_title TEXT,
    content TEXT NOT NULL,
    chroma_id TEXT,
    FOREIGN KEY (source_document_id) REFERENCES source_documents(id)
);

CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER,
    asset_type TEXT NOT NULL,
    product_model TEXT,
    title TEXT,
    caption TEXT,
    file_path TEXT NOT NULL,
    page_no INTEGER,
    section_title TEXT,
    nearby_text TEXT,
    tags TEXT,
    usage TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_document_id) REFERENCES source_documents(id)
);
```

`assets.asset_type` 第一版建议控制在这些值：

```text
产品外观图
结构示意图
安装示意图
系统架构图
接线图
营业执照
资质证书
案例图片
其他
```

## PDF 解析策略

第一版用 `PyMuPDF`：

- 每页抽文本。
- 每页抽图片并保存到 `uploads/assets/{document_id}/page_{page}_img_{n}.png`。
- 图片的 `nearby_text` 先取该页前后 800 字。
- `section_title` 第一版用简单规则识别：页面中较短、包含“章/节/图/说明/结构/安装/参数”的行。
- 图片类型第一版用规则猜测：
  - 附近文本含“外观、产品图、设备图” -> 产品外观图
  - 含“结构、组成、部件” -> 结构示意图
  - 含“安装、部署、固定” -> 安装示意图
  - 含“架构、系统、拓扑” -> 系统架构图
  - 含“接线、端子、电气” -> 接线图

不要第一版就上视觉模型。先保证图片能抽出来、能被选中、能插进 Word。

## 图片检索策略

输入：

```text
产品型号 + 标书章节标题 + 章节意图
```

检索：

1. SQL 过滤：`product_model`、`asset_type`、`usage`。
2. 文本打分：章节标题/意图与 `caption + nearby_text + tags` 做关键词匹配。
3. 可选：把 `caption + nearby_text` 也写入 Chroma，用 embedding 查相似素材。

输出：

```json
{
  "asset_id": 12,
  "file_path": "uploads/assets/1/page_8_img_2.png",
  "caption": "ABC-3000 产品外观图",
  "page_no": 8,
  "source": "ABC-3000产品说明书.pdf"
}
```

## 标书生成方式

让章节生成结果使用 Markdown 图片语法：

```markdown
## 产品结构说明

ABC-3000 由主机、控制面板、传感模块和安装底座组成。

![ABC-3000 产品外观图](uploads/assets/1/page_8_img_2.png)

图 1 ABC-3000 产品外观图
```

然后扩展 `md_to_word.py`：

- 识别 `![caption](path)`。
- 校验路径在项目目录内。
- 用 `doc.add_picture(path, width=Inches(5.5))` 插入。
- 图片居中。
- 自动加图注，或复用 Markdown 下一行图注。

## 编码步骤

### Step 1: 安装依赖

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install PyMuPDF Pillow
```

### Step 2: 新增素材库模块

创建 `asset_store.py`：

- `init_asset_tables()`
- `create_source_document(...)`
- `insert_chunk(...)`
- `insert_asset(...)`
- `search_assets(...)`
- `get_asset(asset_id)`

### Step 3: 新增 PDF 手册解析模块

创建 `pdf_asset_parser.py`：

- `parse_product_manual(pdf_path, product_model)`
- 保存 PDF 元数据到 `source_documents`
- 每页文本写入 `document_chunks`
- 每张图片写入 `assets`
- 每页文本继续调用现有 `file_to_chroma` 或新增 chunk 级 embedding

### Step 4: 新增图片检索模块

创建 `asset_retriever.py`：

- `retrieve_assets(product_model, section_title, intent, asset_type=None, limit=3)`
- 先 SQL 过滤，再关键词打分。
- 返回最相关图片。

### Step 5: 扩展 Word 导出

修改 `md_to_word.py`：

- 增加 Markdown 图片正则：

```python
image_match = re.match(r'^!\[(.*?)\]\((.*?)\)$', line)
```

- 插入图片：

```python
doc.add_picture(image_path, width=Inches(5.5))
doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
```

### Step 6: 做一个端到端 demo 脚本

创建 `scripts/generate_image_bid_demo.py`：

1. 解析一个产品手册 PDF。
2. 检索一张产品外观图。
3. 生成一个 Markdown 标书章节。
4. 调用 `convert_md_to_word()`。
5. 在 `outputs/demo/` 生成 `.docx`。

## 第一版不做的事

- 不做完整多模态 RAG。
- 不做图片相似度检索。
- 不做复杂前端。
- 不做 PostgreSQL 迁移。
- 不做 OnlyOffice 深度集成。
- 不做自动排版完全符合国网格式，只保证 Word 可插图、可人工调整。

## 验收标准

- 能导入一份产品 PDF。
- `uploads/assets/` 下能看到抽取图片。
- `bidding.db.assets` 能查到图片元数据。
- 能按产品型号和“产品外观图/结构示意图”检索图片。
- 生成的 Word 里包含正文、表格和至少一张真实图片。
- 整个流程能在 Mac M1 本地完成。

## 后续增强

- PostgreSQL + pgvector 替代 SQLite + ChromaDB。
- 使用 PaddleOCR 处理扫描版说明书。
- 使用 Qwen-VL/GLM-V 给图片自动生成 caption。
- 加 BGE reranker 提升检索准确率。
- 增加资质有效期、证书版本、使用范围校验。
- 接入 Dify 作为提示词和流程编排后台。
