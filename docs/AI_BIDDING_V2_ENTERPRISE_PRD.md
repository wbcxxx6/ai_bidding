# AI Bidding V2 企业级投标 Agent 平台 PRD

版本：V2.0  
日期：2026-06-09  
适用仓库：`wbcxxx6/ai_bidding` 当前项目改造  
参考仓库：`sunShineLoveMe/ai_bidding_power_grid`  
文档定位：产品需求、业务边界、用户体验、验收口径。架构细节与 DDL 见 `docs/AI_BIDDING_V2_ARCHITECTURE.md`，代码落地顺序见 `docs/AI_BIDDING_V2_REFACTOR_PLAN.md`。

## 1. 产品结论

当前项目已经不是一个纯脚本原型，而是具备企业化雏形的 Flask + MySQL + Vue 工作台：`main.py` 注册了 `api/bidding.py`、`api/knowledge.py`、`api/generation.py`、`api/research.py`、`api/files.py`、`api/settings.py`、`api/users.py`；`core/db.py` 已初始化租户、企业、用户、项目、文件、知识库、分块、标书章节、版本、任务、Agent 运行、证据包、响应矩阵、合规报告、深度研究等表；`services/agent_orchestrator.py` 已出现 `TenderParserAgent`、`FactKeeper`、证据包、版本、合规和改写补丁的雏形；`storage/vector_store.py` 已支持 ChromaDB/Milvus；`api/bidding.py` 的 `/generate-bid-document` 已以 SSE 返回章节级进度；`export/md_to_word.py` 已可把 Markdown 转成 Word，并支持 Mermaid 渲染或降级文本框；`front/src/user/views/Generation.vue` 已有预分析、事实确认、格式确认、目录设计、生成文档五步流程；`front/src/user/views/Editor.vue` 已接入 OnlyOffice；`front/src/admin/views/KnowledgeBase.vue` 已有基础知识库上传。

但当前项目距离“企业级 AI 投标 Agent 平台”还有本质差距。核心问题不是缺少一个大模型调用函数，而是系统仍以“招标文件上传后同步串行生成一份 Word”为中心：知识库没有拆成企业资信库、产品库、历史标书库、图片资产库；RAG 只有向量召回加 MySQL LIKE 降级，没有 PostgreSQL Full Text Search、PGVector、Rerank、Context Builder、引用记录和检索日志；Agent 只有少量函数式封装，没有统一状态机、上下文协议、任务队列和可观测链路；前端编辑器仍是生成后进入 OnlyOffice，缺少 TipTap 级别的实时正文编辑、选区 AI、评论、修订和协同编辑预留；图片系统没有 Image Plan、图片来源优先级、行业 Prompt 模板、AI 生图、质量审核、图片编号、图表目录和交叉引用；Word 导出仅能处理基础标题、表格和 Mermaid，尚不能从结构化章节、图片计划、引用记录生成正式标书级目录、图目录、表目录、页码刷新和图文混排。

参考项目 `ai_bidding_power_grid` 提供了更接近 V2 的路线：后端拆成 `backend/api/*`、`backend/ai/*`、`backend/rag/*`、`backend/parsing/*`、`backend/export/*`；前端是 React + TypeScript + Ant Design + TipTap；数据库迁移为 PostgreSQL + pgvector；招标解析接入 MinerU；大纲生成采用规则版快速骨架 + AI 精修后台替换；正文生成用 `stream_bid_section` 把模型 chunk 透传给前端；RAG 有 `search_knowledge_base`、`search_knowledge_assets`、DashScope `rerank_documents`；分册策略集中在 `backend/core/bid_volumes.py`；Word 导出支持图片、安全远程图片校验、目录页码、书签、LibreOffice headless 刷新字段；产品库、资信库、知识库和成本中心已经有页面和 API。参考项目也不是终态，它更偏电网行业和单企业 MVP，仍有 Supabase 迁移痕迹、文件名乱码资产、业务域耦合、图片规划不够 Agent 化、AI 生图缺失、协同编辑未完整落地等问题。V2 应吸收其架构思想，不应直接照搬目录或行业假设。

V2 产品定位必须从“自动写标书工具”升级为“企业知识驱动的投标 Agent 平台”。平台先理解招标文件，再从企业资信、产品、历史标书、图片资产中检索可引用资料，通过多 Agent 协作规划分册、章节、证据和图片，最后在 TipTap 中流式生成、人工审阅、选区优化、引用溯源、补资料追问，并导出正式 Word。目标体验接近 ChatGPT/Claude/Cursor 的实时生成，编辑体验接近 Notion AI，文档交付能力接近专业标书排版人员的 Word 产物。

## 2. 当前项目现状分析

### 2.1 技术架构

当前项目入口是 `main.py`，使用 Flask 和 Flask-CORS，最大上传 50MB。它会启动时调用 `init_mysql()`，将 schema 初始化逻辑放在 `core/db.py` 的 `SCHEMA_STATEMENTS` 中。业务 API 以蓝图方式注册，其中 `/api/bidding` 承担项目列表、招标文件上传、预分析、目录设计、全文生成、OnlyOffice 回调、事实确认门禁等职责；`/api` 下的 `api/knowledge.py` 承担知识库创建、文件上传、项目文件上传、分块查看、删除向量、检索；`api/generation.py` 承担章节重生成、版本恢复、选区改写任务、合规报告；`api/research.py` 承担深度研究任务；`api/files.py` 承担文件下载与历史。

项目的基础设施已经比普通原型更复杂：`core/db.py` 使用 PyMySQL 封装了一个 SQLite 风格的 `?` 占位兼容层，内部实际执行 MySQL；`storage/storage_service.py` 当前把文件二进制写入 MySQL 的 `document_file_blobs`，同时维护 `document_files`、`document_versions`；`storage/vector_store.py` 提供 ChromaDB 和 Milvus 两种向量后端；`services/model_router.py` 从 `model_settings` 和环境变量中解析模型供应商，按 task_type 记录 `model_call_logs`；`services/deep_research_service.py` 提供联网研究任务；`services/retrieval_router.py` 提供向量检索和 MySQL 文本检索兜底；`services/ingestion_service.py` 用 Mammoth、PyPDF2 和编码探测抽取文本，按 1200 字符、150 overlap 切片并写向量库和 MySQL chunk。

