import os
import re
import sqlite3
import json
import shutil
import hashlib
import hmac
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn

# --- DIRECTORY CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
REPOSITORY_DIR = os.path.join(DATA_DIR, "repository")
DB_PATH = os.path.join(DATA_DIR, "inventory.db")
OPNAME_DOC_DIR = os.path.join(REPOSITORY_DIR, "_opname", "documents")
BRANDING_DIR = os.path.join(REPOSITORY_DIR, "_branding")

# If using a separate persistent storage directory (e.g. Render Disk mount),
# copy initial database seed and initial repository assets if they don't exist yet in DATA_DIR
if DATA_DIR != BASE_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        seed_db = os.path.join(BASE_DIR, "inventory.db")
        if os.path.exists(seed_db):
            try:
                shutil.copy2(seed_db, DB_PATH)
            except Exception as e:
                print(f"Warning: Failed to copy seed database to DATA_DIR: {e}")
    seed_repo = os.path.join(BASE_DIR, "repository")
    if os.path.exists(seed_repo):
        try:
            for root, dirs, files in os.walk(seed_repo):
                rel_path = os.path.relpath(root, seed_repo)
                dest_dir = os.path.join(REPOSITORY_DIR, rel_path)
                os.makedirs(dest_dir, exist_ok=True)
                for file in files:
                    dest_file = os.path.join(dest_dir, file)
                    if not os.path.exists(dest_file):
                        shutil.copy2(os.path.join(root, file), dest_file)
        except Exception as e:
            print(f"Warning: Failed to seed repository assets to DATA_DIR: {e}")

def hash_user_password(password: str, salt: str = "RadarEW_Facility_2026") -> str:
    """Computes salted SHA-256 password hash"""
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def verify_user_password(password: str, hashed: str, salt: str = "RadarEW_Facility_2026") -> bool:
    """Safely verifies password against salted hash"""
    return hmac.compare_digest(hash_user_password(password, salt), hashed)

os.makedirs(REPOSITORY_DIR, exist_ok=True)
os.makedirs(OPNAME_DOC_DIR, exist_ok=True)
os.makedirs(BRANDING_DIR, exist_ok=True)

ALL_STATES = [
    "New Purchase", "Active", "Borrow", "Maintenance", "Repair", "Transfer",
    "Damage", "Broken", "Lost", "Junk", "Donated", "Sell", "Scrapped", "Retired", "Dispose"
]

ALL_CONDITIONS = [
    "Brand New / Sealed",
    "Good / Operational",
    "Calibrated & Certified",
    "Fair / Minor Wear",
    "Needs Cleaning / Consumables",
    "Needs Calibration / Maintenance",
    "Under Repair",
    "Damaged / Degraded",
    "Broken / Inoperable",
    "Decommissioned / Disposed",
    "Missing / Lost"
]

def get_all_conditions() -> List[str]:
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM facility_conditions ORDER BY sort_order ASC, id ASC")
        rows = cursor.fetchall()
        conn.close()
        if rows:
            return [r['name'] for r in rows]
    except Exception:
        pass
    return ALL_CONDITIONS

TERMINAL_STATES = {
    "Dispose", "Sell", "Lost", "Damage", "Broken", "Junk", "Donated", "Scrapped", "Retired"
}

def clean_filename(filename: str) -> str:
    """Safely extracts base filename and cleans illegal Windows filesystem characters"""
    if not filename:
        return "unnamed_document"
    # Normalize Windows backslashes
    basename = os.path.basename(filename.replace('\\', '/'))
    # Filter illegal characters on Windows: <>:"/\|?*
    cleaned = "".join(c for c in basename if c not in '<>:"/\\|?*').strip()
    if not cleaned:
        cleaned = "attachment"
    return cleaned.replace(" ", "_")

CATEGORY_ACRONYMS = {
    # Equipment categories (2 digits)
    "INSTRUMENTATION": "IN",
    "TOOLS": "TL",
    "EQUIPMENT": "EQ",
    "DOCUMENTATION": "DC",
    "SYSTEMS": "SY",
    "ANTENNAS": "AN",
    "CALIBRATION": "CL",
    "MACHINERY": "MC",
    # Consumables / Materials categories (2 digits)
    "CHEMICALS & SOLDERING": "CS",
    "CHEMICALS": "CS",
    "SOLDERING": "SL",
    "TAPES & ADHESIVES": "TA",
    "ADHESIVES": "TA",
    "WIRING & SLEEVING": "WS",
    "WIRING": "WS",
    "SAFETY & PPE": "SF",
    "SAFETY": "SF",
    "HARDWARE & FASTENERS": "HF",
    "HARDWARE": "HF",
    "PROTOTYPING & MATERIALS": "PM",
    "PROTOTYPING": "PR",
    "RF CABLES": "RF",
    "RF CONNECTORS": "RC",
    "CABLES": "CB",
    "CONSUMABLES": "CS",
}

NAME_ACRONYMS = {
    # Test & Measurement Equipment (3 digits)
    "OSCILLOSCOPE": "OSC",
    "DIGITAL STORAGE OSCILLOSCOPE": "OSC",
    "MIXED SIGNAL OSCILLOSCOPE": "MSO",
    "SPECTRUM ANALYZER": "SPE",
    "SIGNAL GENERATOR": "GEN",
    "RF SIGNAL GENERATOR": "RFG",
    "FUNCTION GENERATOR": "FGN",
    "ARBITRARY WAVEFORM GENERATOR": "AWG",
    "VECTOR NETWORK ANALYZER": "VNA",
    "NETWORK ANALYZER": "VNA",
    "MULTIMETER": "MLT",
    "DIGITAL MULTIMETER": "DMM",
    "BENCHTOP MULTIMETER": "DMM",
    "POWER SUPPLY": "PWR",
    "DC POWER SUPPLY": "PWR",
    "AC POWER SOURCE": "ACP",
    "ELECTRONIC LOAD": "ELD",
    "FREQUENCY COUNTER": "FQC",
    "LOGIC ANALYZER": "LOG",
    "LCR METER": "LCR",
    "POWER METER": "PWM",
    "RF POWER METER": "PWM",
    "NOISE FIGURE METER": "NFM",
    "AUDIO ANALYZER": "AUD",
    "OPTICAL POWER METER": "OPM",
    "OPTICAL SPECTRUM ANALYZER": "OSA",
    "ANTENNA ANALYZER": "ANA",
    "HORN ANTENNA": "HRN",
    "ANTENNA": "ANT",
    "JAMMER": "JMR",
    "DIFFERENTIAL PROBE": "PRB",
    "HIGH VOLTAGE PROBE": "HVP",
    "CURRENT PROBE": "CPR",
    "NEAR-FIELD PROBE": "NFP",
    # Soldering & Workshop Equipment
    "SOLDERING STATION": "SLD",
    "REWORK STATION": "REW",
    "HOT AIR REWORK STATION": "HAR",
    "DESOLDERING STATION": "DSD",
    "INFRARED PREHEATER": "PRE",
    "ULTRASONIC CLEANER": "USC",
    "FUME EXTRACTOR": "FUM",
    "REFLOW OVEN": "OVN",
    "PICK AND PLACE MACHINE": "PNP",
    "PCB STENCIL PRINTER": "STN",
    # Fabrication & 3D Prototyping
    "3D PRINTER": "3DP",
    "3D PRINTER (FDM)": "3DP",
    "3D PRINTER (SLA/RESIN)": "3DP",
    "3D PROTOTYPER": "3DP",
    "CNC MILLING MACHINE": "CNC",
    "PCB MILLING MACHINE": "PCM",
    "LASER ENGRAVER & CUTTER": "LSR",
    "LASER CUTTER": "LCU",
    "SPOT WELDER": "WLD",
    "HEAT PRESS MACHINE": "HPM",
    "DRILL PRESS": "DLP",
    "ROTARY TOOL": "ROT",
    # Tools & Hardware
    "DRILL": "DRL",
    "IMPACT DRILL": "DRL",
    "HAMMER DRILL": "DRL",
    "CORDLESS SCREWDRIVER": "SCD",
    "PRECISION SCREWDRIVER SET": "SCD",
    "BENCH GRINDER": "BGD",
    "ANGLE GRINDER": "AGD",
    "BENCH VISE": "VIS",
    "TORQUE WRENCH": "TRQ",
    "TORQUE WRENCH SET": "TRQ",
    "DIGITAL CALIPER": "CLP",
    "CALIPER": "CLP",
    "DIGITAL MICROMETER": "MIC",
    "WIRE CRIMPER": "CRM",
    "DIAGONAL CUTTERS": "CUT",
    "WIRE STRIPPER": "STP",
    "HEX KEY ALLEN WRENCH SET": "ALN",
    "HEAT GUN": "HTG",
    "PRINTER": "PRN",
    "LABEL PRINTER": "LBL",
    "BARCODE SCANNER": "BCS",
    # Optical & Inspection
    "STEREO MICROSCOPE": "MIC",
    "INSPECTION MICROSCOPE": "MIC",
    "DIGITAL MICROSCOPE": "MIC",
    "THERMAL CAMERA": "THM",
    "THERMAL IMAGING CAMERA": "THM",
    "BORESCOPE": "BOR",
    # Consumables / Materials (3 digits)
    "SOLDER WIRE": "SLD",
    "LEAD-FREE SOLDER WIRE": "SLD",
    "63/37 TIN-LEAD SOLDER WIRE": "SLD",
    "SOLDER PASTE": "SLP",
    "SOLDER PASTE FLUX": "FLX",
    "FLUX": "FLX",
    "LIQUID FLUX": "FLX",
    "BGA TACK FLUX GEL": "FLX",
    "DESOLDERING BRAID": "DSB",
    "DESOLDERING BRAID / WICK": "DSB",
    "ISOPROPYL ALCOHOL": "ISO",
    "ISOPROPYL ALCOHOL 99%": "ISO",
    "ISOPROPYL ALCOHOL 99.9%": "ISO",
    "CLEANROOM WIPES": "WIP",
    "LINT-FREE CLEANROOM WIPES": "WIP",
    "KAPTON TAPE": "KAP",
    "HIGH-TEMP MASKING TAPE": "MSK",
    "ELECTRICAL TAPE": "ELT",
    "THERMAL PASTE": "THP",
    "THERMAL GREASE / PASTE": "THP",
    "THERMAL CONDUCTIVE PAD": "THD",
    "HEAT SHRINK TUBING": "HST",
    "CABLE TIES": "ZPT",
    "NYLON CABLE TIES": "ZPT",
    "SILICONE STRANDED WIRE": "WIR",
    "BREADBOARD JUMPER WIRES": "JMP",
    "3D PRINT FILAMENT": "PLA",
    "PLA 3D PRINTER FILAMENT": "PLA",
    "PETG 3D PRINTER FILAMENT": "PTG",
    "ABS 3D PRINTER FILAMENT": "ABS",
    "UV CURING RESIN": "RSN",
    "COPPER CLAD PCB": "PCB",
    "SOLDERLESS BREADBOARD": "BRD",
    "DUST CAPS": "SMA",
    "SMA DUST CAPS": "SMA",
    "COAXIAL DUST CAPS": "SMA",
    "SMA COAXIAL DUST CAPS": "SMA",
    "RF COAXIAL CABLE": "RFC",
    "RG-316 COAXIAL CABLE": "RFC",
    "SMA ATTENUATOR": "ATN",
    "SMA ADAPTER": "ADP",
    "50 OHM RF TERMINATION LOAD": "TRM",
    "ANTI-STATIC GLOVES": "ESD",
    "NITRILE GLOVES": "GLV",
    "SAFETY GOGGLES": "GOG",
    "CYANOACRYLATE SUPER GLUE": "GLU",
    "EPOXY RESIN ADHESIVE": "EPX",
    "THREADLOCKER": "LOX",
    "CONTACT CLEANER": "CLN",
    "ELECTRONIC CONTACT CLEANER": "CLN",
    "AIR DUSTER COMPRESSED GAS": "AIR",
    "M3 SCREWS & NUTS KIT": "SCR",
    "BRASS STANDOFF SPACERS": "STF",
}

def get_category_code(cat: str) -> str:
    cleaned = (cat or "").strip().upper()
    if cleaned in CATEGORY_ACRONYMS:
        return CATEGORY_ACRONYMS[cleaned]
    for k, v in CATEGORY_ACRONYMS.items():
        if k in cleaned or cleaned in k:
            return v
    words = [w for w in re.split(r'[\s&/,_-]+', cleaned) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    elif len(words) == 1 and len(words[0]) >= 2:
        return words[0][:2].upper()
    return "EQ"

def get_name_code(name: str) -> str:
    cleaned = (name or "").strip().upper()
    if cleaned in NAME_ACRONYMS:
        return NAME_ACRONYMS[cleaned]
    best_match = None
    for k, v in NAME_ACRONYMS.items():
        if k in cleaned:
            if best_match is None or len(k) > len(best_match[0]):
                best_match = (k, v)
    if best_match:
        return best_match[1]

    words = [w for w in re.split(r'[\s&/,_-]+', cleaned) if w and w not in ('AND', 'THE', 'OF', 'FOR', 'WITH', 'IN', 'TO')]
    if len(words) >= 3:
        return (words[0][0] + words[1][0] + words[2][0]).upper()
    elif len(words) == 2:
        w1, w2 = words[0], words[1]
        c2 = w2[:2] if len(w2) >= 2 else (w2 + 'X')[:2]
        return (w1[0] + c2).upper()
    elif len(words) == 1:
        w = words[0]
        if len(w) >= 3:
            return w[:3].upper()
        return (w + 'XXX')[:3].upper()
    return "GEN"

def get_next_auto_id(conn, table_name: str, cat: str, name: str) -> str:
    cat_code = get_category_code(cat)
    name_code = get_name_code(name)
    prefix = f"{cat_code}-{name_code}-"

    cursor = conn.cursor()
    cursor.execute(f"SELECT id FROM {table_name}")
    existing_ids = [r[0] for r in cursor.fetchall() if r[0]]

    max_seq = 0
    for eid in existing_ids:
        eid_upper = str(eid).upper().strip()
        if eid_upper.startswith(prefix):
            suffix = eid_upper[len(prefix):]
            m = re.match(r'^(\d+)', suffix)
            if m:
                val = int(m.group(1))
                if val > max_seq:
                    max_seq = val
        elif f"-{name_code}-" in eid_upper:
            parts = eid_upper.split(f"-{name_code}-")
            if len(parts) == 2:
                m = re.match(r'^(\d+)', parts[1])
                if m:
                    val = int(m.group(1))
                    if val > max_seq:
                        max_seq = val

    next_seq = max_seq + 1
    return f"{cat_code}-{name_code}-{next_seq:05d}"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_sample_svg_image(filepath: str, label: str, icon_color: str = "#238636"):
    """Generates a crisp equipment representation SVG image if no photo uploaded"""
    if os.path.exists(filepath):
        return
    svg_data = f"""<svg width="320" height="200" viewBox="0 0 320 200" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect width="320" height="200" fill="#1c2128"/>
    <rect x="2" y="2" width="316" height="196" stroke="#30363d" stroke-width="2" rx="8"/>
    <circle cx="160" cy="85" r="44" fill="{icon_color}" fill-opacity="0.15"/>
    <circle cx="160" cy="85" r="32" stroke="{icon_color}" stroke-width="2.5"/>
    <path d="M160 55V115M130 85H190" stroke="{icon_color}" stroke-width="2" stroke-linecap="round"/>
    <text x="160" y="152" fill="#e6edf3" font-family="Arial" font-size="14" font-weight="bold" text-anchor="middle">{label}</text>
    <text x="160" y="172" fill="#8b949e" font-family="Arial" font-size="11" text-anchor="middle">FACILITY REPOSITORY ASSET</text>
</svg>"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(svg_data)

def init_repository_for_tool(tool_id: str, tool_name: str = "Equipment"):
    """Ensures repository folders exist for the tool: photos and documents, with default svg"""
    tool_photo_dir = os.path.join(REPOSITORY_DIR, tool_id, "photos")
    tool_doc_dir = os.path.join(REPOSITORY_DIR, tool_id, "documents")
    os.makedirs(tool_photo_dir, exist_ok=True)
    os.makedirs(tool_doc_dir, exist_ok=True)
    
    default_svg = os.path.join(tool_photo_dir, "default_equipment.svg")
    create_sample_svg_image(default_svg, f"{tool_name} [{tool_id}]")
    return tool_photo_dir, tool_doc_dir

def sync_equipment_current_states(conn, target_tool_id: Optional[str] = None):
    """
    Requirement 53: If there is a past state, exactly one chronologically latest
    record MUST be the Current state (is_current=1), and all others are past states (is_current=0).
    """
    cursor = conn.cursor()
    if target_tool_id:
        tool_ids = [target_tool_id]
    else:
        cursor.execute("SELECT id FROM tools")
        tool_ids = [r['id'] for r in cursor.fetchall()]

    for tid in tool_ids:
        cursor.execute("SELECT id FROM transactions WHERE tool_id = ? ORDER BY date_time DESC, id DESC", (tid,))
        rows = cursor.fetchall()
        if not rows:
            continue
        latest_id = rows[0]['id']
        cursor.execute("UPDATE transactions SET is_current = 1 WHERE id = ?", (latest_id,))
        if len(rows) > 1:
            past_ids = [r['id'] for r in rows[1:]]
            cursor.execute(f"UPDATE transactions SET is_current = 0 WHERE id IN ({','.join(['?']*len(past_ids))})", past_ids)
    conn.commit()

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            brand TEXT NOT NULL,
            model TEXT NOT NULL,
            tool_type TEXT NOT NULL,
            serial_number TEXT NOT NULL,
            room_title TEXT DEFAULT 'Radar EW Facility Workshop A',
            project TEXT DEFAULT 'Radar EW Facility Project'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT NOT NULL,
            pic TEXT NOT NULL,
            purpose TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            condition TEXT NOT NULL,
            state TEXT DEFAULT 'Active',
            price REAL DEFAULT 0.0,
            photo_path TEXT,
            doc_path TEXT,
            is_current INTEGER DEFAULT 0,
            FOREIGN KEY (tool_id) REFERENCES tools(id)
        )
    """)

    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            city TEXT DEFAULT 'Bandung',
            building TEXT DEFAULT 'Gedung Radar & EW',
            floor TEXT DEFAULT 'Lantai 2',
            storage_place TEXT DEFAULT 'Rack Equipment & Bench'
        )
    """)

    # Ensure columns exist if table was previously created with fewer columns
    cursor.execute("PRAGMA table_info(facility_locations)")
    existing_cols = [r['name'] for r in cursor.fetchall()]
    if 'city' not in existing_cols:
        cursor.execute("ALTER TABLE facility_locations ADD COLUMN city TEXT DEFAULT 'Bandung'")
    if 'building' not in existing_cols:
        cursor.execute("ALTER TABLE facility_locations ADD COLUMN building TEXT DEFAULT 'Gedung Radar & EW'")
    if 'floor' not in existing_cols:
        cursor.execute("ALTER TABLE facility_locations ADD COLUMN floor TEXT DEFAULT 'Lantai 2'")
    if 'storage_place' not in existing_cols:
        cursor.execute("ALTER TABLE facility_locations ADD COLUMN storage_place TEXT DEFAULT 'Rack Equipment & Bench'")

    # Seed default facility locations if empty
    cursor.execute("SELECT COUNT(*) as cnt FROM facility_locations")
    if cursor.fetchone()['cnt'] == 0:
        default_locs = [
            ("Len Industri (Persero)", "Kota Bandung", "Gedung L", "Lantai 1", "Workshop 1", "Lemari 1"),
            ("Len Industri (Persero)", "Kota Bandung", "Gedung L", "Lantai 1", "Workshop 1", "Lemari 2"),
            ("Len Industri (Persero)", "Kota Bandung", "Gedung L", "Lantai 1", "Workshop 2", "Rak Equipment"),
            ("Len Industri (Persero)", "Kota Bandung", "Gedung L", "Lantai 1", "Workshop 2", "Meja Workshop"),
            ("Len Industri (Persero)", "Kota Bandung", "Gedung L", "Lantai 1", "Garasi Luar", "Mobile C4ISR (C-UAS)")
        ]
        now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
        for item in default_locs:
            if len(item) == 6:
                comp, c, b, f, r, s = item
                loc_name = f"{r} - {s}" if s else r
            else:
                loc_name, c, b, f, s = item
            cursor.execute("""
                INSERT OR IGNORE INTO facility_locations (name, created_at, city, building, floor, storage_place)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (loc_name, now_dt, c, b, f, s))
        conn.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facility_conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) as cnt FROM facility_conditions")
    if cursor.fetchone()['cnt'] == 0:
        now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
        for idx, cond in enumerate(ALL_CONDITIONS):
            cursor.execute("INSERT OR IGNORE INTO facility_conditions (name, sort_order, created_at) VALUES (?, ?, ?)", (cond, idx, now_dt))
        conn.commit()

    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS consumables (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            specification TEXT,
            category TEXT,
            unit TEXT DEFAULT 'Pcs',
            quantity REAL DEFAULT 0.0,
            min_stock REAL DEFAULT 3.0,
            unit_price REAL DEFAULT 0.0,
            location TEXT DEFAULT 'Cabinet B - Consumables Shelf',
            project TEXT DEFAULT 'Radar EW Facility Project',
            last_restocked TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(consumables)")
    cons_cols = [c['name'] for c in cursor.fetchall()]
    if 'project' not in cons_cols:
        cursor.execute("ALTER TABLE consumables ADD COLUMN project TEXT DEFAULT 'Radar EW Facility Project'")
        cursor.execute("UPDATE consumables SET project = 'Radar EW Facility Project' WHERE project IS NULL OR project = ''")
        conn.commit()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS consumable_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT NOT NULL,
            consumable_id TEXT NOT NULL,
            tx_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            balance_after REAL NOT NULL,
            pic TEXT NOT NULL,
            purpose TEXT,
            project TEXT DEFAULT 'Radar EW Facility Project',
            FOREIGN KEY (consumable_id) REFERENCES consumables(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_opnames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT NOT NULL,
            pic TEXT NOT NULL,
            location TEXT NOT NULL,
            notes TEXT,
            doc_path TEXT,
            verified_count INTEGER DEFAULT 0,
            total_count INTEGER DEFAULT 0
        )
    """)

    # Seed default system settings if not exists
    cursor.execute("SELECT COUNT(*) as cnt FROM system_settings")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("INSERT INTO system_settings (key, value) VALUES ('room_title', 'Radar EW Facility Workshop A')")
        cursor.execute("INSERT INTO system_settings (key, value) VALUES ('group_title', 'EW Instrumentation & Maintenance Unit')")
        cursor.execute("INSERT INTO system_settings (key, value) VALUES ('room_status', 'active')")
        conn.commit()

    # --- REPORT SIGNATORIES TABLE & HISTORICAL TRACKING ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_signatories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_by TEXT DEFAULT 'admin',
            notes TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            dibuat_label TEXT NOT NULL DEFAULT 'Dibuat',
            dibuat_title TEXT NOT NULL DEFAULT 'Inventory Controller / PIC',
            dibuat_name TEXT NOT NULL DEFAULT 'Officer In Charge',
            diperiksa_label TEXT NOT NULL DEFAULT 'Diperiksa',
            diperiksa_title TEXT NOT NULL DEFAULT 'Head of Warehouse',
            diperiksa_name TEXT NOT NULL DEFAULT 'John',
            disetujui_label TEXT NOT NULL DEFAULT 'Disetujui',
            disetujui_title TEXT NOT NULL DEFAULT 'Facility Manager',
            disetujui_name TEXT NOT NULL DEFAULT 'Andre'
        )
    """)

    cursor.execute("SELECT COUNT(*) as cnt FROM report_signatories")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("""
            INSERT INTO report_signatories (
                version, created_at, updated_by, notes, is_active,
                dibuat_label, dibuat_title, dibuat_name,
                diperiksa_label, diperiksa_title, diperiksa_name,
                disetujui_label, disetujui_title, disetujui_name
            ) VALUES (
                1, ?, 'system', 'Baseline signatory configuration', 1,
                'Dibuat', 'Inventory Controller / PIC', 'Officer In Charge',
                'Diperiksa', 'Head of Warehouse', 'John',
                'Disetujui', 'Facility Manager', 'Andre'
            )
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        conn.commit()

    # --- USERS AUTHENTICATION TABLE ---
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            job_title TEXT DEFAULT 'Radar Technician',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()

    cursor.execute("SELECT id, name FROM tools")
    for r in cursor.fetchall():
        init_repository_for_tool(r['id'], r['name'])

    sync_equipment_current_states(conn)
    conn.close()

def get_current_signatories(conn=None):
    close_at_end = False
    if conn is None:
        conn = get_db()
        close_at_end = True
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM report_signatories 
        WHERE is_active = 1 
        ORDER BY version DESC LIMIT 1
    """)
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT * FROM report_signatories ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
    
    if row:
        res = dict(row)
    else:
        res = {
            "id": 1,
            "version": 1,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_by": "system",
            "notes": "Initial baseline signatory configuration",
            "is_active": 1,
            "dibuat_label": "Dibuat",
            "dibuat_title": "Inventory Controller / PIC",
            "dibuat_name": "Officer In Charge",
            "diperiksa_label": "Diperiksa",
            "diperiksa_title": "Head of Warehouse",
            "diperiksa_name": "John",
            "disetujui_label": "Disetujui",
            "disetujui_title": "Facility Manager",
            "disetujui_name": "Andre"
        }
    if close_at_end:
        conn.close()
    return res

