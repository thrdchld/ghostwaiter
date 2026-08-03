import { state } from './state.js';

export async function api(path, options = {}) {
  const config = { ...options, credentials: "same-origin", headers: { ...(options.headers || {}) } };
  
  const token = localStorage.getItem("ghostwaiter:session") || state.get("sessionToken");
  if (token) config.headers.Authorization = `Bearer ${token}`;

  const provider = localStorage.getItem("ghostwaiter:ai_provider") || "custom";
  const key = localStorage.getItem(`ghostwaiter:key_${provider}`) || localStorage.getItem("ghostwaiter:openrouter_key") || "";
  const model = localStorage.getItem("ghostwaiter:openrouter_model") || "";

  if (!config.headers["X-AI-Provider"]) {
    if (provider === "custom") {
      const customEndpoint = localStorage.getItem("ghostwaiter:custom_endpoint") || "";
      const customApiType = localStorage.getItem("ghostwaiter:custom_api_type") || "openai";
      config.headers["X-AI-Provider"] = `custom|${customApiType}|${customEndpoint}`;
    } else {
      config.headers["X-AI-Provider"] = provider;
    }
  }

  if (key && !config.headers["X-OpenRouter-Key"]) config.headers["X-OpenRouter-Key"] = key;
  if (model && !config.headers["X-OpenRouter-Model"]) config.headers["X-OpenRouter-Model"] = model;

  if (config.body && !(config.body instanceof FormData)) {
    config.headers["Content-Type"] = "application/json";
    if (typeof config.body !== "string") config.body = JSON.stringify(config.body);
  }

  const baseUrl = localStorage.getItem("ghostwaiter:api_base_url") || "";
  const targetUrl = (path.startsWith("/") && baseUrl) ? baseUrl.replace(/\/$/, "") + path : path;
  
  const response = await fetch(targetUrl, config);
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
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

export async function jsonApi(path, options = {}) {
  return (await api(path, options)).json();
}
