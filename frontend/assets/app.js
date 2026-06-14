const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

const state = {
  workspace: "writing",
  workspaces: [],
  currentChat: null,
  currentDraft: null,
  originalAiText: "",
  brain: null,
  brainTab: "style",
  saveTimer: null,
  deferredInstall: null,
};

async function api(path, options = {}) {
  const config = {...options, headers: {...(options.headers || {})}};
  if (config.body && !(config.body instanceof FormData)) {
    config.headers["Content-Type"] = "application/json";
    if (typeof config.body !== "string") config.body = JSON.stringify(config.body);
  }
  const response = await fetch(path, config);
  if (!response.ok) {
    let message = `Request gagal (${response.status})`;
    try {
      const data = await response.json();
      message = data.message || data.detail?.message || data.detail || message;
    } catch (_) {}
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response;
}

async function jsonApi(path, options = {}) {
  return (await api(path, options)).json();
}

function toast(message) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.remove("hidden");
  clearTimeout(node.timer);
  node.timer = setTimeout(() => node.classList.add("hidden"), 2800);
}

function escapeHtml(value = "") {
  return value.replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
}

function openSheet(title, html) {
  $("#sheet-title").textContent = title;
  $("#sheet-content").innerHTML = html;
  $("#sheet").classList.remove("hidden");
  $("#backdrop").classList.remove("hidden");
}

function closeSheet() {
  $("#sheet").classList.add("hidden");
  $("#backdrop").classList.add("hidden");
}

function showView(view) {
  $$(".view").forEach(node => node.classList.toggle("active", node.id === `view-${view}`));
  $$(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.view === view));
  $("#fab").classList.toggle("hidden", view === "menu");
  if (view === "brain") loadBrain();
  if (view === "menu") loadSystemStatus();
}

async function initialize() {
  const auth = await jsonApi("/api/auth/status");
  if (!auth.authenticated) {
    $("#login-screen").classList.remove("hidden");
    return;
  }
  $("#app").classList.remove("hidden");
  await loadWorkspaces();
  await Promise.all([loadModelStatus(), loadSyncStatus()]);
  restoreLocalDraft();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js");
}

async function loadWorkspaces() {
  const [list, current] = await Promise.all([
    jsonApi("/api/workspace/list"),
    jsonApi("/api/workspace/current"),
  ]);
  state.workspaces = list.items;
  state.workspace = current.id;
  $("#workspace-name").textContent = current.name;
}

function showWorkspaceSheet() {
  const items = state.workspaces.map(item => `
    <button class="sheet-option workspace-option" data-id="${escapeHtml(item.id)}" type="button">
      <span><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)}</small></span>
      <b>${item.id === state.workspace ? "✓" : ""}</b>
    </button>`).join("");
  openSheet("Pilih workspace", `${items}
    <button id="create-workspace" class="button primary" style="width:100%;margin-top:16px" type="button">Workspace baru</button>`);
  $$(".workspace-option").forEach(button => button.onclick = () => switchWorkspace(button.dataset.id));
  $("#create-workspace").onclick = createWorkspace;
}

async function switchWorkspace(id) {
  await jsonApi("/api/workspace/switch", {method: "POST", body: {workspace_id: id}});
  state.workspace = id;
  state.currentChat = null;
  state.currentDraft = null;
  const item = state.workspaces.find(workspace => workspace.id === id);
  $("#workspace-name").textContent = item?.name || id;
  resetChat();
  restoreLocalDraft();
  closeSheet();
  await Promise.all([loadBrain(), loadSyncStatus()]);
  toast("Workspace diganti");
}

async function createWorkspace() {
  const name = prompt("Nama workspace baru:");
  if (!name?.trim()) return;
  try {
    const result = await jsonApi("/api/workspace/create", {method: "POST", body: {name: name.trim()}});
    state.workspaces.push(result.workspace);
    await switchWorkspace(result.workspace.id);
  } catch (error) {
    toast(error.message);
  }
}

function appendMessage(role, content = "") {
  const messages = $("#chat-messages");
  if (messages.querySelector(".empty-state")) messages.innerHTML = "";
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = content;
  messages.appendChild(node);
  node.scrollIntoView({behavior: "smooth", block: "end"});
  return node;
}

