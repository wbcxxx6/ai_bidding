# AI Bidding V2 P0 主链路设计

日期：2026-06-09

## 背景

当前仓库已经有 Flask + MySQL + Vue 的投标生成原型，也有较完整的 V2 PRD、架构文档和重构计划。用户确认本轮先落地 P0 主链路，并明确可以重构，不必拘泥于现有项目框架。

本设计采用 V2-first 重构：新能力进入清晰的 V2 模块，旧接口保留兼容，不继续扩大 `api/bidding.py`。

## 目标

P0 的目标是让系统从“全文黑盒生成 Word”转向“章节任务 + token 流 + TipTap 工作台 + 最小引用记录”的主链路。

完成后应满足：

- `/api/v2` 可用。
- 可以创建和查询 Agent task。
- 可以基于已有项目和章节创建单章生成任务。
- 单章正文以 token/chunk 级 SSE 流式返回前端。
- 前端 TipTap 工作台能加载章节、接收流式内容、保存正文。
- 生成时进入 prompt 的 RAG 证据会形成最小 `citation_record`，前端可查看来源列表。
- 旧上传、预分析、目录设计、全文生成和 OnlyOffice 入口不被破坏。

## 非目标

P0 不做以下事项：

- 不迁移 PostgreSQL + PGVector。
- 不实现完整 Hybrid Search、Rerank、PG Full Text Search。
- 不实现图片规划、AI 生图、图片审核、图目录。
- 不实现完整协同编辑、评论线程和修订模式。
- 不迁移对象存储，MySQL BLOB 和现有 storage service 继续作为 P0 兼容路径。
- 不把前端技术栈切到 React。

## 架构

后端保留 Flask 入口，但新建 V2 API 和服务分层。Flask 只是 Gateway，业务逻辑进入 service/repository。

建议新增模块：

```text
api/v2/
  __init__.py
  health.py
  agent_tasks.py
  streams.py
  chapters.py
  rag.py

services/v2/
  __init__.py
  agent_task_service.py
  chapter_generation_service.py
  editor_doc_service.py
  chapter_strategy_service.py
  citation_service.py
  context_builder.py

services/model_center/
  __init__.py
  stream.py
```

旧 `api/bidding.py`、`api/generation.py` 继续服务现有流程。P0 新前端页面优先调用 `/api/v2`。

## 数据模型

P0 暂时在 `core/db.py` 的启动 schema 中追加兼容表，后续 P1 再迁到显式 migrations。

新增表：

- `agent_task`：V2 任务主表，记录 project、chapter、task_type、status、input/output/error。
- `agent_task_event`：任务事件，记录 status、token、citation、error 等流式事件。
- `chapter_strategy`：章节策略，记录 volume_type、target_words、writing_style、forbidden_rules、rag_policy。
- `chapter_editor_docs`：TipTap/Markdown 编辑正文，记录 chapter_id、markdown_content、tiptap_json、version_no。
- `citation_record`：引用记录，记录 project、chapter、task、source_type、chunk_id、source_file_id、citation_key、quote_text、metadata。

兼容原则：

- 继续使用现有 `bid_documents`、`bid_chapters`、`bid_chapter_versions`。
- P0 的 editor doc 与 chapter version 双写：编辑器保存写 `chapter_editor_docs`，生成完成写 `bid_chapter_versions`。
- citation 先记录“进入 prompt 的证据”，不承诺段落级精准引用。

## API

P0 API：

- `GET /api/v2/health`：健康检查。
- `POST /api/v2/agent-tasks`：创建任务。P0 支持 `chapter_generate`。
- `GET /api/v2/agent-tasks/<task_id>`：查询任务和最近事件。
- `GET /api/v2/streams/tasks/<task_id>`：SSE 消费任务事件；如果任务未执行，启动同步流式执行。
- `GET /api/v2/chapters?projectId=<id>`：列出项目章节。
- `GET /api/v2/chapters/<chapter_id>/editor-doc`：读取编辑正文。
- `PUT /api/v2/chapters/<chapter_id>/editor-doc`：保存 Markdown/TipTap JSON。
- `POST /api/v2/rag/search`：P0 context builder 入口，复用现有 `retrieval_router` 并返回 citation candidates。

SSE 事件类型：

- `start`：任务开始。
- `status`：Agent 当前阶段，例如加载章节、检索资料、生成正文、保存版本。
- `citation`：进入 prompt 的证据来源。
- `token`：模型流式文本块。
- `done`：任务完成。
- `error`：任务失败。

## 生成流程

1. 前端在 TipTap 工作台选择章节，调用 `POST /api/v2/agent-tasks`。
2. 后端创建 `agent_task`，状态为 `queued`。
3. 前端连接 `GET /api/v2/streams/tasks/<task_id>`。
4. `chapter_generation_service` 加载章节、项目事实、章节策略和 outline。
5. `context_builder` 复用现有 `retrieval_router.search` 获取资料。
6. `citation_service` 为进入 prompt 的资料创建 `citation_record`。
7. `model_center.stream` 调用 OpenAI-compatible chat completions stream。
8. 每个 chunk 写入 `agent_task_event` 并通过 SSE 返回。
9. 完成后保存 `chapter_editor_docs` 和 `bid_chapter_versions`，任务状态更新为 `succeeded`。

如果模型或检索失败：

- 检索失败时发送 `status` degraded 事件，继续生成但 prompt 明确资料不足。
- 模型失败时任务更新为 `failed`，发送 `error` 事件。
- 高风险资料缺失不在 P0 中强制阻断，只在生成提示和 citation 缺失中体现。

## 前端

新增 Vue 页面 `web/src/user/views/TiptapWorkbench.vue`，路由为 `/project/:id/workbench`。

P0 页面包含：

- 左侧章节列表。
- 中间 TipTap 编辑器。
- 右侧任务事件和引用列表。
- 顶部操作：生成本章、保存、下载/进入 OnlyOffice 终稿。

TipTap 依赖使用 Vue 官方生态：

- `@tiptap/vue-3`
- `@tiptap/starter-kit`

P0 先使用 Markdown 文本作为服务端主存储。TipTap JSON 可选保存，避免 Markdown/Word 导出链路被过早复杂化。

## 测试

后端测试重点：

- `/api/v2/health` 返回 ok。
- 创建 `chapter_generate` task。
- editor doc 保存和读取。
- context builder 能复用现有检索结果并创建 citation。
- stream 模型失败时任务状态为 failed。

前端验证重点：

- Vite build 通过。
- 工作台路由可进入。
- 章节列表可加载。
- 点击生成本章后，SSE token 能进入编辑器。
- 保存后刷新仍能读取正文。

## 验收

P0 验收以“单章主链路跑通”为准：

1. 使用旧流程上传招标文件、预分析、目录设计。
2. 进入新 TipTap Workbench。
3. 选择一个章节，点击生成本章。
4. 前端能看到 Agent 状态、引用来源和流式正文。
5. 生成完成后正文保存到章节版本和 editor doc。
6. 刷新页面后正文仍可加载。
7. 旧 Word 下载和 OnlyOffice 入口仍可使用。

## 风险

- Flask 同步 SSE 在高并发下不是终态，但 P0 可接受；P1/P2 再迁 ASGI 或队列 worker。
- 现有模型供应商不一定都支持 stream；P0 的 stream 客户端按 OpenAI-compatible 实现，不支持时降级为一次性 token 事件。
- citation 先记录 prompt evidence，不等于最终文本逐段引用；前端文案必须标注为“参考来源”。
- TipTap 与 Word 导出不是同一个渲染系统；P0 以 Markdown 为桥接，不承诺浏览器所见即 Word 所见。