当前架构的问题是“有表、有函数、有工作流，但缺服务边界”。`api/bidding.py` 同时做 HTTP 入参、项目创建、文件读取、任务创建、Agent 调用、RAG、章节生成、文档合并、Word 导出、文件入库、SSE 输出，单文件超过千行，业务状态和错误处理分散。生成链路依赖同步 Flask 请求，即使返回 `text/event-stream`，实际只在章节开始、联网搜索、合并和完成时输出事件，正文 token 没有进入前端。数据库自动建表适合原型，但生产无法审计迁移版本，也难以在 PostgreSQL + PGVector 上落地 Hybrid Search。

### 2.2 前端架构

当前项目曾同时存在多套前端痕迹：`frontend/` 是旧版原生 HTML/CSS/JS，`front/src/user` 是 Vue 用户端，`front/src/admin` 是 Vue 管理端。现在正式前端目录统一为 `front/`，Vue 端使用 Element Plus、Pinia 和 Vue Router，`front/src/shared/api.js` 封装了项目、招标、研究、生成、知识库、模型设置 API。

用户端 `Generation.vue` 是当前最重要的业务页，五步流程清晰：预分析、确认事实、格式要求、设计目录、生成文档。它已经能展示事实确认表、封面格式行、必选章节、生成进度、评分覆盖报告和 Word 下载入口。问题是目录结构展示仍是普通树，正文生成不可见，只能看到“正在逐章生成内容”；`generateSSE` 以 fetch 读取 SSE，但后端发送的是进度而非 token；生成结果主要进入 Word 或 OnlyOffice，缺少可控的章节级结构编辑。

`Editor.vue` 只是 OnlyOffice 容器，依赖 `/api/bidding/projects/<project_id>/editor-config` 返回 `DocsAPI.DocEditor` 配置。OnlyOffice 适合终稿编辑和文件级协作，但不适合作为 AI 选区改写、引用溯源、章节状态、RAG 证据和评论系统的主编辑器。`front/src/admin/views/KnowledgeBase.vue` 只支持创建知识库和上传文档，缺少企业资信、产品、历史标书、图片资产的独立管理视图，无法维护产品参数、图片用途、适用章节、脱敏状态和引用政策。

参考项目前端已经体现 V2 方向：`frontend/src/components/editor/TiptapBidEditor.tsx` 基于 TipTap，支持标题、列表、表格、图片节点、Markdown 与 JSON 双向转换和资产签名 URL 替换；`frontend/src/pages/BidEditor/index.tsx` 提供正文模式/目录模式、技术标/商务标筛选、章节树、批量并发生成、章节保存、全文设置、图文导出、合规抽屉、语义复核、章节下载；`frontend/src/pages/KnowledgeBase/index.tsx` 提供知识库列表、分类、索引状态、chunk 预览；`frontend/src/pages/ProductBase/index.tsx` 提供产品资产上传、产品类型、规格型号、适用分册、适用章节、标签、允许自动插入标书等字段。V2 应把当前 Vue 端继续保留为迁移起点，还是切到 React + TipTap，需要在开发计划中定案；从企业编辑体验看，TipTap 主编辑器是必须落地的。

### 2.3 后端架构

当前后端的优点是业务对象已经基本齐全：`bid_projects` 记录项目元数据、行业、预算、截止时间、分析数据、目录结构；`project_facts` 记录项目事实和置信度；`document_files`、`document_versions`、`document_file_blobs` 支持文件版本；`knowledge_bases`、`knowledge_documents`、`document_chunks` 支持知识库文档与分片；`bid_documents`、`bid_chapters`、`bid_chapter_versions` 支持标书章节版本；`generation_tasks` 和 `agent_runs` 支持任务与 Agent 日志；`rag_evidence_packs`、`rag_evidence_items` 支持证据包；`response_matrix_items`、`consistency_issues`、`compliance_reports` 支持合规与响应矩阵；`rewrite_tasks` 支持选区改写补丁；`research_tasks`、`research_reports`、`research_sources` 支持深度研究。

问题是这些表尚未形成稳定业务闭环。例如 `api/bidding.py` 的全文生成会创建 `bid_documents` 和 `bid_chapters`，但 `Generation.vue` 的主要展示仍依赖一次性生成结果；`api/generation.py` 可以重生成章节并创建证据包，但前端没有成熟的章节级编辑工作台；`create_evidence_pack` 记录证据，但生成内容没有细粒度 citation record；`check_chapter_consistency` 和 `create_compliance_report` 更像后处理检查，不是 Agent 状态机中的强制节点；`storage_service` 将二进制塞入 MySQL，生产会被 `max_allowed_packet`、备份恢复和查询性能拖住；`init_mysql()` 在应用启动时建表，迁移可控性不足。

参考项目后端的模块拆分值得吸收。`backend/api/outline.py`、`sections.py`、`knowledge.py`、`assets.py`、`export.py`、`onlyoffice.py`、`compliance.py` 将业务域拆开；`backend/ai/chapter_planner.py` 实现规则版大纲快速流式输出、后台 AI 精修、分册结构标准化、知识库上下文注入；`backend/ai/section_writer.py` 实现正文 token 流式输出、资料候选、分册策略、篇幅不足自动补写；`backend/core/bid_volumes.py` 将技术标、商务标、资格、报价、附件的写作 focus、constraints、retrieval_hint、image_policy 集中定义；`backend/rag/retrieval.py` 实现文档与图片资产检索、Rerank 和关键词兜底；`backend/export/md_to_word.py` 显著增强了 Word 排版、图片插入、目录页码刷新、安全图片读取。V2 后端应采用类似分层，但要以当前项目已有 MySQL 表和 API 为迁移源，不能直接替换成 Supabase SDK。

### 2.4 AI 调用链

当前项目 AI 链路主要有三条。第一条是招标预分析：`api/bidding.py` 的 `/pre-analysis_bid` 读取招标文件，创建 `generation_tasks`，调用 `run_tender_parser_agent`，提取项目名称、采购人、代理机构、采购方式、预算、截止时间、服务期限、资格要求、评分办法、废标条款、关键要求和投标文件格式；随后尝试 `extract_template_contents` 抽取格式章节模板，并调用 `run_fact_keeper_agent` 写入事实确认。第二条是目录设计：`/chapter-design` 基于 `analysis_data` 和用户确认的格式要求构造大 prompt，要求输出含一级章节、二级节、三级小节、目标字数和章节类型的 JSON。第三条是全文生成：`/generate-bid-document` 为每章创建 `bid_chapters`，尝试联网搜索，针对章节用 `retrieval_router.search` 召回 3 个片段，把 RAG 和联网研究上下文拼给 `generate_bid_section`，最后合并 Markdown 并导出 Word。

