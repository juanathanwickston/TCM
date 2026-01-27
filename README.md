# Training Catalog Analyzer

A Streamlit dashboard app that analyzes training catalog folder submissions and displays inventory metrics.

> ⚠️ **System Contract**: All operational metrics are governed by [`SYSTEM_CONTRACT.md`](SYSTEM_CONTRACT.md).  
> **Breaking this contract invalidates all metrics.** Read it before modifying queries or adding pages.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

> **⚠️ Deployment Note**: Production uses `requirements.txt`. Local legacy (Streamlit) uses `requirements-dev.txt`. **Do not add Streamlit packages to `requirements.txt`**—this is enforced by CI tests in `tests/test_requirements.py`.

### 2. Run the App

```bash
streamlit run app.py
```

The app will open in your default browser at `http://localhost:8501`.

## Development Setup

### Pre-commit Hooks (Recommended)

Install pre-commit to catch template syntax errors before committing:

```bash
pip install pre-commit
pre-commit install
```

This validates Django templates on each commit, preventing CI failures.

## Usage

1. **Upload a ZIP file** containing your Training Submission folder
2. The app will automatically:
   - Extract and scan the folder structure
   - Count files and links in each taxonomy folder
   - Display KPI metrics and visualizations
3. **Export** your analysis as CSV or Excel

## Expected Folder Structure

```
[Department Name] – Training Submission/
├── 01_Onboarding/
│   ├── 01_Direct/
│   │   ├── 01_Instructor Led – In Person/
│   │   │   └── links.txt
│   │   ├── 02_Instructor Led – Virtual/
│   │   ├── 03_Self Directed/
│   │   ├── 04_Video On Demand/
│   │   ├── 05_Job Aids/
│   │   └── 06_Resources/
│   ├── 02_Indirect/
│   │   └── (same format folders)
│   └── ... (07_Compliance)
├── 02_Upskilling/
│   └── (same structure as Onboarding)
└── 03_Not Sure (Drop Here)/
    └── (format folders only)
```

## Counting Rules

- **Inventory item** = a file (any extension except `links.txt`) OR a URL line in `links.txt`
- **Link** = any line in `links.txt` starting with `http://` or `https://`
- **links.txt** itself is NOT counted as a file item
- **Folder with content** = has ≥1 file item OR ≥1 link item
- **Empty folder** = 0 file items AND 0 link items
- **Coverage %** = folders with content ÷ total taxonomy folders scanned

## Features

### KPI Tiles
- Total Items (files + links)
- Total Files (excluding links.txt)
- Total Links (URLs from links.txt)
- Folders with Content
- Empty Folders
- Coverage %

### Breakdown Tables
- **Summary**: Grouped by bucket, functional area, and format
- **Folders with Content**: Sorted by total items descending
- **Empty Folders**: List of folders without any items

### Visualizations
- Bar chart: Items by Bucket
- Bar chart: Items by Format

### Exports
- Detailed folder-level CSV
- Grouped summary CSV
- Excel workbook with both sheets

## Notes

- Hidden/system files (Thumbs.db, .DS_Store, etc.) are automatically ignored
- The app is robust to missing expected folders — it reports what it finds
- Works with SharePoint-synced folders via ZIP upload on Windows

---

## Project Structure

```
training_catalog_analyzer/
├── app.py                 # Single entrypoint (streamlit run app.py)
├── db.py                  # Database module (SQLite)
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── SYSTEM_CONTRACT.md     # Metrics contract (READ BEFORE MODIFYING)
├── DEVELOPER_BRIEF.md     # Developer documentation
│
├── assets/                # Static assets (fonts, images, CSS)
├── components/            # Reusable UI components
├── models/                # Data models and enums
├── services/              # Business logic services
├── views/                 # Page view modules
├── tests/                 # Test files
│
├── scripts/               # Utility scripts (NOT runtime)
│   ├── check_db.py        # DB inspection utility
│   ├── reset_data.py      # Demo data reset script
│   └── test_zip.py        # ZIP file testing
│
├── data/                  # Runtime data (gitignored)
│   └── catalog.db         # SQLite database
│
├── docs/                  # Documentation
│   └── audit/             # Audit reports
│
└── Payroc Training Catalogue/  # SOURCE OF TRUTH - DO NOT MODIFY
```

## Important Notes

### Database Location
- **Path**: `data/catalog.db`
- **Generated**: Runtime (not committed to git)
- **Canonical reference**: `db.py` line 15

### What NOT to Touch
- `Payroc Training Catalogue/` — Source of truth for content
- SQL queries in `db.py` unless updating the system contract
- Metrics predicates (`is_archived = 0 AND is_placeholder = 0`)

