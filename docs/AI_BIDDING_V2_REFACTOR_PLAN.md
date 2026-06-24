# AI Bidding V2 代码改造计划

版本：V2.0  
日期：2026-06-09  
范围：基于当前 `ai_bidding` 仓库，不直接照搬参考项目，而是吸收 `ai_bidding_power_grid` 的成熟模块思想，分阶段升级为企业级 AI 投标 Agent 平台。

## 1. 改造原则

当前仓库已有可用骨架：`main.py`、`core/db.py`、`api/*`、`services/*`、`storage/*`、`export/*`、`front/*`。改造不能推倒重来，应先建立 V2 模块和兼容层，再逐步迁移旧链路。

关键原则：

- 不破坏旧接口，先在 `/api/v2` 建新接口。
- 不删除历史数据，先做迁移映射。
- 不继续扩大 `api/bidding.py`，新能力全部进入新模块。
- 不把 MySQL BLOB 当生产存储，文件逐步迁到对象存储。
- 不把 prompt 硬编码在路由里，进入模板和策略系统。
- 不用 OnlyOffice 承担 AI 主编辑，TipTap 是主工作台。
- 不让图片系统成为导出后补丁，图片规划要进入生成前 Agent 链路。

## 2. 当前仓库改造地图

### 2.1 保留目录

| 目录/文件 | 保留原因 | V2 动作 |
| --- | --- | --- |
| `main.py` | Flask 入口和蓝图注册清晰 | 增加 v2 蓝图，旧蓝图兼容 |
| `core/db.py` | 已有业务 schema 雏形 | 拆出 migrations，保留 MySQL 兼容 |
| `core/llm_providers.py` | 多模型配置基础 | 并入 Model Center |
| `services/model_router.py` | 已有路由、fallback、日志 | 增加 stream/embedding/rerank/image |
| `services/agent_orchestrator.py` | Agent、证据包、版本雏形 | 重构为状态机和任务编排 |
| `services/retrieval_router.py` | RAG 入口雏形 | 重写为 Hybrid Search |
| `services/ingestion_service.py` | 基础解析和切片 | 保留为 fallback parser |
| `storage/storage_service.py` | 文件版本模型 | 底层迁到对象存储 |
| `export/md_to_word.py` | Word 基础能力 | 增强图片/目录/引用 |
| `front/` | 当前正式 Vue 前端 | 先接 V2 API，后引入 TipTap |
| `docs/` | 文档目录 | 持续维护 |

### 2.2 重构目录

| 当前目录/文件 | 问题 | 重构目标 |
| --- | --- | --- |
| `api/bidding.py` | 过大，混合上传、解析、目录、生成、导出、OnlyOffice | 拆成 `api/v2/projects.py`、`documents.py`、`interpretation.py`、`outline.py`、`generation.py`、`export.py`、`onlyoffice.py` |
| `api/knowledge.py` | 只有通用知识库 | 拆成 `knowledge_center/company.py`、`products.py`、`history.py`、`images.py` |
| `api/generation.py` | 同步章节生成，无 token stream | 改为 Agent task + TipTap editor AI |
| `storage/vector_store.py` | Chroma/Milvus 与业务库割裂 | PGVector 主路径，Chroma/Milvus 仅开发/迁移 |
| `front/src/user/views/Editor.vue` | OnlyOffice 容器 | 改为 TipTap 主编辑器，OnlyOffice 独立终稿页 |
| `front/src/admin/views/KnowledgeBase.vue` | 管理维度过粗 | 拆成企业资信、产品、历史标书、图片资产 |

### 2.3 删除/冻结目录

| 目录/文件 | 动作 | 时间 |
| --- | --- | --- |
| `frontend/` | 冻结，V2 前端稳定后删除 | P2 |
| `legacy/routes_copy.py` | 迁移有用逻辑后删除 | P1 |
| `api/bidding.py` 中旧接口名 | 保留兼容层，不再新增逻辑 | P0 起 |
| 自动建表生产路径 `init_mysql()` | 开发保留，生产关闭 | P1 |

## 3. 新增目录结构

建议新增：