def get_signatories_history(conn=None):
    close_at_end = False
    if conn is None:
        conn = get_db()
        close_at_end = True
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM report_signatories ORDER BY version DESC, id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    if close_at_end:
        conn.close()
    return rows

def recalculate_consumables_fifo(conn=None, consumable_id: Optional[str] = None):
    """
    Requirement: "Calculation in Consumables Page, especially on Ledger view, should be recalculated by Date, FIFO stages. The Earlier Date is always be an Initial Conditions."
    Recalculates consumable balances chronologically by Date in FIFO stages.
    """
    close_at_end = False
    if conn is None:
        conn = get_db()
        close_at_end = True
    cursor = conn.cursor()

    if consumable_id:
        cursor.execute("SELECT id, quantity, last_restocked FROM consumables WHERE id = ?", (consumable_id,))
        items = cursor.fetchall()
    else:
        cursor.execute("SELECT id, quantity, last_restocked FROM consumables")
        items = cursor.fetchall()

    for it in items:
        cid = it['id']
        cursor.execute("""
            SELECT id, date_time, tx_type, quantity, balance_after
            FROM consumable_transactions
            WHERE consumable_id = ?
        """, (cid,))
        raw_txs = [dict(r) for r in cursor.fetchall()]
        if not raw_txs:
            continue

        # "The Earlier Date is always be an Initial Conditions."
        # If there is an 'Initial Stock' transaction, ensure its timestamp is the earliest for this consumable
        init_tx = next((t for t in raw_txs if 'INITIAL' in (t['tx_type'] or '').upper()), None)
        if init_tx:
            other_dates = [t['date_time'] for t in raw_txs if t['id'] != init_tx['id'] and t['date_time']]
            if other_dates:
                earliest_other = min(other_dates)
                if (init_tx['date_time'] or '') >= earliest_other:
                    day_part = earliest_other.split(' ')[0]
                    new_init_dt = f"{day_part} 00:00"
                    if new_init_dt >= earliest_other:
                        new_init_dt = earliest_other
                    init_tx['date_time'] = new_init_dt
                    cursor.execute("UPDATE consumable_transactions SET date_time = ? WHERE id = ?", (new_init_dt, init_tx['id']))

        # Sorting priority for FIFO staging when dates are identical:
        # Initial Stock (0) -> In/Restock (1) -> Adjust (2) -> Out/Usage (3)
        def tx_priority(t):
            tt = (t['tx_type'] or '').upper()
            if 'INITIAL' in tt:
                return 0
            if any(w in tt for w in ['IN', 'RESTOCK', 'PURCHASE']):
                return 1
            if any(w in tt for w in ['ADJUST', 'COUNT', 'SET', 'OPNAME']):
                return 2
            return 3

        sorted_txs = sorted(raw_txs, key=lambda x: (x['date_time'] or '', tx_priority(x), x['id']))

        running_balance = 0.0
        latest_dt = None
        for t in sorted_txs:
            tid = t['id']
            t_type = (t['tx_type'] or '').upper()
            qty = abs(float(t['quantity'] or 0.0))
            if t['date_time']:
                latest_dt = t['date_time']

            if any(w in t_type for w in ["OUT", "USAGE", "KURANG", "PENGURANGAN", "PAKAI", "ISSUE", "DEDUCT", "EXPENSE"]):
                running_balance = max(0.0, running_balance - qty)
            elif any(w in t_type for w in ["ADJUST", "COUNT", "SET", "OPNAME"]):
                running_balance = qty
            else:  # IN, INITIAL, RESTOCK, PURCHASE
                running_balance = running_balance + qty

            cursor.execute("UPDATE consumable_transactions SET balance_after = ? WHERE id = ?", (running_balance, tid))

        cursor.execute("UPDATE consumables SET quantity = ?, last_restocked = COALESCE(?, last_restocked) WHERE id = ?",
                       (running_balance, latest_dt, cid))

    conn.commit()
    if close_at_end:
        conn.close()

init_db()
recalculate_consumables_fifo()

# --- FASTAPI SERVER ---
app = FastAPI(title="Facility Workshop Inventory & Historical Repository System")

@app.get("/api/signatories/current")
def api_get_current_signatories():
    return get_current_signatories()

@app.get("/api/signatories/history")
def api_get_signatories_history():
    return get_signatories_history()

@app.post("/api/signatories")
def api_update_signatories(
    dibuat_label: str = Form("Dibuat"),
    dibuat_title: str = Form("Inventory Controller / PIC"),
    dibuat_name: str = Form("Officer In Charge"),
    diperiksa_label: str = Form("Diperiksa"),
    diperiksa_title: str = Form("Head of Warehouse"),
    diperiksa_name: str = Form("John"),
    disetujui_label: str = Form("Disetujui"),
    disetujui_title: str = Form("Facility Manager"),
    disetujui_name: str = Form("Andre"),
    notes: Optional[str] = Form(""),
    updated_by: Optional[str] = Form("admin")
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE report_signatories SET is_active = 0")
    cursor.execute("SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM report_signatories")
    next_ver = cursor.fetchone()['next_ver']
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO report_signatories (
            version, created_at, updated_by, notes, is_active,
            dibuat_label, dibuat_title, dibuat_name,
            diperiksa_label, diperiksa_title, diperiksa_name,
            disetujui_label, disetujui_title, disetujui_name
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        next_ver, now_str, updated_by or "admin", notes or "",
        dibuat_label.strip(), dibuat_title.strip(), dibuat_name.strip(),
        diperiksa_label.strip(), diperiksa_title.strip(), diperiksa_name.strip(),
        disetujui_label.strip(), disetujui_title.strip(), disetujui_name.strip()
    ))
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": f"Signatories updated and recorded as version {next_ver}.",
        "version": next_ver
    }