async function sendChat(event) {
  event.preventDefault();
  const input = $("#chat-input");
  const message = input.value.trim();
  if (!message) return;
  appendMessage("user", message);
  input.value = "";
  input.style.height = "auto";
  const assistant = appendMessage("assistant", "");
  $("#chat-send").disabled = true;
  try {
    const response = await api("/api/chat/send", {
      method: "POST",
      body: {workspace_id: state.workspace, chat_id: state.currentChat, message},
    });
    state.currentChat = response.headers.get("X-Chat-Id");
    if ($("#chat-title").textContent === "Obrolan baru") $("#chat-title").textContent = message.slice(0, 60);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      assistant.textContent += decoder.decode(value, {stream: true});
      assistant.scrollIntoView({block: "end"});
    }
  } catch (error) {
    assistant.textContent = `Error: ${error.message}`;
  } finally {
    $("#chat-send").disabled = false;
  }
}

function resetChat() {
  state.currentChat = null;
  $("#chat-title").textContent = "Obrolan baru";
  $("#chat-messages").innerHTML = `<div class="empty-state"><strong>Mulai dari sebuah pemikiran.</strong><span>Diskusikan ide, susun argumen, atau minta umpan balik.</span></div>`;
}

async function showChatList() {
  try {
    const data = await jsonApi(`/api/chat/list?workspace_id=${encodeURIComponent(state.workspace)}`);
    const html = data.items.filter(item => !item.archived).map(item => `
      <button class="sheet-option chat-option" data-id="${escapeHtml(item.id)}" type="button">
        <span><strong>${escapeHtml(item.title)}</strong><small>${item.messages.length} pesan</small></span><b>›</b>
      </button>`).join("") || `<p class="empty-state" style="min-height:180px">Belum ada riwayat.</p>`;
    openSheet("Riwayat chat", `${html}<button id="new-chat" class="button primary" style="width:100%;margin-top:16px">Obrolan baru</button>`);
    $$(".chat-option").forEach(button => button.onclick = () => loadChat(button.dataset.id));
    $("#new-chat").onclick = () => { resetChat(); closeSheet(); };
  } catch (error) {
    toast(error.message);
  }
}

async function loadChat(id) {
  const chat = await jsonApi(`/api/chat/session/${encodeURIComponent(id)}?workspace_id=${encodeURIComponent(state.workspace)}`);
  state.currentChat = id;
  $("#chat-title").textContent = chat.title;
  $("#chat-messages").innerHTML = "";
  chat.messages.forEach(message => appendMessage(message.role, message.content));
  closeSheet();
}

async function generateWriting() {
  const prompt = $("#write-prompt").value.trim();
  if (!prompt) return toast("Tulis instruksi terlebih dahulu");
  const button = $("#generate-button");
  button.disabled = true;
  button.textContent = "Menulis...";
  $("#draft-content").value = "";
  state.originalAiText = "";
  try {
    const response = await api("/api/ai/generate", {
      method: "POST",
      body: {workspace_id: state.workspace, prompt, mode: $("#write-mode").value},
    });
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      $("#draft-content").value += decoder.decode(value, {stream: true});
      $("#draft-content").scrollTop = $("#draft-content").scrollHeight;
    }
    state.originalAiText = $("#draft-content").value;
    scheduleDraftSave();
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Generate";
  }
}

function localDraftKey() {
  return `ghostwriter:draft:${state.workspace}`;
}

function saveDraftLocally() {
  localStorage.setItem(localDraftKey(), JSON.stringify({
    id: state.currentDraft,
    title: $("#draft-title").value,
    content: $("#draft-content").value,
    prompt: $("#write-prompt").value,
    savedAt: Date.now(),
  }));
}

function restoreLocalDraft() {
  const raw = localStorage.getItem(localDraftKey());
  if (!raw) {
    state.currentDraft = null;
    $("#draft-title").value = "Untitled";
    $("#draft-content").value = "";
    $("#write-prompt").value = "";
    return;
  }
  try {
    const draft = JSON.parse(raw);
    state.currentDraft = draft.id;
    $("#draft-title").value = draft.title || "Untitled";
    $("#draft-content").value = draft.content || "";
    $("#write-prompt").value = draft.prompt || "";
    $("#save-state").textContent = "Dipulihkan dari perangkat";
  } catch (_) {}
}