```text
api/
  v2/
    __init__.py
    projects.py
    documents.py
    interpretation.py
    outline.py
    agent_tasks.py
    streams.py
    rag.py
    knowledge_center.py
    images.py
    editor.py
    export.py
    review.py
    settings.py

services/
  agents/
    __init__.py
    base.py
    orchestrator.py
    tender_parser.py
    company_match.py
    product_match.py
    image_planner.py
    writers.py
    reviewer.py
    followup.py
  rag/
    __init__.py
    hybrid_search.py
    keyword_search.py
    vector_search.py
    reranker.py
    context_builder.py
    citation_collector.py
  knowledge_center/
    __init__.py
    company_profile_service.py
    product_library_service.py
    bid_history_service.py
    image_asset_service.py
  images/
    __init__.py
    prompt_templates.py
    image_generation.py
    image_audit.py
    image_plan.py
  documents/
    __init__.py
    parser_router.py
    mineru_parser.py
    office_parser.py
    chunker.py
    tiptap_document.py
  export_center/
    __init__.py
    markdown_builder.py
    word_exporter.py
    image_numbering.py
    citation_exporter.py
  model_center/
    __init__.py
    router.py
    chat.py
    stream.py
    embedding.py
    rerank.py
    image.py

migrations/
  mysql/
  postgres/

front/src/user/views/
  TiptapWorkbench.vue
  KnowledgeCenter.vue
  ImageAssets.vue

front/src/user/components/editor/
  TiptapBidEditor.vue
  AiSelectionMenu.vue
  CitationPopover.vue
  CommentThread.vue
```

若团队决定直接迁移 React，可把参考项目 `frontend/src/components/editor/TiptapBidEditor.tsx`、`BidEditor/index.tsx`、`KnowledgeBase/index.tsx`、`ProductBase/index.tsx` 作为实现参考，但不建议在当前 Vue 项目中同时维护 React 子应用，除非明确进行前端技术栈切换。

## 4. 数据迁移方案

### 4.1 MySQL 到 V2 兼容映射

当前表映射：

| 当前表 | V2 表/对象 | 迁移说明 |
| --- | --- | --- |
| `companies` | `company_profile` | 补充企业简介、注册资本、员工规模、资质和奖项 |
| `knowledge_bases` | `knowledge_center` 逻辑分类 | 不再只靠 kb_type，拆到业务库 |
| `knowledge_documents` | `bid_history`/普通知识文档 | 根据 doc_type、tags、source_project_name 判断 |
| `document_chunks` | `knowledge_chunk` | 补齐 source_type、source_id、page、section_path、embedding |
| `document_files`/`document_versions`/`document_file_blobs` | object storage + file registry | BLOB 导出到对象存储，保留 file_id 映射 |
| `bid_projects` | `bid_projects` | 保留主表，扩展 industry、analysis structure |
| `bid_chapters` | `bid_chapters` + `chapter_strategy` | outline_json 解析出 volume_type 和策略 |
| `bid_chapter_versions` | `bid_chapter_versions` + editor doc | 转 Markdown/TipTap JSON |
| `rag_evidence_items` | `citation_record` candidates | 已进入生成的证据补 citation |
| `agent_runs` | `agent_task`/`agent_task_event` | 老记录只读展示 |

### 4.2 文件迁移步骤

1. 扫描 `document_files` 和 `document_versions`。
2. 从 `document_file_blobs` 导出二进制到对象存储路径：`tenant/{tenant_id}/files/{file_id}/v{version_no}/{filename}`。
3. 回填 `storage_bucket`、`storage_key`、`object_url`。
4. 对大于阈值的 BLOB 做校验 hash。
5. 保留 MySQL blob 一段时间，只读降级。
6. 新上传文件只写对象存储。

### 4.3 向量迁移步骤

1. PostgreSQL 创建 `knowledge_chunk` 和 PGVector 索引。
2. 从 `document_chunks` 读取 chunk_text 和 metadata。
3. 计算或复用 embedding。Chroma/Milvus 无法稳定导出时直接重算。
4. 生成 `search_vector`。
5. 对比旧 `/knowledge/search` 和新 `/rag/search` topK。
6. 切换 RAG Engine 默认后端。

### 4.4 图片资产迁移

当前项目没有图片资产表。迁移来源：

- 历史标书 docx/pdf 中解析出的图片。
- 用户上传的产品图片、证书图片、案例图片。
- 参考项目 assets 仅可作为测试样例，不可作为正式企业资料。

步骤：

1. 新建 `image_asset`。
2. 对现有文件执行图片抽取任务。
3. OCR + AI caption 生成 `searchable_text`。
4. 人工审核分类：产品、案例、施工、架构、流程、证书、组织架构。
5. 设定 `allowed_for_bid` 和脱敏状态。

## 5. P0/P1/P2 优先级

### P0：打通 V2 主链路

目标：不大规模推翻当前项目，先让 V2 主流程可跑通。

任务：