@app.post("/api/signatories/rollback/{version}")
def api_rollback_signatories(version: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM report_signatories WHERE version = ?", (version,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Signatory version {version} not found.")
    cursor.execute("UPDATE report_signatories SET is_active = 0")
    cursor.execute("UPDATE report_signatories SET is_active = 1 WHERE version = ?", (version,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Signatories configuration reverted to version {version}."}

@app.get("/api/settings")
def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM system_settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    
    # 5-Level Room Hierarchy Defaults (Req 4.1)
    if 'hierarchy_city' not in settings:
        settings['hierarchy_city'] = 'Bandung'
    if 'hierarchy_building' not in settings:
        settings['hierarchy_building'] = 'Gedung Radar & EW'
    if 'hierarchy_floor' not in settings:
        settings['hierarchy_floor'] = 'Lantai 2'
    if 'hierarchy_room' not in settings:
        settings['hierarchy_room'] = settings.get('room_title', 'Workshop SS Gedung L')
    if 'hierarchy_storage' not in settings:
        settings['hierarchy_storage'] = 'Rack Equipment & Bench'

    conn.close()
    return settings

@app.post("/api/settings")
def update_settings(
    room_title: str = Form(...),
    group_title: str = Form(...),
    room_status: str = Form(...),
    hierarchy_city: Optional[str] = Form("Bandung"),
    hierarchy_building: Optional[str] = Form("Gedung Radar & EW"),
    hierarchy_floor: Optional[str] = Form("Lantai 2"),
    hierarchy_room: Optional[str] = Form(None),
    hierarchy_storage: Optional[str] = Form("Rack Equipment & Bench")
):
    conn = get_db()
    cursor = conn.cursor()
    pairs = [
        ('room_title', room_title.strip()),
        ('group_title', group_title.strip()),
        ('room_status', room_status.strip()),
        ('hierarchy_city', (hierarchy_city or 'Bandung').strip()),
        ('hierarchy_building', (hierarchy_building or 'Gedung Radar & EW').strip()),
        ('hierarchy_floor', (hierarchy_floor or 'Lantai 2').strip()),
        ('hierarchy_room', (hierarchy_room or room_title).strip()),
        ('hierarchy_storage', (hierarchy_storage or 'Rack Equipment & Bench').strip())
    ]
    for k, v in pairs:
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Settings and Room Hierarchy updated"}

@app.post("/api/settings/branding")
async def update_branding_settings(
    room_title: Optional[str] = Form(None),
    group_title: Optional[str] = Form(None),
    portal_logo: Optional[UploadFile] = File(None),
    app_logo: Optional[UploadFile] = File(None),
    report_logo: Optional[UploadFile] = File(None),
    reset_portal_logo: Optional[int] = Form(0),
    reset_app_logo: Optional[int] = Form(0),
    reset_report_logo: Optional[int] = Form(0),
    role: str = Form("guest")
):
    """Administrator / Superadmin: Update Apps Name Header, Portal Logo, Apps Logo and PDF Report Logo"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can update branding and logos.")
    
    conn = get_db()
    cursor = conn.cursor()
    
    if room_title and room_title.strip():
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('room_title', ?)", (room_title.strip(),))
    if group_title and group_title.strip():
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('group_title', ?)", (group_title.strip(),))
        
    if reset_portal_logo == 1:
        cursor.execute("DELETE FROM system_settings WHERE key = 'portal_logo_url'")
    elif portal_logo and portal_logo.filename:
        safe_name = clean_filename(portal_logo.filename)
        fname = f"portal_logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
        fpath = os.path.join(BRANDING_DIR, fname)
        with open(fpath, "wb") as buf:
            buf.write(await portal_logo.read())
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('portal_logo_url', ?)", (f"/repository/_branding/{fname}",))

    if reset_app_logo == 1:
        cursor.execute("DELETE FROM system_settings WHERE key = 'app_logo_url'")
    elif app_logo and app_logo.filename:
        safe_name = clean_filename(app_logo.filename)
        fname = f"app_logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
        fpath = os.path.join(BRANDING_DIR, fname)
        with open(fpath, "wb") as buf:
            buf.write(await app_logo.read())
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('app_logo_url', ?)", (f"/repository/_branding/{fname}",))
        
    if reset_report_logo == 1:
        cursor.execute("DELETE FROM system_settings WHERE key = 'report_logo_url'")
    elif report_logo and report_logo.filename:
        safe_name = clean_filename(report_logo.filename)
        fname = f"report_logo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
        fpath = os.path.join(BRANDING_DIR, fname)
        with open(fpath, "wb") as buf:
            buf.write(await report_logo.read())
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('report_logo_url', ?)", (f"/repository/_branding/{fname}",))
        
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Branding, application header, and logos updated successfully!"}

def get_report_logo_html(settings: dict) -> str:
    rep_logo = settings.get('report_logo_url') or settings.get('app_logo_url')
    if rep_logo:
        return f'<img src="{rep_logo}" alt="Report Logo" style="height:44px; max-width:160px; object-fit:contain; vertical-align:middle; border-radius:4px;">'
    return """<svg width="40" height="40" viewBox="0 0 100 100" style="vertical-align:middle;">
        <circle cx="50" cy="50" r="46" fill="none" stroke="#1f883d" stroke-width="3"/>
        <circle cx="50" cy="50" r="32" fill="none" stroke="#555" stroke-dasharray="3,3" stroke-width="2"/>
        <circle cx="50" cy="50" r="18" fill="none" stroke="#1f883d" stroke-width="2"/>
        <circle cx="50" cy="50" r="4" fill="#1f883d"/>
        <line x1="50" y1="4" x2="50" y2="96" stroke="#555" stroke-width="1"/>
        <line x1="4" y1="50" x2="96" y2="50" stroke="#555" stroke-width="1"/>
        <path d="M 50 50 L 85 25 A 46 46 0 0 0 50 4 Z" fill="rgba(31,136,61,0.2)"/>
    </svg>"""

@app.get("/api/locations/hierarchy")
def get_locations_hierarchy():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, city, building, floor, storage_place FROM facility_locations ORDER BY name ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/tools")
def get_tools():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools ORDER BY name ASC")
    tools = [dict(row) for row in cursor.fetchall()]
    
    for tool in tools:
        init_repository_for_tool(tool['id'], tool['name'])
        cursor.execute("SELECT state, condition, is_current FROM transactions WHERE tool_id = ? ORDER BY date_time DESC, id DESC LIMIT 1", (tool['id'],))
        latest_row = cursor.fetchone()
        if latest_row:
            tool['current_state'] = latest_row['state']
            tool['current_condition'] = latest_row['condition']
            tool['is_terminal'] = latest_row['state'] in TERMINAL_STATES
        else:
            tool['current_state'] = "New Purchase"
            tool['current_condition'] = "Brand New / Sealed"
            tool['is_terminal'] = False

    conn.close()
    return tools

# API: Register New Equipment / Tool (Any user can add new tools or equipment)
@app.post("/api/tools")
async def create_tool(
    id: Optional[str] = Form(None),
    name: str = Form(...),
    category: str = Form("Tools"),
    brand: str = Form(...),
    model: str = Form(...),
    tool_type: str = Form(...),
    serial_number: str = Form(...),
    room_title: str = Form("Radar EW Facility Workshop A"),
    project: str = Form("Radar EW Facility Project"),
    initial_state: str = Form("New Purchase"),
    initial_condition: str = Form("Brand New / Sealed"),
    price: float = Form(0.0),
    pic: str = Form(...),
    purpose: str = Form("Initial equipment procurement and cataloging"),
    date_time: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    document: Optional[UploadFile] = File(None)
):
    conn = get_db()
    cursor = conn.cursor()

    tool_id = (id or "").strip()
    if not tool_id:
        tool_id = get_next_auto_id(conn, "tools", category, name)
    else:
        cursor.execute("SELECT id FROM tools WHERE id = ?", (tool_id,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Tool ID '{tool_id}' already exists in inventory!")

    cursor.execute("""
        INSERT INTO tools (id, name, category, brand, model, tool_type, serial_number, room_title, project)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (tool_id, name.strip(), category.strip(), brand.strip(), model.strip(), tool_type.strip(), serial_number.strip(), room_title.strip(), project.strip()))

    p_dir, d_dir = init_repository_for_tool(tool_id, name.strip())

    photo_path = None
    if photo and photo.filename:
        safe_fname = clean_filename(photo.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(p_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await photo.read())
        photo_path = f"/repository/{tool_id}/photos/{filename}"

    doc_path = None
    if document and document.filename:
        safe_fname = clean_filename(document.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(d_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await document.read())
        doc_path = f"/repository/{tool_id}/documents/{filename}"

    tx_time = date_time.strip() if (date_time and date_time.strip()) else datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO transactions (date_time, pic, purpose, tool_id, condition, state, price, photo_path, doc_path, is_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (tx_time, pic.strip(), purpose.strip(), tool_id, initial_condition.strip(), initial_state.strip(), float(price or 0.0), photo_path, doc_path))

    sync_equipment_current_states(conn, tool_id)
    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Equipment '{name}' [{tool_id}] registered successfully!",
        "tool_id": tool_id
    }

# API: Transfer Equipment to another Project/Program (Admin only)
@app.post("/api/tools/{tool_id}/transfer-project")
def transfer_tool_project(
    tool_id: str,
    new_project: str = Form(...),
    pic: str = Form(...),
    reason: str = Form(...)
):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM tools WHERE id = ?", (tool_id,))
    tool = cursor.fetchone()
    if not tool:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
        
    old_project = tool['project']
    cursor.execute("UPDATE tools SET project = ? WHERE id = ?", (new_project, tool_id))
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO transactions (date_time, pic, purpose, tool_id, condition, state, price, is_current)
        VALUES (?, ?, ?, ?, ?, 'Transfer', 0.0, 1)
    """, (now_str, pic, f"Transferred from '{old_project}' to '{new_project}'. Reason: {reason}", tool_id, "Good / Transferred"))
    
    sync_equipment_current_states(conn, tool_id)
    conn.close()
    return {"status": "success", "message": f"Equipment {tool_id} successfully transferred to {new_project}"}

# API: Dynamic Filter Options
@app.get("/api/filter-options")
def get_filter_options():
    conn = get_db()
    cursor = conn.cursor()
    
    # Requirement 75: Locations from facility_locations merged with tools
    cursor.execute("SELECT name FROM facility_locations ORDER BY name ASC")
    reg_locs = [r['name'] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT room_title FROM tools WHERE room_title IS NOT NULL AND room_title != ''")
    tool_locs = [r['room_title'] for r in cursor.fetchall()]
    locations = sorted(list(set(reg_locs + tool_locs)))
    
    cursor.execute("SELECT DISTINCT name FROM tools ORDER BY name ASC")
    equipments = [r['name'] for r in cursor.fetchall()]
    
    cursor.execute("SELECT DISTINCT pic FROM transactions WHERE pic IS NOT NULL AND pic != '' ORDER BY pic ASC")
    pics = [r['pic'] for r in cursor.fetchall()]
    
    active_conds = get_all_conditions()
    cursor.execute("SELECT DISTINCT condition FROM transactions WHERE condition IS NOT NULL AND condition != '' ORDER BY condition ASC")
    tx_conditions = [r['condition'] for r in cursor.fetchall()]
    conditions = active_conds.copy()
    for tc in tx_conditions:
        if tc not in conditions:
            conditions.append(tc)
    
    cursor.execute("SELECT DISTINCT state FROM transactions WHERE state IS NOT NULL AND state != '' ORDER BY state ASC")
    states = [r['state'] for r in cursor.fetchall()]
    for s in ALL_STATES:
        if s not in states:
            states.append(s)

    cursor.execute("SELECT DISTINCT project FROM tools WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    t_projs = [r['project'] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT project FROM consumable_transactions WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    c_projs = [r['project'] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT project FROM consumables WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    con_projs = [r['project'] for r in cursor.fetchall()]
    projects = sorted(list(set(t_projs + c_projs + con_projs + ["Radar EW Facility Project"])))
    
    # Requirement 4.2 Organizational Hierarchies
    systems = [
        "Radar Transmitter Subsystem",
        "Radar Receiver Subsystem",
        "Digital Signal Processor (DSP)",
        "Antenna Feed & Pedestal Subsystem",
        "Electronic Countermeasure (ECM)",
        "RF Microwave Calibration System",
        "Avionics Telemetry System"
    ]
    products = [
        "Ground Surveillance Radar 2D/3D",
        "Coastal Maritime Surveillance Radar",
        "Radar Target Simulator Unit",
        "Active Radar EW Jammer",
        "Electronic Support Measures (ESM) Pod",
        "EW Jamming Prototype Pod"
    ]

    cursor.execute("SELECT name, city, building, floor, storage_place FROM facility_locations ORDER BY name ASC")
    loc_hierarchies = [dict(r) for r in cursor.fetchall()]
            
    conn.close()
    return {
        "locations": locations,
        "locations_hierarchy": loc_hierarchies,
        "equipments": equipments,
        "pics": pics,
        "conditions": conditions,
        "states": states,
        "projects": projects,
        "programs": projects,
        "systems": systems,
        "products": products,
        "all_states": ALL_STATES,
        "all_conditions": active_conds
    }

# API: Current Inventory State Only (Requirement 65: All historical hidden)
@app.get("/api/tools/current-inventory")
def get_current_inventory():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools ORDER BY name ASC, id ASC")
    tools = [dict(r) for r in cursor.fetchall()]
    
    result = []
    for tool in tools:
        cursor.execute("""
            SELECT date_time, pic, condition, state, price, is_current
            FROM transactions 
            WHERE tool_id = ? 
            ORDER BY date_time DESC, id DESC LIMIT 1
        """, (tool['id'],))
        tx = cursor.fetchone()
        tool['last_date'] = tx['date_time'] if tx else "N/A"
        tool['current_state'] = tx['state'] if tx else "Active"
        tool['current_condition'] = tx['condition'] if tx else "Good / Operational"
        tool['last_pic'] = tx['pic'] if tx else "N/A"
        result.append(tool)
        
    conn.close()
    return result

# API: Tool Detail Master and Historical Repository Files
@app.get("/api/tools/{tool_id}")
def get_tool_detail(tool_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (tool_id,))
    tool = cursor.fetchone()
    if not tool:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
        
    tool_dict = dict(tool)
    
    cursor.execute("""
        SELECT * FROM transactions 
        WHERE tool_id = ? 
        ORDER BY date_time ASC, id ASC
    """, (tool_id,))
    transactions = [dict(r) for r in cursor.fetchall()]
    
    cursor.execute("SELECT SUM(price) as total_expenses FROM transactions WHERE tool_id = ?", (tool_id,))
    sum_res = cursor.fetchone()['total_expenses']
    total_expenses = float(sum_res) if sum_res is not None else 0.0
    
    current_state = "New Purchase"
    is_terminal = False
    if transactions:
        latest_tx = transactions[-1]
        current_state = latest_tx.get('state') or "Active"
        is_terminal = current_state in TERMINAL_STATES
        
    conn.close()
    
    p_dir, d_dir = init_repository_for_tool(tool_id, tool_dict.get('name', 'Equipment'))
    photos = []
    if os.path.exists(p_dir):
        photos = [
            f"/repository/{tool_id}/photos/{fn}" 
            for fn in sorted(os.listdir(p_dir)) 
            if not fn.startswith('.') and fn.lower() != 'desktop.ini' and not fn.endswith('.ini')
        ]
        
    docs = []
    if os.path.exists(d_dir):
        docs = [
            f"/repository/{tool_id}/documents/{fn}" 
            for fn in sorted(os.listdir(d_dir)) 
            if not fn.startswith('.') and fn.lower() != 'desktop.ini' and not fn.endswith('.ini')
        ]
        
    return {
        "tool": tool_dict,
        "transactions": transactions,
        "photos": photos,
        "documents": docs,
        "total_expenses": total_expenses,
        "current_state": current_state,
        "is_terminal": is_terminal
    }

# API: Direct Repository File Upload for Equipment (Robust document & photo upload)
@app.post("/api/tools/{tool_id}/upload")
async def upload_tool_repository_file(
    tool_id: str,
    file_type: str = Form(...),
    file: UploadFile = File(...)
):
    try:
        p_dir, d_dir = init_repository_for_tool(tool_id)
        target_dir = p_dir if file_type == "photo" else d_dir
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_fname = clean_filename(file.filename)
        safe_name = f"{timestamp}_{safe_fname}"
        target_path = os.path.join(target_dir, safe_name)
        
        content = await file.read()
        with open(target_path, "wb") as buffer:
            buffer.write(content)
            
        subfolder = "photos" if file_type == "photo" else "documents"
        return {
            "status": "success",
            "url": f"/repository/{tool_id}/{subfolder}/{safe_name}",
            "filename": safe_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload error: {str(e)}")

# API: Get Transactions with Filters & Header Sorting
@app.get("/api/transactions")
def get_transactions(
    offset: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    location_filter: Optional[str] = None,
    project_filter: Optional[str] = None,
    tool_filter: Optional[str] = None,
    pic_filter: Optional[str] = None,
    condition_filter: Optional[str] = None,
    state_filter: Optional[str] = None,
    sort_order: Optional[str] = "desc"
):
    conn = get_db()
    cursor = conn.cursor()
    
    where_clause = " WHERE 1=1"
    where_params = []
    
    if search and search.strip():
        wildcard = f"%{search.strip()}%"
        where_clause += """ AND (
            tl.name LIKE ? OR 
            tl.brand LIKE ? OR 
            tl.model LIKE ? OR 
            tl.tool_type LIKE ? OR
            tl.serial_number LIKE ? OR
            tl.category LIKE ? OR
            tl.id LIKE ? OR
            tl.room_title LIKE ? OR
            tl.project LIKE ? OR
            t.date_time LIKE ? OR
            t.pic LIKE ? OR 
            t.purpose LIKE ? OR
            t.condition LIKE ? OR
            t.state LIKE ?
        )"""
        where_params.extend([wildcard] * 14)
        
    if location_filter and location_filter.strip():
        where_clause += " AND tl.room_title = ?"
        where_params.append(location_filter.strip())

    if project_filter and project_filter.strip():
        where_clause += " AND tl.project = ?"
        where_params.append(project_filter.strip())
        
    if tool_filter and tool_filter.strip():
        where_clause += " AND (t.tool_id = ? OR tl.name = ?)"
        where_params.extend([tool_filter.strip(), tool_filter.strip()])
        
    if pic_filter and pic_filter.strip():
        where_clause += " AND t.pic = ?"
        where_params.append(pic_filter.strip())
        
    if condition_filter and condition_filter.strip():
        where_clause += " AND t.condition = ?"
        where_params.append(condition_filter.strip())
        
    if state_filter and state_filter.strip():
        where_clause += " AND t.state = ?"
        where_params.append(state_filter.strip())
        
    order_dir = "DESC" if (not sort_order or sort_order.lower() == "desc") else "ASC"
    query = f"""
        SELECT t.id, t.date_time, t.pic, t.purpose, t.condition, t.state, t.price, t.photo_path, t.doc_path, t.is_current,
               tl.id as tool_id, tl.name as tool_name, tl.category, tl.brand, tl.model, tl.tool_type, tl.serial_number, tl.room_title, tl.project
        FROM transactions t
        LEFT JOIN tools tl ON t.tool_id = tl.id
        {where_clause}
        ORDER BY t.date_time {order_dir}, t.id {order_dir} LIMIT ? OFFSET ?
    """
    query_params = list(where_params) + [limit, offset]
    cursor.execute(query, query_params)
    rows = [dict(row) for row in cursor.fetchall()]
    
    for row in rows:
        t_id = row.get('tool_id')
        row['equipment_photo'] = None
        if t_id:
            p_dir = os.path.join(REPOSITORY_DIR, t_id, "photos")
            if os.path.exists(p_dir):
                flist = [f for f in sorted(os.listdir(p_dir)) if not f.startswith('.') and f.lower() != 'desktop.ini']
                if flist:
                    row['equipment_photo'] = f"/repository/{t_id}/photos/{flist[0]}"
    
    count_query = f"""
        SELECT COUNT(*) as total, SUM(t.price) as filtered_expenses
        FROM transactions t
        LEFT JOIN tools tl ON t.tool_id = tl.id
        {where_clause}
    """
    cursor.execute(count_query, where_params)
    count_row = cursor.fetchone()
    total_count = count_row['total']
    filtered_expenses = float(count_row['filtered_expenses']) if count_row['filtered_expenses'] is not None else 0.0
    
    cursor.execute("SELECT SUM(price) as all_expenses FROM transactions")
    all_exp_row = cursor.fetchone()
    all_expenses = float(all_exp_row['all_expenses']) if all_exp_row['all_expenses'] is not None else 0.0
    
    conn.close()
    return {
        "total": total_count,
        "items": rows,
        "offset": offset,
        "limit": limit,
        "total_expenses": filtered_expenses,
        "all_expenses": all_expenses
    }

# API: Create Transaction with Dynamic Registration (Req 59, 61), Relocation (Req 60) & Upload Fix
@app.post("/api/transactions")
async def create_transaction(
    date_time: str = Form(...),
    pic: str = Form(...),
    purpose: str = Form(...),
    tool_id: str = Form(...),
    condition: str = Form(...),
    state: str = Form("Active"),
    price: float = Form(0.0),
    is_current: int = Form(0),
    superadmin_override: int = Form(0),
    move_location: Optional[str] = Form(None),
    new_tool_name: Optional[str] = Form(None),
    new_tool_id: Optional[str] = Form(None),
    new_tool_brand: Optional[str] = Form(None),
    new_tool_model: Optional[str] = Form(None),
    new_tool_type: Optional[str] = Form(None),
    new_tool_serial: Optional[str] = Form(None),
    new_tool_category: Optional[str] = Form("Tools"),
    new_tool_room: Optional[str] = Form("Radar EW Facility Workshop A"),
    new_tool_project: Optional[str] = Form("Radar EW Facility Project"),
    photo: Optional[UploadFile] = File(None),
    document: Optional[UploadFile] = File(None)
):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM system_settings WHERE key = 'room_status'")
    status = cursor.fetchone()
    if status and status['value'] == 'paused':
        conn.close()
        raise HTTPException(status_code=403, detail="Workshop room is currently PAUSED by Superadmin. Transactions are temporarily locked.")

    # Requirement 59 & 61: On-the-fly equipment registration with auto Title Case
    actual_tool_id = tool_id.strip()
    if actual_tool_id == "NEW":
        t_name = new_tool_name.strip().title() if (new_tool_name and new_tool_name.strip()) else "Equipment"
        if new_tool_id and new_tool_id.strip() and new_tool_id.strip() != "NEW":
            actual_tool_id = new_tool_id.strip()
        else:
            # Generate code based on name abbreviation
            words = [w for w in t_name.split() if w]
            prefix = ("".join([w[0].upper() for w in words])[:3]) if words else "TL"
            if len(prefix) < 2:
                prefix = (prefix + "EQ")[:3]
            cursor.execute("SELECT id FROM tools WHERE id LIKE ?", (f"TL-{prefix}-%",))
            existing_ids = {r['id'] for r in cursor.fetchall()}
            cnt = len(existing_ids) + 1
            candidate_id = f"TL-{prefix}-{cnt:02d}"
            while candidate_id in existing_ids:
                cnt += 1
                candidate_id = f"TL-{prefix}-{cnt:02d}"
            actual_tool_id = candidate_id

        # Insert tool if not exists
        cursor.execute("SELECT id FROM tools WHERE id = ?", (actual_tool_id,))
        if not cursor.fetchone():
            b_name = (new_tool_brand or "Standard").strip()
            m_name = (new_tool_model or "Standard").strip()
            t_type = (new_tool_type or "General Equipment").strip()
            s_num = (new_tool_serial or f"SN-{datetime.now().strftime('%Y%m%d%H%M')}").strip()
            r_room = (new_tool_room or "Radar EW Facility Workshop A").strip()
            p_proj = (new_tool_project or "Radar EW Facility Project").strip()
            cat = (new_tool_category or "Tools").strip()
            cursor.execute("""
                INSERT INTO tools (id, name, category, brand, model, tool_type, serial_number, room_title, project)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (actual_tool_id, t_name, cat, b_name, m_name, t_type, s_num, r_room, p_proj))

    # Check terminal state
    cursor.execute("SELECT state FROM transactions WHERE tool_id = ? ORDER BY date_time DESC, id DESC LIMIT 1", (actual_tool_id,))
    latest = cursor.fetchone()
    if latest and latest['state'] in TERMINAL_STATES and not superadmin_override:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"Equipment [{actual_tool_id}] is in terminal state ({latest['state']}). It has been decommissioned/disposed and cannot accept further transactions."
        )

    # Requirement 60: Option to Move Location
    actual_purpose = purpose.strip()
    if move_location and move_location.strip():
        new_loc = move_location.strip()
        cursor.execute("UPDATE tools SET room_title = ? WHERE id = ?", (new_loc, actual_tool_id))
        if f"Relocated to" not in actual_purpose:
            actual_purpose += f" [Relocated to: {new_loc}]"

    p_dir, d_dir = init_repository_for_tool(actual_tool_id)

    photo_path = None
    if photo and photo.filename:
        safe_fname = clean_filename(photo.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(p_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await photo.read())
        photo_path = f"/repository/{actual_tool_id}/photos/{filename}"

    doc_path = None
    if document and document.filename:
        safe_fname = clean_filename(document.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(d_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await document.read())
        doc_path = f"/repository/{actual_tool_id}/documents/{filename}"

    cursor.execute("""
        INSERT INTO transactions (date_time, pic, purpose, tool_id, condition, state, price, photo_path, doc_path, is_current)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (date_time.strip(), pic.strip(), actual_purpose, actual_tool_id, condition.strip(), state.strip(), float(price or 0.0), photo_path, doc_path, is_current))
    
    sync_equipment_current_states(conn, actual_tool_id)
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": f"Transaction logged successfully for [{actual_tool_id}]",
        "tool_id": actual_tool_id
    }

# API: Update Transaction (Superadmin / Admin: edit any log, fix typos, delete image/doc, edit equipment specs)
@app.put("/api/transactions/{trans_id}")
async def update_transaction(
    trans_id: int,
    date_time: str = Form(...),
    pic: str = Form(...),
    purpose: str = Form(...),
    tool_id: str = Form(...),
    condition: str = Form(...),
    state: str = Form("Active"),
    price: float = Form(0.0),
    is_current: int = Form(0),
    photo: Optional[UploadFile] = File(None),
    document: Optional[UploadFile] = File(None),
    delete_photo: int = Form(0),
    delete_document: int = Form(0),
    tool_name: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    room_title: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    role_q: Optional[str] = Query(None, alias="role")
):
    effective_role = (role or role_q or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. Only Admin can edit transaction logs."
        )
    conn = get_db()
    cursor = conn.cursor()
    
    p_dir, d_dir = init_repository_for_tool(tool_id)
    
    update_photo_sql = ""
    update_doc_sql = ""
    extra_params = []

    # Delete existing image
    if int(delete_photo) == 1:
        cursor.execute("SELECT photo_path FROM transactions WHERE id = ?", (trans_id,))
        p_row = cursor.fetchone()
        if p_row and p_row['photo_path'] and p_row['photo_path'].startswith('/repository/') and not p_row['photo_path'].endswith('default_equipment.svg'):
            local_p = os.path.join(BASE_DIR, p_row['photo_path'].lstrip('/').replace('/', os.sep))
            if os.path.exists(local_p):
                try:
                    os.remove(local_p)
                except Exception:
                    pass
        default_svg = f"/repository/{tool_id}/photos/default_equipment.svg"
        update_photo_sql = ", photo_path = ?"
        extra_params.append(default_svg)
    elif photo and photo.filename:
        safe_fname = clean_filename(photo.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(p_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await photo.read())
        photo_path = f"/repository/{tool_id}/photos/{filename}"
        update_photo_sql = ", photo_path = ?"
        extra_params.append(photo_path)

    # Delete existing document
    if int(delete_document) == 1:
        cursor.execute("SELECT doc_path FROM transactions WHERE id = ?", (trans_id,))
        d_row = cursor.fetchone()
        if d_row and d_row['doc_path'] and d_row['doc_path'].startswith('/repository/'):
            local_d = os.path.join(BASE_DIR, d_row['doc_path'].lstrip('/').replace('/', os.sep))
            if os.path.exists(local_d):
                try:
                    os.remove(local_d)
                except Exception:
                    pass
        update_doc_sql = ", doc_path = ?"
        extra_params.append(None)
    elif document and document.filename:
        safe_fname = clean_filename(document.filename)
        filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_fname}"
        dest = os.path.join(d_dir, filename)
        with open(dest, "wb") as buffer:
            buffer.write(await document.read())
        doc_path = f"/repository/{tool_id}/documents/{filename}"
        update_doc_sql = ", doc_path = ?"
        extra_params.append(doc_path)

    sql = f"""
        UPDATE transactions
        SET date_time = ?, pic = ?, purpose = ?, tool_id = ?, condition = ?, state = ?, price = ?, is_current = ?
        {update_photo_sql} {update_doc_sql}
        WHERE id = ?
    """
    params = [date_time, pic, purpose, tool_id, condition, state, price, is_current] + extra_params + [trans_id]
    cursor.execute(sql, params)
    
    # Also update equipment attributes / typos if provided
    t_updates = []
    t_params = []
    if tool_name and tool_name.strip():
        t_updates.append("name = ?")
        t_params.append(tool_name.strip().title())
    if brand and brand.strip():
        t_updates.append("brand = ?")
        t_params.append(brand.strip())
    if model and model.strip():
        t_updates.append("model = ?")
        t_params.append(model.strip())
    if serial_number and serial_number.strip():
        t_updates.append("serial_number = ?")
        t_params.append(serial_number.strip())
    if category and category.strip():
        t_updates.append("category = ?")
        t_params.append(category.strip())
    if room_title and room_title.strip():
        t_updates.append("room_title = ?")
        t_params.append(room_title.strip())
    if project and project.strip():
        t_updates.append("project = ?")
        t_params.append(project.strip())
    if t_updates:
        cursor.execute(f"UPDATE tools SET {', '.join(t_updates)} WHERE id = ?", t_params + [tool_id])

    sync_equipment_current_states(conn, tool_id)
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Transaction updated successfully"}

# API: Explicit Endpoint to Delete Photo from Transaction Log
@app.delete("/api/transactions/{trans_id}/photo")
def delete_transaction_photo(
    trans_id: int,
    role: Optional[str] = Query(None),
    role_f: Optional[str] = Form(None)
):
    effective_role = (role or role_f or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin or Admin can delete images.")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tool_id, photo_path FROM transactions WHERE id = ?", (trans_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found.")
    
    tid = row['tool_id']
    old_photo = row['photo_path']
    if old_photo and old_photo.startswith("/repository/") and not old_photo.endswith("default_equipment.svg"):
        local_file = os.path.join(BASE_DIR, old_photo.lstrip("/").replace("/", os.sep))
        if os.path.exists(local_file):
            try:
                os.remove(local_file)
            except Exception:
                pass
    
    default_svg = f"/repository/{tid}/photos/default_equipment.svg"
    cursor.execute("UPDATE transactions SET photo_path = ? WHERE id = ?", (default_svg, trans_id))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Image deleted successfully from transaction log.", "photo_path": default_svg}

# API: Explicit Endpoint to Delete Document from Transaction Log
@app.delete("/api/transactions/{trans_id}/document")
def delete_transaction_document(
    trans_id: int,
    role: Optional[str] = Query(None),
    role_f: Optional[str] = Form(None)
):
    effective_role = (role or role_f or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin or Admin can delete documents.")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tool_id, doc_path FROM transactions WHERE id = ?", (trans_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction not found.")
    
    old_doc = row['doc_path']
    if old_doc and old_doc.startswith("/repository/"):
        local_file = os.path.join(BASE_DIR, old_doc.lstrip("/").replace("/", os.sep))
        if os.path.exists(local_file):
            try:
                os.remove(local_file)
            except Exception:
                pass
    
    cursor.execute("UPDATE transactions SET doc_path = NULL WHERE id = ?", (trans_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Document removed successfully from transaction log."}

# API: Update Equipment Details (Superadmin / Admin edit typos, brand, model, serial, room, project)
@app.put("/api/tools/{tool_id}")
def update_tool_details(
    tool_id: str,
    name: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    brand: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    tool_type: Optional[str] = Form(None),
    serial_number: Optional[str] = Form(None),
    room_title: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    role_q: Optional[str] = Query(None, alias="role")
):
    effective_role = (role or role_q or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Admin can edit equipment details.")
    
    tid = tool_id.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM tools WHERE id = ?", (tid,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found.")
    
    updates = []
    params = []
    if name is not None and name.strip():
        updates.append("name = ?")
        params.append(name.strip().title())
    if category is not None and category.strip():
        updates.append("category = ?")
        params.append(category.strip())
    if brand is not None and brand.strip():
        updates.append("brand = ?")
        params.append(brand.strip())
    if model is not None and model.strip():
        updates.append("model = ?")
        params.append(model.strip())
    if tool_type is not None and tool_type.strip():
        updates.append("tool_type = ?")
        params.append(tool_type.strip())
    if serial_number is not None and serial_number.strip():
        updates.append("serial_number = ?")
        params.append(serial_number.strip())
    if room_title is not None and room_title.strip():
        updates.append("room_title = ?")
        params.append(room_title.strip())
    if project is not None and project.strip():
        updates.append("project = ?")
        params.append(project.strip())
    
    if updates:
        cursor.execute(f"UPDATE tools SET {', '.join(updates)} WHERE id = ?", params + [tid])
        conn.commit()
    conn.close()
    return {"status": "success", "message": f"Equipment '{tid}' updated successfully."}

# API: Delete Transaction (Superadmin / Admin per Requirement 2.2)
@app.delete("/api/transactions/{trans_id}")
def delete_transaction(
    trans_id: int, 
    role: Optional[str] = Query(None),
    role_f: Optional[str] = Form(None)
):
    effective_role = (role or role_f or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. Only Superadmin or Admin can delete transaction logs."
        )
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tool_id FROM transactions WHERE id = ?", (trans_id,))
    row = cursor.fetchone()
    tool_id = row['tool_id'] if row else None

    cursor.execute("DELETE FROM transactions WHERE id = ?", (trans_id,))
    if tool_id:
        sync_equipment_current_states(conn, tool_id)
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Transaction deleted successfully"}


# API: Save Inventory Stock Opname with Checklist Document (Requirement 65-66)
@app.post("/api/stock-opname")
async def save_stock_opname(
    date_time: str = Form(...),
    pic: str = Form(...),
    location: Optional[str] = Form(None),
    notes: Optional[str] = Form(""),
    opname_document: Optional[UploadFile] = File(None),
    items_json: str = Form(...) # JSON list of verified tool checks
):
    try:
        items = json.loads(items_json)
    except Exception:
        items = []

    doc_web_url = None
    if opname_document and opname_document.filename:
        safe_doc_name = clean_filename(opname_document.filename)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        dest_filename = f"{timestamp}_{safe_doc_name}"
        doc_dest_path = os.path.join(OPNAME_DOC_DIR, dest_filename)

        content = await opname_document.read()
        with open(doc_dest_path, "wb") as f:
            f.write(content)
        doc_web_url = f"/repository/_opname/documents/{dest_filename}"

    conn = get_db()
    cursor = conn.cursor()

    verified_count = sum(1 for it in items if it.get("verified") or it.get("modified"))
    total_count = len(items)

    # Derive summary location from verified/modified items
    distinct_locs = sorted(list(set(
        it.get("location").strip() for it in items if (it.get("verified") or it.get("modified")) and it.get("location") and it.get("location").strip()
    )))
    summary_location = ", ".join(distinct_locs) if distinct_locs else (location or "Per-Item Validated Locations")

    cursor.execute("""
        INSERT INTO stock_opnames (date_time, pic, location, notes, doc_path, verified_count, total_count)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (date_time, pic, summary_location, notes, doc_web_url, verified_count, total_count))

    for it in items:
        if it.get("verified") or it.get("modified"):
            t_id = it.get("tool_id")
            v_cond = (it.get("condition") or "Good / Operational").strip()
            v_state = (it.get("state") or "Active").strip()
            v_loc = (it.get("location") or "").strip()
            v_notes = (it.get("notes") or "Physical Opname verification completed").strip()

            # Update equipment location in tools table
            if v_loc:
                cursor.execute("UPDATE tools SET room_title = ? WHERE id = ?", (v_loc, t_id))

            # Guarantee Opname transaction is chronologically latest
            cursor.execute("SELECT date_time FROM transactions WHERE tool_id = ? ORDER BY date_time DESC, id DESC LIMIT 1", (t_id,))
            latest_tx = cursor.fetchone()
            tx_dt = date_time.strip()
            if latest_tx and latest_tx['date_time'] > tx_dt:
                tx_dt = latest_tx['date_time']

            loc_str = f" @ {v_loc}" if v_loc else ""
            cursor.execute("""
                INSERT INTO transactions (date_time, pic, purpose, tool_id, condition, state, price, doc_path, is_current)
                VALUES (?, ?, ?, ?, ?, ?, 0.0, ?, 1)
            """, (tx_dt, pic, f"[Stock Opname{loc_str}] {v_notes}", t_id, v_cond, v_state, doc_web_url))
            sync_equipment_current_states(conn, t_id)

    conn.commit()
    conn.close()

    return {
        "status": "success",
        "message": f"Stock Opname verified for {verified_count}/{total_count} equipment items. Locations, states & conditions updated successfully.",
        "doc_url": doc_web_url
    }

# API: Report Data for Period (Requirement 61-64)
@app.get("/api/report/data")
def get_report_data(
    start_date: Optional[str] = Query(None),
    finish_date: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    pic: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    state: Optional[str] = Query(None)
):
    conn = get_db()
    cursor = conn.cursor()

    effective_start = start_date.strip() if start_date and start_date.strip() else "2000-01-01"
    effective_finish = finish_date.strip() if finish_date and finish_date.strip() else datetime.now().strftime("%Y-%m-%d")

    where_sql = " WHERE substr(t.date_time, 1, 10) >= ? AND substr(t.date_time, 1, 10) <= ?"
    params = [effective_start, effective_finish]

    if location and location.strip():
        where_sql += " AND tl.room_title = ?"
        params.append(location.strip())

    if project and project.strip():
        where_sql += " AND tl.project = ?"
        params.append(project.strip())

    if pic and pic.strip():
        where_sql += " AND t.pic = ?"
        params.append(pic.strip())

    if condition and condition.strip():
        where_sql += " AND t.condition = ?"
        params.append(condition.strip())

    if state and state.strip():
        where_sql += " AND t.state = ?"
        params.append(state.strip())

    query = f"""
        SELECT t.id, t.date_time, t.pic, t.purpose, t.condition, t.state, t.price, t.photo_path, t.doc_path, t.is_current,
               tl.id as tool_id, tl.name as tool_name, tl.category, tl.brand, tl.model, tl.tool_type, tl.serial_number, tl.room_title, tl.project
        FROM transactions t
        JOIN tools tl ON t.tool_id = tl.id
        {where_sql}
        ORDER BY t.date_time ASC, t.id ASC
    """
    cursor.execute(query, params)
    items = [dict(r) for r in cursor.fetchall()]

    total_expense = sum(float(r['price'] or 0.0) for r in items)

    cursor.execute("SELECT key, value FROM system_settings")
    settings = {r['key']: r['value'] for r in cursor.fetchall()}

    conn.close()
    return {
        "items": items,
        "total_count": len(items),
        "total_expense": total_expense,
        "settings": settings,
        "filter": {
            "start_date": start_date,
            "finish_date": finish_date,
            "location": location or "All Locations",
            "project": project or "All Projects",
            "pic": pic or "All PICs",
            "condition": condition or "All Conditions",
            "state": state or "All States"
        }
    }

# --- CONSUMABLES & MATERIALS ROUTES (Requirement 75) ---
@app.get("/consumables", response_class=HTMLResponse)
def get_consumables_page():
    page_path = os.path.join(BASE_DIR, "consumables.html")
    if os.path.exists(page_path):
        with open(page_path, "r", encoding="utf-8") as f:
            return HTMLResponse(
                content=f.read(),
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0"
                }
            )
    return HTMLResponse(content="<h1>Consumables page template not found</h1>")

@app.get("/api/consumables")
def get_consumables():
    conn = get_db()
    recalculate_consumables_fifo(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM consumables ORDER BY category ASC, name ASC")
    items = [dict(r) for r in cursor.fetchall()]
    
    for item in items:
        cid = item['id']
        cursor.execute("SELECT tx_type, quantity, date_time FROM consumable_transactions WHERE consumable_id = ? ORDER BY date_time ASC, id ASC", (cid,))
        txs = cursor.fetchall()
        
        total_in = 0.0
        total_out = 0.0
        last_dt = item.get('last_restocked') or "-"
        
        for t in txs:
            t_type = (t['tx_type'] or '').upper()
            qty = float(t['quantity'] or 0.0)
            if any(w in t_type for w in ["OUT", "USAGE", "KURANG", "PAKAI", "ISSUE", "DEDUCT", "EXPENSE"]):
                total_out += qty
            elif any(w in t_type for w in ["IN", "INITIAL", "RESTOCK", "PURCHASE"]):
                total_in += qty
            if t['date_time']:
                last_dt = t['date_time']
                
        # If no transactions recorded yet, default total_in to current quantity
        if not txs:
            total_in = float(item['quantity'] or 0.0)
            
        item['total_in'] = total_in
        item['total_out'] = total_out
        item['balance'] = float(item['quantity'] or 0.0)
        item['date_time'] = last_dt
        item['total_value'] = item['balance'] * float(item['unit_price'] or 0.0)
        
    conn.close()
    return items

@app.get("/api/consumables/transactions")
def get_consumables_transactions(limit: int = 150, sort_order: str = "desc"):
    conn = get_db()
    recalculate_consumables_fifo(conn)
    cursor = conn.cursor()
    order = "DESC" if sort_order.lower() == "desc" else "ASC"
    cursor.execute(f"""
        SELECT 
            ct.id, ct.date_time, ct.consumable_id, ct.tx_type, ct.quantity, ct.balance_after,
            ct.pic, ct.purpose, ct.project,
            c.name as consumable_name, c.category, c.unit, c.unit_price, c.location
        FROM consumable_transactions ct
        LEFT JOIN consumables c ON ct.consumable_id = c.id
        ORDER BY ct.date_time {order},
                 CASE WHEN ct.tx_type LIKE '%Initial%' THEN 0 WHEN ct.tx_type LIKE '%IN%' THEN 1 WHEN ct.tx_type LIKE '%ADJUST%' THEN 2 ELSE 3 END {order},
                 ct.id {order}
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    
    for r in rows:
        t_type = (r['tx_type'] or '').upper()
        qty = float(r['quantity'] or 0.0)
        u_price = float(r.get('unit_price') or 0.0)
        if any(w in t_type for w in ["OUT", "USAGE", "KURANG", "PAKAI", "ISSUE", "DEDUCT", "EXPENSE"]):
            r['stock_in'] = 0.0
            r['stock_out'] = qty
            r['expense_amount'] = qty * u_price
        else:
            r['stock_in'] = qty
            r['stock_out'] = 0.0
            r['expense_amount'] = 0.0
    conn.close()
    return rows

@app.post("/api/consumables")
def create_consumable(
    id: Optional[str] = Form(None),
    name: str = Form(...),
    specification: Optional[str] = Form(""),
    category: str = Form("Consumables"),
    unit: str = Form("Pcs"),
    quantity: float = Form(0.0),
    min_stock: float = Form(3.0),
    unit_price: float = Form(0.0),
    location: Optional[str] = Form("Cabinet B - Consumables Shelf"),
    project: Optional[str] = Form("Radar EW Facility Project"),
    date_time: Optional[str] = Form(None)
):
    conn = get_db()
    cursor = conn.cursor()
    cid = (id or "").strip()
    if not cid:
        cid = get_next_auto_id(conn, "consumables", category, name)
    else:
        cursor.execute("SELECT id FROM consumables WHERE id = ?", (cid,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Materials ID '{cid}' already exists!")

    now_str = date_time.strip() if (date_time and date_time.strip()) else datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO consumables (id, name, specification, category, unit, quantity, min_stock, unit_price, location, project, last_restocked)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (cid, name.strip().title(), (specification or "").strip(), category.strip(), unit.strip(), float(quantity), float(min_stock), float(unit_price), (location or "").strip(), (project or "Radar EW Facility Project").strip(), now_str))

    cursor.execute("""
        INSERT INTO consumable_transactions (date_time, consumable_id, tx_type, quantity, balance_after, pic, purpose, project)
        VALUES (?, ?, 'Initial Stock', ?, ?, 'Inventory Officer', 'Initial catalog registration', ?)
    """, (now_str, cid, float(quantity), float(quantity), (project or "Radar EW Facility Project").strip()))

    recalculate_consumables_fifo(conn, cid)
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Consumable '{name}' registered successfully!"}

@app.post("/api/consumables/transaction")
def create_consumable_transaction(
    consumable_id: str = Form(...),
    tx_type: str = Form(...),
    quantity: float = Form(...),
    pic: str = Form(...),
    date_time: Optional[str] = Form(None),
    purpose: Optional[str] = Form(""),
    project: Optional[str] = Form("Radar EW Facility Project")
):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM consumables WHERE id = ?", (consumable_id,))
    item = cursor.fetchone()
    if not item:
        conn.close()
        raise HTTPException(status_code=404, detail="Consumable item not found")

    qty = abs(float(quantity))
    tx_t = tx_type.strip()
    now_str = date_time.strip() if (date_time and date_time.strip()) else datetime.now().strftime("%Y-%m-%d %H:%M")

    cursor.execute("""
        INSERT INTO consumable_transactions (date_time, consumable_id, tx_type, quantity, balance_after, pic, purpose, project)
        VALUES (?, ?, ?, ?, 0.0, ?, ?, ?)
    """, (now_str, consumable_id, tx_t, qty, pic.strip(), (purpose or "").strip(), (project or "Radar EW Facility Project").strip()))

    recalculate_consumables_fifo(conn, consumable_id)

    cursor.execute("SELECT quantity FROM consumables WHERE id = ?", (consumable_id,))
    upd_row = cursor.fetchone()
    final_balance = float(upd_row['quantity']) if upd_row else 0.0

    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": f"Stock updated. New balance: {final_balance} {item['unit']}",
        "new_balance": final_balance
    }

# API: Update Consumable Movement Log / Fix Typos (Superadmin / Admin)
@app.put("/api/consumables/transactions/{tx_id}")
def update_consumable_transaction(
    tx_id: int,
    date_time: Optional[str] = Form(None),
    tx_type: Optional[str] = Form(None),
    quantity: Optional[float] = Form(None),
    pic: Optional[str] = Form(None),
    purpose: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    role_q: Optional[str] = Query(None, alias="role")
):
    effective_role = (role or role_q or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. Only Superadmin or Admin can edit consumable transaction logs."
        )
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM consumable_transactions WHERE id = ?", (tx_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Consumable transaction #{tx_id} not found.")
    
    cid = existing['consumable_id']
    new_dt = date_time.strip() if (date_time and date_time.strip()) else existing['date_time']
    new_type = tx_type.strip() if (tx_type and tx_type.strip()) else existing['tx_type']
    new_qty = abs(float(quantity)) if quantity is not None else float(existing['quantity'])
    new_pic = pic.strip() if (pic and pic.strip()) else existing['pic']
    new_purpose = purpose.strip() if purpose is not None else existing['purpose']
    new_project = project.strip() if (project and project.strip()) else existing['project']
    
    cursor.execute("""
        UPDATE consumable_transactions
        SET date_time = ?, tx_type = ?, quantity = ?, pic = ?, purpose = ?, project = ?
        WHERE id = ?
    """, (new_dt, new_type, new_qty, new_pic, new_purpose, new_project, tx_id))
    
    recalculate_consumables_fifo(conn, cid)
    cursor.execute("SELECT quantity FROM consumables WHERE id = ?", (cid,))
    upd_row = cursor.fetchone()
    calc_balance = float(upd_row['quantity']) if upd_row else 0.0
    
    conn.commit()
    conn.close()
    return {
        "status": "success",
        "message": f"Consumable transaction #{tx_id} updated. Recalculated stock balance: {calc_balance}",
        "new_balance": calc_balance
    }

# API: Update Consumable Item Details / Rename / Fix Typos (Superadmin / Admin)
@app.put("/api/consumables/{consumable_id}")
def update_consumable_details(
    consumable_id: str,
    name: Optional[str] = Form(None),
    specification: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    unit: Optional[str] = Form(None),
    min_stock: Optional[float] = Form(None),
    unit_price: Optional[float] = Form(None),
    location: Optional[str] = Form(None),
    project: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    role_q: Optional[str] = Query(None, alias="role")
):
    effective_role = (role or role_q or "guest").strip().lower()
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(
            status_code=403, 
            detail="Permission denied. Only Superadmin or Admin can edit consumable details."
        )
    
    cid = consumable_id.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM consumables WHERE id = ?", (cid,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Consumable '{cid}' not found.")
    
    new_name = name.strip().title() if (name and name.strip()) else existing['name']
    new_spec = specification.strip() if specification is not None else existing['specification']
    new_cat = category.strip() if (category and category.strip()) else existing['category']
    new_unit = unit.strip() if (unit and unit.strip()) else existing['unit']
    new_min = float(min_stock) if min_stock is not None else float(existing['min_stock'])
    new_price = float(unit_price) if unit_price is not None else float(existing['unit_price'])
    new_loc = location.strip() if location is not None else existing['location']
    new_proj = project.strip() if (project and project.strip()) else existing['project']
    
    cursor.execute("""
        UPDATE consumables
        SET name = ?, specification = ?, category = ?, unit = ?, min_stock = ?, unit_price = ?, location = ?, project = ?
        WHERE id = ?
    """, (new_name, new_spec, new_cat, new_unit, new_min, new_price, new_loc, new_proj, cid))
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Consumable '{cid}' ({new_name}) details updated successfully."}


# --- FACILITY LOCATIONS API ---
@app.get("/api/locations")
def get_locations():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM facility_locations ORDER BY name ASC")
    registered_locs = [r['name'] for r in cursor.fetchall()]
    
    # Also collect any existing locations in tools table to ensure zero data loss
    cursor.execute("SELECT DISTINCT room_title FROM tools WHERE room_title IS NOT NULL AND room_title != ''")
    tool_locs = [r['room_title'] for r in cursor.fetchall()]
    
    all_unique = sorted(list(set(registered_locs + tool_locs)))
    conn.close()
    return all_unique

@app.get("/api/locations/detailed")
def get_locations_detailed():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, created_at, city, building, floor, storage_place FROM facility_locations ORDER BY name ASC")
    locs = [dict(r) for r in cursor.fetchall()]
    
    # Check for any unlisted room titles in tools
    cursor.execute("SELECT DISTINCT room_title FROM tools WHERE room_title IS NOT NULL AND room_title != ''")
    tool_rooms = [r['room_title'] for r in cursor.fetchall()]
    reg_names = {l['name'] for l in locs}
    for tr in tool_rooms:
        if tr not in reg_names:
            locs.append({
                'id': 0,
                'name': tr,
                'created_at': '-',
                'city': 'Bandung',
                'building': 'Unassigned',
                'floor': '-',
                'storage_place': '-'
            })
            reg_names.add(tr)
            
    # Calculate item counts
    for l in locs:
        cursor.execute("SELECT COUNT(*) as cnt FROM tools WHERE room_title = ?", (l['name'],))
        l['equipment_count'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM consumables WHERE location = ?", (l['name'],))
        l['consumables_count'] = cursor.fetchone()['cnt']
        
    conn.close()
    return locs

@app.post("/api/locations")
def create_location(
    name: str = Form(...),
    city: str = Form("Bandung"),
    building: str = Form("Gedung Radar & EW"),
    floor: str = Form("Lantai 1"),
    storage_place: str = Form("Rack Equipment & Bench"),
    role: str = Form("admin")
):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can register new facility locations.")
    
    loc_name = name.strip()
    if not loc_name:
        raise HTTPException(status_code=400, detail="Location name cannot be empty.")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM facility_locations WHERE LOWER(name) = LOWER(?)", (loc_name,))
    if cursor.fetchone():
        conn.close()
        return {"status": "success", "message": f"Location '{loc_name}' is already registered."}
        
    now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO facility_locations (name, created_at, city, building, floor, storage_place) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, (loc_name, now_dt, city.strip(), building.strip(), floor.strip(), storage_place.strip()))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Location '{loc_name}' registered successfully."}

@app.delete("/api/locations/{location_name}")
def delete_location(location_name: str, role: str = Query("admin")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can delete facility locations.")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM facility_locations WHERE name = ?", (location_name,))
    # Orphaned items move to Unknown Location
    cursor.execute("UPDATE tools SET room_title = 'Unknown Location' WHERE room_title = ?", (location_name,))
    cursor.execute("UPDATE consumables SET location = 'Unknown Location' WHERE location = ?", (location_name,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Location '{location_name}' deleted. Remaining equipment moved to 'Unknown Location'."}

@app.put("/api/locations/{location_name}/details")
def update_location_details(
    location_name: str,
    new_name: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    building: Optional[str] = Form(None),
    floor: Optional[str] = Form(None),
    storage_place: Optional[str] = Form(None),
    role: str = Form("admin")
):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can edit facility locations.")
        
    old_loc = location_name.strip()
    target_name = (new_name.strip() if new_name and new_name.strip() else old_loc)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM facility_locations WHERE name = ?", (old_loc,))
    row = cursor.fetchone()
    if not row:
        now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.execute("INSERT INTO facility_locations (name, created_at, city, building, floor, storage_place) VALUES (?, ?, ?, ?, ?, ?)",
                       (target_name, now_dt, (city or 'Bandung').strip(), (building or 'Gedung Radar & EW').strip(), (floor or 'Lantai 1').strip(), (storage_place or 'Rack & Storage').strip()))
    else:
        cursor.execute("""
            UPDATE facility_locations 
            SET name = ?,
                city = COALESCE(?, city),
                building = COALESCE(?, building),
                floor = COALESCE(?, floor),
                storage_place = COALESCE(?, storage_place)
            WHERE name = ?
        """, (target_name, city.strip() if city else None, building.strip() if building else None, floor.strip() if floor else None, storage_place.strip() if storage_place else None, old_loc))
        
    if target_name != old_loc:
        cursor.execute("UPDATE tools SET room_title = ? WHERE room_title = ?", (target_name, old_loc))
        cursor.execute("UPDATE consumables SET location = ? WHERE location = ?", (target_name, old_loc))
        
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Location '{target_name}' details updated successfully."}

@app.put("/api/locations/{location_name}")
def rename_location(
    location_name: str, 
    new_name: Optional[str] = Form(None), 
    role: Optional[str] = Form(None),
    new_name_q: Optional[str] = Query(None, alias="new_name"),
    role_q: Optional[str] = Query(None, alias="role")
):
    effective_role = (role or role_q or "admin").strip()
    effective_new_name = (new_name or new_name_q or "").strip()
    
    if effective_role not in ["admin", "superadmin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can rename facility locations.")
        
    old_loc = location_name.strip()
    if not effective_new_name:
        raise HTTPException(status_code=400, detail="New location name cannot be empty.")
    if old_loc == effective_new_name:
        return {"status": "success", "message": "Location name unchanged."}

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM facility_locations WHERE name = ?", (effective_new_name,))
    if cursor.fetchone():
        cursor.execute("DELETE FROM facility_locations WHERE name = ?", (old_loc,))
    else:
        cursor.execute("UPDATE facility_locations SET name = ? WHERE name = ?", (effective_new_name, old_loc))
        
    cursor.execute("UPDATE tools SET room_title = ? WHERE room_title = ?", (effective_new_name, old_loc))
    cursor.execute("UPDATE consumables SET location = ? WHERE location = ?", (effective_new_name, old_loc))
    
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Location '{old_loc}' successfully renamed to '{effective_new_name}'."}

@app.post("/api/locations/reassign-items")
def reassign_location_items(
    from_location: str = Form(...),
    to_location: str = Form(...),
    role: str = Form("admin")
):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Administrator can reassign equipment.")
        
    from_loc = from_location.strip()
    to_loc = to_location.strip()
    if not from_loc or not to_loc:
        raise HTTPException(status_code=400, detail="Source and destination locations cannot be empty.")
    if from_loc == to_loc:
        return {"status": "success", "message": "Source and destination are identical."}
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tools SET room_title = ? WHERE room_title = ?", (to_loc, from_loc))
    t_cnt = cursor.rowcount
    cursor.execute("UPDATE consumables SET location = ? WHERE location = ?", (to_loc, from_loc))
    c_cnt = cursor.rowcount
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Successfully moved {t_cnt} equipment items and {c_cnt} consumables from '{from_loc}' to '{to_loc}'."}


# --- CONDITION LIST MANAGEMENT API ---
@app.get("/api/conditions")
def get_conditions_api():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, sort_order, created_at FROM facility_conditions ORDER BY sort_order ASC, id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    if not rows:
        return [{"id": idx, "name": c, "sort_order": idx, "created_at": "-"} for idx, c in enumerate(ALL_CONDITIONS)]
    return rows

@app.post("/api/conditions")
def add_condition_api(name: str = Form(...), role: str = Form("admin")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied.")
    cond_name = name.strip()
    if not cond_name:
        raise HTTPException(status_code=400, detail="Condition name cannot be empty.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM facility_conditions WHERE LOWER(name) = LOWER(?)", (cond_name,))
    if cursor.fetchone():
        conn.close()
        return {"status": "success", "message": f"Condition '{cond_name}' already exists."}
    cursor.execute("SELECT MAX(sort_order) as m FROM facility_conditions")
    m = cursor.fetchone()['m']
    max_order = (m if m is not None else 0) + 1
    now_dt = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO facility_conditions (name, sort_order, created_at) VALUES (?, ?, ?)",
                   (cond_name, max_order, now_dt))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Condition '{cond_name}' added successfully."}

@app.put("/api/conditions/{old_name}")
def rename_condition_api(old_name: str, new_name: str = Form(...), role: str = Form("admin")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied.")
    old_c = old_name.strip()
    new_c = new_name.strip()
    if not new_c:
        raise HTTPException(status_code=400, detail="New condition name cannot be empty.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE facility_conditions SET name = ? WHERE name = ?", (new_c, old_c))
    cursor.execute("UPDATE transactions SET condition = ? WHERE condition = ?", (new_c, old_c))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Condition renamed from '{old_c}' to '{new_c}'."}

@app.delete("/api/conditions/{name}")
def delete_condition_api(name: str, role: str = Query("admin")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied.")
    cond_name = name.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM facility_conditions WHERE name = ?", (cond_name,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Condition '{cond_name}' deleted."}


# --- PRINTABLE A4 STOCK OPNAME CURRENT STATE CHECKLIST (Requirement 76) ---
@app.get("/opname/print-checklist", response_class=HTMLResponse)
def print_stock_opname_checklist():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools ORDER BY room_title ASC, name ASC, id ASC")
    tools = [dict(r) for r in cursor.fetchall()]
    
    for tool in tools:
        cursor.execute("""
            SELECT date_time, pic, condition, state 
            FROM transactions 
            WHERE tool_id = ? 
            ORDER BY date_time DESC, id DESC LIMIT 1
        """, (tool['id'],))
        tx = cursor.fetchone()
        tool['last_date'] = tx['date_time'] if tx else "-"
        tool['current_state'] = tx['state'] if tx else "Active"
        tool['current_condition'] = tx['condition'] if tx else "Good / Operational"
        tool['last_pic'] = tx['pic'] if tx else "-"
        
    cursor.execute("SELECT key, value FROM system_settings")
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    signatories = get_current_signatories(conn)
    report_logo_html = get_report_logo_html(settings)
    conn.close()
    
    rows_html = ""
    for idx, t in enumerate(tools, 1):
        rows_html += f"""
        <tr>
            <td style="text-align:center; font-weight:bold;">{idx}</td>
            <td><strong>{t['id']}</strong></td>
            <td><strong>{t['name']}</strong><br><small style="color:#555;">{t['brand']} {t['model']}</small></td>
            <td><small>{t['serial_number']}</small></td>
            <td><small>{t['room_title']}</small></td>
            <td style="text-align:center; font-weight:bold; color:#1a7f37; font-size:9px;">{t['current_state']}</td>
            <td><small>{t['current_condition']}</small></td>
            <td style="text-align:center;">
                <div style="font-size:8.5px;">[ ] OK<br>[ ] DISC</div>
            </td>
            <td style="border-bottom:1px dashed #999;"></td>
        </tr>
        """
        
    audit_date = datetime.now().strftime("%d %B %Y")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Official Stock Opname Checklist - Current State</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 12mm 10mm;
        }}
        *, *::before, *::after {{
            box-sizing: border-box;
            font-family: Arial, Helvetica, sans-serif !important;
        }}
        body {{
            background: #fff;
            color: #000;
            font-size: 10px;
            line-height: 1.35;
            padding: 8px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #000;
            padding-bottom: 6px;
            margin-bottom: 8px;
        }}
        .header-title h1 {{
            font-size: 15px;
            font-weight: bold;
            margin: 0 0 2px 0;
            text-transform: uppercase;
        }}
        .header-title h2 {{
            font-size: 11px;
            font-weight: normal;
            color: #333;
            margin: 0;
        }}
        .meta-strip {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            background: #f4f4f4;
            border: 1px solid #ccc;
            padding: 6px 8px;
            font-size: 9.5px;
            margin-bottom: 10px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 9px;
            margin-bottom: 14px;
        }}
        th, td {{
            border: 1px solid #666;
            padding: 4px 5px;
            vertical-align: middle;
        }}
        th {{
            background: #e9ecef;
            font-weight: bold;
            text-align: center;
        }}
        .footer-signatures {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 12px;
            margin-top: 20px;
            page-break-inside: avoid;
        }}
        .sign-col {{
            text-align: center;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 8px 6px;
            background: #fafafa;
        }}
        .sign-label {{
            font-weight: bold;
            font-size: 10.5px;
            text-transform: uppercase;
            color: #1f883d;
        }}
        .sign-title {{
            font-size: 9.5px;
            color: #444;
            margin-top: 2px;
            font-weight: 600;
        }}
        .sign-space {{
            height: 48px;
        }}
        .sign-line {{
            border-top: 1px solid #000;
            font-weight: bold;
            font-size: 10.5px;
            padding-top: 3px;
            margin: 0 8px;
        }}
        .sign-sub {{
            font-size: 8.5px;
            color: #666;
            margin-top: 2px;
        }}
        .no-print {{
            background: #1f883d;
            color: #fff;
            padding: 8px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            border-radius: 4px;
        }}
        @media print {{
            .no-print {{ display: none; }}
            body {{ padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="no-print">
        <span><strong>Official Inventory Physical Stock Opname Checklist (A4 Vertical)</strong></span>
        <div>
            <button onclick="window.print()" style="background:#fff; color:#1f883d; border:none; padding:5px 12px; font-weight:bold; cursor:pointer; border-radius:4px;">Print</button>
            <button onclick="window.close()" style="background:transparent; color:#fff; border:1px solid #fff; padding:5px 12px; font-weight:bold; cursor:pointer; border-radius:4px; margin-left:6px;">Close</button>
        </div>
    </div>

    <div class="header">
        <div style="display:flex; align-items:center; gap:12px;">
            {report_logo_html}
            <div class="header-title">
                <h1>{settings.get('room_title', 'RADAR EW FACILITY WORKSHOP')}</h1>
                <h2>Lembar Stock Opname Fisik - Status dan Kondisi Terkini (A4 Vertical)</h2>
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-weight:bold; font-size:10px;">FORM NO: OPNAME-RADAR-EW</div>
            <div style="font-size:9px; color:#555;">Audit Execution Date: {audit_date}</div>
        </div>
    </div>

    <div class="meta-strip">
        <div><strong>Facility:</strong> {settings.get('room_title', 'Radar EW Facility')}</div>
        <div><strong>Group Unit:</strong> {settings.get('group_title', 'EW Maintenance')}</div>
        <div><strong>Total Equipment Items:</strong> {len(tools)} units</div>
        <div><strong>Physical Inspector / PIC:</strong> {signatories['dibuat_name']}</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:24px;">No</th>
                <th style="width:65px;">Tool ID</th>
                <th style="width:130px;">Equipment &amp; Model</th>
                <th style="width:85px;">Serial (S/N)</th>
                <th style="width:90px;">Location</th>
                <th style="width:60px;">State</th>
                <th style="width:75px;">Condition</th>
                <th style="width:50px;">Physical</th>
                <th>Auditor Verification Notes</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="footer-signatures">
        <div class="sign-col">
            <div class="sign-label">{signatories['dibuat_label']}</div>
            <div class="sign-title">{signatories['dibuat_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['dibuat_name']}</div>
            <div class="sign-sub">Tgl Audit: {audit_date}</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['diperiksa_label']}</div>
            <div class="sign-title">{signatories['diperiksa_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['diperiksa_name']}</div>
            <div class="sign-sub">Diperiksa &amp; Diverifikasi</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['disetujui_label']}</div>
            <div class="sign-title">{signatories['disetujui_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['disetujui_name']}</div>
            <div class="sign-sub">Disetujui &amp; Stempel Workshop</div>
        </div>
    </div>

    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 600);
        }};
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


# Static Repository File Server
@app.get("/repository/{tool_id}/{subfolder}/{filename}")
def serve_repository_file(tool_id: str, subfolder: str, filename: str):
    file_path = os.path.join(REPOSITORY_DIR, tool_id, subfolder, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    fallback = os.path.join(BASE_DIR, "repository", tool_id, subfolder, filename)
    if os.path.exists(fallback):
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Repository asset not found")

@app.get("/repository/_opname/documents/{filename}")
def serve_opname_file(filename: str):
    file_path = os.path.join(OPNAME_DOC_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    fallback = os.path.join(BASE_DIR, "repository", "_opname", "documents", filename)
    if os.path.exists(fallback):
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Opname document not found")

@app.get("/repository/_branding/{filename}")
def serve_branding_file(filename: str):
    safe_name = os.path.basename(filename)
    file_path = os.path.join(BRANDING_DIR, safe_name)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    fallback = os.path.join(BASE_DIR, "repository", "_branding", safe_name)
    if os.path.exists(fallback):
        return FileResponse(fallback)
    raise HTTPException(status_code=404, detail="Branding asset not found")

# --- DETAIL PAGE ROUTE ---
DETAIL_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Equipment Detail & Repository - __TOOL_ID__</title>
    <style>
        *, *::before, *::after {
            box-sizing: border-box;
            margin: 0; padding: 0;
            font-family: Arial, Helvetica, sans-serif !important;
        }
        :root[data-theme="light"] {
            --bg-body: #ffffff;
            --bg-card: #f8f9fa;
            --border: #d0d7de;
            --border-subtle: #eaeef2;
            --text-main: #1f2328;
            --text-muted: #656d76;
            --text-current: #1a7f37;
            --text-earlier: #767676;
            --accent: #1f883d;
            --tag-bg: #eef1f4;
        }
        :root[data-theme="dark"] {
            --bg-body: #0d1117;
            --bg-card: #161b22;
            --border: #30363d;
            --border-subtle: #21262d;
            --text-main: #e6edf3;
            --text-muted: #8b949e;
            --text-current: #3fb950;
            --text-earlier: #8b949e;
            --accent: #238636;
            --tag-bg: #21262d;
        }
        body {
            background: var(--bg-body);
            color: var(--text-main);
            padding: 24px;
            font-size: 14px;
        }
        .container {
            max-width: 100%;
            width: 100%;
            margin: 0;
            padding: 16px 28px;
        }
        .header-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        .btn-back {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            text-decoration: none;
            color: var(--text-main);
            font-weight: bold;
            padding: 8px 16px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 6px;
            cursor: pointer;
        }
        .btn-back:hover { border-color: var(--accent); color: var(--accent); }
        .grid-layout {
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 24px;
        }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 24px;
        }
        .card h2 {
            font-size: 1.1rem;
            margin-bottom: 16px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .spec-row {
            display: flex;
            justify-content: space-between;
            padding: 7px 0;
            border-bottom: 1px dashed var(--border-subtle);
        }
        .spec-label { color: var(--text-muted); font-size: 0.85rem; }
        .spec-val { font-weight: bold; }
        .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
            gap: 10px;
            margin-top: 12px;
        }
        .gallery-item {
            border: 1px solid var(--border);
            border-radius: 4px;
            overflow: hidden;
            height: 80px;
            background: #000;
        }
        .gallery-item img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .gallery-item img:hover { transform: scale(1.05); }
        .doc-list { list-style: none; margin-top: 12px; }
        .doc-item {
            padding: 8px 12px;
            background: var(--tag-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .doc-link {
            color: var(--accent);
            text-decoration: none;
            font-weight: bold;
            font-size: 0.85rem;
            display: flex;
            align-items: center;
            gap: 6px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .doc-link:hover { text-decoration: underline; }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }
        th, td {
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
        }
        th {
            background: var(--tag-bg);
            color: var(--text-muted);
            font-weight: bold;
        }
        th.col-purpose,
        td.col-purpose {
            white-space: normal !important;
            min-width: 250px;
            max-width: 450px;
            word-break: break-word;
            line-height: 1.4;
        }
        .state-current { font-weight: bold; color: var(--text-current); }
        .state-past { color: var(--text-earlier); font-style: italic; }
        .date-current { color: var(--text-current); font-weight: bold; }
        .date-earlier { color: var(--text-earlier); }
        .terminal-banner {
            background: #ffebe9;
            color: #cf222e;
            border: 1px solid #ff8182;
            padding: 12px;
            border-radius: 6px;
            font-weight: bold;
            margin-bottom: 16px;
            display: none;
        }
        :root[data-theme="dark"] .terminal-banner {
            background: #490202;
            color: #ff7b72;
            border-color: #cf222e;
        }
        .upload-box {
            border: 2px dashed var(--border);
            border-radius: 6px;
            padding: 14px;
            text-align: center;
            margin-top: 12px;
            background: var(--bg-body);
        }
        .form-control {
            width: 100%;
            padding: 8px 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-card);
            color: var(--text-main);
            font-size: 0.85rem;
            margin-bottom: 8px;
        }
        .btn-action {
            padding: 8px 14px;
            background: var(--accent);
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
        }
        .btn-action:hover { opacity: 0.9; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header-bar">
            <div>
                <a href="/" class="btn-back">Back</a>
                <h1 style="margin-top:12px; font-size:1.4rem;" id="toolHeaderTitle">Equipment Repository: Loading...</h1>
                <div style="color:var(--text-muted); font-size:0.85rem; margin-top:2px;" id="toolHeaderSubtitle">Radar EW Historical Facility Asset</div>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
                <button class="btn-back" onclick="window.open('/detail/' + toolId + '/print', '_blank')" style="color:#0969da; border-color:#0969da; font-weight:bold;">Print</button>
                <button class="btn-action" onclick="openDetailNewTxModal()" style="background:#1f883d;">Log</button>
                <button class="btn-back" id="btnAdminTransfer" onclick="openTransferModal()" style="display:none; color:#0969da; border-color:#0969da;">Transfer</button>
            </div>
        </div>

        <div id="terminalAlert" class="terminal-banner">
            ⚠️ NOTICE: This equipment is in terminal state (<span id="terminalStateName"></span>). It has been decommissioned or disposed.
        </div>

        <div class="grid-layout">
            <div>
                <div class="card">
                    <h2>Equipment Identity</h2>
                    <div class="spec-row"><span class="spec-label">Tool ID</span><span class="spec-val" id="spId">-</span></div>
                    <div class="spec-row"><span class="spec-label">General Name</span><span class="spec-val" id="spName">-</span></div>
                    <div class="spec-row"><span class="spec-label">Brand</span><span class="spec-val" id="spBrand">-</span></div>
                    <div class="spec-row"><span class="spec-label">Model</span><span class="spec-val" id="spModel">-</span></div>
                    <div class="spec-row"><span class="spec-label">Type</span><span class="spec-val" id="spType">-</span></div>
                    <div class="spec-row"><span class="spec-label">Serial Number</span><span class="spec-val" id="spSerial">-</span></div>
                    <div class="spec-row"><span class="spec-label">Category</span><span class="spec-val" id="spCategory">-</span></div>
                    <div class="spec-row"><span class="spec-label">Location</span><span class="spec-val" id="spLocation">-</span></div>
                    <div class="spec-row"><span class="spec-label">Project / Program</span><span class="spec-val" style="color:var(--accent);" id="spProject">-</span></div>
                    <div class="spec-row"><span class="spec-label">Current State</span><span class="spec-val state-current" id="spCurrentState">-</span></div>
                    <div class="spec-row" style="border-bottom:none; margin-top:6px;">
                        <span class="spec-label">Total Lifetime Expenses (IDR)</span>
                        <span class="spec-val" style="color:var(--accent); font-size:1.05rem;" id="spExpenses">0</span>
                    </div>
                    <div id="superadminEqActions" style="display:none; margin-top:14px; padding-top:10px; border-top:1px dashed var(--border); display:flex; flex-direction:column; gap:6px;">
                        <button type="button" onclick="openEditEquipmentModal()" class="btn-action" style="background:#0969da; width:100%; font-size:0.8rem; margin-bottom:6px;">✏️ Edit Equipment Details / Fix Typos</button>
                        <button type="button" onclick="deleteCurrentEquipment()" class="btn-action" style="background:#cf222e; width:100%; font-size:0.8rem;">Delete Equipment</button>
                    </div>
                </div>

                <div class="card">
                    <h2>Photo Repository (<span id="photoCount">0</span>)</h2>
                    <div class="gallery-grid" id="photoGallery"></div>
                    <div class="upload-box">
                        <form onsubmit="handleRepoUpload(event, 'photo')">
                            <label style="font-size:0.75rem; font-weight:bold; color:var(--text-muted); display:block; margin-bottom:4px;">Upload New Photo</label>
                            <input type="file" id="newPhotoFile" accept="image/*" required style="font-size:0.8rem; margin-bottom:6px;">
                            <button type="submit" class="btn-action" style="padding:4px 10px; font-size:0.75rem;">Upload</button>
                        </form>
                    </div>
                </div>

                <div class="card">
                    <h2>Document Repository (<span id="docCount">0</span>)</h2>
                    <ul class="doc-list" id="docList"></ul>
                    <div class="upload-box">
                        <form onsubmit="handleRepoUpload(event, 'document')">
                            <label style="font-size:0.75rem; font-weight:bold; color:var(--text-muted); display:block; margin-bottom:4px;">
                                Upload Document (PDF, DOCX, XLSX, TXT, etc.)
                            </label>
                            <input type="file" id="newDocFile" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,.rar,image/*" required style="font-size:0.8rem; margin-bottom:6px;">
                            <button type="submit" class="btn-action" style="padding:4px 10px; font-size:0.75rem;">Upload</button>
                        </form>
                    </div>
                </div>
            </div>

            <div>
                <div class="card" style="overflow-x:auto;">
                    <h2>Lifetime Historical Sequence (<span id="txCount">0</span> logs)</h2>
                    <table>
                        <thead>
                            <tr>
                                <th style="width:40px; text-align:center;">No</th>
                                <th onclick="toggleDateSort()" style="cursor:pointer; user-select:none; color:var(--text-main);" title="Click to toggle Date Sort (Default Descending)">
                                    Date & Time <span id="sortDateIcon">▼</span>
                                </th>
                                <th>State</th>
                                <th>Condition</th>
                                <th style="text-align:right;">Expenses (IDR)</th>
                                <th>PIC</th>
                                <th class="col-purpose">Purpose / Activity</th>
                                <th>Photo</th>
                                <th>Document</th>
                                <th style="width:70px; text-align:center;" class="admin-only-col">Action</th>
                            </tr>
                        </thead>
                        <tbody id="txTableBody">
                            <tr><td colspan="8" style="text-align:center; color:var(--text-muted);">Loading logs...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- Modal for Logging Transaction Directly inside Detail Page -->
    <div id="detailTxModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:99999; justify-content:center; align-items:center;">
        <div style="background:var(--bg-card); border:1px solid var(--border); border-radius:8px; width:480px; padding:20px;">
            <h3 style="margin-bottom:14px; font-size:1rem;">Log Transaction for this Equipment</h3>
            <form onsubmit="saveDetailTransaction(event)">
                <!-- Requirement 79: Photo & Document Upload on top of form for item awareness & preventing mistakes -->
                <div style="background:var(--tag-bg); padding:10px 12px; border-radius:6px; border:1px solid var(--border); margin-bottom:12px;">
                    <div style="font-size:0.75rem; font-weight:bold; color:var(--text-muted); margin-bottom:8px; text-transform:uppercase; letter-spacing:0.5px;">
                        📸 Visual Item Verification & Media Upload
                    </div>
                    <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Photo Upload (Optional)</label>
                    <input type="file" id="dtPhoto" accept="image/*" class="form-control" style="font-size:0.8rem; margin-bottom:6px;" onchange="previewDtPhoto(this)">
                    <div id="dtPhotoPreviewBox" style="display:none; margin-bottom:8px;">
                        <img id="dtPhotoPreview" src="" alt="Selected Photo" style="max-height:85px; max-width:100%; border-radius:4px; border:1px solid var(--border); object-fit:contain; display:block;">
                    </div>

                    <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Document Upload (Optional)</label>
                    <input type="file" id="dtDoc" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,image/*" class="form-control" style="font-size:0.8rem; margin-bottom:2px;">
                    <div style="font-size:0.7rem; color:var(--text-muted);">PDF, DOCX, XLSX, TXT, CSV, etc.</div>
                </div>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Date & Time *</label>
                <input type="text" id="dtDateTime" class="form-control" required>
                
                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">State Cycle *</label>
                <select id="dtState" class="form-control" required>
                    <option value="Active">Active (Operational)</option>
                    <option value="Maintenance">Maintenance</option>
                    <option value="Repair">Repair</option>
                    <option value="Borrow">Borrow</option>
                    <option value="Transfer">Transfer</option>
                    <option value="New Purchase">New Purchase</option>
                    <option value="Damage">Damage</option>
                    <option value="Broken">Broken</option>
                    <option value="Lost">Lost</option>
                    <option value="Junk">Junk</option>
                    <option value="Donated">Donated</option>
                    <option value="Sell">Sell</option>
                    <option value="Scrapped">Scrapped</option>
                    <option value="Retired">Retired</option>
                    <option value="Dispose">Dispose</option>
                </select>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Current Condition *</label>
                <select id="dtCondition" class="form-control" required>
                    <option value="Good / Operational">Good / Operational</option>
                    <option value="Calibrated & Certified">Calibrated & Certified</option>
                    <option value="Brand New / Sealed">Brand New / Sealed</option>
                    <option value="Fair / Minor Wear">Fair / Minor Wear</option>
                    <option value="Needs Cleaning / Consumables">Needs Cleaning / Consumables</option>
                    <option value="Needs Calibration / Maintenance">Needs Calibration / Maintenance</option>
                    <option value="Under Repair">Under Repair</option>
                    <option value="Damaged / Degraded">Damaged / Degraded</option>
                    <option value="Broken / Inoperable">Broken / Inoperable</option>
                    <option value="Decommissioned / Disposed">Decommissioned / Disposed</option>
                </select>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Expense / Price in IDR</label>
                <input type="text" inputmode="numeric" id="dtPrice" class="form-control" value="0" oninput="formatNumberInput(this)">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">PIC *</label>
                <input type="text" id="dtPic" class="form-control" required placeholder="e.g. Amina K.">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Purpose / Activity *</label>
                <textarea id="dtPurpose" class="form-control" rows="3" required placeholder="Activity details..."></textarea>

                <div style="display:flex; justify-content:flex-end; gap:8px;">
                    <button type="button" onclick="closeDetailNewTxModal()" class="btn-back">Cancel</button>
                    <button type="submit" class="btn-action">Save</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal for Project Transfer -->
    <div id="transferModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:99999; justify-content:center; align-items:center;">
        <div style="background:var(--bg-card); border:1px solid var(--border); border-radius:8px; width:440px; padding:20px;">
            <h3 style="margin-bottom:14px; font-size:1rem;">Transfer Project / Program</h3>
            <form onsubmit="executeProjectTransfer(event)">
                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">New Target Project / Program *</label>
                <input type="text" id="tfProject" class="form-control" required placeholder="e.g. Maritime Surveillance Radars">
                
                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Authorizing PIC *</label>
                <input type="text" id="tfPic" class="form-control" required placeholder="e.g. Administrator">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Transfer Reason / Authorization Note *</label>
                <textarea id="tfReason" class="form-control" rows="3" required placeholder="Official justification for program transfer..."></textarea>

                <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:14px;">
                    <button type="button" onclick="closeTransferModal()" class="btn-back">Cancel</button>
                    <button type="submit" class="btn-action" style="background:#0969da;">Transfer</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal for Editing Equipment Details / Fixing Typos -->
    <div id="editEquipmentModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:99999; justify-content:center; align-items:center;">
        <div style="background:var(--bg-card); border:1px solid var(--border); border-radius:8px; width:480px; padding:20px; max-height:90vh; overflow-y:auto;">
            <h3 style="margin-bottom:14px; font-size:1rem;">✏️ Edit Equipment Details / Fix Typos</h3>
            <form onsubmit="saveEditEquipment(event)">
                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">General Name *</label>
                <input type="text" id="eeName" class="form-control" required style="margin-bottom:8px;">

                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Brand</label>
                        <input type="text" id="eeBrand" class="form-control" style="margin-bottom:8px;">
                    </div>
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Model</label>
                        <input type="text" id="eeModel" class="form-control" style="margin-bottom:8px;">
                    </div>
                </div>

                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Type</label>
                        <input type="text" id="eeType" class="form-control" style="margin-bottom:8px;">
                    </div>
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Serial Number</label>
                        <input type="text" id="eeSerial" class="form-control" style="margin-bottom:8px;">
                    </div>
                </div>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Category</label>
                <select id="eeCategory" class="form-control" style="margin-bottom:8px;">
                    <option value="Instrumentation">Instrumentation</option>
                    <option value="Tools">Tools</option>
                    <option value="Equipment">Equipment</option>
                    <option value="Machinery">Machinery</option>
                    <option value="Documentation">Documentation</option>
                    <option value="Systems">Systems</option>
                    <option value="Antennas">Antennas</option>
                    <option value="Calibration">Calibration</option>
                    <option value="Consumables">Consumables</option>
                </select>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Location</label>
                <input type="text" id="eeLocation" class="form-control" style="margin-bottom:8px;">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Project / Program</label>
                <input type="text" id="eeProject" class="form-control" style="margin-bottom:12px;">

                <div style="display:flex; justify-content:flex-end; gap:8px;">
                    <button type="button" onclick="closeEditEquipmentModal()" class="btn-back">Cancel</button>
                    <button type="submit" class="btn-action" style="background:#0969da;">Save Changes</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Modal for Editing Existing Transaction Log -->
    <div id="editDetailTxModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.5); z-index:99999; justify-content:center; align-items:center;">
        <div style="background:var(--bg-card); border:1px solid var(--border); border-radius:8px; width:480px; padding:20px; max-height:90vh; overflow-y:auto;">
            <h3 style="margin-bottom:14px; font-size:1rem;">✏️ Edit Transaction Log #<span id="edTxIdDisplay"></span></h3>
            <form onsubmit="saveEditedDetailTx(event)">
                <input type="hidden" id="edTxId">
                <input type="hidden" id="edDeletePhoto" value="0">
                <input type="hidden" id="edDeleteDoc" value="0">

                <!-- Visual Media & Document Section -->
                <div style="background:var(--tag-bg); padding:10px 12px; border-radius:6px; border:1px solid var(--border); margin-bottom:12px;">
                    <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Photo Attachment</label>
                    <div id="edExistingPhotoBox" style="margin-bottom:6px;"></div>
                    <input type="file" id="edNewPhoto" accept="image/*" class="form-control" style="font-size:0.8rem; margin-bottom:8px;">

                    <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Document Attachment</label>
                    <div id="edExistingDocBox" style="margin-bottom:6px;"></div>
                    <input type="file" id="edNewDoc" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.zip,image/*" class="form-control" style="font-size:0.8rem;">
                </div>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Date & Time *</label>
                <input type="text" id="edDateTime" class="form-control" required style="margin-bottom:8px;">

                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">State Cycle *</label>
                        <select id="edState" class="form-control" required style="margin-bottom:8px;">
                            <option value="Active">Active (Operational)</option>
                            <option value="Maintenance">Maintenance</option>
                            <option value="Repair">Repair</option>
                            <option value="Borrow">Borrow</option>
                            <option value="Transfer">Transfer</option>
                            <option value="New Purchase">New Purchase</option>
                            <option value="Damage">Damage</option>
                            <option value="Broken">Broken</option>
                            <option value="Lost">Lost</option>
                            <option value="Junk">Junk</option>
                            <option value="Donated">Donated</option>
                            <option value="Sell">Sell</option>
                            <option value="Scrapped">Scrapped</option>
                            <option value="Retired">Retired</option>
                            <option value="Dispose">Dispose</option>
                        </select>
                    </div>
                    <div>
                        <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Condition *</label>
                        <select id="edCondition" class="form-control" required style="margin-bottom:8px;">
                            <option value="Good / Operational">Good / Operational</option>
                            <option value="Calibrated & Certified">Calibrated & Certified</option>
                            <option value="Brand New / Sealed">Brand New / Sealed</option>
                            <option value="Fair / Minor Wear">Fair / Minor Wear</option>
                            <option value="Needs Cleaning / Consumables">Needs Cleaning / Consumables</option>
                            <option value="Needs Calibration / Maintenance">Needs Calibration / Maintenance</option>
                            <option value="Under Repair">Under Repair</option>
                            <option value="Damaged / Degraded">Damaged / Degraded</option>
                            <option value="Broken / Inoperable">Broken / Inoperable</option>
                            <option value="Decommissioned / Disposed">Decommissioned / Disposed</option>
                        </select>
                    </div>
                </div>

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Expense / Price in IDR</label>
                <input type="text" inputmode="numeric" id="edPrice" class="form-control" oninput="formatNumberInput(this)" style="margin-bottom:8px;">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">PIC *</label>
                <input type="text" id="edPic" class="form-control" required style="margin-bottom:8px;">

                <label style="font-size:0.8rem; font-weight:bold; display:block; margin-bottom:4px;">Purpose / Activity *</label>
                <textarea id="edPurpose" class="form-control" rows="3" required style="margin-bottom:12px;"></textarea>

                <div style="display:flex; justify-content:flex-end; gap:8px;">
                    <button type="button" onclick="closeEditDetailTxModal()" class="btn-back">Cancel</button>
                    <button type="submit" class="btn-action" style="background:#0969da;">Update Log</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        const toolId = "__TOOL_ID__";
        let historicalTransactions = [];
        let sortDateDesc = true; // Req 74: Default is Descending from Date

        function formatNumberInput(input) {
            let cursor = input.selectionStart || 0;
            const originalVal = input.value;
            const digitsBeforeCursor = (originalVal.slice(0, cursor).match(/[0-9]/g) || []).length;
            let raw = originalVal.replace(/[^0-9]/g, '');
            if (!raw) {
                input.value = '0';
                input.setSelectionRange(1, 1);
                return;
            }
            let num = parseInt(raw, 10);
            let formatted = num.toLocaleString('en-US');
            input.value = formatted;
            let newCursor = 0;
            let digitsEncountered = 0;
            for (let i = 0; i < formatted.length; i++) {
                if (/[0-9]/.test(formatted[i])) digitsEncountered++;
                if (digitsEncountered >= digitsBeforeCursor) {
                    newCursor = i + 1;
                    break;
                }
            }
            if (digitsBeforeCursor === 0) newCursor = 0;
            input.setSelectionRange(newCursor, newCursor);
        }

        function toggleDateSort() {
            sortDateDesc = !sortDateDesc;
            renderHistoricalTable();
        }

        function renderHistoricalTable() {
            const tbody = document.getElementById('txTableBody');
            tbody.innerHTML = '';
            const icon = document.getElementById('sortDateIcon');
            if (icon) icon.innerText = sortDateDesc ? '▼' : '▲';

            const sorted = [...historicalTransactions].sort((a, b) => {
                const da = a.date_time || '';
                const db = b.date_time || '';
                return sortDateDesc ? db.localeCompare(da) : da.localeCompare(db);
            });

            if (sorted.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-muted);">No transaction logs recorded yet.</td></tr>';
                return;
            }

            sorted.forEach((tx, idx) => {
                const isCurrent = (tx.is_current === 1);
                const stateClass = isCurrent ? 'state-current' : 'state-past';
                const dateClass = isCurrent ? 'date-current' : 'date-earlier';
                const priceFormatted = Math.round(tx.price || 0).toLocaleString('en-US');

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td style="text-align:center; font-weight:bold; color:var(--text-muted);">${idx + 1}</td>
                    <td><span class="${dateClass}">${tx.date_time}</span></td>
                    <td><span class="${stateClass}">${tx.state || 'Active'}</span></td>
                    <td>${tx.condition}</td>
                    <td style="text-align:right; font-weight:bold;">${priceFormatted}</td>
                    <td><strong>${tx.pic}</strong></td>
                    <td class="col-purpose">${tx.purpose}</td>
                    <td style="text-align:center;">
                        ${tx.photo_path ? `<a href="${tx.photo_path}" target="_blank"><img src="${tx.photo_path}" style="width:36px; height:26px; object-fit:cover; border-radius:3px;"></a>` : '-'}
                    </td>
                    <td style="text-align:center;">
                        ${tx.doc_path ? `<a href="${tx.doc_path}" target="_blank" title="Open Document" style="font-size:1.25rem; text-decoration:none;">📄</a>` : '-'}
                    </td>
                    <td style="text-align:center;">
                        ${(currentRole === 'superadmin' || currentRole === 'admin') ? `
                            <div style="display:flex; gap:4px; justify-content:center;">
                                <button onclick="openEditDetailLog(${tx.id})" class="btn-action" style="background:#0969da; padding:2px 8px; font-size:0.75rem;">Edit</button>
                                <button onclick="deleteDetailLog(${tx.id})" class="btn-action" style="background:#cf222e; padding:2px 8px; font-size:0.75rem;">Delete</button>
                            </div>
                        ` : '-'}
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }
        const currentRole = localStorage.getItem('auth-role') || 'guest';
        const theme = localStorage.getItem('inventory-theme') || 'light';
        document.documentElement.setAttribute('data-theme', theme);

        if (currentRole === 'superadmin' || currentRole === 'admin') { 
            const sec = document.getElementById('superadminEqActions'); 
            if (sec) sec.style.display = 'flex'; 
        }
        if (currentRole === 'admin' || currentRole === 'superadmin') {
            document.getElementById('btnAdminTransfer').style.display = 'inline-flex';
        }

        let currentToolObj = null;

        function openEditEquipmentModal() {
            if (!currentToolObj) return;
            document.getElementById('eeName').value = currentToolObj.name || '';
            document.getElementById('eeBrand').value = currentToolObj.brand || '';
            document.getElementById('eeModel').value = currentToolObj.model || '';
            document.getElementById('eeType').value = currentToolObj.tool_type || '';
            document.getElementById('eeSerial').value = currentToolObj.serial_number || '';
            document.getElementById('eeCategory').value = currentToolObj.category || 'Equipment';
            document.getElementById('eeLocation').value = currentToolObj.room_title || '';
            document.getElementById('eeProject').value = currentToolObj.project || 'Radar EW Facility Project';
            document.getElementById('editEquipmentModal').style.display = 'flex';
        }

        function closeEditEquipmentModal() {
            document.getElementById('editEquipmentModal').style.display = 'none';
        }

        async function saveEditEquipment(e) {
            e.preventDefault();
            const fd = new FormData();
            fd.append('name', document.getElementById('eeName').value.trim());
            fd.append('brand', document.getElementById('eeBrand').value.trim());
            fd.append('model', document.getElementById('eeModel').value.trim());
            fd.append('tool_type', document.getElementById('eeType').value.trim());
            fd.append('serial_number', document.getElementById('eeSerial').value.trim());
            fd.append('category', document.getElementById('eeCategory').value);
            fd.append('room_title', document.getElementById('eeLocation').value.trim());
            fd.append('project', document.getElementById('eeProject').value.trim());
            fd.append('role', currentRole || 'superadmin');

            try {
                const res = await fetch(`/api/tools/${encodeURIComponent(toolId)}`, {
                    method: 'PUT',
                    body: fd
                });
                const resData = await res.json();
                if (res.ok) {
                    alert("Equipment details and typos updated successfully!");
                    closeEditEquipmentModal();
                    await loadToolDetail();
                } else {
                    alert("Update failed: " + (resData.detail || "Server rejected request."));
                }
            } catch(err) {
                alert("Error: " + err.message);
            }
        }

        function openEditDetailLog(txId) {
            const tx = historicalTransactions.find(t => t.id === txId);
            if (!tx) return;

            document.getElementById('edTxId').value = tx.id;
            document.getElementById('edTxIdDisplay').innerText = tx.id;
            document.getElementById('edDateTime').value = tx.date_time || '';
            document.getElementById('edState').value = tx.state || 'Active';
            document.getElementById('edCondition').value = tx.condition || 'Good / Operational';
            document.getElementById('edPrice').value = Math.round(tx.price || 0).toLocaleString('en-US');
            document.getElementById('edPic').value = tx.pic || '';
            document.getElementById('edPurpose').value = tx.purpose || '';
            document.getElementById('edDeletePhoto').value = '0';
            document.getElementById('edDeleteDoc').value = '0';
            document.getElementById('edNewPhoto').value = '';
            document.getElementById('edNewDoc').value = '';

            const pBox = document.getElementById('edExistingPhotoBox');
            if (tx.photo_path && !tx.photo_path.endsWith('default_equipment.svg')) {
                pBox.innerHTML = `
                    <div style="display:flex; align-items:center; gap:8px; margin-top:2px;">
                        <img src="${tx.photo_path}" style="max-height:48px; border-radius:4px; border:1px solid var(--border);">
                        <button type="button" class="btn-action" style="background:#cf222e; padding:2px 8px; font-size:0.75rem;" onclick="deleteDetailTxPhoto(${tx.id})">🗑️ Delete Image</button>
                    </div>
                `;
            } else {
                pBox.innerHTML = '<span style="font-size:0.75rem; color:var(--text-muted);">No custom photo attached.</span>';
            }

            const dBox = document.getElementById('edExistingDocBox');
            if (tx.doc_path) {
                dBox.innerHTML = `
                    <div style="display:flex; align-items:center; gap:8px; margin-top:2px;">
                        <a href="${tx.doc_path}" target="_blank" class="doc-link" style="font-size:0.8rem;">📄 View Document</a>
                        <button type="button" class="btn-action" style="background:#cf222e; padding:2px 8px; font-size:0.75rem;" onclick="deleteDetailTxDoc(${tx.id})">🗑️ Delete Doc</button>
                    </div>
                `;
            } else {
                dBox.innerHTML = '<span style="font-size:0.75rem; color:var(--text-muted);">No document attached.</span>';
            }

            document.getElementById('editDetailTxModal').style.display = 'flex';
        }

        function closeEditDetailTxModal() {
            document.getElementById('editDetailTxModal').style.display = 'none';
        }

        async function deleteDetailTxPhoto(txId) {
            if (!confirm(`Are you sure you want to permanently delete the image from transaction #${txId}?`)) return;
            try {
                const res = await fetch(`/api/transactions/${txId}/photo?role=${encodeURIComponent(currentRole || 'superadmin')}`, { method: 'DELETE' });
                if (res.ok) {
                    alert("Image deleted successfully.");
                    document.getElementById('edExistingPhotoBox').innerHTML = '<span style="font-size:0.75rem; color:var(--text-muted);">Image deleted (reverted to default).</span>';
                    await loadToolDetail();
                } else {
                    const d = await res.json();
                    alert("Failed to delete image: " + (d.detail || ""));
                }
            } catch(e) {
                alert("Error: " + e.message);
            }
        }

        async function deleteDetailTxDoc(txId) {
            if (!confirm(`Are you sure you want to permanently delete the document from transaction #${txId}?`)) return;
            try {
                const res = await fetch(`/api/transactions/${txId}/document?role=${encodeURIComponent(currentRole || 'superadmin')}`, { method: 'DELETE' });
                if (res.ok) {
                    alert("Document deleted successfully.");
                    document.getElementById('edExistingDocBox').innerHTML = '<span style="font-size:0.75rem; color:var(--text-muted);">Document removed.</span>';
                    await loadToolDetail();
                } else {
                    const d = await res.json();
                    alert("Failed to delete document: " + (d.detail || ""));
                }
            } catch(e) {
                alert("Error: " + e.message);
            }
        }

        async function saveEditedDetailTx(e) {
            e.preventDefault();
            const txId = document.getElementById('edTxId').value;
            const fd = new FormData();
            fd.append('date_time', document.getElementById('edDateTime').value.trim());
            fd.append('state', document.getElementById('edState').value);
            fd.append('condition', document.getElementById('edCondition').value);
            fd.append('price', (document.getElementById('edPrice').value || '0').replace(/,/g, ''));
            fd.append('pic', document.getElementById('edPic').value.trim());
            fd.append('purpose', document.getElementById('edPurpose').value.trim());
            fd.append('role', currentRole || 'superadmin');

            const pFile = document.getElementById('edNewPhoto').files[0];
            if (pFile) fd.append('photo', pFile);
            const dFile = document.getElementById('edNewDoc').files[0];
            if (dFile) fd.append('document', dFile);

            try {
                const res = await fetch(`/api/transactions/${txId}`, {
                    method: 'PUT',
                    body: fd
                });
                const resData = await res.json();
                if (res.ok) {
                    alert("Transaction log updated successfully!");
                    closeEditDetailTxModal();
                    await loadToolDetail();
                } else {
                    alert("Update failed: " + (resData.detail || "Server rejected request."));
                }
            } catch(err) {
                alert("Error: " + err.message);
            }
        }
        
        async function deleteDetailLog(txId) {
            if (currentRole !== 'superadmin' && currentRole !== 'admin') return;
            if (!confirm(`Are you sure you want to delete transaction log #${txId}?`)) return;
            try {
                const res = await fetch(`/api/transactions/${txId}?role=${encodeURIComponent(currentRole || 'superadmin')}`, { method: 'DELETE' });
                if (res.ok) {
                    await loadToolDetail();
                } else {
                    alert("Failed to delete transaction log.");
                }
            } catch(err) {
                alert("Error: " + err.message);
            }
        }

        async function deleteCurrentEquipment() {
            if (currentRole !== 'superadmin') return;
            if (!confirm(`Are you sure you want to permanently delete equipment [${toolId}] and all its associated records?`)) return;
            try {
                const res = await fetch(`/api/tools/${encodeURIComponent(toolId)}?role=superadmin`, { method: 'DELETE' });
                if (res.ok) {
                    alert("Equipment deleted successfully.");
                    window.location.href = '/';
                } else {
                    alert("Failed to delete equipment.");
                }
            } catch(err) {
                alert("Error: " + err.message);
            }
        }

        async function loadToolDetail() {
            try {
                const res = await fetch(`/api/tools/${toolId}`);
                if (!res.ok) {
                    alert("Failed to load tool details");
                    return;
                }
                const data = await res.json();
                const tool = data.tool;
                currentToolObj = tool;

                document.getElementById('toolHeaderTitle').innerText = `${tool.name} [${tool.id}]`;
                document.getElementById('toolHeaderSubtitle').innerText = `${tool.brand} ${tool.model} • S/N: ${tool.serial_number}`;

                document.getElementById('spId').innerText = tool.id;
                document.getElementById('spName').innerText = tool.name;
                document.getElementById('spBrand').innerText = tool.brand;
                document.getElementById('spModel').innerText = tool.model;
                document.getElementById('spType').innerText = tool.tool_type;
                document.getElementById('spSerial').innerText = tool.serial_number;
                document.getElementById('spCategory').innerText = tool.category;
                document.getElementById('spLocation').innerText = tool.room_title;
                document.getElementById('spProject').innerText = tool.project || 'Radar EW Facility Project';
                document.getElementById('spCurrentState').innerText = data.current_state;
                document.getElementById('spExpenses').innerText = Math.round(data.total_expenses).toLocaleString('en-US');

                if (data.is_terminal) {
                    document.getElementById('terminalAlert').style.display = 'block';
                    document.getElementById('terminalStateName').innerText = data.current_state;
                }

                // Photos
                const photoGallery = document.getElementById('photoGallery');
                photoGallery.innerHTML = '';
                document.getElementById('photoCount').innerText = data.photos.length;
                data.photos.forEach(p => {
                    const div = document.createElement('div');
                    div.className = 'gallery-item';
                    div.innerHTML = `<a href="${p}" target="_blank"><img src="${p}" alt="Photo"></a>`;
                    photoGallery.appendChild(div);
                });

                // Documents
                const docList = document.getElementById('docList');
                docList.innerHTML = '';
                document.getElementById('docCount').innerText = data.documents.length;
                if (data.documents.length === 0) {
                    docList.innerHTML = '<li style="color:var(--text-muted); font-size:0.8rem;">No documents uploaded yet.</li>';
                } else {
                    data.documents.forEach(d => {
                        const filename = d.split('/').pop();
                        const li = document.createElement('li');
                        li.className = 'doc-item';
                        li.innerHTML = `
                            <a href="${d}" target="_blank" class="doc-link" title="${filename}">📄 ${filename}</a>
                            <a href="${d}" download class="btn-back" style="padding:2px 8px; font-size:0.75rem;">Download</a>
                        `;
                        docList.appendChild(li);
                    });
                }

                // Transactions (Requirement 74: Default Descending with header toggle)
                historicalTransactions = data.transactions || [];
                document.getElementById('txCount').innerText = historicalTransactions.length;
                renderHistoricalTable();

            } catch (err) {
                console.error("Failed to load tool detail", err);
            }
        }

        function previewDtPhoto(input) {
            const box = document.getElementById('dtPhotoPreviewBox');
            const img = document.getElementById('dtPhotoPreview');
            if (input.files && input.files[0]) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    img.src = e.target.result;
                    box.style.display = 'block';
                };
                reader.readAsDataURL(input.files[0]);
            } else {
                img.src = '';
                box.style.display = 'none';
            }
        }

        function openDetailNewTxModal() {
            const now = new Date();
            document.getElementById('dtDateTime').value = now.toISOString().slice(0, 16).replace('T', ' ');
            document.getElementById('dtPic').value = '';
            document.getElementById('dtPurpose').value = '';
            document.getElementById('dtCondition').value = 'Good / Operational';
            document.getElementById('dtPrice').value = '0';
            document.getElementById('dtState').value = 'Active';
            document.getElementById('dtPhoto').value = '';
            document.getElementById('dtDoc').value = '';
            const dtPBox = document.getElementById('dtPhotoPreviewBox');
            if (dtPBox) dtPBox.style.display = 'none';
            const dtPImg = document.getElementById('dtPhotoPreview');
            if (dtPImg) dtPImg.src = '';
            document.getElementById('detailTxModal').style.display = 'flex';
        }
        function closeDetailNewTxModal() {
            document.getElementById('detailTxModal').style.display = 'none';
            const dtPBox = document.getElementById('dtPhotoPreviewBox');
            if (dtPBox) dtPBox.style.display = 'none';
            const dtPImg = document.getElementById('dtPhotoPreview');
            if (dtPImg) dtPImg.src = '';
        }

        async function saveDetailTransaction(e) {
            e.preventDefault();
            const fd = new FormData();
            fd.append('date_time', document.getElementById('dtDateTime').value);
            fd.append('tool_id', toolId);
            fd.append('state', document.getElementById('dtState').value);
            fd.append('price', (document.getElementById('dtPrice').value || '0').replace(/,/g, ''));
            fd.append('condition', document.getElementById('dtCondition').value);
            fd.append('pic', document.getElementById('dtPic').value);
            fd.append('purpose', document.getElementById('dtPurpose').value);
            fd.append('is_current', '1');

            const pFile = document.getElementById('dtPhoto').files[0];
            if (pFile) fd.append('photo', pFile);
            const dFile = document.getElementById('dtDoc').files[0];
            if (dFile) fd.append('document', dFile);

            const role = localStorage.getItem('auth-role');
            if (role === 'superadmin') {
                fd.append('superadmin_override', '1');
            }

            try {
                const res = await fetch('/api/transactions', { method: 'POST', body: fd });
                const data = await res.json();
                if (res.ok) {
                    closeDetailNewTxModal();
                    alert("Transaction logged successfully!");
                    loadToolDetail();
                } else {
                    alert("Transaction failed: " + (data.detail || "Server rejected transaction."));
                }
            } catch (err) {
                alert("Error logging transaction: " + err.message);
            }
        }

        async function handleRepoUpload(e, type) {
            e.preventDefault();
            const fileInput = document.getElementById(type === 'photo' ? 'newPhotoFile' : 'newDocFile');
            if (!fileInput.files || !fileInput.files[0]) {
                alert("Please select a file to upload.");
                return;
            }

            const fd = new FormData();
            fd.append('file_type', type);
            fd.append('file', fileInput.files[0]);

            try {
                const res = await fetch(`/api/tools/${toolId}/upload`, {
                    method: 'POST',
                    body: fd
                });
                const resData = await res.json();
                if (res.ok) {
                    fileInput.value = '';
                    alert(`${type === 'photo' ? 'Photo' : 'Document'} uploaded successfully to historical repository!`);
                    loadToolDetail();
                } else {
                    alert("Upload error: " + (resData.detail || "Server rejected file."));
                }
            } catch (err) {
                alert("Upload failed: " + err.message);
            }
        }

        function openTransferModal() {
            document.getElementById('transferModal').style.display = 'flex';
        }
        function closeTransferModal() {
            document.getElementById('transferModal').style.display = 'none';
        }

        async function executeProjectTransfer(e) {
            e.preventDefault();
            const fd = new FormData();
            fd.append('new_project', document.getElementById('tfProject').value);
            fd.append('pic', document.getElementById('tfPic').value);
            fd.append('reason', document.getElementById('tfReason').value);

            try {
                const res = await fetch(`/api/tools/${toolId}/transfer-project`, {
                    method: 'POST',
                    body: fd
                });
                const data = await res.json();
                if (res.ok) {
                    closeTransferModal();
                    alert(data.message);
                    loadToolDetail();
                } else {
                    alert("Transfer error: " + (data.detail || "Could not transfer project"));
                }
            } catch (err) {
                alert("Transfer request failed: " + err.message);
            }
        }

        loadToolDetail();
    </script>
</body>
</html>
"""

@app.get("/detail/{tool_id}", response_class=HTMLResponse)
def get_detail_page(tool_id: str):
    return HTMLResponse(content=DETAIL_PAGE_TEMPLATE.replace("__TOOL_ID__", tool_id))

# --- STANDALONE A4 PRINTABLE REPORT VIEW ---
@app.get("/report/print", response_class=HTMLResponse)
def print_report_view(
    start_date: Optional[str] = Query(None),
    finish_date: Optional[str] = Query(None),
    location: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    pic: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    state: Optional[str] = Query(None)
):
    report_data = get_report_data(start_date, finish_date, location, project, pic, condition, state)
    items = report_data['items']
    settings = report_data['settings']
    total_expense = report_data['total_expense']
    f = report_data['filter']
    signatories = get_current_signatories()
    dibuat_name = f['pic'] if (f.get('pic') and f['pic'] != 'All PICs') else signatories['dibuat_name']
    report_logo_html = get_report_logo_html(settings)

    rows_html = ""
    for idx, it in enumerate(items, 1):
        price_str = f"{int(it['price']):,}" if it['price'] else "0"
        rows_html += f"""
        <tr>
            <td style="text-align:center;">{idx}</td>
            <td><small>{it['date_time']}</small></td>
            <td><strong>{it['tool_name']}</strong><br><small style="color:#555;">{it['tool_id']} | S/N: {it['serial_number']}</small></td>
            <td><small>{it['brand']} {it['model']}</small></td>
            <td style="font-weight:bold; color:#1a7f37; font-size:9px;">{it['state']}</td>
            <td><small>{it['condition']}</small></td>
            <td style="text-align:right; font-weight:bold;">{price_str}</td>
            <td><small>{it['pic']}</small></td>
            <td><small>{it['purpose']}</small></td>
        </tr>
        """

    total_expense_str = f"{int(total_expense):,}"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Inventory Transaction Report ({start_date} to {finish_date}) - A4 Vertical</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 15mm 10mm;
        }}
        *, *::before, *::after {{
            box-sizing: border-box;
            font-family: Arial, Helvetica, sans-serif !important;
        }}
        body {{
            background: #fff;
            color: #000;
            font-size: 10px;
            line-height: 1.35;
            padding: 8px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #000;
            padding-bottom: 8px;
            margin-bottom: 10px;
        }}
        .header-title h1 {{
            font-size: 16px;
            font-weight: bold;
            margin: 0 0 2px 0;
            text-transform: uppercase;
        }}
        .header-title h2 {{
            font-size: 11px;
            font-weight: normal;
            color: #333;
            margin: 0;
        }}
        .meta-box {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            background: #f4f4f4;
            border: 1px solid #ccc;
            padding: 6px 10px;
            font-size: 9.5px;
            margin-bottom: 12px;
        }}
        .meta-item strong {{ display: inline-block; width: 80px; color: #444; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 9px;
            margin-bottom: 16px;
        }}
        th, td {{
            border: 1px solid #777;
            padding: 4px 6px;
            text-align: left;
            vertical-align: top;
        }}
        th {{
            background: #e9ecef;
            font-weight: bold;
            color: #000;
            text-align: center;
        }}
        .footer-signatures {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 14px;
            margin-top: 25px;
            page-break-inside: avoid;
        }}
        .sign-col {{
            text-align: center;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 8px 6px;
            background: #fafafa;
        }}
        .sign-label {{
            font-weight: bold;
            font-size: 11px;
            text-transform: uppercase;
            color: #1f883d;
        }}
        .sign-title {{
            font-size: 9.5px;
            color: #444;
            margin-top: 2px;
            font-weight: 600;
        }}
        .sign-space {{
            height: 50px;
        }}
        .sign-line {{
            border-top: 1px solid #000;
            font-weight: bold;
            font-size: 11px;
            padding-top: 4px;
            margin: 0 8px;
        }}
        .sign-sub {{
            font-size: 8.5px;
            color: #666;
            margin-top: 2px;
        }}
        .no-print-bar {{
            background: #1f883d;
            color: #fff;
            padding: 8px 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
            border-radius: 4px;
        }}
        @media print {{
            .no-print-bar {{ display: none; }}
            body {{ padding: 0; }}
        }}
    </style>
