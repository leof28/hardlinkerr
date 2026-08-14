import sqlite3
import time

conn = sqlite3.connect('test.db')
c = conn.cursor()
c.execute('CREATE TABLE IF NOT EXISTS t (id INT, val TEXT)')
c.execute('DELETE FROM t')
conn.commit()

start = time.time()
for i in range(10000):
    c.execute('INSERT INTO t VALUES (?, ?)', (i, str(i)))
conn.commit()
print("Single (file DB):", time.time() - start)

c.execute('DELETE FROM t')
conn.commit()

start = time.time()
data = [(i, str(i)) for i in range(10000)]
c.executemany('INSERT INTO t VALUES (?, ?)', data)
conn.commit()
print("Batch (file DB):", time.time() - start)
