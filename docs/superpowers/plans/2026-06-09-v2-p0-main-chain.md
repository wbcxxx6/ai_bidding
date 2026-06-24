# AI Bidding V2 P0 Main Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the V2 P0 main chain: `/api/v2`, task state, single-chapter streaming generation, editor document persistence, minimal citation records, and a Vue TipTap workbench.

**Architecture:** Add V2-first modules beside the existing Flask/Vue code instead of expanding `api/bidding.py`. Keep MySQL and current retrieval/storage as P0 compatibility paths while introducing service boundaries that can migrate to PostgreSQL/ASGI later.

**Tech Stack:** Flask, MySQL via existing `core.db`, OpenAI-compatible HTTP streaming through `requests`, Vue 3, Element Plus, TipTap Vue 3.

---

## File Structure

- Create `api/v2/__init__.py`: registers V2 blueprints.
- Create `api/v2/health.py`: `/api/v2/health`.
- Create `api/v2/agent_tasks.py`: create/query V2 tasks.
- Create `api/v2/streams.py`: SSE stream endpoint for task execution.
- Create `api/v2/chapters.py`: chapter list and editor document API.
- Create `api/v2/rag.py`: P0 RAG/search endpoint.
- Create `services/v2/agent_task_service.py`: task and event persistence.
- Create `services/v2/editor_doc_service.py`: editor doc read/write and chapter version sync.
- Create `services/v2/chapter_strategy_service.py`: infer/store P0 chapter strategies.
- Create `services/v2/citation_service.py`: create/list minimal citation records.
- Create `services/v2/context_builder.py`: wraps existing `retrieval_router`.
- Create `services/v2/chapter_generation_service.py`: orchestrates single-chapter streaming.
- Create `services/model_center/stream.py`: OpenAI-compatible streaming and fallback.
- Modify `core/db.py`: add P0 schema statements.
- Modify `main.py`: register V2 blueprints.
- Modify `requirements.txt`: add TipTap dependencies in frontend only via `web/package.json`.
- Modify `web/package.json`: add `@tiptap/vue-3`, `@tiptap/starter-kit`, and Markdown helper if used.
- Modify `web/src/shared/api.js`: add V2 API helpers.
- Create `web/src/user/views/TiptapWorkbench.vue`: P0 workbench.
- Modify `web/src/user/router.js`: add workbench route.
- Modify `web/src/user/views/ProjectDetail.vue`: add workbench tab.

## Task 1: V2 Schema And Health API

**Files:**
- Modify: `core/db.py`
- Create: `api/v2/__init__.py`
- Create: `api/v2/health.py`
- Modify: `main.py`

- [ ] **Step 1: Add P0 schema statements**

Add `CREATE TABLE IF NOT EXISTS` statements to `SCHEMA_STATEMENTS` in `core/db.py` for:

```sql
CREATE TABLE IF NOT EXISTS agent_task (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL DEFAULT 1,
    project_id BIGINT UNSIGNED NOT NULL,
    bid_document_id BIGINT UNSIGNED NULL,
    chapter_id BIGINT UNSIGNED NULL,
    parent_task_id BIGINT UNSIGNED NULL,
    task_type VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    input_json JSON NULL,
    output_json JSON NULL,
    error_message TEXT NULL,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    created_by BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    INDEX idx_agent_task_project (project_id, status, created_at),
    INDEX idx_agent_task_chapter (chapter_id, status),
    CONSTRAINT fk_v2_agent_task_project FOREIGN KEY (project_id) REFERENCES bid_projects(id),
    CONSTRAINT fk_v2_agent_task_chapter FOREIGN KEY (chapter_id) REFERENCES bid_chapters(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
```

Also add `agent_task_event`, `chapter_strategy`, `chapter_editor_docs`, and `citation_record` with consistent `BIGINT UNSIGNED`, JSON, status, and index fields.

- [ ] **Step 2: Create V2 blueprint module**

Create `api/v2/__init__.py`:

```python
from flask import Blueprint

from api.v2 import agent_tasks, chapters, health, rag, streams

bp = Blueprint("v2", __name__)
bp.register_blueprint(health.bp)
bp.register_blueprint(agent_tasks.bp)
bp.register_blueprint(chapters.bp)
bp.register_blueprint(rag.bp)
bp.register_blueprint(streams.bp)
```

- [ ] **Step 3: Create health endpoint**