这条链路的主要限制是 prompt 巨大而集中，Agent 不可替换，输出不可中断，不支持 token 级前端接收，不支持每章独立 retry 和并行，不记录每段内容的来源，不区分企业资料、产品资料、历史标书、图片资料，不支持 Reviewer 在生成前拦截风险，也没有缺资料追问闭环。`services/qwen_client.py` 的 `generate_bid_section` 强制每章不少于 3000 字、技术方案不少于 4000 字、包含 Mermaid，这会导致部分资格、商务、报价章节被灌水，并且 Mermaid 不是企业图片资产或正式图表目录的替代。

参考项目的 AI 链路更接近 V2：`chapter_planner.py` 先用规则大纲秒级输出，再后台 AI 精修，防止用户长时间等待；大纲最小章节数由评分项、要求数量和风险项动态计算；`section_writer.py` 通过 `stream_dashscope_api` 或 DeepSeek stream 将 chunk 输出给前端，篇幅不足时用补写 prompt；`bid_volumes.py` 明确不同分册的禁编造约束；`compliance_checker.py` 将要求条款、评分项和风险项映射到章节，形成覆盖报告；`semantic_compliance.py` 进一步做 LLM 语义复核。V2 应将这些思想升级为正式多 Agent 编排，而不是继续把它们散落在函数里。

### 2.5 数据流

当前数据流为：用户上传招标文件到 `/api/bidding/upload`，后端创建 `bid_projects`、`bidding`、`document_files`、`document_file_blobs`，然后 `ingest_document` 抽取文本、切片、写入向量库和 `document_chunks`。预分析读取 `bidding.file_id` 最新 blob，LLM 输出 JSON 存入 `bid_projects.analysis_data`，事实进入 `project_facts`。目录设计只返回前端 JSON，不稳定落入结构化章节表，直到全文生成时才创建 `bid_documents` 和 `bid_chapters`。全文生成过程逐章生成 content，写入 `bid_chapter_versions`，最终合并为 Markdown 和 DOCX，再作为 `document_files` 保存。OnlyOffice 编辑时通过 callback 从 OnlyOffice 下载新文件，追加 `document_versions`。

V2 数据流必须变化为：招标文件入库后先进入 Document Center，解析结果以章节、页码、表格、图片、OCR 质量、原文位置存储；Tender Parser Agent 输出项目事实、评分项、风险项、格式模板、响应矩阵；Chapter Planner 创建 `bid_document`、`bid_chapter` 和 `chapter_strategy`，并将分册策略写入数据库；RAG Engine 对每个章节生成检索任务，Knowledge Center 返回文本证据和图片候选，写入 `retrieval_log` 和 `citation_record`；Image Planning Agent 在章节生成前输出 `image_plan`，Image Center 按优先级选择企业图片、历史图片或 AI 生图；Writer Agent token 流式写入 TipTap 文档；Reviewer Agent 产生风险、缺失、重复和格式问题；用户在 TipTap 中确认、修改、评论；Export Center 从结构化章节、引用、图片计划和模板生成 Word，并写回版本。

### 2.6 文件解析流程

当前解析能力以 `services/ingestion_service.py` 为核心，使用 PyPDF2 读 PDF 文本，Mammoth 读 doc/docx 文本，普通文本用编码列表解码。优点是轻量、依赖少；缺点是无法稳定处理扫描版 PDF、复杂表格、图片、页码、版面结构、目录、证书扫描件和图文混排历史标书。`extract_text_from_bytes` 只返回纯文本，分片时丢失页码和图像位置，后续引用溯源只能靠 chunk，而不是准确定位到页、表、图、附件。

参考项目引入 `backend/parsing/mineru_client.py`、`document_parser.py`、`bid_interpreter.py`，能将 MinerU 产物中的 Markdown、content_list、page_idx、block type、图片节点和质量报告写入 PostgreSQL。`bid_interpreter.py` 的 `build_mineru_quality_report` 会统计 Markdown 字符数、内容块、页数、疑似乱码和缺页；`build_document_chunks` 会把 `source_page`、`source_section`、parser、bid_file_id 写入 metadata。V2 应将解析分为三层：基础文本解析保留当前 Mammoth/PyPDF2 作为降级；标准解析使用 LibreOffice/Pandoc/Mammoth 组合处理 docx；高质量解析使用 MinerU/OCR 处理扫描 PDF、图片和版面。解析后的所有 chunk 必须带页码、章节路径、块类型、原文 hash 和文件版本。

### 2.7 Word 导出流程

当前 `export/md_to_word.py` 能设置页眉页脚、封面、标题、列表、表格和 Mermaid。它用 `python-docx` 逐行解析 Markdown，Mermaid 优先调用 `mmdc` 转 PNG，失败则用 Word 表格文本框表达流程；封面可从招标文件 `cover_page.cover_lines` 和 `project_facts` 填充；页脚有 PAGE 和 NUMPAGES 字段。问题是没有正式目录页、没有图表目录、没有图片资产插入、没有引用尾注、没有交叉引用、没有 LibreOffice 刷新页码，没有对远程图片安全和压缩处理，也没有按分册拆包。

参考项目的导出能力更强：`backend/export/md_to_word.py` 有 `clean_formal_bid_text` 清理正式标书不适合的符号，有 `_add_toc_page` 创建目录和 `PAGEREF` 字段，有 `_add_bookmark` 书签，有 `refresh_docx_fields_with_soffice` 用 LibreOffice headless 刷新目录页码，有 `process_markdown_image` 插入 Markdown 图片并生成中文图注，有远程图片安全校验和图片压缩，有 `build_project_bid_markdown` 从 `bid_sections` 快照导出并自动插入知识库图片。V2 应以该方向重建 Export Center：导出不再从一次性 Markdown 字符串开始，而从章节树、正文 JSON、图片计划、引用记录、封面模板、目录策略和分册策略生成。

### 2.8 知识库设计

