from flask import Flask, jsonify, request, send_from_directory
import os
import subprocess
import json
import requests
from datetime import datetime, timedelta
import time
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- CONFIGURATION ---
CONFIG_DIR = "/app/config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_PATH = os.path.join(CONFIG_DIR, "scan_cache.json")
LOGS_PATH = os.path.join(CONFIG_DIR, "logs.json")
IGNORE_PATH = os.path.join(CONFIG_DIR, "ignored.json")
SCRIPT_PATH = "./hardlink_manager.sh"
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# --- SCHEDULER ---
scheduler = BackgroundScheduler()
scheduler.start()


def load_config():
    defaults = {
        "radarrUrl": "",
        "apiKey": "",
        "sonarrUrl": "",
        "sonarrApiKey": "",
        "sourceRoot": "/media/movies/A trier",
        "mediaRoot": "/media/movies",
        "seriesSourceRoot": "/media/series/Source",
        "seriesCheckRoot": "/media/series/Check",
        "ownerUser": "",
        "ownerGroup": "",
        "genreMapping": {},
        "autoSync": {
            "enabled": False,
            "cronSchedule": "0 */6 * * *",
            "lastRun": None,
            "lastFullScan": None
        },
        "seriesAutoCheck": {
            "enabled": False,
            "cronSchedule": "0 */12 * * *",
            "lastRun": None
        },
        "webhookEnabled": False,
        "webhookSecret": "",
        "scanOptimization": {
            "enabled": True,
            "recentHours": 3,
            "fullScanInterval": 24
        },
        "seriesCheck": {
            "enabled": False
        },
        "jellystatUrl": "",
        "jellystatApiKey": ""
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                saved = json.load(f)
                # Deep merge for nested dicts
                result = {**defaults, **saved}
                for key in ('autoSync', 'seriesAutoCheck', 'scanOptimization', 'seriesCheck'):
                    if key in defaults and key in saved and isinstance(saved[key], dict):
                        result[key] = {**defaults[key], **saved[key]}
                return result
        except Exception:
            return defaults
    return defaults


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
    setup_cron_jobs(config)


def load_cache():
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=4)


# --- LOGS ---

def load_logs():
    if os.path.exists(LOGS_PATH):
        try:
            with open(LOGS_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_logs(logs):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(LOGS_PATH, 'w') as f:
        json.dump(logs, f)


def append_log(level, category, message, details=None):
    """Ajoute une entrée dans le journal persistant (max 1000 entrées)."""
    logs = load_logs()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,       # "info" | "success" | "warning" | "error"
        "category": category, # "hardlink" | "series" | "cron" | "delete" | "webhook" | "scan" | "ignore"
        "message": message,
    }
    if details:
        entry["details"] = details
    logs.append(entry)
    if len(logs) > 1000:
        logs = logs[-1000:]
    save_logs(logs)
    return entry


# --- IGNORE ---