Create `api/v2/health.py`:

```python
from flask import Blueprint, jsonify

bp = Blueprint("v2_health", __name__)


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "version": "v2", "phase": "p0"})
```

- [ ] **Step 4: Register V2 blueprint**

In `main.py`, import `api.v2` and register it:

```python
from api import bidding, files, generation, knowledge, research, settings, users
from api import v2

app.register_blueprint(v2.bp, url_prefix="/api/v2")
```

- [ ] **Step 5: Verify import and health route**

Run:

```bash
python -m py_compile main.py api/v2/__init__.py api/v2/health.py core/db.py
```

Expected: command exits with code 0.

## Task 2: Agent Task Service And API

**Files:**
- Create: `services/v2/__init__.py`
- Create: `services/v2/agent_task_service.py`
- Create: `api/v2/agent_tasks.py`

- [ ] **Step 1: Implement task persistence**

Create `services/v2/agent_task_service.py` with functions:

```python
import json
from datetime import datetime

from core.db import get_db


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def dumps(value):
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def loads(value):
    if not value:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def create_task(*, project_id, task_type, chapter_id=None, bid_document_id=None, input_json=None, created_by=None):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO agent_task
            (tenant_id, project_id, bid_document_id, chapter_id, task_type, status, input_json,
             created_by, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)
            """,
            (project_id, bid_document_id, chapter_id, task_type, dumps(input_json), created_by, now(), now()),
        )
        task_id = cursor.lastrowid
        conn.commit()
        return get_task(task_id)
    finally:
        conn.close()
```

Include `get_task`, `update_task`, `append_event`, and `list_events` in the same file.

- [ ] **Step 2: Implement agent task API**

Create `api/v2/agent_tasks.py` with:

```python
from flask import Blueprint, jsonify, request

from services.v2.agent_task_service import create_task, get_task, list_events

bp = Blueprint("v2_agent_tasks", __name__, url_prefix="/agent-tasks")


@bp.route("", methods=["POST"])
def create_agent_task():
    data = request.get_json(silent=True) or {}
    task_type = data.get("taskType") or data.get("task_type")
    project_id = data.get("projectId") or data.get("project_id")
    if task_type != "chapter_generate":
        return jsonify({"error": "Only chapter_generate is supported in P0."}), 400
    if not project_id or not data.get("chapterId"):
        return jsonify({"error": "projectId and chapterId are required."}), 400
    task = create_task(
        project_id=int(project_id),
        chapter_id=int(data["chapterId"]),
        task_type=task_type,
        input_json=data.get("input") or {},
        created_by=data.get("userId"),
    )
    return jsonify({"task": task}), 201
```

Add `GET /<int:task_id>` returning task plus events.

- [ ] **Step 3: Verify syntax**

Run:

```bash
python -m py_compile services/v2/agent_task_service.py api/v2/agent_tasks.py
```

Expected: command exits with code 0.

## Task 3: Editor Document, Strategy, Citation, And Context Services

**Files:**
- Create: `services/v2/editor_doc_service.py`
- Create: `services/v2/chapter_strategy_service.py`
- Create: `services/v2/citation_service.py`
- Create: `services/v2/context_builder.py`
- Create: `api/v2/chapters.py`
- Create: `api/v2/rag.py`

- [ ] **Step 1: Implement editor doc service**

Create `services/v2/editor_doc_service.py` with:

```python
import json
from datetime import datetime

from core.db import get_db
from services.agent_orchestrator import create_chapter_version


def now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def get_editor_doc(chapter_id):
    conn = get_db()
    try:
        row = conn.execute(
            """
            SELECT * FROM chapter_editor_docs
            WHERE chapter_id=? AND status='active'
            ORDER BY version_no DESC LIMIT 1
            """,
            (chapter_id,),
        ).fetchone()
        if row:
            return {
                "chapterId": chapter_id,
                "markdown": row.get("markdown_content") or "",
                "tiptapJson": json.loads(row["tiptap_json"]) if row.get("tiptap_json") else None,
                "versionNo": row["version_no"],
            }
        version = conn.execute(
            """
            SELECT v.content
            FROM bid_chapters c
            LEFT JOIN bid_chapter_versions v ON v.id = c.current_version_id
            WHERE c.id=?
            """,
            (chapter_id,),
        ).fetchone()
        return {"chapterId": chapter_id, "markdown": (version or {}).get("content") or "", "tiptapJson": None, "versionNo": 0}
    finally:
        conn.close()
```

