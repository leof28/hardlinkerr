#!/bin/bash

############################################################
# HARDLINK MANAGER v2.1
# Création intelligente de hardlinks pour Radarr
############################################################

# Options par défaut
dryrun=0
status_only=0
force_sync=0

# Parse arguments
while getopts "nsy" opt; do
    case $opt in
        n) dryrun=1 ;;
        s) status_only=1 ;;
        y) force_sync=1 ;;
    esac
done

# Fonction pour appliquer les permissions
apply_owner() {
    if [ $dryrun -eq 0 ]; then
        chown -R "$OWNER_USER:$OWNER_GROUP" "$1" 2>/dev/null
        chmod -R 775 "$1" 2>/dev/null
    fi
}

# Fonction pour obtenir l'inode d'un fichier
inode_of() {
    stat -c '%i' "$1" 2>/dev/null || echo ""
}

# Fonction pour vérifier si deux chemins sont sur le même device
same_device() {
    local dev1=$(stat -c '%d' "$1" 2>/dev/null)
    local dev2=$(stat -c '%d' "$2" 2>/dev/null)
    [ "$dev1" = "$dev2" ]
}

# --- CHARGEMENT DU MAPPING DES GENRES ---
declare -A GENRE_TO_LOCAL
IFS='|' read -ra ADDR <<< "$GENRE_MAPPING_STR"
for i in "${ADDR[@]}"; do
    IFS=':' read -r r_gen l_gen <<< "$i"
    if [ -n "$r_gen" ]; then
        GENRE_TO_LOCAL["$r_gen"]="$l_gen"
    fi
done

# --- RÉCUPÉRATION DES FILMS DEPUIS RADARR ---
movies_json=$(curl -s -f -m 30 -H "X-Api-Key: $API_KEY" "$RADARR_URL/api/v3/movie")
if [ $? -ne 0 ]; then
    echo "ERREUR: Impossible de se connecter à Radarr" >&2
    exit 1
fi

# Compteurs
count_total=0
count_linked=0
count_skipped=0
count_errors=0

