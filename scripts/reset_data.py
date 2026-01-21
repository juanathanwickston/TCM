"""
Reset script: Check schema, fix missing columns, reset scrub statuses.
Run this once to prepare data for demo.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "catalog.db"

def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Check schema
    cursor.execute("PRAGMA table_info(resource_containers)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {columns}")
    
    # 2. Add scrub_reasons column if missing
    if 'scrub_reasons' not in columns:
        print("Adding missing 'scrub_reasons' column...")
        cursor.execute("ALTER TABLE resource_containers ADD COLUMN scrub_reasons TEXT")
        conn.commit()
        print("Added 'scrub_reasons' column")
    else:
        print("'scrub_reasons' column exists")
    
    # 3. Reset all scrub statuses to 'not_reviewed'
    cursor.execute("""
        UPDATE resource_containers 
        SET scrub_status = 'not_reviewed',
            scrub_notes = NULL,
            scrub_owner = NULL,
            scrub_reasons = NULL,
            scrub_updated = NULL
        WHERE is_archived = 0
    """)
    rows_updated = cursor.rowcount
    conn.commit()
    print(f"Reset {rows_updated} containers to 'not_reviewed'")
    
    # 4. Verify counts
    cursor.execute("SELECT COUNT(*) as total FROM resource_containers WHERE is_archived = 0 AND is_placeholder = 0")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) as unrev FROM resource_containers WHERE is_archived = 0 AND is_placeholder = 0 AND scrub_status = 'not_reviewed'")
    unreviewed = cursor.fetchone()[0]
    
    print(f"\nVerification:")
    print(f"  Total active containers: {total}")
    print(f"  Unreviewed: {unreviewed}")
    print(f"  All reset: {total == unreviewed}")
    
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    main()
