# EquipmentExplorer
A web app that allows technicians to navigate documentation about their equipment.

## Features

- **Search**: Full-text search for cables and equipment tags with autocomplete
- **Cable List**: DataTables-powered view of all cables with connections (Excel-like experience)
- **Documents**: Browse all indexed PDFs with tag counts and direct access
- **Dark/Light Mode**: Toggle with `T` key or button
- **Keyboard Shortcuts**: Fast navigation (`/` to search, `?` for help)
- **PWA Support**: Works offline, installable on desktop/mobile
- **Compartment Lookup**: Room tags enriched with descriptions

## Installation

Make sure Python 3.12+ is installed.

1. **Activate Python virtual environment**
  ```bash
  # On linux:
  source bin/activate
  
  # On windows:
  ./Scripts/Activate
  ```
  
Then change working directory to `src`:
  ```bash
  cd src
  ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Prepare data files** (if not already done):
   ```bash
   # Import cables from Excel
   python import_cable_list.py Cable_list.xlsx ship_cables.db
   
   # Import drawing metadata
   python import_drawing_metadata.py "Overview_Drawings_and_Documents.xlsx" drawing_metadata.pkl
   
   # Create compartment lookup
   python create_compartment_pickle.py Compartment_number_plan.csv compartments.pkl
   
   # Index PDFs (optional, requires PyMuPDF)
   python index_pdfs.py --dir /path/to/pdf/drawings --db ship_cables.db
   ```
   
Configure PDF_ROOT in .env.

4. **Run the server**:
   ```bash
   waitress-serve --host=127.0.0.1 app:app
   ```
   
   Configure nginx to allow the server to be accessed from the LAN.

5. **Access the interface**:
   Open http://localhost:8000 in your browser

## Command Line Options

```
python app.py [options]

Options:
  --port, -p        Port to run on (default: 5000)
  --host, -H        Host to bind to (default: 127.0.0.1)
  --db              Path to SQLite database (default: ship_cables.db)
  --pdf-root        Root directory for PDF files
  --metadata        Path to metadata pickle (default: drawing_metadata.pkl)
  --compartments    Path to compartments pickle (default: compartments.pkl)
  --debug           Enable debug mode
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `/` | Focus search |
| `Esc` | Clear search / Close modals |
| `T` | Toggle dark/light theme |
| `?` | Show keyboard shortcuts |
| `G` then `H` | Go to Dashboard |
| `G` then `S` | Go to Search |
| `G` then `C` | Go to Cables |
| `G` then `D` | Go to Documents |

## File Structure

```
ship-cable-web/
├── app.py                 # Main Flask application
├── database.py            # Database operations
├── schema.sql             # Database schema
├── requirements.txt       # Python dependencies
├── ship_cables.db         # SQLite database (generated)
├── drawing_metadata.pkl   # Document metadata cache
├── compartments.pkl       # Room descriptions cache
├── static/
│   ├── css/
│   │   └── main.css       # Main stylesheet
│   ├── js/
│   │   ├── main.js        # Global JavaScript
│   │   ├── search.js      # Search page logic
│   │   └── sw.js          # Service worker (PWA)
│   └── icons/
│       └── icon-*.png     # PWA icons
└── templates/
    ├── base.html          # Base template with nav
    ├── index.html         # Dashboard
    ├── search.html        # Search interface
    ├── cables.html        # Cable list
    └── documents.html     # Document list
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | Database statistics |
| `GET /api/search/tag/<tag>` | Search for exact tag |
| `GET /api/search/partial/<partial>` | Partial tag search |
| `GET /api/search/autocomplete?q=...` | Autocomplete suggestions |
| `GET /api/cables` | All cables (for DataTables) |
| `GET /api/documents` | All documents (for DataTables) |
| `GET /api/pdf/<id>/tags` | Tags found in a PDF |
| `GET /pdf/<path>` | Serve PDF file |

## Network Access

Use ([nginx](https://nginx.org/)) to route traffic from port 80 to 8080 and configure the firewall to allow this traffic.

## Notes

- PDFs are served through the web app, so the `--pdf-root` must be accessible
- The PDF viewer includes search highlighting via `#search=TAG` fragment
- Firefox and Chrome both support the search highlighting feature
- The app caches data in the browser for offline access (PWA)

## Troubleshooting

**PDFs not loading?**
- Check that `--pdf-root` is correctly set
- Verify the path matches what's in the database

**Search not finding tags?**
- Run `index_pdfs.py` to index your PDFs
- Check if the tag exists with partial search

**Slow loading?**
- The cable list has 23,000+ rows; DataTables pagination helps
- Consider filtering by deck or category

