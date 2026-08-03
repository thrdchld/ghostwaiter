class StateManager {
  constructor() {
    this.data = {
      workspace: localStorage.getItem("ghostwaiter:workspace") || "personal",
      sessionToken: localStorage.getItem("ghostwaiter:session") || "",
      activeView: localStorage.getItem("ghostwaiter:activeView") || "chat",
      theme: localStorage.getItem("ghostwaiter:theme") || "auto",
      language: localStorage.getItem("ghostwaiter:language") || "en",
      currentChatId: null,
      currentDraftId: null,
      notes: [],
      drafts: [],
      chats: [],
      brain: { style: [], thinking: [], memory: [], proposals: [] },
      modelStatus: { connected: false, message: "" }
    };
    this.listeners = new Set();
  }

  get(key) {
    return this.data[key];
  }

  set(key, value) {
    this.data[key] = value;
    this.notify(key, value);
  }

  update(partial) {
    Object.assign(this.data, partial);
    for (const [key, value] of Object.entries(partial)) {
      this.notify(key, value);
    }
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify(key, value) {
    for (const listener of this.listeners) {
      try {
        listener(key, value, this.data);
      } catch (err) {
        console.error("State listener error:", err);
      }
    }
  }
}

export const state = new StateManager();