</head>
<body>
    <div class="no-print-bar">
        <span><strong>Official Inventory Report (A4 Vertical Printable Document)</strong></span>
        <div>
            <button onclick="window.print()" style="background:#fff; color:#1f883d; border:none; padding:5px 14px; font-weight:bold; cursor:pointer; border-radius:4px;">Print</button>
            <button onclick="window.close()" style="background:transparent; color:#fff; border:1px solid #fff; padding:5px 14px; font-weight:bold; cursor:pointer; border-radius:4px; margin-left:8px;">Close</button>
        </div>
    </div>

    <div class="header">
        <div style="display:flex; align-items:center; gap:12px;">
            {report_logo_html}
            <div class="header-title">
                <h1>{settings.get('room_title', 'RADAR EW FACILITY WORKSHOP')}</h1>
                <h2>{settings.get('group_title', 'EW Instrumentation & Maintenance Unit')} — Historical Inventory Log Report (A4 Vertical)</h2>
            </div>
        </div>
        <div style="text-align:right;">
            <div style="font-weight:bold; font-size:11px;">CONFIDENTIAL REPORT</div>
            <div style="font-size:9.5px; color:#555;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </div>
    </div>

    <div class="meta-box">
        <div class="meta-item"><strong>Period:</strong> {f['start_date']} s/d {f['finish_date']}</div>
        <div class="meta-item"><strong>Location:</strong> {f['location']}</div>
        <div class="meta-item"><strong>Project:</strong> {f.get('project', 'All Projects')}</div>
        <div class="meta-item"><strong>PIC:</strong> {f['pic']}</div>
        <div class="meta-item"><strong>Condition:</strong> {f['condition']}</div>
        <div class="meta-item"><strong>State:</strong> {f['state']}</div>
        <div class="meta-item"><strong>Total Records:</strong> {len(items)} logs</div>
        <div class="meta-item" style="grid-column: span 2;"><strong>Total Expenses (IDR):</strong> {total_expense_str}</div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:24px;">No</th>
                <th style="width:75px;">Date &amp; Time</th>
                <th style="width:125px;">Equipment &amp; ID</th>
                <th style="width:85px;">Brand &amp; Model</th>
                <th style="width:60px;">State</th>
                <th style="width:75px;">Condition</th>
                <th style="width:75px; text-align:right;">Expenses (IDR)</th>
                <th style="width:70px;">PIC</th>
                <th>Purpose / Detail</th>
            </tr>
        </thead>
        <tbody>
            {rows_html if rows_html else '<tr><td colspan="9" style="text-align:center; padding:16px;">No transaction logs found for the selected period and filter criteria.</td></tr>'}
        </tbody>
    </table>

    <div class="footer-signatures">
        <div class="sign-col">
            <div class="sign-label">{signatories['dibuat_label']}</div>
            <div class="sign-title">{signatories['dibuat_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{dibuat_name}</div>
            <div class="sign-sub">Tgl: {datetime.now().strftime('%d %B %Y')}</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['diperiksa_label']}</div>
            <div class="sign-title">{signatories['diperiksa_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['diperiksa_name']}</div>
            <div class="sign-sub">Official Stamp &amp; Sign</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['disetujui_label']}</div>
            <div class="sign-title">{signatories['disetujui_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['disetujui_name']}</div>
            <div class="sign-sub">Official Facility Stamp</div>
        </div>
    </div>

    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 600);
        }};
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)