Add `save_editor_doc` that inserts a new `chapter_editor_docs` version and optionally calls `create_chapter_version` when `sync_chapter_version=True`.

- [ ] **Step 2: Implement strategy service**

Create `services/v2/chapter_strategy_service.py` with deterministic P0 inference:

```python
def infer_volume_type(title, chapter_type=None):
    text = f"{title or ''} {chapter_type or ''}"
    if any(word in text for word in ["报价", "价格", "分项报价"]):
        return "pricing"
    if any(word in text for word in ["资格", "资质", "证书", "人员", "业绩"]):
        return "qualification"
    if any(word in text for word in ["商务", "合同", "承诺", "偏离"]):
        return "commercial"
    if any(word in text for word in ["附件", "附录"]):
        return "appendix"
    return "technical"
```

Add `get_or_create_strategy(chapter)` that stores `volume_type`, `target_words`, `writing_style`, `forbidden_rules_json`, and `rag_policy_json`.

- [ ] **Step 3: Implement citation service**

Create `services/v2/citation_service.py` with `create_citation_records(task, context_items)` and `list_chapter_citations(chapter_id)`. Generate keys as `CIT-001`, `CIT-002`, etc. Store `source_type`, `source_file_id`, `chunk_id`, `chunk_uid`, `source_title`, `quote_text`, `metadata_json`.

- [ ] **Step 4: Implement context builder**

Create `services/v2/context_builder.py` that calls existing retrieval:

```python
from services.retrieval_router import retrieval_router


def build_context(query, *, project_id, chapter_id=None, limit=5):
    pack = retrieval_router.search(query, project_id=project_id, limit=limit)
    items = pack.get("items") or []
    context_text = "\n\n".join(
        f"[CIT-{index + 1:03d}] {item.get('source_title') or '参考资料'}\n{(item.get('content') or '')[:900]}"
        for index, item in enumerate(items)
    )
    return {
        "query": query,
        "items": items,
        "contextText": context_text,
        "degraded": pack.get("degraded", False),
        "degradedReason": pack.get("degraded_reason"),
    }
```

- [ ] **Step 5: Implement chapter API**

Create `api/v2/chapters.py` with:

- `GET /chapters?projectId=<id>` returning existing `bid_chapters`.
- If no chapters exist but project `directory_structure` exists, materialize it into `bid_documents` and `bid_chapters`.
- `GET /chapters/<id>/editor-doc`.
- `PUT /chapters/<id>/editor-doc`.
- `GET /chapters/<id>/citations`.

- [ ] **Step 6: Implement RAG API**

Create `api/v2/rag.py` with `POST /rag/search` calling `build_context` and returning `items`, `contextText`, `degraded`.

- [ ] **Step 7: Verify syntax**

Run:

```bash
python -m py_compile services/v2/editor_doc_service.py services/v2/chapter_strategy_service.py services/v2/citation_service.py services/v2/context_builder.py api/v2/chapters.py api/v2/rag.py
```

Expected: command exits with code 0.

## Task 4: Streaming Model And Chapter Generation

**Files:**
- Create: `services/model_center/__init__.py`
- Create: `services/model_center/stream.py`
- Create: `services/v2/chapter_generation_service.py`
- Create: `api/v2/streams.py`

- [ ] **Step 1: Implement OpenAI-compatible stream**

Create `services/model_center/stream.py`. Use `ModelRouter.route_for_task("generate_chapter")`, POST to `/chat/completions` with `stream=True`, parse `data:` lines, yield content deltas. If streaming fails because the provider returns a normal JSON response, yield the final content once.

- [ ] **Step 2: Implement P0 prompt builder and generator**

Create `services/v2/chapter_generation_service.py` with `stream_chapter_generation(task_id)`. It should:

- Load task and chapter.
- Append `start` and `status` events.
- Build context from chapter title and outline.
- Create citation records and emit `citation` events.
- Build a strategy-driven prompt without the old hardcoded “每章必须 3000 字/必须 Mermaid” rule.
- Stream chunks through `stream_chat_completion`.
- Save editor doc and chapter version when done.
- Update task to `succeeded` or `failed`.

- [ ] **Step 3: Implement streams API**

Create `api/v2/streams.py`:

