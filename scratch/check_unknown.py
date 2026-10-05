import sqlite3

conn = sqlite3.connect('inventory.db')
c = conn.cursor()
c.execute("SELECT id, name, room_title FROM tools WHERE room_title = 'Unknown Location' or room_title is null or room_title = ''")
rows = c.fetchall()
print(f"Tools in Unknown Location: {len(rows)}")
for r in rows[:10]:
    print(r)

c.execute("SELECT id, name, location FROM consumables WHERE location = 'Unknown Location' or location is null or location = ''")
crows = c.fetchall()
print(f"Consumables in Unknown Location: {len(crows)}")
for r in crows[:10]:
    print(r)

# Check all registered locations in facility_locations
c.execute("SELECT * FROM facility_locations ORDER BY name ASC")
locs = c.fetchall()
print("Registered facility_locations:")
for l in locs:
    print(l)

conn.close()
