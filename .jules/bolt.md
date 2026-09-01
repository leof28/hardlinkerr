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
## 2026-07-26 - Pre-computing and Compiling Regex Outside of Loops
**Learning:** In the `sync_database` and `get_jellystat_history` functions within `bridge.py`, `import re` and regex evaluation `re.sub(r'\s*\(\d{4}\)$', ...)` were repeatedly executed inside O(N) loops. This caused redundant `sys.modules` dictionary lookups and prevented efficient re-use of pre-compiled regex pattern objects.
**Action:** When performing regex substitutions or match operations in iterations, always hoist the module import and the `re.compile()` operation outside the loop to eliminate redundant internal caching overhead.
## 2026-07-27 - Bash O(N) Process Forks Elimination
**Learning:** Inside `while` loops processing many items, spawning multiple subshells and external processes (like `jq`, `basename`, `tr`) per iteration creates an O(N) process fork bottleneck, massively slowing down bash script execution.
**Action:** Pre-process the JSON data into a tab-separated value (TSV) stream with a single `jq` execution, and read the fields directly using `while IFS=$'\t' read -r ...`. Replace external commands with native bash parameter expansion (e.g., `${var##*/}` instead of `basename`).
## 2024-11-20 - [Frontend Rendering Optimization]
**Learning:** Extracting large list items (like MovieCards in LibraryTab) into standalone components wrapped in `React.memo` (and ensuring props like functions are stable via `useCallback`) is critical in large React grids. Without it, toggling state on a single item causes an O(N) re-render of every DOM node in the list, creating noticeable UI lag for thousands of items.
**Action:** Always wrap list item components in `React.memo` when rendering large lists, and hoist loop-invariant operations (like `.toLowerCase()` on search terms) outside the `.map()` or `.filter()` loops to avoid redundant O(N) evaluations.
## 2026-08-15 - SQLite N+1 Execution Inside Loops Optimization
**Learning:** The `sync_database` function contained a classic performance bottleneck where individual `cursor.execute()` calls for `INSERT` and `DELETE` operations were being invoked inside an O(N) loop iterating over all movies. This caused significant execution overhead due to repeated query parsing and excessive disk fsync operations.
**Action:** Replaced the individual loop executions by accumulating the parameterized tuples into lists and executing them outside the loop using `cursor.executemany()`. This batching approach dramatically reduces SQLite disk I/O and speeds up database synchronization for large libraries.

## 2026-09-01 - Bash Hardlink Checking Process Forks
**Learning:** Checking for hardlinks by calling `stat -c '%i'` inside subshells (e.g., `src_inode=$(inode_of "$src_file")`) in a loop over files creates an extreme O(N) process fork bottleneck (4000ms+ for 500 files).
**Action:** Always use the native bash builtin `[ "$file1" -ef "$file2" ]` to test if two files share the same device and inode. It eliminates the need for external `stat` calls and subshells, running ~400x faster.
