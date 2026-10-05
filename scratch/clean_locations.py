import sqlite3

conn = sqlite3.connect('inventory.db')
c = conn.cursor()

# 1. Standardize Workshop SS Gedung L to Workshop SS, Gedung L Lt. 1
c.execute("""
    UPDATE facility_locations 
    SET name = 'Workshop SS, Gedung L Lt. 1', building = 'Gedung L', floor = 'Lantai 1', storage_place = 'Rack Equipment & Bench A'
    WHERE name LIKE '%Workshop SS%'
""")
c.execute("UPDATE tools SET room_title = 'Workshop SS, Gedung L Lt. 1' WHERE room_title LIKE '%Workshop SS%'")
c.execute("UPDATE consumables SET location = 'Workshop SS, Gedung L Lt. 1' WHERE location LIKE '%Workshop SS%'")

# 2. Fix Rooftop
c.execute("""
    UPDATE facility_locations 
    SET floor = 'Atap / Rooftop', storage_place = 'Outdoor Antenna & Radar Test Platform'
    WHERE name = 'Rooftop'
""")

# 3. Fix Mini Pantry
c.execute("""
    UPDATE facility_locations 
    SET floor = 'Lantai 1', storage_place = 'Pantry Shelf & Refreshment Station'
    WHERE name = 'Mini Pantry'
""")

# 4. Fix Stationary Desk
c.execute("""
    UPDATE facility_locations 
    SET storage_place = 'Office Stationery Cabinet & Desk'
    WHERE name = 'Stationary Desk'
""")

# 5. Fix Ruang Kantor Utama
c.execute("""
    UPDATE facility_locations 
    SET storage_place = 'Executive Desk & Archive Cabinet'
    WHERE name = 'Ruang Kantor Utama'
""")

conn.commit()

c.execute("SELECT id, name, building, floor, storage_place FROM facility_locations ORDER BY id ASC")
for row in c.fetchall():
    print(row)

conn.close()
