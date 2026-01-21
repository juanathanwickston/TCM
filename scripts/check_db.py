import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "catalog.db"
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Check ZIP file's contents_count
cursor.execute("""
    SELECT display_name, container_type, relative_path, contents_count 
    FROM resource_containers 
    WHERE display_name LIKE '%onePOS Support%'
""")

for row in cursor.fetchall():
    print(dict(row))

conn.close()
