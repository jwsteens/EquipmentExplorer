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

Install [Docker](https://docs.docker.com/get-started/get-docker/). [Git](https://git-scm.com/install/) can be used to clone the repository, or it can be cloned manually.

1. **Clone the repository**
   ```bash
   git clone https://github.com/jwsteens/EquipmentExplorer
   cd EquipmentExplorer/
   ```

2. **Build the image and start the container**
   ```bash
   docker compose up -d
   ```

The app is now running at `http://localhost:5000`.

## Data Setup

After installation, import your data and index documents.

1. **Open a terminal in the container**
   ```bash
   docker compose exec equipment-explorer bash
   ```

2. **Import data** using the interactive CLI tool
   ```bash
   python manage.py setup
   ```
   This guides you through:
   - Importing equipment & cables from Excel;
   - Importing compartment descriptions from CSV;
   - Scanning and registering PDF documents;
   - Importing document metadata.

3. **First login** — go to `http://localhost:5000` and log in with the default credentials (`admin` / `admin`). Change the admin password, then go to the Documents page and select which documents to index.

4. **Index PDFs**
   ```bash
   python manage.py index-documents
   ```

## Network Access

Use [nginx](https://nginx.org/) to route traffic from port 80 to the app port and configure the firewall to allow this traffic.

If you do not have nginx installed on your system yet, follow these steps to get it going for this project:
1. Install **nginx**.
   ```bash
   sudo apt update
   sudo apt install nginx
   ```
2. Modify `/etc/nginx/nginx.conf`
   In the `http` block, add the following block:
   ```
   server {
      listen 80;
      server_name _;

      location / {
         proxy_pass http://127.0.0.1:5000;
         proxy_set_header Host $host;
         proxy_set_header X-Real-IP $remote_addr;
         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
         proxy_set_header X-Forwarded-Proto $scheme;
      }
   }
   ```

   Or simply copy `nginx.conf` from this repo into `/etc/nginx/`.


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
│   │   ├── db.py
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
│       ├── error.html          # Error page
│       ├── help.html           # Help page
│       ├── login.html          # Login page
│       ├── profile.html        # User profile / password change
│       └── admin/              # Admin interface templates
│           ├── access_logs.html
│           ├── dashboard.html
│           ├── error_logs.html
│           ├── user_form.html
│           └── users.html
├── data/
│   ├── equipment_explorer.db   # SQLite database
│   └── setup/                  # Source data files (xlsx)
├── documents/                  # PDF documents (vessel-specific)
├── Dockerfile
├── docker-compose.yml
├── nginx.conf
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

## Notes

- The PDF viewer supports tag highlighting via `#search=TAG` — works in both Firefox, or Chromium browsers (Chrome, Brave, Edge, etc.) with the [pdf.js viewer](https://chromewebstore.google.com/detail/pdf-viewer/oemmndcbldboiebfnladdacbdfmadadm) extension installed.
- Sessions persist across app restarts and expire after 24 hours.

## Future features
These features may be implemented in the future:
- IO tag connections.
- HTTPS support.
- Connection graph from pinned equipment and cables.
- Tracking of updated cable list and documents and automatic re-indexing.
- Quick import using JSON profiles.