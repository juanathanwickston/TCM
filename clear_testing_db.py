import psycopg2
import sys

DATABASE_URL = "postgresql://postgres:wYmxwGDOtpWFBpiOefSlhDvbXpMgUaGA@monorail.proxy.rlwy.net:37844/railway"

try:
    print("Connecting to Testing database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()
    
    print("Deleting all containers...")
    cursor.execute("DELETE FROM resource_containers")
    
    print("Verifying...")
    cursor.execute("SELECT COUNT(*) FROM resource_containers")
    count = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    print(f"✓ Success! Database cleared. Current count: {count}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    sys.exit(1)