function scheduleDraftSave() {
  saveDraftLocally();
  $("#save-state").textContent = navigator.onLine ? "Menyimpan..." : "Tersimpan offline";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveDraftToServer, 1200);
}

async function saveDraftToServer() {
  if (!navigator.onLine) return;
  const title = $("#draft-title").value.trim() || "Untitled";
  const content = $("#draft-content").value;
  try {
    if (!state.currentDraft) {
      const draft = await jsonApi("/api/draft/create", {
        method: "POST", body: {workspace_id: state.workspace, title},
      });
      state.currentDraft = draft.id;
    }
    await jsonApi("/api/draft/update", {
      method: "POST",
      body: {workspace_id: state.workspace, draft_id: state.currentDraft, title, content},
    });
    saveDraftLocally();
    $("#save-state").textContent = "Tersimpan";
    loadSyncStatus();
  } catch (error) {
    $("#save-state").textContent = "Tersimpan offline";
  }
}

async function showDraftList() {
  const data = await jsonApi(`/api/draft/list?workspace_id=${encodeURIComponent(state.workspace)}`);
  const html = data.items.map(item => `
    <button class="sheet-option draft-option" data-id="${escapeHtml(item.id)}" type="button">
      <span><strong>${escapeHtml(item.title)}</strong><small>${new Date(item.updated_at).toLocaleString("id-ID")}</small></span><b>›</b>
    </button>`).join("") || `<p class="empty-state" style="min-height:180px">Belum ada draft.</p>`;
  openSheet("Draft", html);
  $$(".draft-option").forEach(button => button.onclick = () => loadDraft(button.dataset.id));
}

async function loadDraft(id) {
  const draft = await jsonApi(`/api/draft/${encodeURIComponent(id)}?workspace_id=${encodeURIComponent(state.workspace)}`);
  state.currentDraft = draft.id;
  state.originalAiText = draft.content;
  $("#draft-title").value = draft.title;
  $("#draft-content").value = draft.content;
  $("#save-state").textContent = "Tersimpan";
  saveDraftLocally();
  closeSheet();
}

async function trainRevision() {
  const revised = $("#draft-content").value.trim();
  if (!state.originalAiText || !revised) return toast("Generate tulisan lalu edit sebelum Train");
  if (revised === state.originalAiText.trim()) return toast("Belum ada revisi yang dapat dipelajari");
  const button = $("#train-button");
  button.disabled = true;
  button.textContent = "Learning...";
  try {
    const result = await jsonApi("/api/brain/learn/revision", {
      method: "POST",
      body: {workspace_id: state.workspace, ai_output: state.originalAiText, user_revision: revised},
    });
    state.originalAiText = revised;
    toast(`${result.analysis.style_rules.length + result.analysis.thinking_patterns.length} pola dipelajari`);
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Train";
  }
}

async function loadBrain() {
  try {
    state.brain = await jsonApi(`/api/brain/profile?workspace_id=${encodeURIComponent(state.workspace)}`);
    $("#style-count").textContent = state.brain.style_profile.rules.length;
    $("#thinking-count").textContent = state.brain.thinking_profile.patterns.length;
    $("#revision-count").textContent = state.brain.revision_count;
    renderBrainTab();
  } catch (error) {
    toast(error.message);
  }
}

function renderBrainTab() {
  if (!state.brain) return;
  $("#brain-list").classList.toggle("hidden", ["raw", "references"].includes(state.brainTab));
  $("#brain-teach").classList.toggle("hidden", state.brainTab !== "raw");
  $("#reference-search").classList.toggle("hidden", state.brainTab !== "references");
  let items = [];
  if (state.brainTab === "style") items = state.brain.style_profile.rules;
  if (state.brainTab === "thinking") items = state.brain.thinking_profile.patterns;
  $("#brain-list").innerHTML = items.map(item => `<article class="insight">${escapeHtml(item)}</article>`).join("")
    || `<div class="empty-state" style="min-height:240px"><strong>Belum ada pola.</strong><span>Train revisi atau ajarkan contoh tulisan Anda.</span></div>`;
}

