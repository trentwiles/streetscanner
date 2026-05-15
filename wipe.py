#!/usr/bin/env python3
"""
wipe.py — delete all rows from every table. Schema is preserved.
Gives a 5-second window to abort with Ctrl-C.
"""
import time
import db

TABLES = ["trips", "magic_links", "queue", "translations", "cities"]

print("WARNING: this will delete all rows from every table.")
print("Press Ctrl-C within 5 seconds to abort.\n")

for i in range(5, 0, -1):
    print(f"  wiping in {i}...", flush=True)
    time.sleep(1)

print()

with db.get_conn() as conn:
    for table in TABLES:
        cur = conn.execute(f"DELETE FROM {table}")
        print(f"  {table}: {cur.rowcount} row(s) deleted")

print("\nDone.")
