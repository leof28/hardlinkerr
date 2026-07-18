## 2024-07-16 - Path Traversal Vulnerability in Deletion Endpoints
**Vulnerability:** Several API endpoints (like `/api/delete-file`, `/api/delete-series`, etc.) accepted absolute or relative paths directly from the request JSON and passed them directly to `os.remove` or `shutil.rmtree` without any validation. This allowed path traversal (e.g. using `../../`) or specifying arbitrary absolute paths (e.g. `/etc/passwd`) leading to arbitrary file deletion on the host.
**Learning:** The endpoints trusted user input representing file paths blindly. This pattern indicates a lack of centralized path validation before file system operations.
**Prevention:** Implement a robust `is_safe_path` utility that relies on `os.path.abspath` and `os.path.commonpath` to ensure that any target path strictly falls within one of the application's configured and allowed root directories. Always invoke this validation before passing any path to `os.remove` or `shutil.rmtree`.

## 2026-07-18 - [Path Traversal in bridge.py API endpoints]
 **Vulnerability:** Path Traversal in `/api/delete-movie` inside `bridge.py` allowing deletion of unintended files by crafting payloads containing `..`
 **Learning:** When user input constructs a file path for sensitive operations like `shutil.rmtree`, it needs validation against a known base path to prevent traversal.
 **Prevention:** Implement and enforce a path sanitization function like `is_safe_path` before all file I/O or delete operations constructed from user inputs.