# --- TRAITEMENT DE CHAQUE FILM ---
echo "$movies_json" | jq -c '.[] | select(.hasFile == true)' | while read -r movie; do
    title=$(echo "$movie" | jq -r '.title')
    folder_path=$(echo "$movie" | jq -r '.path')
    folder_name=$(basename "$folder_path")
    
    # Construire le chemin source
    src_path="$SOURCE_ROOT/$folder_name"
    
    # Vérifier que le dossier source existe
    if [ ! -d "$src_path" ]; then
        continue
    fi
    
    # Filtrer par film spécifique si demandé
    if [[ -n "$SPECIFIC_MOVIE" && "$src_path" != "$SPECIFIC_MOVIE" ]]; then
        continue
    fi
    
    # Vérifier qu'il y a au moins un fichier MKV
    shopt -s nullglob
    mkv_files=("$src_path"/*.mkv)
    if [ ${#mkv_files[@]} -eq 0 ]; then
        continue
    fi
    
    ((count_total++))
    
    # Récupérer tous les fichiers à lier
    all_files=("$src_path"/*.{mkv,mp4,avi,ts,mov,jpg,png,nfo,srt,sub,txt})
    
    # Récupérer les genres du film depuis Radarr
    movie_genres=$(echo "$movie" | jq -r '.genres[] | if type == "object" then .name else . end')
    
    # IMPORTANT: Construire la liste des dossiers de destination UNIQUEMENT pour les genres de CE film
    declare -A target_folders
    for genre in $movie_genres; do
        # Filtrer par genre spécifique si demandé
        if [[ -n "$SPECIFIC_GENRES" && "$genre" != "$SPECIFIC_GENRES" ]]; then
            continue
        fi
        
        # Vérifier que ce genre est mappé ET activé dans la config
        local_folder="${GENRE_TO_LOCAL[$genre]}"
        if [ -n "$local_folder" ]; then
            target_folders["$local_folder"]="$genre"
        fi
    done
    
    # Si aucun dossier de destination, passer au suivant
    if [ ${#target_folders[@]} -eq 0 ]; then
        ((count_skipped++))
        continue
    fi
    
    # Pour chaque dossier de destination
    for local_folder in "${!target_folders[@]}"; do
        genre_name="${target_folders[$local_folder]}"
        target_dir="${MEDIA_ROOT}/${local_folder}/${folder_name}"
        
        found_valid=0
        total_files=${#all_files[@]}
        
        # MODE STATUS : Compter les hardlinks RÉELS (même inode)
        if [ "$status_only" -eq 1 ]; then
            # Vérifier que le dossier de destination existe
            if [ ! -d "$target_dir" ]; then
                # Dossier n'existe pas = 0 hardlinks
                echo "HARDLINK_STATUS|$folder_name|$genre_name|$local_folder|0|$total_files"
                continue
            fi
            
            # Compter fichier par fichier
            for src_file in "${all_files[@]}"; do
                [ ! -f "$src_file" ] && continue
                
                dest_file="$target_dir/$(basename "$src_file")"
                
                # Vérifier si le fichier de destination existe
                if [ ! -e "$dest_file" ]; then
                    # Fichier n'existe pas = pas un hardlink
                    continue
                fi
                
                # Comparer les inodes (vrai test de hardlink)
                src_inode=$(inode_of "$src_file")
                dest_inode=$(inode_of "$dest_file")
                
                # Si les inodes sont identiques ET non vides, c'est un vrai hardlink
                if [ -n "$src_inode" ] && [ -n "$dest_inode" ] && [ "$src_inode" = "$dest_inode" ]; then
                    ((found_valid++))
                fi
            done
            
            # Afficher le statut
            echo "HARDLINK_STATUS|$folder_name|$genre_name|$local_folder|$found_valid|$total_files"
        else
            # MODE CRÉATION : Créer les hardlinks manquants
            need_creation=0
            
            for src_file in "${all_files[@]}"; do
                [ ! -f "$src_file" ] && continue
                
                dest_file="$target_dir/$(basename "$src_file")"
                src_inode=$(inode_of "$src_file")
                dest_inode=$(inode_of "$dest_file")
                
                # Ne créer le lien que si nécessaire
                if [ "$src_inode" != "$dest_inode" ] || [ ! -e "$dest_file" ]; then
                    ((need_creation++))
                fi
            done
            
            if [ $need_creation -gt 0 ] || [ $force_sync -eq 1 ]; then
                # Créer le dossier de destination
                if [ $dryrun -eq 0 ]; then
                    mkdir -p "$target_dir"
                    apply_owner "$target_dir"
                    apply_owner "${MEDIA_ROOT}/${local_folder}"
                fi
                
                # Créer les hardlinks
                for src_file in "${all_files[@]}"; do
                    [ ! -f "$src_file" ] && continue
                    
                    dest_file="$target_dir/$(basename "$src_file")"
                    src_inode=$(inode_of "$src_file")
                    dest_inode=$(inode_of "$dest_file")
                    
                    # Ne créer le lien que si nécessaire
                    if [ "$src_inode" != "$dest_inode" ] || [ ! -e "$dest_file" ]; then
                        # Vérifier que les deux chemins sont sur le même device
                        if ! same_device "$src_file" "$target_dir" 2>/dev/null; then
                            echo "ERREUR: $src_file et $target_dir ne sont pas sur le même système de fichiers" >&2
                            ((count_errors++))
                            continue
                        fi
                        
                        if [ $dryrun -eq 1 ]; then
                            echo "[DRYRUN] ln '$src_file' '$dest_file'"
                        else
                            # Supprimer l'ancien fichier si nécessaire
                            rm -f "$dest_file" 2>/dev/null
                            
                            # Créer le hardlink
                            if ln "$src_file" "$dest_file" 2>/dev/null; then
                                chown "$OWNER_USER:$OWNER_GROUP" "$dest_file" 2>/dev/null
                                chmod 0640 "$dest_file" 2>/dev/null
                                ((count_linked++))
                            else
                                echo "ERREUR: Impossible de créer le hardlink pour $dest_file" >&2
                                ((count_errors++))
                            fi
                        fi
                    fi
                done
            else
                ((count_skipped++))
            fi
        fi
    done
    
    # Nettoyer le tableau associatif pour le prochain film
    unset target_folders
done

# --- RÉSUMÉ ---
if [ "$status_only" -eq 0 ]; then
    echo "=== RÉSUMÉ ==="
    echo "Films traités: $count_total"
    echo "Hardlinks créés: $count_linked"
    echo "Films ignorés: $count_skipped"
    echo "Erreurs: $count_errors"
fi

exit 0