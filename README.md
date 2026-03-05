# 🔗 Hardlink Manager

> **⚠️ 100% Vibe Code** — This project was entirely built using AI (Claude). I'm not a developer at all. Use at your own risk, no guarantees, no support promised. It works for me though!

A web dashboard to manage hardlinks between your media source folder and genre folders, with Radarr, Sonarr, and Jellystat integration. Built for self-hosted NAS setups (Synology, QNAP, TrueNAS, Unraid, etc.).

---

## 🇫🇷 / 🇬🇧 Language

The interface supports **French and English**. Switch with the button in the top-right corner of the UI. Your preference is saved in the browser.

---

## ✨ Features

- 🎬 **Hardlink management** — Creates hardlinks from source to genre folders (Radarr metadata)
- 📺 **Sonarr integration** — Detects orphan series in your check folder
- 📊 **Jellystat integration** — Shows watch count and history per movie
- 🔔 **Webhooks** — Auto-create hardlinks on Radarr/Jellyfin events
- ⏰ **Cron automation** — Schedule hardlink creation and orphan checks
- 🔍 **Duplicate/orphan detection** — Find wrong-genre or orphaned files
- 🚫 **Exclusion lists** — Ignore movies/series you don't want flagged
- 📋 **Activity log** — Full log of all operations

---

## 🚀 Deploy on your NAS

### Prerequisites

- Docker and Docker Compose installed on your NAS
- Git installed (optional, you can also download the ZIP)
- Your media files must be on the **same filesystem** as your genre folders (required for hardlinks)

### Step 1 — Clone the repo

```bash
git clone https://github.com/leof28/radarr-manager.git
cd radarr-manager
```

Or download the ZIP from GitHub and extract it.

### Step 2 — Edit `docker-compose.yml`

Open `docker-compose.yml` and update **every value** marked with `YOUR_`:

```yaml
volumes:
  - /YOUR/MEDIA/PATH:/media          # Path to your media root on the NAS
  - /YOUR/MEDIA/PATH/config:/app/config  # Where config will be stored

environment:
  - RADARR_URL=http://YOUR_NAS_IP:7878   # IP of your NAS (e.g. 192.168.1.100)
  - API_KEY=YOUR_RADARR_API_KEY          # Found in Radarr → Settings → General
  - SOURCE_ROOT=/media/movies/Unsorted   # Where new movies land (inside container)
  - MEDIA_ROOT=/media/movies             # Root of your library (inside container)
  - OWNER_USER=1000   # Run: id -u   on your NAS to get your UID
  - OWNER_GROUP=1000  # Run: id -g   on your NAS to get your GID
  - TZ=America/Toronto  # Your timezone
```

> **Important:** `SOURCE_ROOT` and `MEDIA_ROOT` must be on the **same filesystem** (same volume mount) for hardlinks to work.

### Step 3 — Build and start

```bash
docker compose up -d --build
```

### Step 4 — Open the UI

Navigate to `http://YOUR_NAS_IP:5550` in your browser.

### Step 5 — Configure in the UI

1. Go to **Settings → Connections** and fill in your Radarr/Sonarr/Jellystat URLs and API keys
2. Go to **Settings → Paths** and set your source and destination paths
3. Go to **Settings → Genres** → click **Load from Radarr** to map genres to folders
4. Click **Save**, then **Scan** to see your library

---

## 📁 Hardlink Logic

```
Source folder (Unsorted):
  /media/movies/Unsorted/The Matrix (1999)/The Matrix (1999).mkv

↓ hardlinks created in genre folders:

/media/movies/Sci-Fi/The Matrix (1999)/The Matrix (1999).mkv   ← hardlink
/media/movies/Action/The Matrix (1999)/The Matrix (1999).mkv   ← hardlink
```

Both files share the same disk blocks — no extra space used.

---

## 🔔 Webhooks

Configure Radarr/Jellyfin to call these endpoints on import/play events:

- `POST http://YOUR_NAS_IP:5550/api/webhook/radarr`
- `POST http://YOUR_NAS_IP:5550/api/webhook/jellyfin`

Optionally set a **webhook secret** in Settings → Automation → Webhooks.

---

## 🛑 Disclaimer

- This is **100% vibe code** — built entirely with AI assistance
- I am **not a developer**
- There is **no warranty** of any kind
- **File deletions are permanent** — always double check before deleting
- Test in a non-production environment first

---

## 📄 License

MIT — See [LICENSE](LICENSE)