async function learnRawWriting() {
  const content = $("#raw-writing").value.trim();
  if (!content) return toast("Masukkan contoh tulisan");
  const button = $("#learn-raw-button");
  button.disabled = true;
  button.textContent = "Menganalisis...";
  try {
    await jsonApi("/api/brain/learn/raw-writing", {
      method: "POST", body: {workspace_id: state.workspace, content, type: "user"},
    });
    $("#raw-writing").value = "";
    state.brainTab = "style";
    $$(".chip").forEach(chip => chip.classList.toggle("active", chip.dataset.brainTab === "style"));
    await loadBrain();
    toast("Gaya tulisan dipelajari");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Analisis tulisan";
  }
}

async function searchReferences() {
  const query = $("#reference-query").value.trim();
  if (!query) return;
  $("#reference-button").disabled = true;
  try {
    const data = await jsonApi("/api/reference/search", {
      method: "POST", body: {workspace_id: state.workspace, query, auto_save: true},
    });
    renderReferences(data.items);
    toast(`${data.items.length} referensi disimpan`);
  } catch (error) {
    toast(error.message);
  } finally {
    $("#reference-button").disabled = false;
  }
}

function renderReferences(items) {
  $("#reference-list").innerHTML = items.map(item => `
    <article class="reference-item">
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
      <p>${escapeHtml(item.summary)}</p>
    </article>`).join("");
}

async function loadReferences() {
  try {
    const data = await jsonApi(`/api/reference/list?workspace_id=${encodeURIComponent(state.workspace)}`);
    renderReferences(data.items);
  } catch (_) {}
}

async function loadModelStatus() {
  try {
    const data = await jsonApi("/api/model/status");
    $("#model-status").className = `status-pill ${data.configured ? "ok" : "error"}`;
    $("#model-status span").textContent = data.configured ? "AI" : "No token";
    $("#model-detail").textContent = data.active_model;
  } catch (_) {}
}

async function loadSyncStatus() {
  try {
    const data = await jsonApi("/api/sync/status");
    const pill = $("#sync-status");
    pill.className = `status-pill ${data.queue_size ? "warn" : "ok"}`;
    pill.querySelector("span").textContent = data.queue_size ? `${data.queue_size} pending` : "Synced";
    $("#sync-detail").textContent = data.configured ? `${data.queue_size} perubahan menunggu` : "Secret GitHub belum dikonfigurasi";
  } catch (_) {}
}

async function showModelSheet() {
  const status = await jsonApi("/api/model/status");
  const html = status.fallback_chain.map((model, index) => `
    <button class="sheet-option model-option" data-model="${escapeHtml(model)}" type="button">
      <span><strong>${escapeHtml(model)}</strong><small>${index === 0 ? "Default" : `Fallback ${index}`}</small></span>
      <b>${model === status.active_model ? "✓" : ""}</b>
    </button>`).join("");
  openSheet("Model AI", html);
  $$(".model-option").forEach(button => button.onclick = async () => {
    await jsonApi("/api/model/set-default", {method: "POST", body: {model_id: button.dataset.model}});
    closeSheet();
    loadModelStatus();
    toast("Model default diperbarui");
  });
}

async function manualSync() {
  try {
    $("#manual-sync").disabled = true;
    await jsonApi("/api/sync/run", {method: "POST"});
    toast("Sync selesai");
    await loadSyncStatus();
  } catch (error) {
    toast(error.message);
  } finally {
    $("#manual-sync").disabled = false;
  }
}

async function createSnapshot() {
  try {
    const result = await jsonApi("/api/snapshot/create", {method: "POST"});
    toast(`Snapshot ${result.id} dibuat`);
  } catch (error) {
    toast(error.message);
  }
}