当前知识库以 `knowledge_bases`、`knowledge_documents`、`document_chunks` 为中心，`kb_type` 可填 enterprise/department/project，上传时 `doc_type` 默认 history_bid，文件先写 `document_files` 再 `ingest_document`。检索入口 `/knowledge/search` 调 `retrieval_router.search`，可以按项目、知识库和 doc_type 过滤。这个设计适合作为统一文档入库的最小骨架，但不适合企业投标知识中心，因为企业资信、产品、历史标书和图片资产的元数据完全不同。

V2 Knowledge Center 要把“库”变成业务对象。企业资信库要维护企业名称、简介、成立时间、注册资本、员工规模、核心资质、获奖情况、证书、人员、业绩、信誉和审查状态；产品库要维护产品介绍、技术参数、图片、方案、案例、适用行业、适用分册和禁用规则；历史标书库要维护技术标、商务标、资格标、报价标、附件、项目类型、中标状态、客户、行业、复用政策；图片资产库要维护产品图片、项目案例图片、施工图片、架构图、流程图、证书图片、组织架构图，并记录图片来源、授权、脱敏、合成、AI 审核结果、适用章节和可插入状态。参考项目的 `knowledge_assets` 和产品库页面说明了该方向，但 V2 需要将其行业泛化，不只服务电网。

### 2.9 Prompt 设计

当前 prompt 主要硬编码在 `services/agent_orchestrator.py`、`services/qwen_client.py`、`api/bidding.py`。它们的问题不是“不够长”，而是缺少可配置、可追踪、可继承、可测试。目录设计 prompt 对所有项目使用同一套章节数量和结构要求，正文 prompt 对所有章节都要求大量二级节、三级小节和 Mermaid，容易引入不符合格式性章节的内容。图片 prompt 尚不存在。历史标书复用政策没有进入 prompt。RAG 证据和引用格式没有统一输出协议。

参考项目将分册策略放在 `backend/core/bid_volumes.py`，这是一个好方向：技术标强调施工组织、技术方案、质量安全、产品图；商务标强调条款响应和禁编造金额日期；资格文件强调证照、业绩、人员和脱敏说明；报价文件禁止编造金额；附件强调来源和替换要求。V2 需要进一步建立 Prompt Template Management：行业模板、企业模板、项目模板、章节模板四级继承；系统 prompt、任务 prompt、输出 schema、禁编造清单、引用格式、图片 prompt 均版本化；每次 Agent 调用记录 template_id、template_version、变量、模型、输出和审阅结果。

## 3. 保留、重构、删除与技术债

### 3.1 当前项目应保留

保留 `core/db.py` 中的业务对象思想，但迁移为显式 migrations。租户、企业、项目、文件、知识库、chunk、章节、版本、任务、Agent 运行、证据包、响应矩阵、合规报告、研究来源都是 V2 需要的对象。保留 `storage/storage_service.py` 的文件版本模型，但生产实现从 MySQL BLOB 迁移到 MinIO/OSS/S3，本地可保留 MySQL/本地文件作为开发模式。保留 `services/model_router.py` 的多模型路由和调用日志思想，但扩展为 Model Center，支持流式、Embedding、Rerank、图像生成、图像审核和成本核算。保留 `services/ingestion_service.py` 的轻量解析作为降级路径。保留 `api/bidding.py` 的事实确认门禁体验，升级为多确认 Gate：项目事实、评分项、目录、图片计划、关键风险、引用缺失。保留 `api/generation.py` 的章节版本和选区改写任务思想，接入 TipTap 选区和建议系统。保留 OnlyOffice，但定位为终稿编辑和客户已有文档编辑，而不是主 AI 编辑器。保留 `export/md_to_word.py` 的基础 Word 能力，作为 Export Center 的早期实现。

### 3.2 当前项目必须重构

`api/bidding.py` 必须拆分。上传/项目、解析/预分析、目录、生成、导出、OnlyOffice 回调、确认门禁不能继续混在一个蓝图中。`/generate-bid-document` 必须从一次请求串行全文生成，重构为 Agent Task + SSE/WebSocket 事件 + 可恢复章节任务。`services/qwen_client.py` 必须从单 provider wrapper，升级为支持 OpenAI-compatible stream、DashScope stream、DeepSeek stream、Embedding、Rerank、Image Generation 的模型中心客户端。`services/retrieval_router.py` 必须升级为 Hybrid Search：PostgreSQL Full Text Search、PGVector、DashScope Rerank、Context Builder、缓存、检索日志、citation record。`storage/vector_store.py` 的 Chroma/Milvus 适配可保留开发降级，但企业级默认应迁移 PostgreSQL + PGVector，减少业务数据和向量数据割裂。`front/src/user/views/Generation.vue` 的五步流程要升级为项目工作台，生成不再是最后一步黑盒，而是进入 TipTap 实时编辑工作台。`front/src/admin/views/KnowledgeBase.vue` 必须拆成企业资信库、产品库、历史标书库、图片资产库。`export/md_to_word.py` 必须支持图片目录、图表编号、交叉引用、引用尾注、分册导出和字段刷新。

### 3.3 当前项目应删除或冻结

`frontend/` 旧版原生页面应冻结并最终删除。`legacy/routes_copy.py` 应迁移有用逻辑后删除。`api/bidding.py` 中的旧接口名 `/pre-analysis_bid`、`/chapter-analysis_bid` 建议保留兼容层一段时间，但新前端只能调用 `/api/v2/projects/{id}/interpretation` 等规范接口。硬编码的“每章至少 3000 字、必须 Mermaid”生成规则应删除，改为 `chapter_strategy` 驱动。生产环境不应继续默认将所有文件二进制写入 MySQL。自动建表的 `init_mysql()` 生产路径应关闭，由迁移工具负责 schema。

### 3.4 技术债务

当前主要技术债包括：Flask 同步请求承载长任务，缺少队列和任务恢复；SSE 是章节进度流，不是 token 流；MySQL BLOB 存储大文件导致数据库膨胀；RAG 分片无页码、无结构、无引用；知识库类型过粗；AI prompt 硬编码且无版本；Agent 状态只有日志，没有状态机；前端编辑器无法承载 AI 选区操作；OnlyOffice 回调对安全和版本冲突处理不足；`storage/vector_store.py` Milvus 查询只返回 metadata，需要再 hydrate，且出错自动回 Chroma，生产可能静默降级；`retrieval_router._mysql_text_search` 用 LIKE，无法满足企业全文检索；`_fill_enterprise_info` 用字符串替换“本公司”“投标人”，可能破坏语义和正式称谓；Word 导出逐行解析 Markdown，复杂表格、图片、页码和引用都脆弱。

