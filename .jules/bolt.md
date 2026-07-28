## 2026-07-16 - SQLite N+1 Queries in Hardlink Manager
**Learning:** The `get_status` and `get_library_stats` endpoints in this Flask app were executing an N+1 query pattern, looping over every movie and making a subsequent query for its hardlinks. This caused a severe bottleneck for large media libraries (e.g. 5,000+ movies = 5,001+ queries).
**Action:** Replaced the per-movie hardlink queries with a single batch `SELECT * FROM hardlinks`, mapped the results into an in-memory dictionary grouped by `movie_folder`, and used O(1) dictionary lookups instead. This reduced execution time by over 50%. Next time, proactively search for nested `cursor.execute` calls inside loops.
## 2026-07-18 - File-Based JSON Caching Optimization
**Learning:** In multi-worker or looped environments, repeatedly reading and parsing JSON cache files from disk (e.g. `load_platforms_cache()` called within an O(N) loop over all movies) causes massive synchronous I/O and CPU bottlenecks.
**Action:** Implemented a module-level in-memory dictionary cache combined with an `os.path.getmtime(path)` check to validate cache coherence before falling back to disk reads. This eliminated O(N) redundant disk I/O while preserving synchronization across multiple processes.
## 2026-07-19 - Reduce External API Calls by Preferring Local SQLite Cache
**Learning:** For endpoints like `/api/genres`, `/api/studios`, and `/api/platforms` that previously fetched metadata entirely via external Radarr API requests, it is extremely inefficient when the local SQLite database (`movies` table) already contains synchronized JSON metadata. Blocking external API calls within these highly queried routes creates unnecessary latency.
**Action:** Before making external API requests, implement a step to query the local SQLite database (`SELECT genres FROM movies`, etc.) to parse and extract the required unique attributes. Preserve the external API call only as a fallback if the local database returns empty results. This significantly reduces response times and avoids unnecessary network overhead.
## 2026-07-20 - File-Based JSON Caching Optimization for Configuration
**Learning:** `load_config` was being called frequently across multiple endpoints (e.g. `bridge.py` has over 25 usages). Reading from disk (`config.json`) synchronously on every function call was causing unnecessary I/O overhead.
**Action:** Implemented the module-level in-memory cache using `os.path.getmtime(CONFIG_PATH)` in `load_config()`. Used `copy.deepcopy()` to avoid unintended mutability issues since configurations are typically passed around as mutable dictionaries.
## 2025-02-28 - Avoid O(N²) String Manipulation in Loop Iterations
**Learning:** In loops containing many iterations (like processing `os.listdir`), repeatedly iterating over dictionary items (`.items()`) to perform lowercasing, stripping, and character replacement causes an O(N²) performance bottleneck.
**Action:** When normalizing keys for matching against lists of items, pre-compute a dictionary using normalized keys outside of the main loop to enable fast O(1) hash map lookups.
## 2026-07-26 - Pre-computing Normalized Dictionaries to Avoid O(N²) String Manipulation
**Learning:** Replaced O(N²) nested loops containing string normalizations with a pre-computed normalized dictionary for O(1) hash map lookups.
**Action:** Identify and replace repeated string normalizations within loops by pre-computing a normalized mapping dictionary beforehand.

## 2024-05-24 - [Avoid O(N) process forks in Bash Loops]
**Learning:** In bash scripts (like `hardlink_manager.sh`), using subshells (e.g., `$(jq ...)`, `$(basename ...)`) inside a `while` loop that iterates over many items causes an O(N) performance bottleneck due to excessive process forks.
**Action:** Pre-process the data into a TSV stream using a single `jq` pass, and parse it using `while IFS=$'\t' read -r ...` along with native bash parameter expansion to eliminate the need for subshells inside the loop entirely.
