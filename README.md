---
title: Ghostwriter
emoji: ✍️
colorFrom: red
colorTo: pink
sdk: docker
app_port: 7860
fullWidth: true
pinned: false
short_description: Personal writing assistant that learns style, thinking, and memory.
models:
  - Qwen/Qwen3-4B-Instruct-2507
  - Qwen/Qwen3-8B
  - mistralai/Mistral-7B-Instruct-v0.3
tags:
  - writing
  - pwa
  - fastapi
  - inference-providers
---

# GhostWriter v1.5

GhostWriter adalah web app penulisan personal yang menggabungkan chat, editor tulisan, sistem pembelajaran gaya, dan backup GitHub. Aplikasi ini berjalan sebagai satu halaman PWA dengan backend FastAPI yang menyimpan data secara lokal dan menyediakan sinkronisasi manual ke GitHub.

## Ringkasan versi 1.5

- UI utama: Chat, Write, Brain, dan Settings.
- Provider AI dapat dipilih dari UI (OpenRouter, Google Gemini, Groq, DeepSeek, Mistral, Kilo).
- Chat dan generate tulisan berjalan dengan streaming.
- Draft autosave dan word count tersedia di editor.
- Brain menyimpan style rules, thinking patterns, memory, rules, references, dan learning proposals.
- Workspace dapat dibuat, dipilih, di-rename, dan dihapus (kecuali workspace default `writing`).
- Data dapat diekspor/impor dalam format ZIP dan disinkronkan ke GitHub secara manual.

## Fitur utama

- Multi-provider inference dengan model yang dipilih dari UI.
- Streaming chat dan writing generation.
- Safe Markdown rendering dengan filter otomatis untuk blok `<think>`.
- Draft editor dengan autosave lokal dan tombol train/copy.
- Brain Center untuk mengelola style, thinking, memory, rules, dan proposal.
- Referensi web via Tavily untuk mendukung pembelajaran.
- Snapshot, export ZIP, dan import ZIP.
- PWA dengan service worker dan install support.

## Konfigurasi environment

Untuk deployment (misalnya Hugging Face Space), atur secret/variable berikut:

| Jenis | Nama | Wajib | Keterangan |
|---|---|---:|---|
| Secret | `HF_TOKEN` | Ya | Token untuk Inference Providers |
| Secret | `APP_PASSWORD` | Tidak | Password aplikasi jika ingin proteksi single-user |
| Secret | `SESSION_SECRET` | Tidak | Secret untuk session cookie |
| Secret | `GITHUB_TOKEN` | Tidak | Token GitHub untuk backup/sync |
| Secret | `TAVILY_API_KEY` | Tidak | API key untuk pencarian referensi web |
| Variable | `HF_MODEL` | Tidak | Model default, default: `Qwen/Qwen3-4B-Instruct-2507` |
| Variable | `HF_FALLBACK_MODELS` | Tidak | Daftar fallback model |
| Variable | `GITHUB_BACKUP_REPO` | Tidak | Format `owner/repo` |
| Variable | `SYNC_DEBOUNCE_SECONDS` | Tidak | Delay autosync, default `45` |
| Variable | `DATA_DIR` | Tidak | Lokasi storage data jika ingin menyimpan di path lain |

## Struktur data

Aplikasi menyimpan metadata di folder `data` (atau lokasi yang ditentukan oleh `DATA_DIR`). Struktur utama:

```text
data/
  system/
    settings.json
    models.json
    workspaces.json
  workspaces/
    <workspace_id>/
      drafts/
      chats/
      brain/
      references/
      summary/
      learning/
      settings/
  queue/
  snapshots/
  archive/
```

## Menjalankan lokal

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload --port 7860
```

Jika Anda tidak menggunakan `.env`, export variabel yang diperlukan sebelum menjalankan server.

## Catatan arsitektur

- Backend: FastAPI, REST API, streaming response, auth cookie/session.
- Frontend: static HTML/CSS/JS, no heavy framework.
- Storage: JSON file per entity, not a single monolithic DB.
- Sync: manual GitHub push/pull via GitHub API.
- PWA: service worker + Web App Manifest untuk install di mobile.

## Bukan fitur

Implementasi ini sengaja tidak menyediakan terminal agent, command execution, atau model lokal GGUF. File `base-project.sh` tetap ada sebagai referensi lama, tapi aplikasi saat ini berjalan dari backend dan frontend yang ada di repo ini.