### 3.5 性能瓶颈

上传后同步 ingest 会阻塞用户；Embedding 批大小固定为 10，缺少异步批处理和重试；全文生成串行逐章调用模型，几十章会导致分钟级等待且断线丢失；检索每章实时调用向量库和 MySQL，没有缓存；深度研究在全文生成前同步执行，网络不稳定会拖慢生成；大文件写入 MySQL blob 会占用连接和 packet；Flask dev server 不适合长 SSE，参考项目 README 已明确使用 gunicorn gevent 解决长连接阻塞；前端 fetch SSE 没有断线恢复和 task resume；Word 导出在请求内完成，复杂图片和 LibreOffice 刷新会阻塞。

### 3.6 扩展性问题

行业扩展目前靠 prompt 常识，不能配置电网、新能源、建筑、制造、医疗、交通、水利、教育、通信、军工、政务等行业模板。知识库扩展目前靠 doc_type 字符串，无法表达产品参数、图片权限、证书有效期、案例地域、历史标书复用策略。Agent 扩展目前靠新增 Python 函数，没有统一输入输出 schema、状态流和错误恢复。前端扩展目前缺主编辑器插件系统。导出扩展目前只有 Markdown 到 Word，不支持模板包、分册包、引用尾注和图表目录。

### 3.7 用户体验问题

用户看不到 token 级生成过程，只能等待进度条；生成后如果某章不满意，要么 OnlyOffice 人工改，要么调用较原始的章节重生成接口；缺少“为什么这样写”的引用来源；缺少“哪些资料不足”的追问；知识库上传后不知道哪些片段可用、哪些图片能插入；目录生成后不能像专业标书目录一样按分册查看、拖拽、标记风险；Word 下载前不知道评分项、资格项、图片和附件是否齐全；图片只能靠模型写 Mermaid，无法插入企业真实产品图、证书图和案例图。

## 4. V2 产品目标

V2 的一句话目标：将当前项目升级为可私有化部署、可持续沉淀企业资料、可多 Agent 协作生成和审阅、可实时编辑和正式导出的企业级 AI 投标 Agent 平台。

核心能力包括：招标文件解析、企业知识库、产品知识库、历史标书知识库、图片知识库、多 Agent 协作、企业级 RAG、长文本生成、智能配图、AI 生图、Word 自动排版、引用溯源、流式生成、在线协同编辑。V2 不再接受“上传招标文件、调用大模型、输出标书”作为产品闭环；每个生成结果都必须能追溯到招标要求、企业资料、历史案例或明确标记为模型生成建议。

V2 的产品成功标准分为四类。第一类是可用：企业用户能够上传招标文件、维护知识中心、生成分册目录、逐章流式生成、在线编辑、导出 Word。第二类是可信：每个关键事实、产品参数、资质、案例、图片都能点击查看来源；缺失资料用待补充和追问体现，不编造。第三类是可控：用户能确认事实、确认目录、调整章节策略、选择图片、接受或拒绝 AI 改写、查看风险和覆盖率。第四类是可运营：管理员能管理模型、知识库、图片模板、行业模板、成本、任务日志和审计。

## 5. 用户角色与场景

标书负责人：负责项目投标全流程，希望快速解读招标文件、规划分册、分配章节、审阅风险、导出正式 Word。该角色关注评分点覆盖、格式响应、风险拦截、目录完整和交付时间。

标书撰写人员：负责技术标、商务标、资格文件或报价说明的具体章节，希望 AI 生成初稿后能在编辑器中续写、改写、润色、扩写、压缩、问答和选区优化。该角色关注流式体验、引用依据、段落质量、选区改写和版本回退。

企业知识库管理员：负责上传企业资质、产品资料、历史标书、案例图片、证书图片和标准话术，希望资料被正确解析、分类、脱敏、审核和召回。该角色关注资料结构化、检索效果、权限、有效期和可插入状态。

产品/技术专家：负责维护产品介绍、技术参数、产品方案、案例和图片，希望投标时产品能力被正确匹配，不被模型编造参数。该角色关注产品库字段、参数来源、适用行业、图片质量和章节适配。

审核人员/法务/商务：负责检查一致性、格式、缺失、风险、重复内容、报价禁区和引用合规。该角色关注审核 Agent 输出、修订建议、评论、待办和导出前阻断。

系统管理员：负责模型配置、部署、成本、权限、审计和安全。该角色关注多模型路由、API Key 管理、任务队列、日志、费用、租户隔离和备份。

## 6. 端到端用户旅程

旅程一：招标文件解读。用户创建项目并上传招标文件。系统进入 Document Center，优先使用高质量解析，解析出文本、表格、图片、页码、章节路径和 OCR 质量。Tender Parser Agent 输出项目识别、行业识别、评分项、招标要求、资格要求、格式要求、废标风险、附件清单和项目事实。系统展示事实确认页面，用户可以确认、修改或标记待补充。确认后生成响应矩阵。

旅程二：知识准备。用户进入 Knowledge Center，维护企业资信库、产品库、历史标书库、图片资产库。系统对文本做 chunk 和 embedding，对图片做 OCR、AI caption、适用章节识别和向量化。管理员可以设置资料复用政策：可直接引用、必须改写、仅内部参考、禁止引用。图片资产可以设置是否脱敏、是否合成、是否允许自动插入标书、适用行业、适用分册、适用章节和版权说明。

旅程三：目录与策略。Chapter Planner 根据招标文件格式要求、评分项、风险项、企业资料可用性生成分册目录。系统先流式展示规则骨架，再用 AI 精修补全。用户可以按技术标、商务标、资格标、报价标、附件查看目录，拖拽调整章节，设置目标页数/目标字数，确认每章的 strategy、target_words、needs_table、needs_image、needs_qualification、needs_case。

旅程四：章节生成。用户点击生成本章或一键编写全文。Agent Orchestrator 创建任务，RAG Engine 对章节执行 Hybrid Search，Image Planning Agent 输出 Image Plan，Writer Agent token 级流式写入 TipTap，Citation Collector 同步记录引用。若正文不足目标篇幅，Section Planner 拆分为小节，Writer 分段生成，Reviewer 检查后 Merge Agent 合并。前端展示正在生成、检索到的资料、正在插入的图片、风险提示和 token 流。

