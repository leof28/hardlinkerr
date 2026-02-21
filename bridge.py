from flask import Flask, jsonify, request, send_from_directory
import os
import subprocess
import json
import requests
from datetime import datetime, timedelta
import threading
import time
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# --- CONFIGURATION ---
CONFIG_DIR = "/app/config"
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
CACHE_PATH = os.path.join(CONFIG_DIR, "scan_cache.json")
SCRIPT_PATH = "./hardlink_manager.sh"
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# --- SCHEDULER ---
scheduler = BackgroundScheduler()
scheduler.start()

def load_config():
    defaults = {
        "radarrUrl": "http://192.168.1.100:7878",
        "apiKey": "b51d90f91eca475cb5cca7d84cc33a28",
        "sonarrUrl": "",
        "sonarrApiKey": "",
        "sourceRoot": "/media/movies/A trier",
        "mediaRoot": "/media/movies",
        "seriesSourceRoot": "/media/series/Source",
        "seriesCheckRoot": "/media/series/Check",
        "ownerUser": "media",
        "ownerGroup": "3001",
        "genreMapping": {},
        "autoSync": {
            "enabled": False,
            "cronSchedule": "0 */6 * * *",
            "lastRun": None,
            "lastFullScan": None
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
        }
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return {**defaults, **json.load(f)}
        except:
            return defaults
    return defaults

def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)
    setup_cron_job(config)

def load_cache():
    """Charge le cache des scans précédents"""
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    """Sauvegarde le cache"""
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=4)

def get_recent_movies(config):
    """Récupère uniquement les films ajoutés récemment"""
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
            
            # Vérifier la date de modification du dossier
            mtime = datetime.fromtimestamp(os.path.getmtime(folder_path))
            
            if mtime > cutoff_time:
                # Vérifier qu'il contient des MKV
                has_mkv = any(f.lower().endswith('.mkv') for f in os.listdir(folder_path))
                if has_mkv:
                    recent_movies.append({
                        'folder_name': folder_name,
                        'path': folder_path,
                        'mtime': mtime.isoformat()
                    })
    except Exception as e:
        print(f"Erreur get_recent_movies: {str(e)}")
    
    return recent_movies

def should_do_full_scan(config):
    """Détermine si un scan complet est nécessaire"""
    optimization = config.get('scanOptimization', {})
    if not optimization.get('enabled', True):
        return True
    
    last_full_scan = config.get('autoSync', {}).get('lastFullScan')
    if not last_full_scan:
        return True
    
    full_scan_interval = optimization.get('fullScanInterval', 24)
    last_scan_time = datetime.fromisoformat(last_full_scan)
    hours_since = (datetime.now() - last_scan_time).total_seconds() / 3600
    
    return hours_since >= full_scan_interval

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

