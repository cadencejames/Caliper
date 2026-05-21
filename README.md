<p align="center">
  <img src="static/favicon.svg" width="80" height="80" alt="Caliper">
</p>

# Caliper: The Physical Library Manager
![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Flask](https://img.shields.io/badge/framework-Flask-lightgrey)
![Docker](https://img.shields.io/badge/container-Docker-2496ED)
![License](https://img.shields.io/github/license/cadencejames/caliper)
![Last Commit](https://img.shields.io/github/last-commit/cadencejames/Caliper)
![Contributors](https://img.shields.io/github/contributors/cadencejames/Caliper)

Caliper is a self-hosted, mobile-responsive web application designed for book collectors who care about **physical editions**. Unlike ebook managers (Calibre) or reading trackers (Goodreads/StoryGraph), Caliper focuses on inventory management of your physical shelf: precise dimensions, weights, binding types, and series consistency.

Built with **Python (Flask)**, **SQLite**, and **Docker**.

---

## 🚀 Key Features

*   **Physical Tracking:** Track height (mm), width (mm), and weight (g).
*   **Series Intelligence:** Automatically groups books by Series and sorts them by internal chronology (e.g., Book 0.5, 1, 2) rather than alphabetical title.
*   **Metadata Automation:** "Magic Fetch" button uses the Open Library API to auto-fill metadata, covers, and page counts by ISBN.
*   **Audit Mode:** A dedicated high-speed interface for fixing missing data. Includes an Excel-style inline editor for rapid physical measuring.
*   **Advanced Search:** Query all books by any field (height, width, weight, title, author, binding) using a flexible field/operator/value filter. Available in both Admin and Public modes.
*   **Twin-Mode Deployment:**
    *   **Admin Mode:** Full Add/Edit/Delete capabilities.
    *   **Public Mode:** Read-only view for sharing your library with the world securely.
*   **Mobile Optimized:** Automatically switches from a Data Table view (Desktop) to a Card view (Mobile).
*   **Smart Linking:** Automatically detects and links duplicate copies (e.g., Hardcover vs. Paperback) on the detail page.
*   **Reading Status:** Track Read, TBR, DNF, and Signed copies with visual badges.
*   **Data Import/Export:** One-click CSV export of your full library. CSV import with a preview/confirm step — review all rows before anything is saved, with skipped rows shown with reasons.
*   **TBR Shuffle:** A "Shuffle" button picks a random book from your To Read pile and presents it on a reveal page with cover art, series info, and the option to pick again.

---

## 🛠️ Project Structure

    Caliper/
    ├── app.py                  # Main Flask application & routes
    ├── docker-compose.yml      # Deployment config (Admin + Public containers)
    ├── Dockerfile              # Build recipe
    ├── maintenance.py          # CLI tool for manual database edits
    ├── setup_example_db.py     # Script to generate a dummy database for testing
    ├── requirements.txt        # Python dependencies
    ├── templates/              # HTML templates (Jinja2)
    │   ├── index.html          # Home/Search/Filter
    │   ├── book_detail.html    # Single book view
    │   ├── add_book.html       # Add & Edit form
    │   ├── audit.html          # Data hygiene dashboard
    │   ├── search.html         # Advanced field/operator/value query
    │   ├── stats.html          # Collection analytics dashboard
    │   ├── import.html         # CSV import/export
    │   └── random.html         # TBR shuffle / reveal page
    ├── static/                 # Static assets
    │   ├── favicon.svg         # Site favicon
    │   └── covers/             # Locally hosted cover images
    └── data/                   # Database storage
        └── books.db            # Books Database

---

## ⚡ Quick Start (Local Development)

### 1. Clone and Setup
```
git clone https://github.com/cadencejames/Caliper.git
cd Caliper

# Create virtual environment (Optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Generate Database
Don't have a database yet? Run this script to generate `data/books.db` with sample data.
```
python setup_example_db.py
```

### 3. Run the App
```
python app.py
```

Access the site at **http://127.0.0.1:5000**

---

## 🐳 Deployment (Docker / TrueNAS)

Caliper is designed to run in a "Master/Mirror" configuration using Docker Compose. This allows you to expose a public read-only version while keeping the admin tools restricted to a private port.

### 1. Build the Image
```
docker build -t caliper-app .
```

### 2. Run with Compose
The `docker-compose.yml` is pre-configured to spin up two containers sharing the same database volume.
```
docker-compose up -d
```

### 3. Ports
*   **Admin Console (Read/Write):** `http://localhost:5011`
    *   *Features:* Add, Edit, Delete, Audit, Import/Export, Stats, Shuffle, Search, Filter, Sort, View Details.
*   **Public Mirror (Read-Only):** `http://localhost:5010`
    *   *Features:* Search, Filter, Sort, Advanced Search, View Details, Stats, Shuffle. All admin routes return 404.

---

## 🔍 Workflows

### The Audit Workflow
Navigate to `/audit` (or click the **Audit** button in Admin mode).
1.  **Bibliographic Audit:** Lists books missing ISBNs.
2.  **Physical Audit:** Lists books missing dimensions. This view features **Inline Editing**. Type `Height` -> `Tab` -> `Width` -> `Enter` to auto-save and jump to the next row.

### The "No ISBN" Flag
For books that pre-date ISBNs or are limited editions:
1.  Go to Audit page.
2.  Click **"No ISBN Exists"**.
3.  The book is flagged in the database and removed from the Audit list.

### The Import / Export Workflow
Navigate to `/import` (or click **Import / Export** in Admin mode).

**Exporting:** Click **Download CSV** to download your full library as `caliper_library.csv`. All fields are included, making it suitable for backups or migrating to a new instance.

**Importing:**
1.  Select a `.csv` file and click **Preview Import**.
2.  Review the parsed rows before anything is saved. Books missing a title or author are shown in a separate Skipped Rows table with the reason.
3.  Click **Import N Books** to confirm. All rows are inserted in a single transaction — if anything fails, nothing is written.

The CSV format matches the export exactly. `read_status` values are case-sensitive: `Read`, `To Read`, `DNF`, `Reference`. Invalid values are imported as blank.

---

## 🛣️ Roadmap & Versioning

**Current Version:** v2.2.0

### Changelog

**v2.2.0** - TBR Shuffle (`/random`): picks a random To Read book and presents it on a reveal page with cover art, title, author, series, and format. Includes "Let's Read It" and "Pick Again" buttons. Empty TBR shows a friendly message.  
**v2.1.0** - Admin-only CSV import/export. Export downloads a full library CSV including all fields. Import uses a preview/confirm flow: parse the file, review all rows before anything is committed, with skipped rows shown with reasons. Handles Excel BOM encoding, rejects non-CSV files, and wraps all inserts in a single transaction (rolls back on failure). Also adds `cover_filename` to the database schema.  
**v2.0.0** - Stats Dashboard (`/stats`) with Chart.js visualizations: reading status distribution, format breakdown, unfinished series tracker, TBR page mountain, library weight, shelf height, signed copies, DNF rate, oldest and longest book highlights. Also adds input sanitization (whitespace trimming) on all Add/Edit book fields.  
**v1.3.0** - Advanced Search page (`/search`) with field/operator/value query builder across all books. Available in both Admin and Public modes. Also adds dynamic filter to the Physical Audit tab.  
**v1.2.1** - Add cover_filename field on Add and Edit forms in the Admin view.  
**v1.2.0** - Local cover image support via static/covers volume mount.  
**v1.1.0** - Full visual refresh of all templates.  
**v1.0.1** - Audit page now includes books missing weight data.  
**v1.0.0** - Initial Release (Phase 1 Completed)

### Phase 1: Core & Infrastructure (Completed)
- [x] Database normalization and CSV import logic
- [x] Docker containerization (Master/Mirror architecture)
- [x] Mobile-responsive Card UI
- [x] Open Library API integration (Metadata & Covers)
- [x] Audit Dashboard for rapid data entry
- [x] Smart "Duplicate Copy" detection

### Phase 2: Discovery & Visualization (Completed)
- [x] **Stats Dashboard:** Visual charts and metrics including reading status distribution, library weight, format breakdown, TBR page mountain, DNF rate, longest/oldest book, signed copies count, total shelf height, and unfinished series.
- [x] **Random Picker:** A "Shuffle" button presents a random TBR book on a reveal page with cover art and pick-again option.
- [x] **Data Import/Export:** CSV export and import with a preview/confirm flow. Admin-only.

### Phase 3: Architecture & Enrichment (Planned)
- [ ] **Barcode Scanning:** Native camera integration to add books by scanning physical barcodes.
- [ ] **Tagging System:** Custom user-defined tags for custom collections.

### Phase 4: Relational Data (Planned)
- [ ] **Author Table:** Relational `Authors` table with enriched metadata (nationality, gender, birth year) sourced via API with manual override.
- [ ] **Series Table:** Relational `Series` table with full series knowledge — total book count, individual titles, and publication order — sourced from Google Books and Wikidata with manual override.
- [ ] **Series Navigation:** Dedicated series view with gap detection, showing owned books in order and flagging missing entries against known series totals.
- [ ] **Fun Stats:** Relational-data-powered stats including series gap detection and most collected author — enabled by the Author and Series tables.

---

## 🖼️ Local Cover Images

Caliper supports locally hosted cover images as the primary cover source, falling back to the Open Library API, then a CSS placeholder if neither is available.

1. Place cover images in the `static/covers/` folder, named `<isbn>.jpg` (e.g. `9780441172719.jpg`).
2. Set the `cover_filename` column in the database to the filename for that book.
3. If the file exists on disk, it will be used. If not, the Open Library cover URL is used instead.

When deploying with Docker, the `static/covers/` directory is mounted as a volume so covers persist across container rebuilds.

---

## 🛡️ Security

This app uses Environment Variables to toggle security modes.
*   `APP_MODE=ADMIN` (Default): Enables all routes.
*   `APP_MODE=PUBLIC`: Disables `/add`, `/edit`, `/delete`, `/audit`, `/import`, and `/export` at the code level.

This logic ensures that even if the public site is exposed to the internet, modification of the database is impossible via the web interface.

---

## 📄 License
[MIT License](LICENSE)
