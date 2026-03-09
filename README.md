# EquipmentExplorer

A web app that allows technicians to search and navigate ship equipment documentation. Search for cable and equipment tags and instantly find which PDF drawings they appear in.

## Features

- **Search**: Full-text search for cable and equipment tags with autocomplete
- **Cable List**: DataTables-powered view of all cables with connections and locations
- **Documents**: Browse all indexed PDFs with tag counts and metadata
- **Admin Dashboard**: User management, session control, access logs, error logs
- **Dark/Light Mode**: Toggle with `T` key or button
- **Keyboard Shortcuts**: Fast navigation (`/` to search, `?` for help)
- **Role-Based Access**: Admin, Editor, and Viewer roles
- **PDF Viewer**: In-browser PDF viewing with tag highlighting. To make optimal use of this feature, use Firefox or use the [pdf.js viewer](https://chromewebstore.google.com/detail/pdf-viewer/oemmndcbldboiebfnladdacbdfmadadm) extension.

## Installation

Install Python, pip and git.

1. **Clone git**
   ```bash
   git clone https://github.com/jwsteens/EquipmentExplorer
   ```

2. **Create Python and activate virtual environment**
   ```bash
   python -m venv EquipmentExplorer/
   
   cd EquipmentExplorer/
   source bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r src/requirements.txt
   ```

4. **Import data** using the Command Line Interface tool
   ```bash
   python src/manage.py setup
   ```
   This guides you through:
   - Importing equipment & cables from Excel;
   - Importing compartment descriptions from CSV;
   - Scanning and registering PDF documents;
   - Importing document metadata.

5. **Start web app**
   ```bash
   cd src
   waitress-serve --host=127.0.0.1 --port=8080 app:app
   ```

   1. Log in with default credentials (admin / admin);
   2. Change password for admin;
   3. Go to Documents page and select documents to be indexed.

6. **Index PDFs**
   ```bash
   python src/manage.py index-documents
   ```

## File Structure

```
EquipmentExplorer/
├── src/
│   ├── app.py                  # Main Flask application
│   ├── database.py             # Database operations
│   ├── auth.py                 # Authentication & session management
│   ├── admin_routes.py         # Admin dashboard blueprint
│   ├── index_documents.py      # PDF indexer (multicore)
│   ├── manage.py               # Interactive setup/import CLI
│   ├── search.py               # CLI search interface
│   ├── schema.sql              # Database schema
│   ├── requirements.txt        # Python dependencies
│   ├── setup/                  # Data import scripts
│   │   ├── import_equipment_and_cables.py
│   │   ├── import_compartments.py
│   │   ├── import_documents.py
│   │   └── import_metadata.py
│   ├── static/
│   │   ├── css/main.css        # Main stylesheet
│   │   ├── js/
│   │   │   ├── main.js         # Global JavaScript
│   │   │   ├── search.js       # Search page logic
│   │   │   └── sw.js           # Service worker (PWA)
│   │   └── icons/              # PWA icons
│   └── templates/
│       ├── base.html           # Base template with navigation
│       ├── index.html          # Dashboard
│       ├── search.html         # Search interface
│       ├── cables.html         # Cable list
│       ├── documents.html      # Document list
│       ├── help.html           # Help page
│       ├── login.html          # Login page
│       ├── profile.html        # User profile / password change
│       └── admin/              # Admin interface templates
├── data/
│   └── equipment_explorer.db   # SQLite database
├── sample_data/                # Example data files
└── .env                        # Environment configuration
```

## User Roles

| Role | Access |
|------|--------|
| **Admin** | Full access: user management, admin dashboard, all pages |
| **Editor** | Access to all pages, can manage document indexing flags |
| **Viewer** | Read-only access to search, cables, and documents |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | Database statistics |
| `GET /api/search/tag/<tag>` | Search for exact tag |
| `GET /api/search/partial/<partial>` | Partial tag search |
| `GET /api/search/autocomplete?q=...` | Autocomplete suggestions |
| `GET /api/cables` | All cables (for DataTables) |
| `GET /api/cables/server-side` | Server-side paginated cables |
| `GET /api/documents` | All documents (for DataTables) |
| `PATCH /api/documents/<id>/index-flag` | Set document indexing flag (Admin) |
| `GET /api/pdf/<id>/tags` | Tags found in a PDF |
| `GET /pdf/<path>` | Serve PDF file |

## Network Access

Use [nginx](https://nginx.org/) to route traffic from port 80 to the app port and configure the firewall to allow this traffic.

## Notes

- The PDF viewer supports tag highlighting via `#search=TAG` — works in both Firefox and Chrome/Chromium with [pdf.js viewer](https://chromewebstore.google.com/detail/pdf-viewer/oemmndcbldboiebfnladdacbdfmadadm) extension.
- Sessions persist across app restarts and expire after 24 hours
