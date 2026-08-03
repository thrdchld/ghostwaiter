# Ghostwaiter

Ghostwaiter adalah aplikasi web penulisan personal yang menggabungkan fitur chat pintar, editor tulisan (Auto Writer), sistem pembelajaran gaya bahasa (Brain Center), dan pengelolaan catatan. 

Aplikasi ini berjalan sebagai satu halaman **PWA (Progressive Web App)** dengan backend **FastAPI** (Python) dan frontend statis (HTML/CSS/JS).

---

## Alur Penyimpanan Data (Storage)

Aplikasi ini memiliki sistem penyimpanan hibrida:
1. **Penyimpanan Supabase**: Jika variabel environment `SUPABASE_URL` dan `SUPABASE_KEY` diatur, aplikasi akan menyimpan seluruh data (workspaces, chats, drafts, notes) secara cloud di database Supabase Anda.
2. **Penyimpanan Lokal (Local Fallback)**: Jika Supabase tidak dikonfigurasi, aplikasi akan otomatis menyimpan data secara lokal pada server/perangkat dalam folder `data/` dengan struktur:
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
   ```

---

## Fitur Utama

- **Inference Multi-Provider**: Pilih model AI langsung dari UI menggunakan API Key Anda sendiri (OpenRouter, Google Gemini, Groq, DeepSeek, Mistral, dll.).
- **Streaming Response**: Chat dan penulisan teks (generate) berjalan secara streaming dengan filter otomatis untuk blok `<think>`.
- **Auto Writer**: Menulis draf, menulis ulang (*rewrite*), atau parafrase teks otomatis sesuai gaya penulisan Anda.
- **Notes Grid**: Catatan cepat terintegrasi dengan filter tag, penyematan (pin), dan unggah gambar.
- **Brain Center**: Menyimpan aturan gaya bahasa (*style rules*), pola berpikir (*thinking patterns*), dan memori AI yang diekstraksi dari contoh tulisan Anda.
- **GitHub Sync & Backup**: Sinkronisasi data manual (backup/restore) ke repositori GitHub Anda.
- **Standalone & Cloud-Ready**: Aplikasi web mandiri berbasis Python FastAPI yang dapat dijalankan secara lokal atau dideploy ke berbagai cloud provider (Vercel, Render, Railway, VPS, Termux, dll.) dengan Supabase sebagai database utama.

---

## Konfigurasi Environment (Secrets & Variables)

Atur variabel environment berikut di server lokal Anda (dalam file `.env`) atau di Secrets/Variables Hugging Face Space:

| Nama Variabel | Jenis | Wajib | Keterangan |
| :--- | :---: | :---: | :--- |
| `SUPABASE_URL` | Variable | Tidak | URL proyek Supabase Anda (untuk cloud database). |
| `SUPABASE_KEY` | Secret | Tidak | Kunci API `anon` / `public` Supabase Anda. |
| `APP_PASSWORD` | Secret | Tidak | Password masuk aplikasi. Jika diisi, halaman login akan aktif. |
| `SESSION_SECRET` | Secret | Tidak | Secret key untuk session cookie. |
| `GITHUB_TOKEN` | Secret | Tidak | Token GitHub untuk kebutuhan sinkronisasi backup repositori. |
| `GITHUB_BACKUP_REPO` | Variable | Tidak | Repositori tujuan backup di GitHub, format: `owner/repo`. |
| `TAVILY_API_KEY` | Secret | Tidak | Kunci API Tavily untuk mendukung fitur pencarian referensi web. |
| `SYNC_DEBOUNCE_SECONDS` | Variable | Tidak | Delay otomatisasi sinkronisasi (default: `45` detik). |
| `DATA_DIR` | Variable | Tidak | Lokasi folder penyimpanan lokal jika tidak menggunakan Supabase. |

---

## Skema Database Supabase

Jika menggunakan Supabase, pastikan Anda menjalankan skrip berikut di **SQL Editor** pada dasbor Supabase Anda untuk membuat tabel yang dibutuhkan:

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

## Menjalankan Server Lokal

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Buat file .env dan isi variabel yang dibutuhkan
uvicorn app:app --reload --port 7860
```

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Buat file .env dan isi variabel yang dibutuhkan
uvicorn app:app --reload --port 7860
```

### Termux (Android)
```bash
pkg update && pkg upgrade
pkg install python binutils
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Buat file .env dan isi variabel yang dibutuhkan
uvicorn app:app --reload --port 7860
```
Buka browser Anda dan akses halaman di `http://localhost:7860`.

---

## Deployment ke GitHub Pages

Frontend aplikasi (HTML/CSS/JS) dapat di-host secara gratis langsung di **GitHub Pages**:

1. Pushed repositori Anda ke GitHub.
2. Workflow GitHub Actions `.github/workflows/deploy-pages.yml` akan secara otomatis mempublikasikan folder `frontend` ke GitHub Pages.
3. Masuk ke **Settings > Pages** di repositori GitHub Anda dan pilih Source: **GitHub Actions**.
4. Jika backend Anda di-host secara terpisah (misalnya di Render/Railway/VPS), Anda dapat mengatur **API Base URL** pada menu Settings di aplikasi agar PWA di GitHub Pages dapat berkomunikasi dengan backend Anda.