```python
import json

from flask import Blueprint, Response

from services.v2.chapter_generation_service import stream_chapter_generation

bp = Blueprint("v2_streams", __name__, url_prefix="/streams")


def sse(event):
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@bp.route("/tasks/<int:task_id>", methods=["GET"])
def stream_task(task_id):
    def generate():
        for event in stream_chapter_generation(task_id):
            yield sse(event)
    return Response(generate(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

- [ ] **Step 4: Verify syntax**

Run:

```bash
python -m py_compile services/model_center/stream.py services/v2/chapter_generation_service.py api/v2/streams.py
```

Expected: command exits with code 0.

## Task 5: Frontend TipTap Workbench

**Files:**
- Modify: `web/package.json`
- Modify: `web/src/shared/api.js`
- Create: `web/src/user/views/TiptapWorkbench.vue`
- Modify: `web/src/user/router.js`
- Modify: `web/src/user/views/ProjectDetail.vue`

- [ ] **Step 1: Add dependencies**

Run:

```bash
cd web
npm install @tiptap/vue-3 @tiptap/starter-kit
```

Expected: dependencies are added to `web/package.json` and `web/package-lock.json`.

- [ ] **Step 2: Add V2 API helpers**

Modify `web/src/shared/api.js` to export `v2Api`:

```javascript
export const v2Api = {
  health: () => http.get('/v2/health'),
  listChapters: (projectId) => http.get('/v2/chapters', { params: { projectId } }),
  getEditorDoc: (chapterId) => http.get(`/v2/chapters/${chapterId}/editor-doc`),
  saveEditorDoc: (chapterId, data) => http.put(`/v2/chapters/${chapterId}/editor-doc`, { ...data, userId: getUserId() }),
  listCitations: (chapterId) => http.get(`/v2/chapters/${chapterId}/citations`),
  createTask: (data) => http.post('/v2/agent-tasks', { ...data, userId: getUserId() }),
  streamTaskUrl: (taskId) => {
    const base = window.location.port === '5173' ? 'http://127.0.0.1:3012' : ''
    return `${base}/api/v2/streams/tasks/${taskId}`
  },
}
```

- [ ] **Step 3: Create workbench page**

Create `web/src/user/views/TiptapWorkbench.vue` with an Element Plus layout:

- Left rail: chapter list, status tags.
- Center: TipTap editor using `EditorContent`.
- Right rail: event timeline and reference list.
- Toolbar: generate selected chapter, save, refresh chapters, open final editor.

Use neutral colors, compact dashboard spacing, and explicit loading/empty/error states.

- [ ] **Step 4: Add route**

Modify `web/src/user/router.js`:

```javascript
{ path: '/project/:id/workbench', name: 'workbench', component: () => import('./views/TiptapWorkbench.vue') },
```

- [ ] **Step 5: Add project tab**

Modify `web/src/user/views/ProjectDetail.vue`:

```vue
<el-tab-pane label="AI 工作台" name="workbench">
  <TiptapWorkbench :project-id="id" />
</el-tab-pane>
```

Import `TiptapWorkbench`.

- [ ] **Step 6: Verify frontend build**

Run:

```bash
cd web
npm run build
```

Expected: Vite build succeeds.

## Task 6: End-To-End Verification

**Files:**
- No new files required.

- [ ] **Step 1: Verify backend imports**

Run:

```bash
python -m py_compile main.py api/v2/*.py services/v2/*.py services/model_center/*.py
```

Expected: command exits with code 0.

- [ ] **Step 2: Verify git diff scope**

Run:

```bash
git status --short
git diff --stat
```

Expected: changes are limited to V2 modules, schema additions, frontend workbench, and plan/spec files. The user's untracked V2 docs remain unmodified.

- [ ] **Step 3: Optional manual run**

Run backend if local DB is available:

```bash
python main.py
```

Expected: app starts and `GET /api/v2/health` returns `{"ok": true, "version": "v2", "phase": "p0"}`.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add api/v2 services/v2 services/model_center core/db.py main.py web/package.json web/package-lock.json web/src/shared/api.js web/src/user/views/TiptapWorkbench.vue web/src/user/router.js web/src/user/views/ProjectDetail.vue docs/superpowers/plans/2026-06-09-v2-p0-main-chain.md
git commit -m "feat: add v2 p0 streaming workbench"
```

Expected: commit succeeds. Do not add the user's untracked V2 requirement docs unless explicitly requested.