- 新增 `/api/v2` 蓝图和 Agent task 基础表。
- 拆出 `services/model_center/stream.py`，支持 OpenAI-compatible stream。
- 将当前 `/generate-bid-document` 的章节级 SSE 升级为单章 token 流式接口。
- 新增 `chapter_strategy`，替换硬编码大 prompt 的章节策略部分。
- 新增 TipTap 编辑器原型页，支持 Markdown/HTML/JSON 基础转换、流式写入。
- 新增 `citation_record` 最小闭环：RAG context 进入 prompt 时生成 citation candidate，正文可点击查看来源。
- 增强 `retrieval_router` 为 context builder，先保留 MySQL + Chroma/Milvus。
- 知识库管理新增库类型入口：企业资信、产品、历史标书、图片资产，先用表单和现有文件上传。
- 导出保留当前 `md_to_word.py`，先支持从章节表导出，而不是一次性字符串。

验收标准：

- 上传招标文件、预分析、事实确认、目录生成仍可用。
- 单章正文能 token 流式进入 TipTap。
- 章节生成后有版本、任务、引用记录。
- 至少可维护产品资料和图片资产 metadata。
- Word 导出不低于当前能力。

### P1：企业级 RAG 与图片系统

目标：建立 Knowledge Center、Hybrid Search、Image Plan、图片插入。

任务：

- 引入 PostgreSQL + PGVector migrations。
- 新增 `knowledge_chunk`、`company_profile`、`product_library`、`bid_history`、`image_asset`、`retrieval_log`。
- 实现 Hybrid Search：FTS + PGVector + DashScope Rerank + Context Builder。
- 实现企业资信库、产品库、历史标书库、图片资产库页面。
- 实现 Image Planning Agent 和 Image Plan 表。
- 实现图片检索优先级：企业图片 → 历史标书图片 → AI 生图占位。
- 初步接入 AI 生图适配层，先支持 ComfyUI 或 Qwen Image 之一。
- 实现图片审核 Agent 的最小规则版。
- 增强 Word 导出：图片插入、图注、图片来源、图编号。
- 实现 Follow-up Questions。

验收标准：

- RAG 返回 keyword/vector/rerank 分数和 retrieval log。
- 章节生成能区分企业、产品、历史标书和图片资料。
- 图片规划能为组织架构、系统架构、产品介绍、实施方案生成 Image Plan。
- Word 中自动插入图片并显示“图 3-1 ...”。
- 缺资料和缺图片能形成待办。

### P2：协同编辑、长文本和正式导出

目标：接近企业级交付体验。

任务：

- 接入 WebSocket 和协同编辑预留，支持评论、修订建议、多人 presence。
- 实现长文本生成 DAG：Chapter Planner → Section Planner → Writer → Reviewer → Merge。
- 实现全文批量并发生成、暂停、恢复、失败重试。
- 增强审核 Agent：一致性、格式、缺失、风险、重复、引用缺失。
- 完整导出：封面模板、目录、图目录、表目录、交叉引用、引用清单、LibreOffice 刷新字段。
- 成本中心：LLM/Embedding/Rerank/OCR/Image/Export 计费。
- 删除旧 `frontend/` 和 `legacy/`。
- 生产部署脚本：PostgreSQL、Redis、MinIO、Worker、OnlyOffice、可选 MinerU/ComfyUI。

验收标准：

- 100 页级标书可分章节生成、恢复、导出。
- 导出前高风险缺失会阻断或要求确认。
- 全篇引用和图片来源可审计。
- 多人评论和修订建议数据结构可用。

## 6. 开发路线图

### Phase 1：基础重构

工时：2-3 周。

内容：

- `/api/v2` 框架。
- Agent task 表和状态流。
- Model Center stream。
- TipTap 原型。
- 单章 token 流。
- 旧接口兼容层。

风险：

- Flask 同步模型对 SSE 长连接不稳定。
- 当前 Vue 引入 TipTap 需要编辑器封装成本。

验收：

- 单章生成可流式显示。
- 任务状态可查询和取消。
- 旧上传/预分析/目录不回归。

### Phase 2：知识库

工时：3-4 周。

内容：

- 企业资信、产品、历史标书、图片资产表和页面。
- 对象存储迁移。
- 文档解析任务异步化。
- 图片 OCR/caption。

风险：

- MySQL BLOB 导出和对象存储映射出错。
- 图片资产审核工作量大。

验收：

- 四类知识库可 CRUD、上传、预览、审核。
- 图片资产可被章节按类型检索。

