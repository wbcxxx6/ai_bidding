const state = {
  userId: null,
  providers: [],
  config: null,
  activeModule: "overview",
  project: {
    projectId: null,
    biddingId: null,
    fileId: null,
    filename: "",
  },
  chapterDesign: null,
  onlyoffice: {
    scriptPromise: null,
    editor: null,
  },
};

const moduleMeta = {
  overview: { eyebrow: "Enterprise Console", title: "招投标智能工作台" },
  project: { eyebrow: "Project Center", title: "项目中心" },
  knowledge: { eyebrow: "Knowledge Base", title: "知识库" },
  research: { eyebrow: "Deep Research", title: "联网研究" },
  generation: { eyebrow: "Generation Pipeline", title: "生成与审核" },
  settings: { eyebrow: "Model Settings", title: "模型设置" },
};

const $ = (id) => document.getElementById(id);

function setActiveModule(moduleName) {
  state.activeModule = moduleName;
  document.querySelectorAll("[data-module]").forEach((button) => {
    button.classList.toggle("active", button.dataset.module === moduleName);
  });
  document.querySelectorAll(".module-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `module-${moduleName}`);
  });
  $("moduleEyebrow").textContent = moduleMeta[moduleName].eyebrow;
  $("moduleTitle").textContent = moduleMeta[moduleName].title;
}

function writeResult(value) {
  $("settingsResult").textContent =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

function ensureProject() {
  if (!state.project.biddingId) {
    throw new Error("请先在项目中心上传招标文件。");
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers:
      options.body instanceof FormData
        ? options.headers || {}
        : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `请求失败：${response.status}`);
  }
  return data;
}