def load_ignored():
    if os.path.exists(IGNORE_PATH):
        try:
            with open(IGNORE_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {"series": [], "movies": []}
    return {"series": [], "movies": []}


def save_ignored(ignored):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(IGNORE_PATH, 'w') as f:
        json.dump(ignored, f, indent=2)


# --- HARDLINK HELPERS ---

def get_env(config, movie="", genres=""):
    mapping_str = "|".join([
        f"{genre}:{settings['folder']}"
        for genre, settings in config.get('genreMapping', {}).items()
        if settings.get('enabled', False)
    ])
    env = os.environ.copy()
    env.update({
        "RADARR_URL": config.get('radarrUrl', ''),
        "API_KEY": config.get('apiKey', ''),
        "SOURCE_ROOT": config.get('sourceRoot', ''),
        "MEDIA_ROOT": config.get('mediaRoot', ''),
        "GENRE_MAPPING_STR": mapping_str,
        "OWNER_USER": str(config.get('ownerUser', '')),
        "OWNER_GROUP": str(config.get('ownerGroup', '')),
        "SPECIFIC_MOVIE": str(movie),
        "SPECIFIC_GENRES": str(genres)
    })
    return env


def _parse_hardlink_summary(output):
    """Parse le résumé de hardlink_manager.sh et retourne un dict."""
    summary = {"total": 0, "linked": 0, "skipped": 0, "errors": 0}
    for line in output.split('\n'):
        if line.startswith("Films traités:"):
            try: summary["total"] = int(line.split(":")[1].strip())
            except: pass
        elif line.startswith("Hardlinks créés:"):
            try: summary["linked"] = int(line.split(":")[1].strip())
            except: pass
        elif line.startswith("Films ignorés:"):
            try: summary["skipped"] = int(line.split(":")[1].strip())
            except: pass
        elif line.startswith("Erreurs:"):
            try: summary["errors"] = int(line.split(":")[1].strip())
            except: pass
    return summary


def execute_hardlinks(config, movie_path='', genres=''):
    env = get_env(config, movie_path, genres)
    label = os.path.basename(movie_path) if movie_path else ("genre=" + genres if genres else "tous")
    try:
        process = subprocess.run(
            [SCRIPT_PATH, "-y"],
            capture_output=True, text=True, env=env, timeout=600
        )
        result = {"status": "ok", "output": process.stdout, "errors": process.stderr}

        # Log the result
        summary = _parse_hardlink_summary(process.stdout)
        if process.returncode != 0 or process.stderr.strip():
            append_log("error", "hardlink",
                       f"Hardlinks [{label}] — erreurs détectées",
                       {"summary": summary, "stderr": process.stderr[:500]})
        elif summary["linked"] > 0:
            append_log("success", "hardlink",
                       f"Hardlinks créés [{label}] — {summary['linked']} lien(s), {summary['skipped']} ignoré(s)",
                       {"summary": summary})
        else:
            append_log("info", "hardlink",
                       f"Hardlinks [{label}] — rien de nouveau ({summary['skipped']} ignoré(s))",
                       {"summary": summary})

        return result
    except Exception as e:
        append_log("error", "hardlink", f"Hardlinks [{label}] — exception: {e}")
        return {"status": "error", "error": str(e)}


def get_hardlink_status(config):
    env = get_env(config)
    try:
        process = subprocess.run(
            [SCRIPT_PATH, "-s"],
            capture_output=True, text=True, env=env, timeout=300
        )
        hardlink_status = {}
        for line in process.stdout.split('\n'):
            if line.startswith("HARDLINK_STATUS"):
                parts = line.split('|')
                if len(parts) >= 6:
                    folder_name = parts[1]
                    genre = parts[2]
                    local_folder = parts[3]
                    found = int(parts[4])
                    total = int(parts[5])
                    hardlink_status.setdefault(folder_name, []).append({
                        "genre": genre,
                        "folder": local_folder,
                        "found": found,
                        "total": total,
                        "exists": found >= total and total > 0
                    })
        return hardlink_status
    except Exception as e:
        print(f"Erreur get_hardlink_status: {e}")
        return {}


# --- SCAN OPTIMIZATION ---

def should_do_full_scan(config):
    optimization = config.get('scanOptimization', {})
    if not optimization.get('enabled', True):
        return True
    last_full_scan = config.get('autoSync', {}).get('lastFullScan')
    if not last_full_scan:
        return True
    full_scan_interval = optimization.get('fullScanInterval', 24)
    hours_since = (datetime.now() - datetime.fromisoformat(last_full_scan)).total_seconds() / 3600
    return hours_since >= full_scan_interval


def get_recent_movies(config):
    source_root = config.get('sourceRoot', '')
    recent_hours = config.get('scanOptimization', {}).get('recentHours', 3)
    cutoff_time = datetime.now() - timedelta(hours=recent_hours)
    recent_movies = []
    try:
        if not os.path.isdir(source_root):
            return []
        for folder_name in os.listdir(source_root):
            folder_path = os.path.join(source_root, folder_name)
            if not os.path.isdir(folder_path):
                continue
            mtime = datetime.fromtimestamp(os.path.getmtime(folder_path))
            if mtime > cutoff_time:
                if any(f.lower().endswith('.mkv') for f in os.listdir(folder_path)):
                    recent_movies.append({'folder_name': folder_name, 'path': folder_path})
    except Exception as e:
        print(f"Erreur get_recent_movies: {e}")
    return recent_movies


# --- CRON HANDLERS ---

def cron_job_handler():
    print(f"[{datetime.now()}] Cron films: Démarrage...")
    append_log("info", "cron", "Cron films démarré")
    config = load_config()
    do_full_scan = should_do_full_scan(config)

    if do_full_scan:
        print(f"[{datetime.now()}] Scan complet")
        append_log("info", "cron", "Scan complet en cours...")
        execute_hardlinks(config)
        config['autoSync']['lastFullScan'] = datetime.now().isoformat()
    else:
        recent_movies = get_recent_movies(config)
        if recent_movies:
            print(f"[{datetime.now()}] {len(recent_movies)} films récents")
            append_log("info", "cron", f"Scan optimisé — {len(recent_movies)} film(s) récent(s)")
            for movie in recent_movies:
                execute_hardlinks(config, movie['path'])
        else:
            print(f"[{datetime.now()}] Aucun film récent")
            append_log("info", "cron", "Scan optimisé — aucun film récent, rien à faire")

    config['autoSync']['lastRun'] = datetime.now().isoformat()
    save_config(config)
    append_log("success", "cron", "Cron films terminé")
    print(f"[{datetime.now()}] Cron films terminé")


def series_cron_handler():
    print(f"[{datetime.now()}] Cron séries: Démarrage...")
    append_log("info", "cron", "Cron séries démarré")
    config = load_config()
    issues = detect_series_issues(config)
    config.setdefault('seriesAutoCheck', {})['lastRun'] = datetime.now().isoformat()
    save_config(config)
    msg = f"Cron séries terminé — {len(issues)} orpheline(s) trouvée(s)"
    append_log("success" if len(issues) == 0 else "warning", "cron", msg)
    print(f"[{datetime.now()}] {msg}")


def setup_cron_jobs(config):
    scheduler.remove_all_jobs()

    # Cron films
    if config.get('autoSync', {}).get('enabled', False):
        _add_cron_job('auto_hardlink', cron_job_handler,
                      config['autoSync'].get('cronSchedule', '0 */6 * * *'))

    # Cron vérification séries
    if config.get('seriesAutoCheck', {}).get('enabled', False):
        _add_cron_job('auto_series_check', series_cron_handler,
                      config['seriesAutoCheck'].get('cronSchedule', '0 */12 * * *'))


def _add_cron_job(job_id, handler, cron_schedule):
    parts = cron_schedule.split()
    if len(parts) != 5:
        print(f"Cron invalide pour {job_id}: {cron_schedule}")
        return
    try:
        scheduler.add_job(
            handler, 'cron',
            minute=parts[0], hour=parts[1], day=parts[2],
            month=parts[3], day_of_week=parts[4],
            id=job_id
        )
        print(f"Cron {job_id}: {cron_schedule}")
    except Exception as e:
        print(f"Erreur cron {job_id}: {e}")


# Init cron au démarrage
setup_cron_jobs(load_config())


# --- SERIES DETECTION ---

def _sonarr_folder_name(raw_path):
    """Extrait le nom du dossier depuis un chemin Sonarr (gère \ et /)."""
    return os.path.basename(raw_path.replace('\\', '/').rstrip('/'))


def detect_series_issues(config):
    """
    Détecte les séries orphelines dans le dossier Check.

    Logique :
      - Récupère la liste des séries depuis Sonarr (episodeFileCount, monitored)
      - Récupère la file de téléchargement Sonarr (activeDL)
      - Pour chaque dossier dans Check :
          • Trouvé dans Sonarr ET (a des fichiers OU est monitoré OU en DL) → pas orpheline
          • Sinon → orpheline
      - Fallback sans Sonarr : vérifie seriesSourceRoot sur le disque
      - Les séries dans la liste d'ignorées sont exclues
    """
    issues = []

    if not config.get('seriesCheck', {}).get('enabled', False):
        return issues

    series_source = config.get('seriesSourceRoot', '')
    series_check = config.get('seriesCheckRoot', '')
    sonarr_url = config.get('sonarrUrl', '').rstrip('/')
    sonarr_api_key = config.get('sonarrApiKey', '')

    if not series_check or not os.path.isdir(series_check):
        return issues

    ignored = load_ignored()
    ignored_series = set(ignored.get("series", []))

    try:
        sonarr_by_folder = {}   # folder_name → {id, path, title, monitored, episodeFileCount}
        active_series_ids = set()
        sonarr_available = bool(sonarr_url and sonarr_api_key)

        if sonarr_available:
            headers = {"X-Api-Key": sonarr_api_key}

            # 1. Séries
            try:
                resp = requests.get(f"{sonarr_url}/api/v3/series",
                                    headers=headers, timeout=30)
                resp.raise_for_status()
                for s in resp.json():
                    raw_path = s.get('path', '')
                    folder = _sonarr_folder_name(raw_path)
                    if folder:
                        sonarr_by_folder[folder] = {
                            'id': s.get('id'),
                            'path': raw_path,
                            'title': s.get('title', ''),
                            'monitored': s.get('monitored', False),
                            'episodeFileCount': s.get('statistics', {}).get('episodeFileCount', 0)
                        }
                print(f"[SERIES] {len(sonarr_by_folder)} séries dans Sonarr")
            except Exception as e:
                print(f"[SERIES] Erreur API séries: {e}")

            # 2. File de téléchargement (activeDL)
            try:
                q_resp = requests.get(f"{sonarr_url}/api/v3/queue",
                                      headers=headers,
                                      params={"pageSize": 1000},
                                      timeout=30)
                q_resp.raise_for_status()
                q_data = q_resp.json()
                records = q_data.get('records', q_data) if isinstance(q_data, dict) else q_data
                for item in records:
                    sid = item.get('seriesId') or (item.get('series') or {}).get('id')
                    if sid:
                        active_series_ids.add(sid)
                print(f"[SERIES] {len(active_series_ids)} séries en téléchargement")
            except Exception as e:
                print(f"[SERIES] Erreur API queue: {e}")

        # 3. Scan du dossier Check
        for series_folder in sorted(os.listdir(series_check)):
            check_path = os.path.join(series_check, series_folder)
            if not os.path.isdir(check_path):
                continue

            # Vérifier si ignorée
            if series_folder in ignored_series:
                print(f"[SERIES] {series_folder} → ignorée (liste d'exclusion)")
                continue

            # Recherche dans Sonarr : exact d'abord, puis normalisé
            sonarr_info = sonarr_by_folder.get(series_folder)
            if sonarr_info is None:
                norm = series_folder.replace('.', ' ').replace('_', ' ').lower().strip()
                for k, v in sonarr_by_folder.items():
                    if k.replace('.', ' ').replace('_', ' ').lower().strip() == norm:
                        sonarr_info = v
                        break

            is_orphan = False
            reason = ''
            sonarr_path = None
            in_active_dl = False
            sonarr_title = None

            if sonarr_info:
                sonarr_path = sonarr_info['path']
                sonarr_title = sonarr_info['title']
                series_id = sonarr_info['id']
                in_active_dl = series_id in active_series_ids
                has_files = sonarr_info['episodeFileCount'] > 0
                monitored = sonarr_info['monitored']

                if has_files:
                    print(f"[SERIES] {series_folder} → actif ({sonarr_info['episodeFileCount']} fichiers)")
                    continue
                elif monitored:
                    print(f"[SERIES] {series_folder} → monitoré (0 fichiers pour l'instant)")
                    continue
                elif in_active_dl:
                    print(f"[SERIES] {series_folder} → téléchargement actif (ID={series_id})")
                    continue
                else:
                    is_orphan = True
                    reason = 'Série non monitorée sans fichiers dans Sonarr'
            else:
                # Pas dans Sonarr → fallback filesystem
                if series_source and os.path.isdir(os.path.join(series_source, series_folder)):
                    print(f"[SERIES] {series_folder} → trouvée dans Source (fallback)")
                    continue
                is_orphan = True
                reason = ('Série absente de Sonarr' if sonarr_available
                          else f'Série absente de "{os.path.basename(series_source)}"')

            if is_orphan:
                file_count, total_size = 0, 0
                for root, _, files in os.walk(check_path):
                    for f in files:
                        if f.lower().endswith(('.mkv', '.mp4', '.avi')):
                            file_count += 1
                            try:
                                total_size += os.path.getsize(os.path.join(root, f))
                            except OSError:
                                pass

                issues.append({
                    'series': series_folder,
                    'sonarrTitle': sonarr_title or series_folder,
                    'path': check_path,
                    'type': 'series_orphan',
                    'reason': reason,
                    'fileCount': file_count,
                    'size': total_size,
                    'sonarrPath': sonarr_path,
                    'inActiveDL': in_active_dl
                })

        print(f"[SERIES] {len(issues)} séries orphelines détectées")
        return issues

    except Exception as e:
        print(f"Erreur detect_series_issues: {e}")
        import traceback
        traceback.print_exc()
        return []


# --- FILM DETECTION ---

def detect_duplicates(config):
    """Détecte doublons MKV, orphelins (source supprimée) et genres incorrects.
    Les films dans la liste d'ignorées sont exclus."""
    duplicates = []
    ignored = load_ignored()
    ignored_movies = set(ignored.get("movies", []))

    try:
        response = requests.get(
            f"{config['radarrUrl']}/api/v3/movie",
            headers={"X-Api-Key": config['apiKey']},
            timeout=30
        )
        response.raise_for_status()
        movies = response.json()

        movie_info = {}
        for movie in movies:
            if movie.get('hasFile'):
                folder_name = os.path.basename(movie['path'])
                file_path = movie.get('movieFile', {}).get('relativePath', '')
                official_name = os.path.basename(file_path) if file_path else ''
                genres = [g['name'] if isinstance(g, dict) else g for g in movie.get('genres', [])]
                movie_info[folder_name] = {
                    'official': official_name,
                    'genres': genres,
                    'title': movie['title']
                }

        genre_to_folder = {
            genre: settings['folder']
            for genre, settings in config.get('genreMapping', {}).items()
            if settings.get('enabled', False)
        }

        media_root = config.get('mediaRoot', '')
        source_root = config.get('sourceRoot', '')

        for genre_folder in os.listdir(media_root):
            genre_path = os.path.join(media_root, genre_folder)
            if not os.path.isdir(genre_path) or genre_folder == 'A trier':
                continue

            for movie_folder in os.listdir(genre_path):
                movie_path = os.path.join(genre_path, movie_folder)
                if not os.path.isdir(movie_path):
                    continue

                # Vérifier si ignoré
                if movie_folder in ignored_movies:
                    continue

                source_path = os.path.join(source_root, movie_folder)
                source_exists = os.path.isdir(source_path)
                info = movie_info.get(movie_folder, {})
                official = info.get('official', '')
                movie_genres = info.get('genres', [])
                movie_title = info.get('title', movie_folder)

                if not source_exists:
                    for mkv in [f for f in os.listdir(movie_path) if f.lower().endswith('.mkv')]:
                        full_path = os.path.join(movie_path, mkv)
                        duplicates.append({
                            'movie': movie_folder, 'title': movie_title,
                            'genre': genre_folder, 'file': mkv, 'path': full_path,
                            'isOfficial': True, 'inSource': False, 'wrongGenre': False,
                            'type': 'orphan',
                            'reason': 'Dossier source supprimé de "A trier"',
                            'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                        })
                    continue

                allowed_folders = {genre_to_folder[g] for g in movie_genres if g in genre_to_folder}
                is_wrong_genre = bool(allowed_folders) and genre_folder not in allowed_folders
                mkv_files = [f for f in os.listdir(movie_path) if f.lower().endswith('.mkv')]

                if len(mkv_files) > 1:
                    for mkv in mkv_files:
                        if mkv != official:
                            full_path = os.path.join(movie_path, mkv)
                            duplicates.append({
                                'movie': movie_folder, 'title': movie_title,
                                'genre': genre_folder, 'file': mkv, 'path': full_path,
                                'isOfficial': False,
                                'inSource': os.path.exists(os.path.join(source_path, mkv)),
                                'wrongGenre': is_wrong_genre,
                                'type': 'duplicate',
                                'reason': 'Ancienne version (pas le fichier officiel Radarr)',
                                'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                            })
                elif len(mkv_files) == 1 and is_wrong_genre:
                    mkv = mkv_files[0]
                    full_path = os.path.join(movie_path, mkv)
                    duplicates.append({
                        'movie': movie_folder, 'title': movie_title,
                        'genre': genre_folder, 'file': mkv, 'path': full_path,
                        'isOfficial': mkv == official, 'inSource': True, 'wrongGenre': True,
                        'type': 'wrong_genre',
                        'reason': f'Mauvais genre ! Devrait être dans : {", ".join(sorted(allowed_folders))}',
                        'correctFolders': list(allowed_folders),
                        'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                    })

        return duplicates
    except Exception as e:
        print(f"Erreur detect_duplicates: {e}")
        import traceback
        traceback.print_exc()
        return []


# --- JELLYSTAT ---

def get_jellystat_history(config):
    """Récupère tout l'historique de visionnage depuis Jellystat.
    Retourne un dict { titre_lower: [date_str, ...] } pour les films."""
    jellystat_url = config.get('jellystatUrl', '').rstrip('/')
    jellystat_key = config.get('jellystatApiKey', '')
    if not jellystat_url or not jellystat_key:
        return {}
    try:
        resp = requests.get(
            f"{jellystat_url}/api/getItemsPlaybackActivity",
            headers={"api-key": jellystat_key},
            timeout=30
        )
        resp.raise_for_status()
        raw = resp.json()
        # La réponse peut être une liste ou un dict avec une clé data/results
        items = raw if isinstance(raw, list) else raw.get('data', raw.get('results', []))
        history = {}
        for item in items:
            # Nom du film — plusieurs variantes de champ selon la version Jellystat
            name = (
                item.get('NomElement') or
                item.get('ItemName') or
                item.get('Name') or
                item.get('EpisodeName') or ''
            ).strip()
            # Date de visionnage
            date_str = (
                item.get('ActivityDateInserted') or
                item.get('DateEcoute') or
                item.get('Date') or
                item.get('PlaybackStart') or ''
            )
            # Type : on ne garde que les films
            item_type = (
                item.get('Type') or
                item.get('ItemType') or
                item.get('MediaType') or ''
            ).lower()
            if name and ('episode' not in item_type and 'series' not in item_type):
                key = name.lower()
                history.setdefault(key, []).append(date_str)
        print(f"[JELLYSTAT] {len(history)} titre(s) avec historique")
        return history
    except Exception as e:
        print(f"[JELLYSTAT] Erreur: {e}")
        return {}


# --- ROUTES ---

@app.route('/')
def index():
    return send_from_directory(TEMPLATE_DIR, 'index.html')


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        save_config(request.json)
        return jsonify({"status": "ok"})
    return jsonify(load_config())


@app.route('/api/genres', methods=['GET'])
def get_all_genres():
    config = load_config()
    try:
        response = requests.get(
            f"{config['radarrUrl']}/api/v3/movie",
            headers={"X-Api-Key": config['apiKey']},
            timeout=30
        )
        response.raise_for_status()
        all_genres = set()
        for movie in response.json():
            for genre in movie.get('genres', []):
                all_genres.add(genre['name'] if isinstance(genre, dict) else genre)

        current_mapping = config.get('genreMapping', {})
        return jsonify([
            {
                'name': genre,
                'enabled': current_mapping.get(genre, {}).get('enabled', False),
                'folder': current_mapping.get(genre, {}).get('folder', genre)
            }
            for genre in sorted(all_genres)
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def scan():
    config = load_config()
    try:
        return jsonify({"status": "success", "hardlinks": get_hardlink_status(config)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    config = load_config()
    try:
        response = requests.get(
            f"{config['radarrUrl']}/api/v3/movie",
            headers={"X-Api-Key": config['apiKey']},
            timeout=30
        )
        response.raise_for_status()
        all_movies = response.json()

        print(f"[SCAN] {len(all_movies)} films depuis Radarr")
        hardlink_status = get_hardlink_status(config)
        source_root = config['sourceRoot']

        # Récupération Jellystat (une seule fois pour tous les films)
        jellystat_history = get_jellystat_history(config)
        jellystat_enabled = bool(config.get('jellystatUrl') and config.get('jellystatApiKey'))

        result = []

        for movie in all_movies:
            if not movie.get('hasFile'):
                continue
            folder_name = os.path.basename(movie['path'])
            source_path = os.path.join(source_root, folder_name)
            if not os.path.isdir(source_path):
                continue
            try:
                if not any(f.lower().endswith('.mkv') for f in os.listdir(source_path)):
                    continue
            except OSError:
                continue

            genres = [g['name'] if isinstance(g, dict) else g for g in movie.get('genres', [])]
            poster = next((img.get('remoteUrl') for img in movie.get('images', [])
                           if img.get('coverType') == 'poster'), None)

            # Données Jellystat : matching par titre (insensible à la casse)
            title_key = movie['title'].lower()
            watch_dates_raw = jellystat_history.get(title_key, [])
            watch_dates_sorted = sorted([d for d in watch_dates_raw if d], reverse=True)

            result.append({
                "title": movie['title'],
                "path": source_path,
                "folderName": folder_name,
                "poster": poster,
                "genres": genres,
                "hardlinks": hardlink_status.get(folder_name, []),
                "addedTime": os.path.getmtime(source_path),
                "addedToRadarr": movie.get('added', ''),
                "fileSize": movie.get('movieFile', {}).get('size', 0),
                "tmdbId": movie.get('tmdbId'),
                "watchCount": len(watch_dates_raw),
                "watchDates": watch_dates_sorted[:10],
                "jellystatEnabled": jellystat_enabled
            })

        result.sort(key=lambda x: x['addedTime'], reverse=True)
        append_log("info", "scan", f"Scan bibliothèque — {len(result)} film(s) trouvé(s)")
        print(f"[SCAN] {len(result)} films retournés")
        return jsonify(result)
    except Exception as e:
        print(f"[ERREUR] {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/series-issues', methods=['GET'])
def get_series_issues():
    config = load_config()
    try:
        issues = detect_series_issues(config)
        if issues:
            append_log("warning", "series",
                       f"Scan séries — {len(issues)} orpheline(s) détectée(s)",
                       {"series": [i["series"] for i in issues]})
        else:
            append_log("success", "series", "Scan séries — aucune orpheline détectée")
        return jsonify(issues)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete-series', methods=['POST'])
def delete_series():
    import shutil
    data = request.json or {}
    series_path = data.get('path', '')
    series_name = data.get('name', os.path.basename(series_path))
    try:
        if series_path and os.path.isdir(series_path):
            shutil.rmtree(series_path)
            append_log("success", "delete", f"Série supprimée : {series_name}", {"path": series_path})
            return jsonify({"status": "ok", "message": f"Supprimé: {series_path}"})
        return jsonify({"error": "Dossier non trouvé"}), 404
    except Exception as e:
        append_log("error", "delete", f"Erreur suppression série {series_name}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete-all-series', methods=['POST'])
def delete_all_series():
    import shutil
    config = load_config()
    try:
        issues = detect_series_issues(config)
        success, errors = [], []
        for issue in issues:
            try:
                if os.path.isdir(issue['path']):
                    shutil.rmtree(issue['path'])
                    success.append(issue['series'])
                else:
                    errors.append(f"Non trouvé: {issue['series']}")
            except Exception as e:
                errors.append(f"Erreur {issue['series']}: {e}")
        if success:
            append_log("success", "delete",
                       f"{len(success)} série(s) orpheline(s) supprimée(s)",
                       {"deleted": success, "errors": errors})
        return jsonify({"status": "ok", "deleted": len(success),
                        "errors": len(errors), "details": {"success": success, "errors": errors}})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/duplicates', methods=['GET'])
def get_duplicates():
    config = load_config()
    try:
        dups = detect_duplicates(config)
        if dups:
            append_log("warning", "scan",
                       f"Scan films — {len(dups)} problème(s) détecté(s)",
                       {"orphans": sum(1 for d in dups if d["type"] == "orphan"),
                        "duplicates": sum(1 for d in dups if d["type"] == "duplicate"),
                        "wrong_genre": sum(1 for d in dups if d["type"] == "wrong_genre")})
        else:
            append_log("success", "scan", "Scan films — aucun problème détecté")
        return jsonify(dups)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete-file', methods=['POST'])
def delete_file():
    data = request.json or {}
    file_path = data.get('path', '')
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            parent = os.path.dirname(file_path)
            if os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
            append_log("success", "delete", f"Fichier supprimé : {os.path.basename(file_path)}", {"path": file_path})
            return jsonify({"status": "ok"})
        return jsonify({"error": "Fichier non trouvé"}), 404
    except Exception as e:
        append_log("error", "delete", f"Erreur suppression fichier: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/delete-duplicates', methods=['POST'])
def delete_duplicates():
    data = request.json or {}
    file_paths = data.get('paths', [])
    if not file_paths:
        return jsonify({"error": "Aucun fichier"}), 400

    success, errors = [], []
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                success.append(file_path)
                parent = os.path.dirname(file_path)
                if os.path.isdir(parent) and not os.listdir(parent):
                    os.rmdir(parent)
            else:
                errors.append(f"Non trouvé: {file_path}")
        except Exception as e:
            errors.append(f"Erreur {file_path}: {e}")

    if success:
        append_log("success", "delete",
                   f"{len(success)} fichier(s) supprimé(s)",
                   {"count": len(success), "errors": len(errors)})
    return jsonify({"status": "ok", "deleted": len(success), "errors": len(errors),
                    "details": {"success": success, "errors": errors}})


@app.route('/api/delete-movie', methods=['POST'])
def delete_movie():
    """Supprime un film : dossier source (A trier) + tous les hardlinks dans les dossiers genre."""
    import shutil
    data = request.json or {}
    source_path = data.get('sourcePath', '')
    folder_name = data.get('folderName', '') or (os.path.basename(source_path) if source_path else '')
    title = data.get('title', folder_name)
    config = load_config()
    media_root = config.get('mediaRoot', '')

    deleted = []
    errors = []

    # 1. Suppression du dossier source
    if source_path and os.path.isdir(source_path):
        try:
            shutil.rmtree(source_path)
            deleted.append(source_path)
        except Exception as e:
            errors.append(f"Source '{source_path}': {e}")
    elif source_path:
        errors.append(f"Source non trouvée: {source_path}")

    # 2. Suppression des hardlinks dans chaque sous-dossier genre de mediaRoot
    if folder_name and media_root and os.path.isdir(media_root):
        for genre_folder in os.listdir(media_root):
            genre_path = os.path.join(media_root, genre_folder)
            if not os.path.isdir(genre_path) or genre_folder == os.path.basename(config.get('sourceRoot', '')):
                continue
            movie_genre_path = os.path.join(genre_path, folder_name)
            if os.path.isdir(movie_genre_path):
                try:
                    shutil.rmtree(movie_genre_path)
                    deleted.append(movie_genre_path)
                except Exception as e:
                    errors.append(f"Hardlink '{genre_folder}/{folder_name}': {e}")

    if deleted:
        append_log("success", "delete",
                   f"Film supprimé (source + hardlinks) : {title}",
                   {"deleted": deleted, "errors": errors, "count": len(deleted)})
        return jsonify({"status": "ok", "deleted": deleted, "errors": errors})

    append_log("error", "delete", f"Suppression film échouée : {title}", {"errors": errors})
    return jsonify({"error": "Aucun dossier supprimé", "errors": errors}), 404


@app.route('/api/run', methods=['POST'])
def run_action():
    data = request.json or {}
    config = load_config()
    movie_paths = data.get('movie_paths', [])

    if not movie_paths:
        return jsonify(execute_hardlinks(config, data.get('movie_path', ''), data.get('genres', '')))

    results = [{"movie": os.path.basename(mp), **execute_hardlinks(config, mp)}
               for mp in movie_paths]
    return jsonify({"status": "ok", "results": results})


@app.route('/api/run-all', methods=['POST'])
def run_all():
    return jsonify(execute_hardlinks(load_config()))


@app.route('/api/run-by-genre', methods=['POST'])
def run_by_genre():
    data = request.json or {}
    genres = data.get('genres', [])
    if not genres:
        return jsonify({"error": "Aucun genre"}), 400
    config = load_config()
    results = [{"genre": g, **execute_hardlinks(config, '', g)} for g in genres]
    return jsonify({"status": "ok", "results": results})


@app.route('/api/webhook/jellyfin', methods=['POST'])
def jellyfin_webhook():
    config = load_config()
    if not config.get('webhookEnabled', False):
        return jsonify({"error": "Webhook désactivé"}), 403
    secret = config.get('webhookSecret', '')
    if secret and request.headers.get('X-Webhook-Secret', '') != secret:
        return jsonify({"error": "Secret invalide"}), 403
    try:
        data = request.json
        notif_type = data.get('NotificationType', '')
        if notif_type in ['ItemAdded', 'MovieAdded']:
            item = data.get('Item', {})
            item_path = item.get('Path', '')
            append_log("info", "webhook", f"Webhook Jellyfin reçu : {item.get('Name', '?')} ({notif_type})")
            time.sleep(5)
            movie_path = os.path.join(config['sourceRoot'],
                                      os.path.basename(os.path.dirname(item_path))) if item_path else ''
            result = execute_hardlinks(config, movie_path)
            return jsonify({"status": "ok", "message": f"Hardlinks créés pour {item.get('Name','')}", "result": result})
        return jsonify({"status": "ignored"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/webhook/radarr', methods=['POST'])
def radarr_webhook():
    config = load_config()
    if not config.get('webhookEnabled', False):
        return jsonify({"error": "Webhook désactivé"}), 403
    try:
        data = request.json
        event_type = data.get('eventType', '')
        if event_type in ['Download', 'Rename', 'MovieFileDelete']:
            movie = data.get('movie', {})
            append_log("info", "webhook",
                       f"Webhook Radarr reçu : {movie.get('title', '?')} ({event_type})")
            time.sleep(5)
            folder_name = os.path.basename(movie.get('folderPath', ''))
            movie_path = os.path.join(config['sourceRoot'], folder_name)
            result = execute_hardlinks(config, movie_path)
            return jsonify({"status": "ok", "message": f"Hardlinks créés pour {movie.get('title','')}", "result": result})
        return jsonify({"status": "ignored"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cron/status', methods=['GET'])
def cron_status():
    jobs = scheduler.get_jobs()
    return jsonify({
        "enabled": len(jobs) > 0,
        "jobs": [{
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        } for job in jobs]
    })


@app.route('/api/cron/trigger', methods=['POST'])
def trigger_cron():
    try:
        cron_job_handler()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/cron/series-trigger', methods=['POST'])
def trigger_series_cron():
    try:
        series_cron_handler()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- LOGS API ---

@app.route('/api/logs', methods=['GET'])
def get_logs():
    logs = load_logs()
    level = request.args.get('level', '')
    category = request.args.get('category', '')
    limit = min(int(request.args.get('limit', 200)), 1000)

    if level:
        logs = [l for l in logs if l.get('level') == level]
    if category:
        logs = [l for l in logs if l.get('category') == category]

    # Most recent first
    return jsonify(list(reversed(logs[-limit:])))


@app.route('/api/logs', methods=['DELETE'])
def clear_logs():
    save_logs([])
    append_log("info", "scan", "Journal effacé")
    return jsonify({"status": "ok"})


# --- IGNORE API ---

@app.route('/api/ignore', methods=['GET'])
def get_ignored():
    return jsonify(load_ignored())


@app.route('/api/ignore', methods=['POST'])
def add_ignored():
    data = request.json or {}
    item_type = data.get('type', '')   # "series" or "movies"
    item_name = data.get('name', '')
    label = data.get('label', item_name)

    if not item_type or not item_name:
        return jsonify({"error": "type et name requis"}), 400

    ignored = load_ignored()
    if item_type not in ignored:
        ignored[item_type] = []
    if item_name not in ignored[item_type]:
        ignored[item_type].append(item_name)
        save_ignored(ignored)
        append_log("info", "ignore",
                   f"{'Série' if item_type == 'series' else 'Film'} ignoré(e) : {label}")
    return jsonify({"status": "ok", "ignored": ignored})


@app.route('/api/ignore/<item_type>/<path:item_name>', methods=['DELETE'])
def remove_ignored(item_type, item_name):
    ignored = load_ignored()
    if item_type in ignored and item_name in ignored[item_type]:
        ignored[item_type].remove(item_name)
        save_ignored(ignored)
        append_log("info", "ignore",
                   f"{'Série' if item_type == 'series' else 'Film'} retiré(e) de la liste d'exclusion : {item_name}")
    return jsonify({"status": "ok", "ignored": ignored})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
