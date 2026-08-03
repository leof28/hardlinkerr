import os

config = {
    'mediaRoot': '/tmp/media',
    'sourceRoot': '/tmp/media/A trier',
}

def is_safe_path(path_to_check, config):
    if not path_to_check:
        return False
    allowed_keys = ['mediaRoot', 'sourceRoot', 'seriesSourceRoot', 'seriesCheckRoot']
    allowed_roots = [os.path.realpath(config.get(k)) for k in allowed_keys if config.get(k)]
    if not allowed_roots:
        return False

    target = os.path.realpath(path_to_check)
    for root in allowed_roots:
        try:
            if os.path.commonpath([root, target]) == root:
                # Interdire la suppression du répertoire racine lui-même
                if root != target:
                    return True
        except ValueError:
            pass
    return False

print("is_safe_path('/tmp/media/A trier/movie.mkv', config)", is_safe_path('/tmp/media/A trier/movie.mkv', config))