### Phase 3：RAG 升级

工时：3-4 周。

内容：

- PostgreSQL + PGVector。
- FTS + vector + rerank。
- Context Builder。
- retrieval_log 和 citation_record。

风险：

- MySQL 到 PostgreSQL 双写/迁移复杂。
- 中文全文检索分词质量需要调参。

验收：

- `/api/v2/rag/search` 返回可解释分数。
- 生成内容可点击来源。
- 检索降级可观测。

### Phase 4：Agent 系统

工时：4-5 周。

内容：

- TenderParser、CompanyMatch、ProductMatch、Writer、Reviewer、FollowUp。
- 分册 Strategy Pattern。
- 章节 DAG 和任务恢复。

风险：

- Agent 输出 schema 不稳定。
- 并发生成带来模型限流。

验收：

- Agent 状态机可视化。
- 技术标/商务标/资格/报价策略差异可验证。
- Reviewer 能输出风险和缺失。

### Phase 5：智能图片系统

工时：4-6 周。

内容：

- Image Plan。
- 图片来源优先级。
- 行业 Prompt Template Library。
- AI 生图适配。
- 图片审核 Agent。
- Word 自动插图、图编号、图目录。

风险：

- AI 图片合规风险。
- Word 图编号和交叉引用复杂。

验收：

- 典型章节可自动规划图片。
- 企业图片优先于 AI 生图。
- Word 自动插图含图注和来源。

### Phase 6：企业级增强

工时：4-8 周。

内容：

- 协同编辑。
- 评论、修订模式。
- 成本中心。
- 权限、审计、安全。
- 生产部署。

风险：

- WebSocket/Yjs 与后端版本管理冲突。
- 企业权限模型需要业务确认。

验收：

- 多用户评论和修订建议可用。
- 成本和审计可追踪。
- 私有化部署脚本可重复执行。

## 7. 代码改造步骤

### Step 1：建立 V2 API 骨架

新增：

- `api/v2/__init__.py`
- `api/v2/agent_tasks.py`
- `api/v2/streams.py`
- `api/v2/editor.py`

修改：

- `main.py` 注册 `api.v2`。
- `core/db.py` 暂时追加 P0 表，后续迁出 migrations。

验收：

- `GET /api/v2/health` 返回 ok。
- `POST /api/v2/agent-tasks` 能创建任务。

### Step 2：流式模型中心

新增：

- `services/model_center/stream.py`
- `services/model_center/router.py`

迁移：

- 从 `services/model_router.py` 复用 provider、fallback、日志。
- 参考 `ai_bidding_power_grid/backend/ai/qwen_client.py` 实现 DeepSeek/DashScope stream。

验收：

- mock 模型流可输出 token。
- 真实 OpenAI-compatible stream 可透传 SSE。

### Step 3：TipTap 主编辑器

新增：

- `front/src/user/components/editor/TiptapBidEditor.vue`
- `front/src/user/views/TiptapWorkbench.vue`

参考：

- `ai_bidding_power_grid/frontend/src/components/editor/TiptapBidEditor.tsx`
- `ai_bidding_power_grid/frontend/src/pages/BidEditor/index.tsx`

验收：

- Markdown 可加载到 TipTap。
- TipTap 编辑可保存 Markdown/JSON。
- token chunk 能追加到当前章节。

### Step 4：RAG Context Builder

新增：

- `services/rag/context_builder.py`
- `services/rag/citation_collector.py`

修改：

- `services/retrieval_router.py` 返回 context_pack，不只是 items。
- `api/generation.py` 或 v2 generation 调用 context_pack。

验收：

- 每章生成前有 retrieval_log。
- 生成结果有 citation_record。

### Step 5：知识中心拆分

新增：

- `services/knowledge_center/*`
- `api/v2/knowledge_center.py`
- 前端四个管理视图。

迁移：

- 现有 `knowledge_bases` 和 `knowledge_documents` 映射为历史标书/通用知识。

验收：

- 企业资信、产品、历史标书、图片资产可维护。

### Step 6：图片系统

新增：

- `services/images/image_plan.py`
- `services/images/prompt_templates.py`
- `services/images/image_generation.py`
- `services/images/image_audit.py`
- `api/v2/images.py`

验收：

- 章节可生成 Image Plan。
- 图片库可匹配图片。
- Word 可插入图片和图注。

### Step 7：导出中心

新增：

- `services/export_center/markdown_builder.py`
- `services/export_center/word_exporter.py`
- `services/export_center/image_numbering.py`
- `services/export_center/citation_exporter.py`

