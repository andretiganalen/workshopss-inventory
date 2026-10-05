import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app_path = os.path.join(BASE_DIR, "app.py")

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace any strict role == "superadmin" or role.strip() != "superadmin"
old_pattern1 = 'if role.strip() != "superadmin":'
new_pattern1 = 'if role.strip().lower() not in ["superadmin", "admin", "administrator"]:'

content = content.replace(old_pattern1, new_pattern1)

# Also check effective_role not in ["admin", "superadmin"] and similar
content = content.replace('if effective_role not in ["admin", "superadmin"]:', 'if effective_role not in ["admin", "superadmin", "administrator"]:')
content = content.replace('if effective_role not in ["superadmin", "admin"]:', 'if effective_role not in ["admin", "superadmin", "administrator"]:')
content = content.replace('if role.strip() not in ["superadmin", "admin"]:', 'if role.strip().lower() not in ["superadmin", "admin", "administrator"]:')

with open(app_path, "w", encoding="utf-8") as f:
    f.write(content)

print("ROLES UPDATED SUCCESSFULLY")
