import sqlite3

conn = sqlite3.connect('inventory.db')
c = conn.cursor()

# Check before
c.execute("SELECT COUNT(*) FROM tools WHERE room_title = 'Unknown Location' OR room_title IS NULL OR room_title = ''")
before_count = c.fetchone()[0]
print(f"Before: {before_count} tools in Unknown Location")

# Update to Workshop 1
c.execute("UPDATE tools SET room_title = 'Workshop 1' WHERE room_title = 'Unknown Location' OR room_title IS NULL OR room_title = ''")
conn.commit()

# Check after
c.execute("SELECT COUNT(*) FROM tools WHERE room_title = 'Unknown Location' OR room_title IS NULL OR room_title = ''")
after_count = c.fetchone()[0]
print(f"After: {after_count} tools in Unknown Location")

c.execute("SELECT room_title, COUNT(*) FROM tools GROUP BY room_title")
print("Tools by location:")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
