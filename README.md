# Caliper: The Physical Library Manager

Caliper is a self-hosted, mobile-responsive web application designed for book collectors who care about physical editions. Unlike standard trackers (Goodreads/StoryGraph), Caliper focuses on inventory management: precise dimensions, weights, binding types, and series consistency.

Built with **Python (Flask)**, **SQLite**, and **Docker**.

---

## 🚀 Key Features

*   **Physical Tracking:** Track height (mm), width (mm), and weight (g).
*   **Series Intelligence:** Automatically groups books by Series and sorts them by internal chronology (e.g., Book 0.5, 1, 2) rather than alphabetical title.
*   **Metadata Automation:** "Magic Fetch" button uses the Open Library API to auto-fill metadata, covers, and page counts by ISBN.
*   **Audit Mode:** A dedicated high-speed interface for fixing missing data. Includes an Excel-style inline editor for rapid physical measuring.
*   **Twin-Mode Deployment:**
    *   **Admin Mode:** Full Add/Edit/Delete capabilities.
    *   **Public Mode:** Read-only view for sharing your library with the world securely.
*   **Mobile Optimized:** Automatically switches from a Data Table view (Desktop) to a Card view (Mobile).
*   **Smart Linking:** Automatically detects and links duplicate copies (e.g., Hardcover vs. Paperback) on the detail page.
*   **Reading Status:** Track Read, TBR, DNF, and Signed copies with visual badges.

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
    │   └── audit.html          # Data hygiene dashboard
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
    *   *Features:* Add, Edit, Delete, Audit, Settings.
*   **Public Mirror (Read-Only):** `http://localhost:5010`
    *   *Features:* Search, Filter, Sort, View Details. All admin routes return 404.

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

---

## 🛣️ Roadmap & Versioning

**Current Version:** v1.0.0 (Phase 1 Complete)

### Phase 1: Core & Infrastructure (Completed)
- [x] Database normalization and CSV import logic
- [x] Docker containerization (Master/Mirror architecture)
- [x] Mobile-responsive Card UI
- [x] Open Library API integration (Metadata & Covers)
- [x] Audit Dashboard for rapid data entry
- [x] Smart "Duplicate Copy" detection

### Phase 2: Discovery & Visualization (In Progress)
- [ ] **Stats Dashboard:** Visual charts for reading status, library weight, and format distribution.
- [ ] **Series Navigation:** Dedicated view to list books in a series order (e.g. 1, 2, 3) to identify gaps.
- [ ] **Random Picker:** A "Shuffle" button to help pick the next read from the TBR pile.
- [ ] **Data Export:** One-click CSV/DB backup from the Admin interface.

### Phase 3: Architecture & Enrichment (Planned)
- [ ] **Author Normalization:** Migration to a relational `Authors` table to better track metadata (Gender, Nationality).
- [ ] **Barcode Scanning:** Native camera integration to add books by scanning physical barcodes.
- [ ] **Advanced API Fallbacks:** Fallback to Google Books API if Open Library data is missing.
- [ ] **Tagging System:** Custom user-defined tags for custom collections.

---

## 🛡️ Security

This app uses Environment Variables to toggle security modes.
*   `APP_MODE=ADMIN` (Default): Enables all routes.
*   `APP_MODE=PUBLIC`: Disables `/add`, `/edit`, `/delete`, and `/audit` at the code level.

This logic ensures that even if the public site is exposed to the internet, modification of the database is impossible via the web interface.

---

## 📄 License
[MIT License](LICENSE)
