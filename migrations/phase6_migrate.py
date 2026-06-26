"""One-shot DB migration: add watermark columns to vertical_renders,
   add vertical_presets table.

This is the same pattern we used in Phase 2 to add the clips table.
Safe to run multiple times (uses ALTER TABLE ... add column only if missing).
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "app.db"

if not DB_PATH.exists():
    print(f"DB not found: {DB_PATH}")
    sys.exit(1)

con = sqlite3.connect(str(DB_PATH))
cur = con.cursor()

# 1) Add watermark columns to vertical_renders (idempotent)
existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(vertical_renders)").fetchall()}
print(f"Current columns in vertical_renders: {len(existing_cols)}")
for col_name, col_type in [
    ("watermark_path", "VARCHAR(500)"),
    ("watermark_position", "VARCHAR(20)"),
    ("watermark_opacity", "REAL"),
]:
    if col_name not in existing_cols:
        cur.execute(f"ALTER TABLE vertical_renders ADD COLUMN {col_name} {col_type}")
        print(f"  + Added column: vertical_renders.{col_name}")
    else:
        print(f"  · Column already exists: vertical_renders.{col_name}")

# 2) Create vertical_presets table (idempotent via IF NOT EXISTS)
cur.execute("""
CREATE TABLE IF NOT EXISTS vertical_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    layout VARCHAR(20) DEFAULT 'split',
    bg_style VARCHAR(20) DEFAULT 'blur',
    bg_color VARCHAR(9) DEFAULT '#1a1a2e',
    bg_color2 VARCHAR(9) DEFAULT '#16213e',
    sub_style VARCHAR(20) DEFAULT 'karaoke',
    sub_color VARCHAR(9) DEFAULT '#FFFFFF',
    sub_highlight VARCHAR(9) DEFAULT '#FFD700',
    sub_outline VARCHAR(9) DEFAULT '#000000',
    sub_size INTEGER DEFAULT 64,
    sub_position INTEGER DEFAULT 200,
    add_title INTEGER DEFAULT 1,
    title_color VARCHAR(9) DEFAULT '#FFFFFF',
    title_size INTEGER DEFAULT 72,
    watermark_path VARCHAR(500),
    watermark_position VARCHAR(20) DEFAULT 'bottom_right',
    watermark_opacity REAL DEFAULT 0.8,
    created_at DATETIME,
    updated_at DATETIME
)
""")
cur.execute("CREATE INDEX IF NOT EXISTS ix_vertical_presets_name ON vertical_presets(name)")
print("  + Ensured table: vertical_presets")

# 3) Create index on vertical_presets
con.commit()

# 4) Verify
print("\n=== Verification ===")
n_renders = cur.execute("SELECT COUNT(*) FROM vertical_renders").fetchone()[0]
n_presets = cur.execute("SELECT COUNT(*) FROM vertical_presets").fetchone()[0]
new_cols = {row[1] for row in cur.execute("PRAGMA table_info(vertical_renders)").fetchall()}
print(f"vertical_renders: {n_renders} rows, columns: {len(new_cols)}")
print(f"  watermark columns: {[c for c in new_cols if 'watermark' in c]}")
print(f"vertical_presets: {n_presets} rows")
con.close()
print("\nMigration done.")