# --- HEALTH CHECK FOR RENDER & MONITORING ---
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "radar-ew-inventory", "timestamp": datetime.now().isoformat()}

# --- LANDING PAGE & DASHBOARD ROUTES ---
@app.get("/", response_class=HTMLResponse)
@app.get("/landing", response_class=HTMLResponse)
def landing_page():
    landing_path = os.path.join(BASE_DIR, "landing.html")
    if os.path.exists(landing_path):
        with open(landing_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = "<h1>Template landing.html not found</h1>"
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/dashboard", response_class=HTMLResponse)
@app.get("/inventory", response_class=HTMLResponse)
def index_dashboard():
    template_path = os.path.join(BASE_DIR, "index_template.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = "<h1>Template index_template.html not found</h1>"
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

# --- USER AUTHENTICATION API ---
@app.post("/api/auth/register")
async def api_auth_register(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
    
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    job_title = str(data.get("job_title", "Radar Technician")).strip()
    password = str(data.get("password", ""))
    repeat_password = str(data.get("repeat_password", ""))
    
    if not name or not email or not password or not repeat_password:
        raise HTTPException(status_code=400, detail="Semua kolom wajib diisi.")
    
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Format alamat email tidak valid.")
        
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Kata sandi minimal harus 6 karakter.")
        
    if password != repeat_password:
        raise HTTPException(status_code=400, detail="Kata sandi dan ulangi kata sandi tidak cocok.")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Email ini sudah terdaftar. Silakan masuk.")
        
    pwd_hash = hash_user_password(password)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        INSERT INTO users (email, name, password_hash, role, job_title, created_at)
        VALUES (?, ?, ?, 'user', ?, ?)
    """, (email, name, pwd_hash, job_title, now_str))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "status": "success",
        "message": "Pendaftaran akun berhasil!",
        "user": {
            "id": user_id,
            "name": name,
            "email": email,
            "role": "user",
            "job_title": job_title
        }
    }

@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")
        
    login_input = str(data.get("username_or_email", "")).strip()
    password = str(data.get("password", ""))
    
    if not login_input or not password:
        raise HTTPException(status_code=400, detail="Email/username dan kata sandi wajib diisi.")
        
    # Check built-in administrative credentials
    if login_input == "superadmin" and password == "Administrasi##":
        return {
            "status": "success",
            "message": "Administrator clearance granted.",
            "user": {
                "id": 0,
                "name": "Administrator",
                "email": "admin@radarew.local",
                "role": "superadmin",
                "job_title": "Facility Lead"
            }
        }
        
    if login_input == "admin" and password == "Administrasi#":
        return {
            "status": "success",
            "message": "Administrator clearance granted.",
            "user": {
                "id": -1,
                "name": "Administrator",
                "email": "admin@radarew.local",
                "role": "admin",
                "job_title": "Inventory Controller"
            }
        }
        
    # Query database users
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM users 
        WHERE LOWER(email) = LOWER(?) OR LOWER(name) = LOWER(?)
        LIMIT 1
    """, (login_input, login_input))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=401, detail="Email/Username atau Kata Sandi salah.")
        
    user = dict(user_row)
    if not verify_user_password(password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email/Username atau Kata Sandi salah.")
        
    return {
        "status": "success",
        "message": "Login berhasil!",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user.get("role", "user"),
            "job_title": user.get("job_title", "Radar Technician")
        }
    }

@app.get("/api/auth/users")
def api_auth_list_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, role, job_title, created_at FROM users ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows



# --- PRINTABLE A4 DETAIL EQUIPMENT LIFECYCLE REPORT (Requirement 80) ---
@app.get("/detail/{tool_id}/print", response_class=HTMLResponse)
def print_equipment_detail_a4(tool_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (tool_id,))
    tool_row = cursor.fetchone()
    if not tool_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Equipment not found")
    tool = dict(tool_row)
    
    cursor.execute("""
        SELECT * FROM transactions 
        WHERE tool_id = ? 
        ORDER BY date_time DESC, id DESC
    """, (tool_id,))
    transactions = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT key, value FROM system_settings")
    settings = {r['key']: r['value'] for r in cursor.fetchall()}
    conn.close()
    report_logo_html = get_report_logo_html(settings)
    
    total_expenses = sum(float(t.get('price') or 0.0) for t in transactions)
    total_expenses_str = f"{total_expenses:,.0f}"
    current_tx = transactions[0] if transactions else {}
    current_state = current_tx.get('state', 'Active')
    current_condition = current_tx.get('condition', 'Good / Operational')
    current_pic = current_tx.get('pic', 'Facility Lead')
    signatories = get_current_signatories()
    
    now_str = datetime.now().strftime("%d %B %Y, %H:%M")
    
    rows_html = ""
    for idx, tx in enumerate(transactions, 1):
        price_num = float(tx.get('price') or 0.0)
        price_str = f"{price_num:,.0f}"
        is_curr = (tx.get('is_current') == 1) or (idx == 1)
        state_style = "font-weight:bold; color:#1a7f37; font-size:9px;" if is_curr else "color:#666; font-style:italic; font-size:9px;"
        date_style = "font-weight:bold; color:#1a7f37;" if is_curr else "color:#666;"
        doc_cell = f"<a href='{tx['doc_path']}' target='_blank' style='text-decoration:none; font-size:11px;'>📄</a>" if tx.get('doc_path') else "-"
        
        rows_html += f"""
        <tr>
            <td style="text-align:center; font-weight:bold;">{idx}</td>
            <td><span style="{date_style}"><small>{tx.get('date_time', '-')}</small></span></td>
            <td><span style="{state_style}">{tx.get('state', '-')}</span></td>
            <td><small>{tx.get('condition', '-')}</small></td>
            <td style="text-align:right; font-weight:bold;">{price_str}</td>
            <td><small><strong>{tx.get('pic', '-')}</strong></small></td>
            <td><small>{tx.get('purpose', '-')}</small></td>
            <td style="text-align:center;">{doc_cell}</td>
        </tr>
        """
        
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>A4 Equipment Lifecycle Audit - {tool['id']} (Vertical)</title>
    <style>
        @page {{
            size: A4 portrait;
            margin: 10mm 10mm 12mm 10mm;
        }}
        *, *::before, *::after {{
            box-sizing: border-box;
            font-family: Arial, Helvetica, sans-serif !important;
        }}
        body {{
            background: #fff;
            color: #000;
            font-size: 10px;
            line-height: 1.35;
            padding: 8px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #000;
            padding-bottom: 8px;
            margin-bottom: 10px;
        }}
        .logo-wrap {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo-wrap svg {{
            width: 40px;
            height: 40px;
        }}
        .title-block h1 {{
            font-size: 14px;
            font-weight: bold;
            margin: 0 0 2px 0;
            text-transform: uppercase;
        }}
        .title-block h2 {{
            font-size: 10.5px;
            font-weight: normal;
            color: #333;
            margin: 0;
        }}
        .meta-strip {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 6px;
            background: #f4f6f8;
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 6px 10px;
            margin-bottom: 12px;
            font-size: 9.5px;
        }}
        .meta-strip div {{
            display: flex;
            flex-direction: column;
        }}
        .meta-label {{
            color: #555;
            font-size: 8px;
            text-transform: uppercase;
            font-weight: bold;
        }}
        .meta-val {{
            font-weight: bold;
            font-size: 10px;
            margin-top: 1px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 9px;
            margin-bottom: 16px;
        }}
        th, td {{
            border: 1px solid #777;
            padding: 4px 6px;
            text-align: left;
        }}
        th {{
            background: #eaeaea;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 9px;
        }}
        .footer-signatures {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 14px;
            margin-top: 24px;
            page-break-inside: avoid;
        }}
        .sign-col {{
            text-align: center;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 8px 6px;
            background: #fafafa;
        }}
        .sign-label {{
            font-weight: bold;
            font-size: 11px;
            text-transform: uppercase;
            color: #1f883d;
        }}
        .sign-title {{
            font-size: 9.5px;
            color: #444;
            margin-top: 2px;
            font-weight: 600;
        }}
        .sign-space {{
            height: 48px;
        }}
        .sign-line {{
            border-top: 1px solid #000;
            font-weight: bold;
            font-size: 10.5px;
            padding-top: 4px;
            margin: 0 8px;
        }}
        .sign-sub {{
            font-size: 8.5px;
            color: #666;
            margin-top: 2px;
        }}
        @media print {{
            .no-print {{ display: none !important; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="logo-wrap">
            {report_logo_html}
            <div class="title-block">
                <h1>{settings.get('room_title', 'RADAR & ELECTRONIC WARFARE FACILITY')}</h1>
                <h2>Official Equipment Lifecycle &amp; Historical Audit Dossier (A4 Vertical)</h2>
            </div>
        </div>
        <div style="text-align:right; font-size:9.5px;">
            <div><strong>Ref:</strong> AUDIT-{tool['id']}</div>
            <div><strong>Printed:</strong> {now_str}</div>
            <div style="margin-top:4px;" class="no-print">
                <button onclick="window.print()" style="font-weight:bold; padding:4px 12px; cursor:pointer;">Print</button>
            </div>
        </div>
    </div>

    <div class="meta-strip">
        <div><span class="meta-label">Equipment Name</span><span class="meta-val">{tool['name']}</span></div>
        <div><span class="meta-label">Tool ID</span><span class="meta-val">{tool['id']}</span></div>
        <div><span class="meta-label">Serial Number</span><span class="meta-val">{tool['serial_number']}</span></div>
        <div><span class="meta-label">Category / Type</span><span class="meta-val">{tool['category']} • {tool['tool_type']}</span></div>
        <div><span class="meta-label">Brand &amp; Model</span><span class="meta-val">{tool['brand']} {tool['model']}</span></div>
        <div><span class="meta-label">Facility Location</span><span class="meta-val">{tool['room_title']}</span></div>
        <div><span class="meta-label">Current State</span><span class="meta-val" style="color:#1a7f37;">{current_state}</span></div>
        <div><span class="meta-label">Total Expenses (IDR)</span><span class="meta-val">{total_expenses_str}</span></div>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width:24px; text-align:center;">No</th>
                <th style="width:80px;">Date &amp; Time</th>
                <th style="width:65px;">State</th>
                <th style="width:75px;">Condition</th>
                <th style="width:75px; text-align:right;">Expenses (IDR)</th>
                <th style="width:75px;">PIC</th>
                <th>Purpose / Maintenance Activity</th>
                <th style="width:30px; text-align:center;">Doc</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <div class="footer-signatures">
        <div class="sign-col">
            <div class="sign-label">{signatories['dibuat_label']}</div>
            <div class="sign-title">{signatories['dibuat_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{current_pic or signatories['dibuat_name']}</div>
            <div class="sign-sub">Equipment PIC / Creator</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['diperiksa_label']}</div>
            <div class="sign-title">{signatories['diperiksa_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['diperiksa_name']}</div>
            <div class="sign-sub">Facility Inspection</div>
        </div>

        <div class="sign-col">
            <div class="sign-label">{signatories['disetujui_label']}</div>
            <div class="sign-title">{signatories['disetujui_title']}</div>
            <div class="sign-space"></div>
            <div class="sign-line">{signatories['disetujui_name']}</div>
            <div class="sign-sub">Approved / Facility Manager</div>
        </div>
    </div>

    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 400);
        }};
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html)


# --- SUPERADMIN RECORD DELETION ENDPOINTS (Requirement 88, 90) ---
@app.delete("/api/tools/{tool_id}")
def delete_equipment(tool_id: str, role: str = Query("guest")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can delete equipment records.")
    t_id = tool_id.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tools WHERE id = ?", (t_id,))
    cursor.execute("DELETE FROM transactions WHERE tool_id = ?", (t_id,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Equipment '{t_id}' and all associated transaction records deleted."}

@app.delete("/api/consumables/{consumable_id}")
def delete_consumable(consumable_id: str, role: str = Query("guest")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can delete consumable records.")
    cid = consumable_id.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM consumables WHERE id = ?", (cid,))
    cursor.execute("DELETE FROM consumable_transactions WHERE consumable_id = ?", (cid,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Consumable '{cid}' and movement records deleted."}

@app.delete("/api/consumables/transactions/{tx_id}")
def delete_consumable_transaction(tx_id: int, role: str = Query("guest")):
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can delete transaction logs.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT consumable_id FROM consumable_transactions WHERE id = ?", (tx_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Transaction log not found.")
    cid = row['consumable_id']
    cursor.execute("DELETE FROM consumable_transactions WHERE id = ?", (tx_id,))
    
    # Recalculate consumable balance using Date FIFO stages
    recalculate_consumables_fifo(conn, cid)
    cursor.execute("SELECT quantity FROM consumables WHERE id = ?", (cid,))
    upd_row = cursor.fetchone()
    calc_balance = float(upd_row['quantity']) if upd_row else 0.0
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Consumable transaction #{tx_id} deleted. Balance recalculated to {calc_balance}."}


# --- SUPERADMIN CONSOLE ROUTE & EXTENDED APIs (Requirements 59, 61, 62, 63, 64, 65, 100, 105) ---
@app.get("/console", response_class=HTMLResponse)
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
    )

@app.get("/api/programs")
def get_programs():
    """Requirement 59: Program hierarchy listing"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT project FROM tools WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    t_projs = [r['project'] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT project FROM consumable_transactions WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    c_projs = [r['project'] for r in cursor.fetchall()]
    cursor.execute("SELECT DISTINCT project FROM consumables WHERE project IS NOT NULL AND project != '' ORDER BY project ASC")
    con_projs = [r['project'] for r in cursor.fetchall()]
    all_programs = sorted(list(set(t_projs + c_projs + con_projs + ["Radar EW Facility Project", "Unknown Program"])))
    conn.close()
    return all_programs

@app.put("/api/programs/{program_name}")
def rename_program(program_name: str, new_name: str = Form(...), role: str = Form("guest")):
    """Requirement 61: Superadmin can rename Program and its children"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can rename Programs.")
    p_old = program_name.strip()
    p_new = new_name.strip()
    if not p_new:
        raise HTTPException(status_code=400, detail="New program name cannot be empty.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tools SET project = ? WHERE project = ?", (p_new, p_old))
    cursor.execute("UPDATE consumable_transactions SET project = ? WHERE project = ?", (p_new, p_old))
    cursor.execute("UPDATE consumables SET project = ? WHERE project = ?", (p_new, p_old))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Program '{p_old}' renamed to '{p_new}'."}

@app.delete("/api/programs/{program_name}")
def delete_program(program_name: str, role: str = Query("guest")):
    """Requirement 61 & 62: Superadmin deletes Program; items move to Unknown Program"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can delete Programs.")
    p_del = program_name.strip()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tools SET project = 'Unknown Program' WHERE project = ?", (p_del,))
    cursor.execute("UPDATE consumable_transactions SET project = 'Unknown Program' WHERE project = ?", (p_del,))
    cursor.execute("UPDATE consumables SET project = 'Unknown Program' WHERE project = ?", (p_del,))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Program '{p_del}' deleted. Associated equipment moved to 'Unknown Program'."}

@app.post("/api/superadmin/merge-tools")
def merge_tools(
    target_tool_id: str = Form(...),
    source_tool_id: str = Form(...),
    role: str = Form("guest")
):
    """Requirement 63: Superadmin can merge equipment with identical Brand, Model, Serial Number"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can merge equipment.")
    tgt = target_tool_id.strip()
    src = source_tool_id.strip()
    if tgt == src:
        raise HTTPException(status_code=400, detail="Target and source equipment cannot be identical.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (tgt,))
    t_tgt = cursor.fetchone()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (src,))
    t_src = cursor.fetchone()
    if not t_tgt or not t_src:
        conn.close()
        raise HTTPException(status_code=404, detail="One or both equipment records not found.")
    
    # Reassign transactions from source to target
    cursor.execute("UPDATE transactions SET tool_id = ? WHERE tool_id = ?", (tgt, src))
    # Delete source tool
    cursor.execute("DELETE FROM tools WHERE id = ?", (src,))
    sync_equipment_current_states(conn, tgt)
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Equipment '{src}' merged into '{tgt}' successfully."}

@app.post("/api/superadmin/rename-tool")
def rename_tool(
    tool_id: str = Form(...),
    new_name: str = Form(...),
    role: str = Form("guest")
):
    """Requirement 64: Superadmin rename equipment name (auto Title Case)"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can rename equipment.")
    tid = tool_id.strip()
    name_clean = " ".join(w.capitalize() for w in new_name.strip().split())
    if not name_clean:
        raise HTTPException(status_code=400, detail="Equipment name cannot be empty.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tools SET name = ? WHERE id = ?", (name_clean, tid))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Equipment '{tid}' renamed to '{name_clean}'."}

@app.post("/api/superadmin/split-tool")
def split_tool(
    tool_id: str = Form(...),
    new_tool_id: str = Form(...),
    role: str = Form("guest")
):
    """Requirement 65: Superadmin can split an equipment record"""
    if role.strip().lower() not in ["superadmin", "admin", "administrator"]:
        raise HTTPException(status_code=403, detail="Permission denied. Only Superadmin can split equipment.")
    orig_id = tool_id.strip()
    new_id = new_tool_id.strip()
    if not new_id or new_id == orig_id:
        raise HTTPException(status_code=400, detail="Invalid new tool ID for split.")
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tools WHERE id = ?", (orig_id,))
    orig = cursor.fetchone()
    if not orig:
        conn.close()
        raise HTTPException(status_code=404, detail="Source equipment not found.")
    cursor.execute("SELECT id FROM tools WHERE id = ?", (new_id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Equipment ID '{new_id}' already exists.")
    
    # Create clone equipment
    cursor.execute("""
        INSERT INTO tools (id, name, category, brand, model, tool_type, serial_number, room_title, project)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (new_id, orig['name'], orig['category'], orig['brand'], orig['model'], orig['tool_type'], f"{orig['serial_number']}-SPLIT", orig['room_title'], orig['project']))
    
    # Create initial active transaction for split tool
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO transactions (date_time, pic, purpose, tool_id, condition, state, price, is_current)
        VALUES (?, 'Superadmin', ?, ?, 'Good / Operational', 'Active', 0.0, 1)
    """, (now_str, f"Split from equipment {orig_id}", new_id))
    
    init_repository_for_tool(new_id, orig['name'])
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Equipment '{orig_id}' split into new record '{new_id}'."}


if __name__ == "__main__":
    print("Starting Facility Workshop Inventory Web App on http://127.0.0.1:8000 ...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)

