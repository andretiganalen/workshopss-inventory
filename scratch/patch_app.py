import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app_path = os.path.join(BASE_DIR, "app.py")

with open(app_path, "r", encoding="utf-8") as f:
    content = f.read()

start_marker = '@app.get("/console", response_class=HTMLResponse)\ndef get_admin_console_page():'
end_marker = '</html>""")'

replacement = '''@app.get("/console", response_class=HTMLResponse)
def get_admin_console_page():
    console_path = os.path.join(BASE_DIR, "console.html")
    if os.path.exists(console_path):
        with open(console_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = "<h1>Template console.html not found</h1>"
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )'''

s_pos = content.find(start_marker)
if s_pos != -1:
    e_pos = content.find(end_marker, s_pos)
    if e_pos != -1:
        e_pos += len(end_marker)
        new_content = content[:s_pos] + replacement + content[e_pos:]
        with open(app_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("SUCCESSFULLY REPLACED CONSOLE ROUTE")
    else:
        print("END MARKER NOT FOUND")
else:
    print("START MARKER NOT FOUND")