function fingerprint() {
  const key = "ai_bidding_fingerprint";
  let value = localStorage.getItem(key);
  if (!value) {
    value = `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(key, value);
  }
  return value;
}

async function identifyUser() {
  const data = await api("/api/users/identify", {
    method: "POST",
    body: JSON.stringify({ fingerprintId: fingerprint() }),
  });
  state.userId = data.userId;
  $("userChip").textContent = `User #${data.userId}`;
}

function selectedProvider() {
  return state.providers.find((item) => item.id === $("providerSelect").value);
}

function renderProviders() {
  $("providerSelect").innerHTML = state.providers
    .map((provider) => `<option value="${provider.id}">${provider.name}</option>`)
    .join("");

  $("providerDocs").innerHTML = state.providers
    .map(
      (provider) =>
        `<a href="${provider.official_docs}" target="_blank" rel="noreferrer">
          <strong>${provider.name}</strong>
          <span>${provider.base_url}</span>
        </a>`,
    )
    .join("");
}

function applyProvider(provider, keepModel = false) {
  if (!provider) return;
  $("baseUrlInput").value = provider.base_url;
  $("modelHint").textContent = provider.model_hint || "";
  if (!keepModel) {
    $("modelInput").value = provider.default_model || "";
  }
}

async function loadConfig() {
  const [providersData, configData] = await Promise.all([
    api("/api/settings/model-providers"),
    api("/api/settings/model-config"),
  ]);

  state.providers = providersData.providers || [];
  state.config = configData;
  renderProviders();

  $("providerSelect").value = configData.activeProvider;
  $("modelInput").value = configData.model || "";
  $("baseUrlInput").value = configData.baseUrl || "";
  $("apiKeyInput").placeholder = configData.apiKeySet
    ? `已保存：${configData.apiKeyMasked}`
    : "请输入 API Key";

  applyProvider(selectedProvider(), true);
  $("currentProviderPill").textContent = `${configData.providerName || "未配置"} · ${configData.model || ""}`;
  $("backendStatus").textContent = "已连接";
  $("metricProvider").textContent = configData.providerName || "未配置";
}

async function saveModelConfig(event) {
  event.preventDefault();
  const payload = {
    activeProvider: $("providerSelect").value,
    model: $("modelInput").value.trim(),
    apiKey: $("apiKeyInput").value.trim(),
    baseUrl: $("baseUrlInput").value.trim(),
  };
  const data = await api("/api/settings/model-config", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  writeResult(data);
  $("apiKeyInput").value = "";
  await loadConfig();
}

async function testModel() {
  writeResult("正在测试模型连接...");
  writeResult(await api("/api/settings/test-model", { method: "POST", body: "{}" }));
}

function updateProjectView(data) {
  state.project = {
    projectId: data.projectId || state.project.projectId,
    biddingId: data.biddingId || state.project.biddingId,
    fileId: data.fileId || state.project.fileId,
    filename: data.originalFilename || state.project.filename,
  };
  $("currentProjectId").textContent = state.project.projectId || "-";
  $("currentBiddingId").textContent = state.project.biddingId || "-";
  $("currentFileId").textContent = state.project.fileId || "-";
  $("currentFilename").textContent = state.project.filename || "-";
  $("metricProjectStatus").textContent = state.project.projectId ? "已创建" : "未创建";
}

function formatFileSize(value) {
  const size = Number(value || 0);
  if (!size) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function renderHistory(items = []) {
  $("historyList").innerHTML = items.length
    ? items
        .map(
          (item) =>
            `<article class="history-item">
              <div>
                <strong>${item.originalFilename || `文件 #${item.fileId}`}</strong>
                <span>${item.projectName || "未关联项目"} · ${item.statusLabel || item.overallStatus || "未知"}</span>
                <small>${item.category || "-"} · ${formatFileSize(item.fileSize)} · ${item.createdAt || ""}</small>
              </div>
              <a class="download-link" href="${item.downloadUrl}" target="_blank" rel="noreferrer">下载</a>
            </article>`,
        )
        .join("")
    : `<div class="empty">暂无历史记录</div>`;
}

function setOnlyOfficeStatus(message) {
  $("onlyofficeStatus").textContent = message;
}

function onlyOfficeScriptUrl() {
  return `${window.location.origin}/web-apps/apps/api/documents/api.js`;
}

function loadOnlyOfficeScript() {
  if (window.DocsAPI) return Promise.resolve();
  if (state.onlyoffice.scriptPromise) return state.onlyoffice.scriptPromise;

  state.onlyoffice.scriptPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = onlyOfficeScriptUrl();
    script.onload = () => resolve();
    script.onerror = () =>
      reject(new Error("OnlyOffice 插件加载失败，请确认文档服务已部署并可访问 /web-apps/apps/api/documents/api.js。"));
    document.head.appendChild(script);
  });
  return state.onlyoffice.scriptPromise;
}

async function renderOnlyOffice(editorConfig, fileUrl) {
  if (!editorConfig) {
    throw new Error("生成结果缺少 editorConfig，无法加载 OnlyOffice。");
  }

  setOnlyOfficeStatus("正在加载 OnlyOffice 编辑器...");
  $("onlyofficeFrame").innerHTML = `<div id="onlyofficeEditor" class="office-editor"></div>`;

  if (state.onlyoffice.editor?.destroyEditor) {
    state.onlyoffice.editor.destroyEditor();
    state.onlyoffice.editor = null;
  }

  await loadOnlyOfficeScript();
  if (!window.DocsAPI?.DocEditor) {
    throw new Error("OnlyOffice DocsAPI 不可用。");
  }

  state.onlyoffice.editor = new window.DocsAPI.DocEditor("onlyofficeEditor", editorConfig);
  setOnlyOfficeStatus("Word 文档已加载，可在线预览和编辑");

  if (fileUrl) {
    $("generatedDownloadLink").href = fileUrl;
    $("generatedDownloadLink").classList.remove("hidden");
  }
}

function openHistoryModal() {
  $("historyModal").classList.add("open");
  $("historyModal").setAttribute("aria-hidden", "false");
}

function closeHistoryModal() {
  $("historyModal").classList.remove("open");
  $("historyModal").setAttribute("aria-hidden", "true");
}

async function loadHistory() {
  openHistoryModal();
  $("historyList").innerHTML = `<div class="empty">正在加载历史记录...</div>`;
  if (!state.userId) await identifyUser();
  writeResult("正在加载历史记录...");
  const data = await api(`/api/users/${state.userId}/files/history?limit=50`);
  renderHistory(data.items || []);
  writeResult(data);
}

async function uploadTender(event) {
  event.preventDefault();
  const file = $("tenderFileInput").files[0];
  if (!file) throw new Error("请选择招标文件。");
  if (!state.userId) await identifyUser();

  const form = new FormData();
  form.append("file", file);
  form.append("userId", state.userId);
  writeResult("正在上传招标文件...");
  const data = await api("/api/bidding/upload", { method: "POST", body: form });
  updateProjectView(data);
  writeResult(data);
}

function renderKnowledge(items = []) {
  $("metricKnowledgeBase").textContent = `${items.length} 个`;
  $("kbSelect").innerHTML = items.length
    ? items.map((item) => `<option value="${item.id}">${item.kbName}</option>`).join("")
    : `<option value="">暂无知识库</option>`;
  $("knowledgeList").innerHTML = items.length
    ? items
        .map(
          (item) =>
            `<article>
              <strong>${item.kbName}</strong>
              <span>${item.kbType || "enterprise"} · ${item.status || "active"}</span>
              <small>${item.description || "未填写描述"}</small>
            </article>`,
        )
        .join("")
    : `<div class="empty">暂无知识库</div>`;
}

async function loadKnowledgeBases() {
  const data = await api("/api/knowledge-bases");
  renderKnowledge(data.items || []);
  return data;
}

async function createKnowledgeBase(event) {
  event.preventDefault();
  const kbName = $("kbNameInput").value.trim();
  if (!kbName) throw new Error("请输入知识库名称。");
  const data = await api("/api/knowledge-bases", {
    method: "POST",
    body: JSON.stringify({
      kbName,
      description: $("kbDescInput").value.trim(),
      userId: state.userId,
    }),
  });
  writeResult(data);
  await loadKnowledgeBases();
}

async function uploadKnowledgeDocument(event) {
  event.preventDefault();
  const kbId = $("kbSelect").value;
  const file = $("kbFileInput").files[0];
  if (!kbId) throw new Error("请先选择知识库。");
  if (!file) throw new Error("请选择要上传的资料。");
  if (!state.userId) await identifyUser();

  const form = new FormData();
  form.append("file", file);
  form.append("userId", state.userId);
  form.append("docType", $("docTypeSelect").value);
  const data = await api(`/api/knowledge-bases/${kbId}/documents`, { method: "POST", body: form });
  writeResult(data);
}

async function startResearch(event) {
  event.preventDefault();
  if (!state.project.projectId) throw new Error("请先上传招标文件创建项目。");
  const query = $("researchQueryInput").value.trim();
  const chapterQuery = $("researchChapterQueryInput").value.trim();
  const sources = $("researchSourcesInput").value
    .split(/\n+/)
    .map((url) => url.trim())
    .filter(Boolean);
  const payload = {
    userId: state.userId,
    query,
    chapterQuery,
    months: Number($("researchMonthsInput").value || 12),
    maxSources: Number($("researchMaxSourcesInput").value || 8),
  };
  if (sources.length) {
    payload.sources = sources;
  }

  writeResult("正在执行自动联网研究...");
  const data = await api(`/api/projects/${state.project.projectId}/research-tasks`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderResearchSources(data.sources || []);
  writeResult(data);
}

function parseReferenceValue(value) {
  if (!value) return {};
  if (typeof value === "object") return value;
  try {
    return JSON.parse(value);
  } catch (_error) {
    return { reference_value: value };
  }
}

function percent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${Math.round(number * 100)}%`;
}

async function confirmResearchSource(sourceId) {
  if (!state.userId) await identifyUser();
  writeResult("正在确认研究来源并入库...");
  const data = await api(`/api/research-sources/${sourceId}/confirm`, {
    method: "POST",
    body: JSON.stringify({ userId: state.userId }),
  });
  writeResult(data);
}

async function loadResearchReports() {
  if (!state.project.projectId) throw new Error("请先上传招标文件创建项目。");
  const data = await api(`/api/projects/${state.project.projectId}/research-reports`);
  $("researchList").innerHTML = (data.items || []).length
    ? data.items
        .map(
          (item) =>
            `<article>
              <strong>${item.report_title || `研究报告 #${item.id}`}</strong>
              <span>${item.created_at || ""}</span>
              <small>${item.summary || "无摘要"}</small>
            </article>`,
        )
        .join("")
    : `<div class="empty">暂无研究报告</div>`;
  writeResult(data);
}

function renderResearchSources(sources) {
  $("researchList").innerHTML = sources.length
    ? sources
        .map((item) => {
          const meta = parseReferenceValue(item.reference_value);
          const score = meta.reflection_score ?? item.reflection_score ?? item.credibility_score;
          const selected = meta.selected_for_generation ?? item.selected_for_generation;
          return `<article class="research-source">
            <div>
              <strong>${item.title || item.source_url || item.url}</strong>
              <span>${item.domain || item.source_type || ""} · 评分 ${percent(score)} · ${selected ? "已选入生成" : "参考来源"}</span>
              <small>${item.summary || "无摘要"}</small>
            </div>
            ${item.id ? `<button class="ghost small" type="button" data-confirm-source="${item.id}">确认入库</button>` : ""}
          </article>`;
        })
        .join("")
    : `<div class="empty">暂无研究结果</div>`;

  document.querySelectorAll("[data-confirm-source]").forEach((button) => {
    button.addEventListener("click", () => {
      confirmResearchSource(button.dataset.confirmSource).catch((error) => writeResult(error.message));
    });
  });
}

async function preAnalysis() {
  ensureProject();
  writeResult("正在执行预分析...");
  writeResult(
    await api("/api/bidding/pre-analysis_bid", {
      method: "POST",
      body: JSON.stringify({ biddingId: state.project.biddingId }),
    }),
  );
}

async function chapterAnalysis() {
  ensureProject();
  writeResult("正在分析章节结构...");
  writeResult(
    await api("/api/bidding/chapter-analysis_bid", {
      method: "POST",
      body: JSON.stringify({ biddingId: state.project.biddingId }),
    }),
  );
}

async function chapterDesign() {
  ensureProject();
  writeResult("正在生成章节大纲...");
  const data = await api("/api/bidding/chapter-design", {
    method: "POST",
    body: JSON.stringify({ biddingId: state.project.biddingId }),
  });
  state.chapterDesign = data;
  $("chapterDesignText").value = JSON.stringify(data, null, 2);
  writeResult(data);
}

async function generateDocument() {
  ensureProject();
  const raw = $("chapterDesignText").value.trim();
  if (!raw) throw new Error("请先生成或粘贴章节大纲 JSON。");
  const chapterDesignData = JSON.parse(raw);
  writeResult("正在生成投标文件，耗时可能较长...");
  setOnlyOfficeStatus("正在生成 Word 文档...");
  const data = await api("/api/bidding/generate-bid-document", {
    method: "POST",
    body: JSON.stringify({ biddingId: state.project.biddingId, chapterDesign: chapterDesignData }),
  });
  writeResult(data);
  await renderOnlyOffice(data.editorConfig, data.fileUrl);
}

function bindEvents() {
  document.querySelectorAll("[data-module]").forEach((button) => {
    button.addEventListener("click", () => setActiveModule(button.dataset.module));
  });
  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => setActiveModule(button.dataset.jump));
  });

  $("uploadTenderForm").addEventListener("submit", (event) => uploadTender(event).catch((error) => writeResult(error.message)));
  $("kbForm").addEventListener("submit", (event) => createKnowledgeBase(event).catch((error) => writeResult(error.message)));
  $("kbDocumentForm").addEventListener("submit", (event) => uploadKnowledgeDocument(event).catch((error) => writeResult(error.message)));
  $("researchForm").addEventListener("submit", (event) => startResearch(event).catch((error) => writeResult(error.message)));
  $("loadHistoryBtn").addEventListener("click", () => loadHistory().catch((error) => writeResult(error.message)));
  $("closeHistoryBtn").addEventListener("click", closeHistoryModal);
  $("historyModal").addEventListener("click", (event) => {
    if (event.target === $("historyModal")) closeHistoryModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeHistoryModal();
  });
  $("loadReportsBtn").addEventListener("click", () => loadResearchReports().catch((error) => writeResult(error.message)));
  $("loadKnowledgeBtn").addEventListener("click", () => loadKnowledgeBases().catch((error) => writeResult(error.message)));

  $("preAnalysisBtn").addEventListener("click", () => preAnalysis().catch((error) => writeResult(error.message)));
  $("chapterAnalysisBtn").addEventListener("click", () => chapterAnalysis().catch((error) => writeResult(error.message)));
  $("chapterDesignBtn").addEventListener("click", () => chapterDesign().catch((error) => writeResult(error.message)));
  $("generateDocBtn").addEventListener("click", () => generateDocument().catch((error) => writeResult(error.message)));

  $("providerSelect").addEventListener("change", () => applyProvider(selectedProvider()));
  $("modelForm").addEventListener("submit", (event) => saveModelConfig(event).catch((error) => writeResult(error.message)));
  $("testModelBtn").addEventListener("click", () => testModel().catch((error) => writeResult(error.message)));
  $("refreshConfigBtn").addEventListener("click", () => loadConfig().catch((error) => writeResult(error.message)));
  $("clearResultBtn").addEventListener("click", () => writeResult("等待操作"));
}

async function init() {
  bindEvents();
  setActiveModule(state.activeModule);
  updateProjectView({});
  try {
    await identifyUser();
  } catch (error) {
    $("userChip").textContent = "未识别用户";
    writeResult(error.message);
  }
  await loadConfig();
  await loadKnowledgeBases();
}

init().catch((error) => {
  $("backendStatus").textContent = "连接失败";
  writeResult(error.message);
});