修改：

- `export/md_to_word.py` 逐步迁入 Export Center。

参考：

- 参考项目增强版 `backend/export/md_to_word.py` 的目录、书签、图片和 LibreOffice 刷新字段。

验收：

- 从章节树导出 Word。
- 目录、图片编号、引用清单可用。

## 8. 技术债处理计划

| 技术债 | 处理阶段 | 方案 |
| --- | --- | --- |
| `api/bidding.py` 过大 | P0-P1 | 新接口迁移后只留兼容层 |
| SSE 非 token 级 | P0 | Model Center stream + editor stream |
| MySQL BLOB | P1 | 对象存储迁移 |
| 自动建表 | P1 | Alembic/Flyway migrations |
| RAG 只有 vector/LIKE | P1 | PostgreSQL FTS + PGVector + Rerank |
| Prompt 硬编码 | P1-P2 | prompt template + chapter_strategy |
| OnlyOffice 主编辑 | P0-P2 | TipTap 主编辑，OnlyOffice 终稿 |
| Word 导出弱 | P1-P2 | Export Center |
| 无图片系统 | P1-P2 | Image Center |
| 无任务恢复 | P0-P2 | Agent task + queue |

## 9. 回滚策略

- P0 新接口不替换旧接口，失败可回退旧 `Generation.vue` 流程。
- 数据库新增表不修改旧表字段语义。
- 对象存储迁移先双写，旧 MySQL BLOB 保留只读。
- RAG 新旧检索并行比对，确认后切默认。
- 导出中心先作为新下载入口，旧 `convert_md_to_word` 保留。

## 10. 测试计划

### 单元测试

- chunk 策略。
- Hybrid score。
- context builder token 截断。
- Image Plan schema。
- citation collector。
- Word image numbering。
- Agent 状态机。

### 集成测试

- 上传 docx/pdf → 解析 → chunk → RAG。
- 章节生成 → token stream → TipTap 保存。
- 产品库/图片库 → Image Plan → Word 插图。
- 引用点击 → 来源预览。
- 导出 full/volume/chapter。

### 回归测试

- 旧 `/api/bidding/upload`。
- 旧 `/pre-analysis_bid`。
- 旧 `/chapter-design`。
- 旧 `/generate-bid-document`。
- OnlyOffice editor-config。

### 性能测试

- 100MB 上传。
- 1000 chunks 检索。
- 50 章节批量生成。
- 100 页 Word 导出。
- SSE 断线恢复。

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 前端技术栈分裂 | 开发效率下降 | Vue 内先集成 TipTap，除非明确整体切 React |
| PostgreSQL 迁移大 | 延期 | P0 保留 MySQL，P1 双写迁移 |
| AI 生图合规 | 严重 | 默认禁生成证件/合同/报价，审核 Agent + 人工确认 |
| 引用记录不准 | 信任受损 | 先记录进入 prompt 的 evidence，再逐步做段落级 citation |
| Word 排版复杂 | 交付质量差 | 借鉴参考项目导出实现，增加 render 验证 |
| 模型限流 | 生成失败 | 并发限制、重试、fallback、任务恢复 |

## 12. 近期开发切入点

建议第一周只做三件事：

1. 新建 `/api/v2/agent-tasks` 和 SSE task stream，跑通 mock token。
2. 新建 TipTap Workbench，能加载一个 `bid_chapter_versions.content` 并流式追加。
3. 把 `generate_bid_section` 包一层 streaming writer，先生成单章，不碰全文导出。

这三件事完成后，团队会立刻看到 V2 与当前系统的体验差异，也不会在数据库大迁移前卡住。

## 13. 交付检查清单

P0 完成时：

- [ ] `/api/v2` 可用。
- [ ] Agent task 创建、查询、取消可用。
- [ ] 单章 token 流式生成可用。
- [ ] TipTap 保存章节可用。
- [ ] RAG context pack 可查看。
- [ ] citation_record 最小闭环可用。
- [ ] 旧生成流程不回归。

P1 完成时：

- [ ] 四类知识库可用。
- [ ] PostgreSQL + PGVector 可用。
- [ ] Hybrid Search 可用。
- [ ] 图片资产可检索。
- [ ] Image Plan 可生成。
- [ ] Word 自动插图可用。

P2 完成时：

- [ ] 长文本 DAG 可用。
- [ ] 评论/修订预留可用。
- [ ] 图目录/表目录/引用清单可用。
- [ ] 成本中心可用。
- [ ] 生产部署脚本可用。