旅程五：编辑与协同。用户在 TipTap 中选择文本，点击 AI 续写、改写、润色、扩写、压缩、问答、选区优化。系统将选区、上下文、章节策略、引用约束传给编辑 Agent，返回建议而不是直接覆盖，用户接受或拒绝。审核人员可加评论、修订建议和风险标签。协同编辑 V2 预留 Yjs/Hocuspocus/Tiptap Collaboration 数据结构，企业版可开启多人光标、评论、版本快照和冲突解决。

旅程六：导出与交付。Export Center 根据章节树、正文、引用、图片计划、封面模板和分册策略生成 Word。系统自动插入图片编号，如“图 3-1 项目组织架构图”，生成图片说明、图片来源、图表目录、图片交叉引用和引用尾注。导出前 Reviewer 检查评分项覆盖、格式要求、缺失资料、缺失图片、重复内容、风险项和报价禁区。通过后生成完整标书、技术标、商务标、资格文件、报价文件、附件包。

## 7. 统一知识中心需求

Knowledge Center 是 V2 的数据核心，不再只是“上传文件到向量库”。它必须支持四类一等公民：企业资信库、产品库、历史标书库、图片资产库。

企业资信库字段包括企业名称、企业简介、成立时间、注册资本、员工规模、核心资质、获奖情况、营业执照、资质证书、安全生产许可证、人员证书、社保资料、业绩证明、信誉承诺、财务资料、有效期、审核状态、脱敏状态、可引用范围。系统要支持从上传文档、图片和人工表单中抽取结构化字段。凡涉及证书编号、人员姓名、合同金额、日期等高风险事实，必须有来源，缺失时 Writer Agent 只能输出待补充。

产品库字段包括产品介绍、技术参数、产品图片、产品方案、产品案例、规格型号、适用行业、适用分册、适用章节、关键能力标签、禁用行业、竞品替换规则、参数来源、版本、审核状态。产品图片必须可被 Image Planning Agent 召回，技术参数必须可被 RAG 召回，产品方案必须可被 Writer Agent 生成技术标章节。

历史标书库字段包括项目名称、客户/采购人、行业、地域、年份、中标状态、标书类型、技术标、商务标、资格标、报价标、附件、章节结构、评分项映射、复用政策、敏感等级、来源文件、版本。系统要支持将历史标书拆成章节级 knowledge chunk，并保留原标书图片作为历史图片库候选。中标标书可优先召回，但必须按当前项目改写；失败或未知结果标书默认仅参考结构，不直接复用。

图片资产库字段包括产品图片、项目案例图片、施工图片、架构图、流程图、证书图片、组织架构图、图片标题、说明、图片类型、行业、适用章节、适用分册、标签、来源、版权、是否企业自有、是否 AI 合成、是否脱敏、清晰度、尺寸、审核状态、可插入状态。系统要支持图片预览、OCR、AI caption、向量化、相似图片检测和批量审核。

## 8. 企业级 RAG 需求

V2 RAG 必须采用 Hybrid Search，而不是单向量召回。标准链路为 Query → Keyword Recall → Vector Recall → Rerank → Context Builder → LLM。关键词召回使用 PostgreSQL Full Text Search 和 trigram/LIKE 兜底，解决资质名称、证书编号、产品型号、招标编号等精确命中问题；向量召回使用 PGVector，解决语义相似、历史方案复用、产品能力匹配；Rerank 使用 DashScope Rerank 或可替换 rerank model，解决 topK 噪声；Context Builder 负责去重、按来源类型配额、截断、引用编号、事实禁编造提示和 token 预算。

检索必须按业务域设置配额。例如技术标章节默认从产品库、历史技术标、技术标准、项目资料、图片资产各取候选；资格章节优先企业资信库和历史资格文件；商务章节优先商务模板、合同响应、承诺函和企业资信；报价章节默认不召回具体金额，除非用户上传了当前项目报价资料并确认。每次检索必须写 `retrieval_log`，每个进入 prompt 的片段必须产生可追踪 citation candidate，最终正文引用必须写 `citation_record`。

RAG 验收标准：同一个章节标题和项目事实重复生成时，检索结果可复现；每段引用可追到 source file、chunk、页码、章节路径；检索结果中企业资信、产品参数、历史标书和图片资产不能混淆；资料不足时返回缺口，不允许模型用常识补齐证书、人员、金额和日期。

## 9. 多 Agent 需求

V2 Agent 不是几个函数名，而是可编排、可恢复、可观测的任务系统。必须实现 Agent Orchestrator，统一管理状态、上下文、事件、模型调用、RAG 证据、图片计划、错误重试和用户确认。

招标文件解析 Agent 负责项目识别、行业识别、评分项提取、招标要求提取、资格要求提取、格式模板提取、废标风险识别、附件清单识别和页码溯源。企业匹配 Agent 负责企业资料召回，输出企业能力与招标要求的匹配矩阵。产品匹配 Agent 负责产品资料召回，输出产品能力、参数、图片和案例候选。图片规划 Agent 在章节生成前分析当前章节是否需要图片、需要什么图片、插入到哪里、图片说明是什么，输出 Image Plan。技术标 Agent、商务标 Agent、资格标 Agent、报价标 Agent 按分册策略生成正文。审核 Agent 负责一致性检查、格式检查、缺失检查、风险检查、重复内容检查和引用缺失检查。

Agent 运行状态至少包括 queued、running、waiting_user、blocked、retrying、succeeded、failed、cancelled。每个 Agent 输入输出必须 JSON schema 化，关键字段进入 `agent_task` 和 `agent_run_event`。前端必须能展示 Agent 当前正在做什么，例如“正在召回企业资质”“正在规划产品配图”“正在检查评分项覆盖”“正在写入第 3.2 节”。失败时允许从章节或 Agent 节点恢复。

## 10. 分册写作策略需求

系统必须实现 Strategy Pattern，不同册采用不同约束。技术标强调技术方案、产品能力、案例、实施路径、质量安全、进度资源和可验证措施；允许使用产品图、设备图、架构图、流程图和施工案例图。商务标强调企业实力、项目经验、服务能力、合同条款响应、偏离表和承诺；禁止编造金额、日期、签章、保证金账号、保函编号。资格标强调资质、证书、人员、业绩、信誉和附件索引；图片可使用证照样张，但必须标明脱敏或待替换。报价标强调报价说明、成本逻辑、清单复核和风险边界；禁止生成具体金额、单价、税率和工程量，除非用户确认了当前项目报价资料。附件强调自动引用资料、来源、用途、缺失状态和人工替换要求。

