## 2024-05-18 - Batching Database Writes inside Loops
**Learning:** In the `bridge.py` sync logic, using individual `cursor.execute('DELETE ...')` within a Python `for` loop creates a significant N+1 query problem, causing measurable overhead from query parsing and excessive disk fsyncs for each individual row deletion.
**Action:** Always replace O(N) database operations inside loops with O(1) batched `cursor.executemany()` calls in SQLite to bypass the overhead.