function showQuickActions() {
  openSheet("Quick actions", `
    <button id="quick-note-action" class="sheet-option" type="button"><span><strong>Quick note</strong><small>Simpan ide tanpa meninggalkan halaman</small></span><b>+</b></button>
    <button id="new-draft-action" class="sheet-option" type="button"><span><strong>Draft baru</strong><small>Buka dokumen kosong</small></span><b>+</b></button>
    <button id="new-chat-action" class="sheet-option" type="button"><span><strong>Chat baru</strong><small>Mulai percakapan bersih</small></span><b>+</b></button>`);
  $("#quick-note-action").onclick = showQuickNote;
  $("#new-draft-action").onclick = () => {
    state.currentDraft = null; state.originalAiText = ""; $("#draft-title").value = "Untitled"; $("#draft-content").value = ""; saveDraftLocally(); closeSheet(); showView("write");
  };
  $("#new-chat-action").onclick = () => { resetChat(); closeSheet(); showView("chat"); };
}

function showQuickNote() {
  openSheet("Quick note", `<textarea id="quick-note-text" rows="7" style="width:100%;padding:12px;border:1px solid var(--line);border-radius:12px;resize:vertical" placeholder="Tangkap ide..."></textarea><button id="save-note" class="button primary" style="width:100%;margin-top:12px">Simpan</button>`);
  $("#save-note").onclick = async () => {
    const content = $("#quick-note-text").value.trim();
    if (!content) return;
    await jsonApi("/api/note/create", {method: "POST", body: {workspace_id: state.workspace, content}});
    closeSheet(); toast("Catatan tersimpan"); loadSyncStatus();
  };
}

function bindEvents() {
  $$(".nav-item").forEach(button => button.onclick = () => showView(button.dataset.view));
  $("#workspace-button").onclick = showWorkspaceSheet;
  $("#sheet-close").onclick = closeSheet;
  $("#backdrop").onclick = closeSheet;
  $("#fab").onclick = showQuickActions;
  $("#chat-form").onsubmit = sendChat;
  $("#chat-list-button").onclick = showChatList;
  $("#generate-button").onclick = generateWriting;
  $("#draft-list-button").onclick = showDraftList;
  $("#draft-title").addEventListener("input", scheduleDraftSave);
  $("#draft-content").addEventListener("input", scheduleDraftSave);
  $("#write-prompt").addEventListener("input", saveDraftLocally);
  $("#copy-button").onclick = async () => { await navigator.clipboard.writeText($("#draft-content").value); toast("Disalin"); };
  $("#train-button").onclick = trainRevision;
  $("#refresh-brain").onclick = loadBrain;
  $$(".chip").forEach(chip => chip.onclick = () => {
    state.brainTab = chip.dataset.brainTab;
    $$(".chip").forEach(node => node.classList.toggle("active", node === chip));
    renderBrainTab();
    if (state.brainTab === "references") loadReferences();
  });
  $("#learn-raw-button").onclick = learnRawWriting;
  $("#reference-button").onclick = searchReferences;
  $("#model-button").onclick = showModelSheet;
  $("#model-status").onclick = showModelSheet;
  $("#sync-status").onclick = loadSyncStatus;
  $("#manual-sync").onclick = manualSync;
  $("#snapshot-button").onclick = createSnapshot;
  $("#logout-button").onclick = async () => { await jsonApi("/api/auth/logout", {method: "POST"}); location.reload(); };
  $("#login-form").onsubmit = async event => {
    event.preventDefault();
    try {
      await jsonApi("/api/auth/login", {method: "POST", body: {password: $("#login-password").value}});
      location.reload();
    } catch (error) {
      $("#login-error").textContent = error.message;
    }
  };
  $("#chat-input").addEventListener("input", event => {
    event.target.style.height = "auto";
    event.target.style.height = `${Math.min(event.target.scrollHeight, 130)}px`;
  });
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    state.deferredInstall = event;
    $("#install-button").classList.remove("hidden");
  });
  $("#install-button").onclick = async () => {
    await state.deferredInstall?.prompt();
    state.deferredInstall = null;
    $("#install-button").classList.add("hidden");
  };
  window.addEventListener("online", saveDraftToServer);
}

bindEvents();
initialize().catch(error => {
  if (error.status === 401) $("#login-screen").classList.remove("hidden");
  else toast(error.message);
});
