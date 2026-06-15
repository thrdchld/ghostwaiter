---
title: Ghostwriter
emoji: ✍️
colorFrom: red
colorTo: pink
sdk: docker
app_port: 7860
fullWidth: true
pinned: false
short_description: Personal writing intelligence that learns your style.
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

# GhostWriter

GhostWriter adalah web app penulisan personal berbasis FastAPI dan Hugging Face
Inference Providers. Aplikasi menyimpan draft, chat, Brain profile, references,
dan snapshot secara terisolasi per workspace.

## Fitur

- Chat dan writing generation dengan streaming
- Markdown chat yang dirender aman dan rapi
- Ringkasan serta konsep percakapan yang terhubung antar-chat dalam satu workspace
- Akses workspace lain hanya ketika diminta eksplisit
- Rename, arsip, restore, dan hapus permanen chat
- Usulan pembelajaran chat yang dapat diedit, disetujui, atau ditolak
- Model utama dan fallback melalui Hugging Face
- Pencarian, pengujian, penambahan, dan pengurutan model Hugging Face
- Draft autosave lokal dan server
- PWA mobile-first dengan offline app shell
- Style profile dan thinking profile dari revisi pengguna
- Workspace yang terisolasi
- Quick notes, references, snapshot, export ZIP
- GitHub backup queue dan autosync
- Password protection opsional

## Konfigurasi Space

Tambahkan secrets berikut melalui **Settings → Variables and secrets**:

| Secret | Wajib | Kegunaan |
|---|---:|---|
| `HF_TOKEN` | Ya | Memanggil Hugging Face Inference Providers |
| `APP_PASSWORD` | Disarankan | Membatasi akses aplikasi single-user |
| `SESSION_SECRET` | Disarankan | Menandatangani session cookie |
| `GITHUB_TOKEN` | Tidak | Menyinkronkan backup ke GitHub |
| `TAVILY_API_KEY` | Tidak | Pencarian referensi internet |

Tambahkan variables berikut bila diperlukan:

| Variable | Default |
|---|---|
| `HF_MODEL` | `Qwen/Qwen3-4B-Instruct-2507` |
| `HF_FALLBACK_MODELS` | `Qwen/Qwen3-8B,mistralai/Mistral-7B-Instruct-v0.3` |
| `HF_INFERENCE_PROVIDER` | `auto` |
| `GITHUB_BACKUP_REPO` | kosong, format `owner/repo` |
| `SYNC_DEBOUNCE_SECONDS` | `45` |

Token GitHub memerlukan akses **Contents: Read and write** hanya untuk repository
backup yang dituju. Token disimpan sebagai Space Secret dan tidak dikirim ke
frontend.

## Penyimpanan

Jika `/data` tersedia dan writable, aplikasi menggunakannya sebagai persistent
storage. Tanpa persistent storage, data runtime dapat hilang ketika Space
restart; aktifkan GitHub backup atau lakukan export ZIP berkala.

## Menjalankan lokal

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app:app --reload --port 7860
```

Environment dari `.env` perlu diekspor oleh shell atau loader pilihan Anda.

## Struktur

```text
app.py
backend/
  ai.py
  config.py
  main.py
  storage.py
frontend/
  index.html
  assets/
  manifest.webmanifest
  service-worker.js
  data/
  system/
  workspaces/
  queue/
  snapshots/
```

Brain workspace juga menyimpan:

```text
brain/conversation_memory.json
brain/learning_proposals.json
summary/workspace_summary.json
```

Implementasi ini sengaja tidak memiliki terminal agent, command execution, atau
model GGUF lokal. `base-project.sh` dipertahankan hanya sebagai referensi sistem
lama dan tidak dipakai oleh Docker image.
