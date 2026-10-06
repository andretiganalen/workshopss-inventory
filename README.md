# 🛡️ Radar EW Facility — Workshop Inventory & Historical Repository System

A robust, enterprise-grade inventory management and historical repository system designed for precision radar and electronic warfare workshop equipment, instrumentation, tools, and consumables.

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![SQLite](https://img.shields.io/badge/Database-SQLite3-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Render](https://img.shields.io/badge/Deploy-Render.com-46E3B7.svg?logo=render&logoColor=white)](https://render.com)

---

## 🌟 Key Features

### 1. 🔬 Equipment & Tools Lifecycle Tracking
* **Detailed Equipment Identification**: Tracks General Name, Brand, Model, Type, Serial Number, Category, and Assigned Project/Program.
* **Single-Row Consolidated Views**: Clean table presentations with merged Date & 24h Time, Current State & Condition, and formatted IDR expenses.
* **Active vs. Historical Distinctions**: Clear visual indicators (`LATEST` badge, highlighted styling) separating current operational states from historical logs.
* **Smart Filtering & Search**: Multi-token instant search across brand, serial number, project, and location with responsive pagination.

### 2. 🔐 Role-Based Access Control (RBAC)
* **Guest & Operator View**: Can view inventories, explore equipment details, and log new operational activities (`+ Log`).
* **Admin & Superadmin Exclusive**:
  * Edit and Delete actions are strictly restricted to **Admin** and **Superadmin** roles.
  * Form editing, typo correction, and record deletions are hidden from guest users both in UI tables and slide-in panels.
  * Backend API endpoints enforce 403 Forbidden permissions against unauthorized requests.

### 3. 📦 Consumables & Materials Management
* **Dual Views**:
  * **Balance View**: Real-time stock levels, low-stock warnings, storage locations, unit prices, and total inventory value.
  * **Ledger View**: Chronological audit trail of stock movements (`IN`, `OUT`, `ADJUST`, `OPNAME`).
* **FIFO Recalculation Engine**: Calculates running balances chronologically by transaction date using First-In, First-Out (FIFO) logic.
* **CSV Export**: Direct export of remaining storage balances with Excel UTF-8 BOM encoding.

### 4. 📋 Physical Stock Opname & Auditing
* **Interactive Stock Opname Modal**: Real-time physical check against database records by location and project.
* **Official Printable A4 Checklist**: Ready-to-print stock opname checklist with room hierarchy and official sign-off boxes.

### 5. 🗄️ Dedicated Repository Folder Structure
All files, certificates, photos, and manuals are stored systematically in the `repository/` directory:
```
repository/
├── <TOOL_ID>/
│   ├── photos/       # Equipment images and thumbnails
│   └── documents/    # Manuals, spec sheets, calibration certs (PDF/DOCX)
├── _branding/        # Custom Web & PDF Report logos
└── _opname/          # Signed physical stock opname sheets
```

### 6. 📜 Formal Signatories & Reporting
* **Laporan Transaksi**: Filterable period-based report generator.
* **3-Tier Signatory Configuration**: Configurable *Dibuat* (Created), *Diperiksa* (Inspected), and *Disetujui* (Approved) signers with complete historical rollback tracking.

---

## 🚀 Getting Started Locally

### Prerequisites
* Python 3.10 or higher
* Git

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/andretiganalen/workshopss-inventory.git
   cd workshopss-inventory
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS / Linux:
   source .venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the application:
   ```bash
   python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
   ```
   Or double-click **`start_app.bat`** on Windows.

5. Open your web browser:
   * **Dashboard**: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)
   * **Consumables**: [http://127.0.0.1:8000/consumables](http://127.0.0.1:8000/consumables)
   * **Management Console**: [http://127.0.0.1:8000/console](http://127.0.0.1:8000/console)

---

## ☁️ Deployment on Render.com

The application includes native **`render.yaml`** and **`Procfile`** configurations ready for 1-click deployment on [Render](https://render.com).

### Deployment Steps:
1. Push your repository to **GitHub**:
   ```bash
   git add .
   git commit -m "Deploy Radar EW Workshop Inventory System"
   git push -u origin main
   ```

2. Log in to [Render Dashboard](https://dashboard.render.com/).
3. Click **New +** > **Blueprint** (or **Web Service**).
4. Connect your GitHub repository.
5. In Blueprint mode, Render automatically reads `render.yaml`:
   * **Service Name**: `workshopss-inventory`
   * **Service URL**: `https://workshopss-inventory.onrender.com`
   * **Build Command**: `pip install -r requirements.txt`
   * **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   * **Health Check Path**: `/health`
6. Click **Apply** or **Create Web Service**.

> **Note on Persistent Storage (Render)**:
> In the free tier, Render dynos use ephemeral disks. For production environments where uploaded files and inventory records must persist across dyno redeployments, attach a **Render Persistent Disk** mounted at `/var/data` and set environment variable `DATA_DIR=/var/data` (pre-configured in `render.yaml`).

---

## 🔒 Default Role Credentials

To access administrative functions from the Portal (🔒 icon on the navbar):
* **Superadmin**: Full administrative permissions, branding customization, room status toggling, and equipment deletion.
* **Admin**: Equipment editing, transaction deletion, and consumable modifications.
* **User / Guest**: General inventory inquiry, equipment detail inspection, and logging new activities.

---

## 📄 License
Internal Facility System — Radar & Electronic Warfare Division.
All rights reserved.