当前项目 `generate_bid_section` 对所有章节使用同一套“大篇幅正文”规范必须被替换。参考项目 `bid_volumes.py` 的 `VOLUME_GENERATION_STRATEGIES` 可作为 V2 初始策略来源，但要从代码常量升级到 `chapter_strategy` 表，支持企业和行业覆盖。

## 11. 实时生成与 TipTap 编辑需求

V2 必须实现 token 级流式输出，支持 SSE 和 WebSocket。SSE 用于单向生成事件：章节生成、知识库问答、导出进度、Agent 状态；WebSocket 用于双向协同：多人编辑、AI 工具调用、评论、修订、任务控制。当前 `/generate-bid-document` 的章节级 SSE 只能作为过渡，不满足用户实时看到正文的需求。参考项目 `section_writer.py` 已证明后端可将 `stream_dashscope_api` chunk 透传给前端，V2 应以此重构。

主编辑器必须引入 TipTap。现有 OnlyOffice 保留为终稿编辑，但 TipTap 是 AI 生成和协同编辑主入口。TipTap 页面必须支持 AI 续写、AI 改写、AI 润色、AI 扩写、AI 压缩、AI 问答、AI 选区优化、评论系统、修订模式、协同编辑预留。用户选区后，AI 操作默认返回 suggestion，用户可以接受、拒绝、继续追问或插入评论。正文生成时，token 要逐步进入当前章节，光标和滚动体验接近 ChatGPT/Claude/Cursor。章节树要同步显示生成状态、字数、引用数量、图片数量、风险数量和待补充数量。

TipTap 官方能力选型以其 Content AI、AI Toolkit、Comments、Collaboration 为参考：AI Toolkit 支持读、插入、patch、streaming、suggestions；Comments 支持线程和评论；Collaboration 基于 Yjs/Hocuspocus，支持实时协作、presence、版本历史和 on-prem。V2 首期可先使用开源 TipTap + 自研 AI 菜单 + SSE 写入；企业协同版再接入 Yjs/Hocuspocus 或 Tiptap Collaboration。

## 12. 智能图片系统需求

智能图片系统是 V2 核心能力之一，必须和正文生成同级设计。图片不是“最后插几张图”，而是章节生成前的规划输入。

图片规划 Agent 输入当前章节、章节策略、行业、招标要求、评分项、企业资料、产品资料和历史标书图片。它输出 Image Plan，字段包括 chapter_id、section_path、need_image、image_type、image_count、placement、caption、source_priority、query、prompt_hint、required_resolution、risk_notes。系统应能识别组织架构需要组织架构图，系统架构需要系统架构图，产品介绍需要产品效果图，项目实施方案需要流程图，施工方案需要施工现场图，资格文件需要证书图，附件需要证明材料图。

图片来源策略必须严格按优先级：企业图片知识库 → 历史标书图片库 → AI 自动生成图片。若企业图片库命中高质量真实图片，不允许优先 AI 生图。历史标书图片必须检查复用政策和敏感信息。AI 生图只能用于流程图、架构图、示意图、非特定真实场景或经过企业允许的产品效果图；资质证书、合同、中标通知书、人员证件、报价单不得 AI 生成伪造。

行业识别系统必须自动识别电网、新能源、建筑、制造业、医疗、交通、水利、教育、通信、军工、政务和其他行业。行业识别结果影响 RAG 配额、图片类型、Prompt 模板和审核规则。电网行业图片要求国家电网风格、输电线路、变电站、电力设备、工业蓝白风格、真实工程场景、禁止 AI 插画风。建筑行业要求 BIM、工程现场、施工管理、建筑效果图。医疗行业要求医院环境、医疗设备、临床场景。每个行业模板必须可以被企业模板、项目模板和章节模板继承覆盖。

Prompt 模板管理系统必须支持行业模板、企业模板、项目模板、章节模板四级继承。模板字段包括 positive_prompt、negative_prompt、style_constraints、composition、camera、color、resolution、forbidden_elements、audit_rules、example_images。电网企业可在行业模板基础上加入企业品牌色、产品外观、工程案例风格；项目模板可加入项目地域、场景和采购人风格；章节模板可加入“组织架构图”“实施流程图”等具体图型。

AI 图片生成系统首期设计为适配层，支持 ComfyUI、Flux、SDXL、Qwen Image。流程为行业识别 → 章节理解 → 图片规划 → Prompt 生成 → AI 生图 → 质量审核 → 入库 → 文档插入。每张 AI 图必须记录模型、workflow、seed、prompt、negative_prompt、生成时间、审核结果和是否允许进入正式标书。

图片审核 Agent 必须检查图片相关性、图片质量、清晰度、幻觉、违规内容、文字错误、证件伪造风险、人物肖像风险、品牌风险和行业风格偏差。审核不通过时自动重试生成，重试次数和原因写入 image_generation_task。对于资质、证书、合同等高风险图片，系统只能使用企业上传资料，并强制人工确认。

Word 自动插图必须支持图片编号和目录。例如插入“图 3-1 项目组织架构图”，并自动生成图片说明、图片来源、图片编号、图片目录、图表目录和图片交叉引用。导出时图片编号要随章节编号更新，删除或移动章节后重新编号。

## 13. 引用溯源需求

所有内容必须记录来源，包括企业资料、产品资料、历史标书、图片、案例、参数、法规、招标原文、用户手工确认事实。正文中的关键事实、证书、人员、金额、日期、产品参数、案例名称、图片说明必须关联 `citation_record`。前端支持点击查看来源，来源视图展示文件名、版本、页码、章节路径、chunk 内容、相似度、rerank 分、引用类型和使用方式。若某段为模型总结但无直接来源，必须标记为“AI 生成建议”，不能伪装成企业事实。

引用验收标准：导出前系统能列出全篇引用清单；点击引用能打开来源文件预览或 chunk；删除来源资料后相关章节显示引用失效；图片引用显示来源、版权、脱敏、是否 AI 合成；历史标书引用显示复用政策；引用缺失的高风险事实必须进入审核问题。

