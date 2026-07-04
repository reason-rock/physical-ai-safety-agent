"""Quick DB summary."""
import os
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "demo_data" / "training_history.db"
conn = sqlite3.connect(str(DB))

print("=== DB Summary ===")
print("Runs:", conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0])
print("Scalars:", format(conn.execute("SELECT COUNT(*) FROM scalars").fetchone()[0], ","))
print()

print("=== By server ===")
for row in conn.execute("SELECT server, COUNT(*), SUM(num_events), MAX(max_iteration) FROM runs GROUP BY server"):
    print("  {}: {} runs, {:,} events, max iter {}".format(row[0], row[1], row[2] or 0, row[3]))
print()

print("=== By task ===")
for row in conn.execute("SELECT task, COUNT(*) FROM runs GROUP BY task"):
    print("  {}: {} runs".format(row[0], row[1]))
print()

print("=== Top 10 runs by iteration ===")
for row in conn.execute("SELECT server, run_dir, max_iteration, final_reward, num_checkpoints FROM runs ORDER BY max_iteration DESC LIMIT 10"):
    print("  {:5s} {}  iter={:>6}  reward={:>10.1f}  ckpts={}".format(row[0], row[1], row[2], row[3], row[4]))
print()

print("=== Date range ===")
for row in conn.execute("SELECT MIN(run_dir), MAX(run_dir) FROM runs WHERE run_dir LIKE '2026%'"):
    print("  {} to {}".format(row[0], row[1]))
print()

size_mb = os.path.getsize(str(DB)) / 1024 / 1024
print("DB size: {:.1f} MB".format(size_mb))
conn.close()
