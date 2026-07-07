# Ghostwaiter

Ghostwaiter is a personal writing assistant, note-taking app, and style learning environment. It runs as a progressive web application (PWA) powered by a Python **FastAPI** backend and a static HTML/CSS/JS frontend.

It stores application data in **Supabase** (with automatic fallback to a local directories if not configured) and integrates with **GitHub** for manual sync/backup workflows.

This repository is ready to be hosted as a **Hugging Face Space** using the provided `Dockerfile`.

---

## Features

- **Multi-provider AI Support**: Configure API keys and choose models (Google Gemini, OpenRouter, Groq, DeepSeek, Mistral, etc.) directly from the UI.
- **SSE Streaming**: Real-time response streaming for chat and document writing.
- **Smart Chat Workspace**: Conversational interface with markdown rendering and automated `<think>` reasoning tag filtering.
- **Auto Writer**: Paraphrase, rewrite, or generate drafts automatically based on customized writing guidelines.
- **Notes Grid**: Organize thoughts with pinning, custom tags, and image attachments.
- **Brain Center**: Automatically extracts and manages writing rules, style guides, memory nodes, and thinking patterns from writing samples and revisions.
- **GitHub Sync**: Push and pull database states to a GitHub backup repository.

---

## Configuration & Environment Variables

To configure the application (especially when deploying to Hugging Face Spaces), set the following environment variables:

| Name | Type | Required | Description |
| :--- | :--- | :---: | :--- |
| `SUPABASE_URL` | Variable | Yes | Your Supabase project URL (e.g., `https://your-proj.supabase.co`). |
| `SUPABASE_KEY` | Secret | Yes | Your Supabase Project `anon` / `public` API key. |
| `APP_PASSWORD` | Secret | No | Password for single-user authentication. If empty, authentication is disabled. |
| `SESSION_SECRET` | Secret | No | Encryption secret key for session cookies. |
| `GITHUB_TOKEN` | Secret | No | GitHub Personal Access Token for backup synchronization. |
| `GITHUB_BACKUP_REPO` | Variable | No | Target GitHub repository for backups, in the format `owner/repo`. |
| `TAVILY_API_KEY` | Secret | No | API key for web search reference support. |
| `DATA_DIR` | Variable | No | Custom folder path for local fallback storage. Defaults to `./data`. |

---

## Database Schema (Supabase)

If you configure Supabase, you must run the following SQL script in your Supabase project's **SQL Editor** to initialize the three required tables:

```sql
-- 1. Create Workspaces Table
CREATE TABLE IF NOT EXISTS public.workspaces (
    id TEXT PRIMARY KEY,
    data JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 2. Create Chats Table
CREATE TABLE IF NOT EXISTS public.chats (
    id TEXT PRIMARY KEY,
    history JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- 3. Create Drafts Table
CREATE TABLE IF NOT EXISTS public.drafts (
    id TEXT PRIMARY KEY,
    content JSONB DEFAULT '{}'::jsonb NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

---

## Running Locally

Follow these instructions to run the application server locally on your machine:

### Installation
1. Ensure Python 3.10+ is installed.
2. Clone the repository and navigate to its root directory.
3. Create a virtual environment and install the dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows, use: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Execution
Run the development server using `uvicorn`:
```bash
uvicorn app:app --reload --port 7860
```
Open your browser and navigate to `http://localhost:7860` to access the application.

---

## Architecture Overview

- **Backend**: FastAPI (`app.py` -> `backend/main.py`) provides REST API endpoints, session security, proxy streaming for AI APIs, and database orchestration.
- **Frontend**: Clean static assets (`frontend/index.html` -> CSS/JS) styled using CSS and client logic.
- **Storage**: Maps files or database rows per workspace using `SupabaseStore` (defined in `backend/storage.py`), which falls back automatically to local JSON files if Supabase is offline or not configured.