## 14. AI 追问系统需求

章节生成后，Follow-up Agent 必须自动分析缺失资料、缺失图片、风险点、评分项缺失、建议补充材料，输出 Follow-up Questions。追问不应泛泛问“是否补充更多资料”，而要具体，例如“资格文件第 2.3 节引用项目经理资料，但知识库中没有项目经理注册证书和社保证明，请上传或确认是否删除该章节”；“技术标第 4.2 节需要产品参数表，产品库中缺少额定电压/防护等级/适用标准字段”；“图片规划要求组织架构图，但图片库未命中组织架构图，是否使用系统自动绘制流程图样式”。

追问结果必须可操作：上传资料、填写字段、忽略、改写章节、重新检索、重新生成图片、标记人工处理。追问状态写入数据库，进入项目待办和导出前检查。

## 15. 长文本生成需求

V2 必须解决大模型上下文窗口限制。长文本生成链路为 Chapter Planner → Section Planner → Writer Agent → Reviewer Agent → Merge Agent → Exporter。Chapter Planner 决定章节和目标篇幅，Section Planner 将大章节拆成可独立生成的小节，Writer Agent 按小节流式生成，Reviewer Agent 检查重复、引用、风险和风格，Merge Agent 合并并统一术语、编号、引用和图表，Exporter 输出 Word。

对于 80 页以上技术标，系统不得一次性把所有上下文塞给模型。每个章节只拿必要招标要求、评分项、企业资料和历史案例。Context Builder 负责 token 预算。章节间共享术语和事实通过 Project Memory 管理。重复检查必须跨章节执行，避免多个章节重复“公司高度重视本项目”的空泛段落。

## 16. OpenAPI 与集成需求

V2 API 必须规范化为 `/api/v2`，保留当前接口一段兼容期。接口域包括 Project、Document、Knowledge、RAG、Agent、Image、Editor、Stream、Export、Review、Settings。所有长任务返回 task_id，所有流式接口支持 `Last-Event-ID` 或 task resume。所有关键对象使用稳定 ID，所有修改接口写审计日志。

前端不得直接依赖 `bidding` 旧表语义。新接口要以 project_id、document_id、chapter_id、agent_task_id 为核心。旧接口 `/api/bidding/upload`、`/api/bidding/pre-analysis_bid`、`/api/bidding/chapter-design`、`/api/bidding/generate-bid-document` 可以由兼容层转发到 V2 服务。

## 17. 非功能需求

性能：单个 100MB 招标文件可后台解析，上传接口 3 秒内返回任务；普通章节 token 流首包 5 秒内出现；批量生成支持并发 3 到 5 章，可暂停和恢复；知识库检索 p95 小于 2 秒；Word 导出普通 100 页标书 p95 小于 3 分钟。

可靠性：长任务断线可恢复；模型失败可重试和切换；RAG 失败时明确 degraded，不静默编造；导出失败保留 Markdown 和错误报告；图片生成失败不阻断正文，进入待处理。

安全：租户隔离；知识库权限按企业、部门、项目、个人；API Key 加密存储；文件下载鉴权；OnlyOffice callback 验签；图片远程下载防 SSRF；AI 生图禁止伪造证件和合同；审计记录用户、时间、操作、对象和差异。

可部署：本地开发可使用 Docker Compose PostgreSQL + MinIO + Redis；生产建议 PostgreSQL + PGVector、Redis、对象存储、Celery/RQ、Gunicorn/Uvicorn、Nginx、可选 MinerU/ComfyUI 独立服务；支持内网私有化。

可观测：模型调用、Embedding、Rerank、OCR、生图、导出、Agent 状态、检索质量、引用缺失、成本均可统计。参考项目已有 `ai_usage_logs` 思路，V2 应纳入 Model Center。

## 18. 验收标准

V2 第一阶段可验收为：用户能上传招标文件，解析出项目事实、评分项、风险项和格式要求；用户能维护企业资信、产品、历史标书、图片四类资料；系统能生成分册目录；用户能进入 TipTap 编辑器，看到章节 token 级流式生成；生成内容能显示引用来源；至少支持从图片库自动插入图片到 Word；导出 Word 有封面、目录、页眉页脚、章节编号、图片编号和基础引用清单。

V2 完整验收为：多 Agent 状态可视化；Hybrid Search 有关键词、向量、Rerank、Context Builder；图片规划、来源优先级、AI 生图、图片审核、入库和导出闭环可用；AI 追问可生成可操作待办；长文本生成可拆分、合并、审核；TipTap 支持续写、改写、润色、扩写、压缩、问答、选区优化、评论和修订预留；导出前合规检查能拦截高风险缺失；所有关键事实和图片可点击溯源。

## 19. 产品风险

最大风险一是把 V2 做成“更大的 prompt 工具”，没有真正建立知识中心、引用和任务状态。规避方式是先实现数据结构和引用，再扩写生成能力。最大风险二是图片系统被误用为生成假证件、假合同、假现场。规避方式是建立图片类型黑名单、审核 Agent 和人工确认。最大风险三是 TipTap 与 Word 排版不一致。规避方式是 TipTap 存结构化 JSON/Markdown，Export Center 负责正式 Word，不承诺浏览器像素级 Word 所见即所得。最大风险四是迁移到 PostgreSQL + PGVector 工作量大。规避方式是 P0 保留 MySQL 兼容，但新表和新服务按 PostgreSQL 设计，逐步迁移。

## 20. 与参考项目的吸收边界

应吸收参考项目的模块拆分、流式章节生成、TipTap 编辑器、分册策略、PGVector + Rerank、知识资产检索、产品库页面、合规覆盖检查、正式 Word 导出和 LibreOffice 刷新字段。不能直接照搬参考项目的 Supabase SDK 数据访问层、电网行业硬编码、历史水利/电网种子库、乱码资产、单企业假设和部分页面文案。V2 是行业泛化平台，电网只是行业模板之一。

## 21. 交付物边界

本 PRD 不要求本次直接修改代码。开发团队拿到本 PRD、架构文档和重构计划后，应先建立 V2 分支，完成数据迁移设计、接口契约和 TipTap 原型，再逐步替换当前黑盒生成流程。任何代码改造不得删除用户已有上传文件和生成文档，不得破坏旧接口兼容，不得在没有迁移脚本的情况下改动生产表。