def execute_hardlinks(config, movie_path='', genres=''):
    """Fonction helper pour exécuter la création de hardlinks"""
    env = get_env(config, movie_path, genres)
    
    try:
        process = subprocess.run(
            [SCRIPT_PATH, "-y"],
            capture_output=True,
            text=True,
            env=env,
            timeout=600
        )
        return {
            "status": "ok",
            "output": process.stdout,
            "errors": process.stderr
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

def get_hardlink_status(config):
    """Fonction helper pour récupérer l'état des hardlinks - SANS filtre"""
    env = get_env(config)
    
    try:
        # Appel au script bash pour vérifier l'état (-s = status only)
        # IMPORTANT : Ne pas filtrer, laisser le script bash tout traiter
        process = subprocess.run(
            [SCRIPT_PATH, "-s"],
            capture_output=True,
            text=True,
            env=env,
            timeout=300
        )
        
        # Parse la sortie du script
        hardlink_status = {}
        for line in process.stdout.split('\n'):
            if line.startswith("HARDLINK_STATUS"):
                # Format: HARDLINK_STATUS|folder_name|genre|local_folder|found|total
                parts = line.split('|')
                if len(parts) >= 6:
                    folder_name = parts[1]
                    genre = parts[2]
                    local_folder = parts[3]
                    found = int(parts[4])
                    total = int(parts[5])
                    
                    if folder_name not in hardlink_status:
                        hardlink_status[folder_name] = []
                    
                    hardlink_status[folder_name].append({
                        "genre": genre,
                        "folder": local_folder,
                        "found": found,
                        "total": total,
                        "exists": found >= total and total > 0
                    })
        
        return hardlink_status
    except Exception as e:
        print(f"Erreur get_hardlink_status: {str(e)}")
        return {}

def cron_job_handler():
    """Fonction exécutée par le cron - optimisée"""
    print(f"[{datetime.now()}] Cron job: Démarrage...")
    
    config = load_config()
    
    # Déterminer le type de scan
    do_full_scan = should_do_full_scan(config)
    
    if do_full_scan:
        print(f"[{datetime.now()}] Scan complet de tous les films")
        result = execute_hardlinks(config)
        config['autoSync']['lastFullScan'] = datetime.now().isoformat()
    else:
        print(f"[{datetime.now()}] Scan optimisé (films récents uniquement)")
        recent_movies = get_recent_movies(config)
        
        if recent_movies:
            print(f"[{datetime.now()}] {len(recent_movies)} films récents détectés")
            for movie in recent_movies:
                execute_hardlinks(config, movie['path'])
        else:
            print(f"[{datetime.now()}] Aucun film récent")
    
    config['autoSync']['lastRun'] = datetime.now().isoformat()
    save_config(config)
    
    print(f"[{datetime.now()}] Cron job terminé")

def setup_cron_job(config):
    """Configure ou met à jour le cron job"""
    scheduler.remove_all_jobs()
    
    if config.get('autoSync', {}).get('enabled', False):
        cron_schedule = config['autoSync'].get('cronSchedule', '0 */6 * * *')
        parts = cron_schedule.split()
        if len(parts) == 5:
            try:
                scheduler.add_job(
                    cron_job_handler,
                    'cron',
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                    id='auto_hardlink'
                )
                print(f"Cron job configuré: {cron_schedule}")
            except Exception as e:
                print(f"Erreur configuration cron: {str(e)}")

# Initialiser le cron au démarrage
initial_config = load_config()
setup_cron_job(initial_config)

def detect_series_issues(config):
    """Détecte les séries orphelines dans Check via Sonarr API (path sur disque + file de téléchargement)"""
    issues = []

    if not config.get('seriesCheck', {}).get('enabled', False):
        return issues

    series_source = config.get('seriesSourceRoot', '')
    series_check = config.get('seriesCheckRoot', '')
    sonarr_url = config.get('sonarrUrl', '')
    sonarr_api_key = config.get('sonarrApiKey', '')

    if not series_check or not os.path.isdir(series_check):
        return issues

    try:
        # --- 1. Récupérer les séries depuis Sonarr indexées par nom de dossier ---
        # { folder_name: { 'id': int, 'path': str, 'title': str } }
        sonarr_by_folder = {}
        # ensemble des IDs de séries en cours de téléchargement
        active_series_ids = set()
        sonarr_available = bool(sonarr_url and sonarr_api_key)

        if sonarr_available:
            # Séries
            try:
                print(f"[SERIES] Connexion à Sonarr : {sonarr_url}")
                resp = requests.get(
                    f"{sonarr_url}/api/v3/series",
                    headers={"X-Api-Key": sonarr_api_key},
                    timeout=30
                )
                resp.raise_for_status()
                for series in resp.json():
                    s_path = series.get('path', '').rstrip('/')
                    s_id = series.get('id')
                    s_title = series.get('title', '')
                    if s_path:
                        folder = os.path.basename(s_path)
                        sonarr_by_folder[folder] = {
                            'id': s_id,
                            'path': s_path,
                            'title': s_title
                        }
                print(f"[SERIES] {len(sonarr_by_folder)} séries récupérées depuis Sonarr")
            except Exception as e:
                print(f"[SERIES] Erreur API Sonarr (series): {str(e)}")

            # File de téléchargement (activeDL)
            try:
                q_resp = requests.get(
                    f"{sonarr_url}/api/v3/queue",
                    headers={"X-Api-Key": sonarr_api_key},
                    params={"pageSize": 1000},
                    timeout=30
                )
                q_resp.raise_for_status()
                q_data = q_resp.json()
                records = q_data.get('records', q_data) if isinstance(q_data, dict) else q_data
                for item in records:
                    sid = item.get('seriesId') or (item.get('series') or {}).get('id')
                    if sid:
                        active_series_ids.add(sid)
                print(f"[SERIES] {len(active_series_ids)} séries en téléchargement actif")
            except Exception as e:
                print(f"[SERIES] Erreur API Sonarr (queue): {str(e)}")

        # --- 2. Parcourir le dossier Check ---
        for series_folder in os.listdir(series_check):
            check_path = os.path.join(series_check, series_folder)
            if not os.path.isdir(check_path):
                continue

            # Trouver la correspondance dans Sonarr (par nom de dossier exact puis normalisé)
            sonarr_info = sonarr_by_folder.get(series_folder)
            if sonarr_info is None:
                normalized_check = series_folder.replace('.', ' ').replace('_', ' ').lower().strip()
                for known_folder, info in sonarr_by_folder.items():
                    normalized_known = known_folder.replace('.', ' ').replace('_', ' ').lower().strip()
                    if normalized_check == normalized_known:
                        sonarr_info = info
                        break

            is_orphan = False
            reason = ''
            sonarr_path = None
            in_active_dl = False

            if sonarr_info:
                sonarr_path = sonarr_info['path']
                series_id = sonarr_info['id']
                in_active_dl = series_id in active_series_ids

                if os.path.isdir(sonarr_path):
                    # Le chemin Sonarr existe sur le disque → série toujours active
                    print(f"[SERIES] {series_folder} → chemin OK: {sonarr_path}")
                    continue
                elif in_active_dl:
                    # Chemin absent mais téléchargement en cours
                    print(f"[SERIES] {series_folder} → téléchargement actif (ID={series_id}), ignorée")
                    continue
                else:
                    # Chemin introuvable sur disque et pas en DL → orpheline
                    is_orphan = True
                    reason = f'Chemin Sonarr introuvable sur le disque : {sonarr_path}'
            else:
                # Série inconnue de Sonarr → vérifier le dossier Source comme fallback
                if series_source and os.path.isdir(os.path.join(series_source, series_folder)):
                    print(f"[SERIES] {series_folder} → trouvée dans Source (fallback)")
                    continue
                is_orphan = True
                reason = 'Série absente de Sonarr' if sonarr_available else f'Série absente de "{os.path.basename(series_source)}"'

            if is_orphan:
                file_count = 0
                total_size = 0
                for root, dirs, files in os.walk(check_path):
                    for file in files:
                        if file.lower().endswith(('.mkv', '.mp4', '.avi')):
                            file_count += 1
                            fp = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(fp)
                            except:
                                pass

                issues.append({
                    'series': series_folder,
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
        print(f"Erreur detect_series_issues: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def detect_duplicates(config):
    """Détecte les problèmes : doublons MKV, orphelins, genres incorrects"""
    duplicates = []
    
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
                
                genres = []
                for g in movie.get('genres', []):
                    genre_name = g['name'] if isinstance(g, dict) else g
                    genres.append(genre_name)
                
                movie_info[folder_name] = {
                    'official': official_name,
                    'genres': genres,
                    'title': movie['title']
                }
        
        genre_to_folder = {}
        for genre, settings in config.get('genreMapping', {}).items():
            if settings.get('enabled', False):
                genre_to_folder[genre] = settings['folder']
        
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
                
                source_path = os.path.join(source_root, movie_folder)
                source_exists = os.path.isdir(source_path)
                
                info = movie_info.get(movie_folder, {})
                official = info.get('official', '')
                movie_genres = info.get('genres', [])
                movie_title = info.get('title', movie_folder)
                
                if not source_exists:
                    mkv_files = [f for f in os.listdir(movie_path) if f.lower().endswith('.mkv')]
                    for mkv in mkv_files:
                        duplicates.append({
                            'movie': movie_folder,
                            'title': movie_title,
                            'genre': genre_folder,
                            'file': mkv,
                            'path': os.path.join(movie_path, mkv),
                            'isOfficial': True,
                            'inSource': False,
                            'wrongGenre': False,
                            'type': 'orphan',
                            'reason': 'Dossier source supprimé de "A trier"',
                            'size': os.path.getsize(os.path.join(movie_path, mkv)) if os.path.exists(os.path.join(movie_path, mkv)) else 0
                        })
                    continue
                
                allowed_folders = set()
                for genre in movie_genres:
                    if genre in genre_to_folder:
                        allowed_folders.add(genre_to_folder[genre])
                
                is_wrong_genre = len(allowed_folders) > 0 and genre_folder not in allowed_folders
                
                mkv_files = [f for f in os.listdir(movie_path) if f.lower().endswith('.mkv')]
                
                if len(mkv_files) > 1:
                    for mkv in mkv_files:
                        is_official = (mkv == official)
                        full_path = os.path.join(movie_path, mkv)
                        source_file_path = os.path.join(source_path, mkv)
                        in_source = os.path.exists(source_file_path)
                        
                        if not is_official:
                            duplicates.append({
                                'movie': movie_folder,
                                'title': movie_title,
                                'genre': genre_folder,
                                'file': mkv,
                                'path': full_path,
                                'isOfficial': False,
                                'inSource': in_source,
                                'wrongGenre': is_wrong_genre,
                                'type': 'duplicate',
                                'reason': 'Ancienne version (pas le fichier officiel Radarr)',
                                'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                            })
                elif len(mkv_files) == 1:
                    if is_wrong_genre:
                        mkv = mkv_files[0]
                        full_path = os.path.join(movie_path, mkv)
                        correct_folders = ', '.join(sorted(allowed_folders))
                        
                        duplicates.append({
                            'movie': movie_folder,
                            'title': movie_title,
                            'genre': genre_folder,
                            'file': mkv,
                            'path': full_path,
                            'isOfficial': (mkv == official),
                            'inSource': True,
                            'wrongGenre': True,
                            'type': 'wrong_genre',
                            'reason': f'Mauvais genre ! Devrait être dans : {correct_folders}',
                            'correctFolders': list(allowed_folders),
                            'size': os.path.getsize(full_path) if os.path.exists(full_path) else 0
                        })
        
        return duplicates
    except Exception as e:
        print(f"Erreur detect_duplicates: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

# --- ROUTES ---

@app.route('/')
def index():
    return send_from_directory(TEMPLATE_DIR, 'index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        data = request.json
        save_config(data)
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
        movies = response.json()
        
        all_genres = set()
        for movie in movies:
            for genre in movie.get('genres', []):
                genre_name = genre['name'] if isinstance(genre, dict) else genre
                all_genres.add(genre_name)
        
        current_mapping = config.get('genreMapping', {})
        
        genres_list = []
        for genre in sorted(all_genres):
            if genre in current_mapping:
                genres_list.append({
                    'name': genre,
                    'enabled': current_mapping[genre].get('enabled', False),
                    'folder': current_mapping[genre].get('folder', genre)
                })
            else:
                genres_list.append({
                    'name': genre,
                    'enabled': False,
                    'folder': genre
                })
        
        return jsonify(genres_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/scan', methods=['POST'])
def scan():
    """Scan complet - toujours fiable"""
    config = load_config()
    
    try:
        hardlink_status = get_hardlink_status(config)
        return jsonify({"status": "success", "hardlinks": hardlink_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Récupère la liste des films avec scan complet"""
    config = load_config()
    
    try:
        # Récupérer les films depuis Radarr
        response = requests.get(
            f"{config['radarrUrl']}/api/v3/movie",
            headers={"X-Api-Key": config['apiKey']},
            timeout=30
        )
        response.raise_for_status()
        all_movies = response.json()
        
        # Scanner TOUS les films - le script bash le fait lui-même
        print(f"[SCAN] Début du scan de {len(all_movies)} films...")
        hardlink_status = get_hardlink_status(config)
        print(f"[SCAN] Statuts récupérés pour {len(hardlink_status)} films")
        
        # Construire la réponse
        result = []
        source_root = config['sourceRoot']
        
        for movie in all_movies:
            if not movie.get('hasFile'):
                continue
                
            folder_name = os.path.basename(movie['path'])
            source_path = os.path.join(source_root, folder_name)
            
            if not os.path.isdir(source_path):
                continue
            
            try:
                has_mkv = any(f.lower().endswith('.mkv') for f in os.listdir(source_path))
            except:
                continue
                
            if not has_mkv:
                continue
            
            try:
                added_time = os.path.getmtime(source_path)
            except:
                added_time = 0
            
            genres = []
            for g in movie.get('genres', []):
                genre_name = g['name'] if isinstance(g, dict) else g
                genres.append(genre_name)
            
            poster = None
            for img in movie.get('images', []):
                if img.get('coverType') == 'poster':
                    poster = img.get('remoteUrl')
                    break
            
            # Utiliser les données du scan
            hardlinks = hardlink_status.get(folder_name, [])
            
            result.append({
                "title": movie['title'],
                "path": source_path,
                "poster": poster,
                "genres": genres,
                "hardlinks": hardlinks,
                "addedTime": added_time,
                "tmdbId": movie.get('tmdbId')
            })
        
        result.sort(key=lambda x: x['addedTime'], reverse=True)
        
        print(f"[SCAN] Retour de {len(result)} films")
        return jsonify(result)
    except Exception as e:
        print(f"[ERREUR] {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/series-issues', methods=['GET'])
def get_series_issues():
    """Récupère les problèmes de séries"""
    config = load_config()
    
    try:
        issues = detect_series_issues(config)
        return jsonify(issues)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-series', methods=['POST'])
def delete_series():
    """Supprime un dossier de série complet"""
    data = request.json or {}
    series_path = data.get('path', '')
    
    try:
        if series_path and os.path.isdir(series_path):
            import shutil
            shutil.rmtree(series_path)
            return jsonify({"status": "ok", "message": f"Série supprimée: {series_path}"})
        else:
            return jsonify({"error": "Dossier non trouvé"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-all-series', methods=['POST'])
def delete_all_series():
    """Supprime toutes les séries orphelines"""
    config = load_config()
    
    try:
        issues = detect_series_issues(config)
        results = {'success': [], 'errors': []}
        
        import shutil
        for issue in issues:
            try:
                series_path = issue['path']
                if os.path.isdir(series_path):
                    shutil.rmtree(series_path)
                    results['success'].append(issue['series'])
                else:
                    results['errors'].append(f"Non trouvé: {issue['series']}")
            except Exception as e:
                results['errors'].append(f"Erreur {issue['series']}: {str(e)}")
        
        return jsonify({
            "status": "ok",
            "deleted": len(results['success']),
            "errors": len(results['errors']),
            "details": results
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/duplicates', methods=['GET'])
def get_duplicates():
    config = load_config()
    
    try:
        duplicates = detect_duplicates(config)
        return jsonify(duplicates)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-file', methods=['POST'])
def delete_file():
    data = request.json or {}
    file_path = data.get('path', '')
    
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            parent_dir = os.path.dirname(file_path)
            if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
            return jsonify({"status": "ok"})
        else:
            return jsonify({"error": "Fichier non trouvé"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/delete-duplicates', methods=['POST'])
def delete_duplicates():
    data = request.json or {}
    file_paths = data.get('paths', [])
    
    if not file_paths:
        return jsonify({"error": "Aucun fichier"}), 400
    
    results = {'success': [], 'errors': []}
    
    for file_path in file_paths:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                results['success'].append(file_path)
                parent_dir = os.path.dirname(file_path)
                if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
            else:
                results['errors'].append(f"Non trouvé: {file_path}")
        except Exception as e:
            results['errors'].append(f"Erreur {file_path}: {str(e)}")
    
    return jsonify({
        "status": "ok",
        "deleted": len(results['success']),
        "errors": len(results['errors']),
        "details": results
    })

@app.route('/api/run', methods=['POST'])
def run_action():
    data = request.json or {}
    config = load_config()
    
    movie_paths = data.get('movie_paths', [])
    
    if not movie_paths:
        movie_path = data.get('movie_path', '')
        genres = data.get('genres', '')
        return jsonify(execute_hardlinks(config, movie_path, genres))
    else:
        results = []
        for movie_path in movie_paths:
            result = execute_hardlinks(config, movie_path, '')
            results.append({
                "movie": os.path.basename(movie_path),
                **result
            })
        return jsonify({"status": "ok", "results": results})

@app.route('/api/run-all', methods=['POST'])
def run_all():
    config = load_config()
    return jsonify(execute_hardlinks(config))

@app.route('/api/run-by-genre', methods=['POST'])
def run_by_genre():
    data = request.json or {}
    genres = data.get('genres', [])
    
    if not genres:
        return jsonify({"error": "Aucun genre"}), 400
    
    config = load_config()
    results = []
    
    for genre in genres:
        result = execute_hardlinks(config, '', genre)
        results.append({"genre": genre, **result})
    
    return jsonify({"status": "ok", "results": results})

@app.route('/api/webhook/jellyfin', methods=['POST'])
def jellyfin_webhook():
    config = load_config()
    
    if not config.get('webhookEnabled', False):
        return jsonify({"error": "Webhook désactivé"}), 403
    
    webhook_secret = config.get('webhookSecret', '')
    if webhook_secret:
        provided_secret = request.headers.get('X-Webhook-Secret', '')
        if provided_secret != webhook_secret:
            return jsonify({"error": "Secret invalide"}), 403
    
    try:
        data = request.json
        notification_type = data.get('NotificationType', '')
        
        if notification_type in ['ItemAdded', 'MovieAdded']:
            item = data.get('Item', {})
            item_name = item.get('Name', '')
            item_path = item.get('Path', '')
            
            print(f"Webhook Jellyfin: {item_name}")
            time.sleep(5)
            
            if item_path:
                folder_name = os.path.basename(os.path.dirname(item_path))
                movie_path = os.path.join(config['sourceRoot'], folder_name)
            else:
                movie_path = ''
            
            result = execute_hardlinks(config, movie_path)
            return jsonify({"status": "ok", "message": f"Hardlinks créés pour {item_name}", "result": result})
        else:
            return jsonify({"status": "ignored", "type": notification_type})
            
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
            movie_title = movie.get('title', '')
            movie_folder = movie.get('folderPath', '')
            
            print(f"Webhook Radarr: {event_type} - {movie_title}")
            time.sleep(5)
            
            folder_name = os.path.basename(movie_folder)
            movie_path = os.path.join(config['sourceRoot'], folder_name)
            
            result = execute_hardlinks(config, movie_path)
            return jsonify({"status": "ok", "message": f"Hardlinks créés pour {movie_title}", "result": result})
        else:
            return jsonify({"status": "ignored", "type": event_type})
            
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)