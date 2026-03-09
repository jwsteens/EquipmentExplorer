"""
Equipment Explorer - Web Interface

A Flask-based web application for searching cables, equipment, and drawings.
"""

import os
import secrets
import mimetypes
import traceback
from pathlib import Path
from flask import Flask, render_template, jsonify, request, send_file, abort, session, redirect, url_for, flash, g
from database import ShipCableDB
from auth import AuthManager, login_required, admin_required, editor_required, SECRET_KEY
from admin_routes import admin_bp

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

def _abs(raw: str) -> str:
    p = Path(raw)
    return str(p if p.is_absolute() else _PROJECT_ROOT / p)

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Configuration — always absolute so send_file and ShipCableDB work regardless of CWD
DB_PATH = _abs(os.environ.get('DB_PATH', 'data/equipment_explorer.db'))
PDF_ROOT = _abs(os.environ.get('DOCUMENTS_PATH', 'data/documents'))
# Initialize database and auth
db = None
auth_manager = None


def get_db():
    """Get or create database connection."""
    global db
    if db is None:
        db = ShipCableDB(DB_PATH)
    return db


def get_auth():
    """Get or create auth manager."""
    global auth_manager
    if auth_manager is None:
        auth_manager = AuthManager(get_db())
    return auth_manager


# Load data on startup
with app.app_context():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    get_auth()  # initializes DB schema + auth tables + default admin


# =============================================================================
# AUTHENTICATION MIDDLEWARE & ROUTES
# =============================================================================

# Register admin blueprint
app.register_blueprint(admin_bp)


@app.before_request
def load_user():
    """Load user from session before each request."""
    g.user = None
    session_id = session.get('session_id')
    if session_id:
        auth = get_auth()
        g.user = auth.validate_session(session_id)
        if not g.user:
            # Invalid session, clear it
            session.pop('session_id', None)
    
    # Store db and auth in app config for blueprints
    app.config['DB'] = get_db()
    app.config['AUTH_MANAGER'] = get_auth()


@app.context_processor
def inject_user():
    """Inject user into all templates."""
    return {'current_user': g.get('user')}


@app.after_request
def add_cache_control(response):
    """Add cache control headers to prevent caching of authenticated pages."""
    # Don't cache HTML pages - they contain auth-dependent content
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    # Don't cache API responses either
    elif request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


@app.errorhandler(Exception)
def handle_error(error):
    """Log unhandled errors."""
    auth = get_auth()
    user_id = g.user['user_id'] if g.get('user') else None
    
    # Log the error
    auth.log_error(
        error_type=type(error).__name__,
        error_message=str(error),
        stack_trace=traceback.format_exc(),
        endpoint=request.path,
        user_id=user_id,
        ip_address=request.remote_addr
    )
    
    # Re-raise for default handling in debug mode
    if app.debug:
        raise error
    
    # Return generic error in production
    return render_template('error.html', error=error), 500


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if g.get('user'):
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        auth = get_auth()
        user = auth.authenticate(username, password)
        
        if user:
            session_id = auth.create_session(
                user['user_id'],
                request.remote_addr,
                request.user_agent.string
            )
            session['session_id'] = session_id
            
            # Set g.user for the current request so templates work immediately
            g.user = user
            
            auth.log_access(user['user_id'], username, 'login', 
                          f'Successful login',
                          request.remote_addr, request.user_agent.string)
            
            flash(f'Welcome back, {username}!', 'success')
            
            next_url = request.args.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('index'))
        else:
            auth.log_access(None, username, 'login_failed',
                          f'Failed login attempt',
                          request.remote_addr, request.user_agent.string)
            flash('Invalid username or password.', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout and destroy session."""
    session_id = session.get('session_id')
    if session_id:
        auth = get_auth()
        if g.get('user'):
            auth.log_access(g.user['user_id'], g.user['username'], 'logout',
                          'User logged out',
                          request.remote_addr, request.user_agent.string)
        auth.destroy_session(session_id)
    
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page for changing password."""
    auth = get_auth()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Verify current password
        user = auth.authenticate(g.user['username'], current_password)
        if not user:
            flash('Current password is incorrect.', 'error')
            return render_template('profile.html')
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters.', 'error')
            return render_template('profile.html')
        
        if new_password != confirm_password:
            flash('New passwords do not match.', 'error')
            return render_template('profile.html')
        
        auth.change_password(g.user['user_id'], new_password)
        auth.log_access(g.user['user_id'], g.user['username'], 'password_change',
                      'User changed their password',
                      request.remote_addr, request.user_agent.string)
        flash('Password changed successfully.', 'success')
    
    return render_template('profile.html')


# =============================================================================
# ROUTES - Pages
# =============================================================================

@app.route('/')
@login_required
def index():
    """Dashboard / Home page."""
    db = get_db()
    stats = db.get_stats()
    return render_template('index.html', stats=stats)


@app.route('/search')
@login_required
def search_page():
    """Search interface page."""
    return render_template('search.html')


@app.route('/help')
@login_required
def help_page():
    """Help / instructions page."""
    return render_template('help.html')


@app.route('/cables')
@login_required
def cables_page():
    """Cable list page."""
    return render_template('cables.html')


@app.route('/documents')
@login_required
def documents_page():
    """Documents/drawings list page."""
    return render_template('documents.html')


# =============================================================================
# API ROUTES - Data
# =============================================================================

@app.route('/api/stats')
@login_required
def api_stats():
    """Get database statistics."""
    db = get_db()
    stats = db.get_stats()
    return jsonify(stats)


@app.route('/api/search/tag/<tag_name>')
@login_required
def api_search_tag(tag_name):
    """Search for a specific tag and return all PDFs where it appears."""
    db = get_db()
    
    # Try exact match first, then uppercase
    results = db.search_tag(tag_name)
    search_tag = tag_name
    if not results:
        results = db.search_tag(tag_name.upper())
        search_tag = tag_name.upper()
    
    # Even if no PDF results, try to find tag info from database
    tag_info = None
    if results:
        tag_info = {
            'tag_name': results[0]['tag_name'],
            'tag_type': results[0]['tag_type'],
            'description': results[0]['description']
        }
    else:
        # Try to get tag info even without PDF occurrences
        with db._get_connection() as conn:
            cursor = conn.execute(
                'SELECT tag AS tag_name, description, room_tag, deck FROM equipment WHERE tag = ? OR tag = ?',
                (tag_name, tag_name.upper())
            )
            row = cursor.fetchone()
            if row:
                tag_info = {
                    'tag_name': row['tag_name'],
                    'tag_type': 'equipment',
                    'description': row['description'],
                    'room_tag': row['room_tag'],
                    'deck': row['deck']
                }
                search_tag = row['tag_name']
            else:
                cursor = conn.execute(
                    'SELECT tag AS tag_name, type AS description FROM cables WHERE tag = ? OR tag = ?',
                    (tag_name, tag_name.upper())
                )
                row = cursor.fetchone()
                if row:
                    tag_info = {
                        'tag_name': row['tag_name'],
                        'tag_type': 'cable',
                        'description': row['description'],
                    }
                    search_tag = row['tag_name']
    
    if not tag_info:
        return jsonify({
            'found': False,
            'tag_name': tag_name,
            'results': [],
            'connection': None,
            'connected_cables': [],
            'equipment_location': None
        })
    
    # Get connection info based on tag type
    connection = None
    connected_cables = []
    equipment_location = None
    
    if tag_info['tag_type'] == 'cable':
        connection = db.get_cable_connection(tag_info['tag_name'])
        if connection:
            # Compartment descriptions already in view; also expose under legacy keys
            connection['start_room_description'] = connection.get('start_compartment_description')
            connection['dest_room_description'] = connection.get('dest_compartment_description')
    else:
        # Get equipment location info
        with db._get_connection() as conn:
            cursor = conn.execute(
                'SELECT room_tag, deck FROM equipment WHERE tag = ?',
                (tag_info['tag_name'],)
            )
            row = cursor.fetchone()
            if row and (row['room_tag'] or row['deck']):
                room_tag = str(row['room_tag']).split('.')[0] if row['room_tag'] else None
                equipment_location = {
                    'room_tag': row['room_tag'],
                    'room_description': db.get_compartment_description(room_tag),
                    'deck': row['deck']
                }

        connected_cables = db.get_cables_for_equipment(tag_info['tag_name'])
        for cable in connected_cables:
            cable['start_room_description'] = cable.get('start_compartment_description')
            cable['dest_room_description'] = cable.get('dest_compartment_description')
    
    # Group results by PDF
    pdfs = {}
    for r in results:
        path = r['relative_path']
        if path not in pdfs:
            pdfs[path] = {
                'filename': r['filename'],
                'relative_path': path,
                'document_description': r.get('document_description'),
                'supplier_code': r.get('supplier_code') or '',
                'supplier_name': r.get('supplier_name') or '',
                'pages': []
            }
        if r['page_number']:
            pdfs[path]['pages'].append(r['page_number'])
    
    # Sort pages and convert to list
    pdf_list = list(pdfs.values())
    for pdf in pdf_list:
        pdf['pages'] = sorted(set(pdf['pages']))
    
    return jsonify({
        'found': True,
        'tag_info': tag_info,
        'pdfs': pdf_list,
        'connection': connection,
        'connected_cables': connected_cables,
        'equipment_location': equipment_location
    })


@app.route('/api/search/partial/<partial>')
@login_required
def api_search_partial(partial):
    """Search for tags containing the partial string."""
    db = get_db()
    tag_type = request.args.get('type')  # Optional filter
    
    results = db.search_tag_partial(partial, tag_type)
    return jsonify({
        'query': partial,
        'results': results
    })


@app.route('/api/search/autocomplete')
@login_required
def api_autocomplete():
    """Autocomplete endpoint for tag and PDF search."""
    query = request.args.get('q', '').strip()
    search_type = request.args.get('type', 'all')  # all, cable, equipment, pdf
    
    if len(query) < 2:
        return jsonify([])
    
    suggestions = []
    
    # PDF search
    if search_type == 'pdf':
        query_lower = query.lower()
        db = get_db()
        pdf_matches = []

        with db._get_connection() as conn:
            cursor = conn.execute('''
                SELECT filename, document_description, supplier_code, supplier_name
                FROM documents
                WHERE LOWER(filename) LIKE ?
                   OR LOWER(supplier_code) LIKE ?
                   OR LOWER(document_description) LIKE ?
                   OR LOWER(supplier_name) LIKE ?
                ORDER BY filename
                LIMIT 15
            ''', (f'%{query_lower}%', f'%{query_lower}%', f'%{query_lower}%', f'%{query_lower}%'))
            rows = cursor.fetchall()

        for row in rows:
            fn = (row['filename'] or '').lower()
            sc = (row['supplier_code'] or '').lower()
            desc = (row['document_description'] or '').lower()
            sn = (row['supplier_name'] or '').lower()
            if fn.startswith(query_lower):
                score, match_field = 100, 'filename'
            elif query_lower in fn:
                score, match_field = 50, 'filename'
            elif sc.startswith(query_lower):
                score, match_field = 60, 'supplier_code'
            elif query_lower in sc:
                score, match_field = 30, 'supplier_code'
            elif query_lower in desc:
                score, match_field = 40, 'description'
            elif query_lower in sn:
                score, match_field = 35, 'supplier_name'
            else:
                score, match_field = 10, 'filename'
            pdf_matches.append({
                'filename': row['filename'],
                'document_description': row['document_description'] or '',
                'supplier_code': row['supplier_code'] or '',
                'supplier_name': row['supplier_name'] or '',
                'score': score,
                'match_field': match_field
            })

        pdf_matches.sort(key=lambda x: (-x['score'], x['filename']))
        suggestions = [{
            'tag_name': p['filename'],
            'tag_type': 'pdf',
            'description': p['document_description'],
            'supplier_code': p['supplier_code'],
            'supplier_name': p['supplier_name'],
            'match_field': p['match_field']
        } for p in pdf_matches[:15]]
    
    else:
        # Tag search (existing behavior)
        db = get_db()
        tag_type = search_type if search_type in ['cable', 'equipment'] else None
        results = db.search_tag_partial(query, tag_type)
        
        suggestions = [{
            'tag_name': r['tag_name'],
            'tag_type': r['tag_type'],
            'description': r.get('description', ''),
            'pdf_count': r['pdf_count'] or 0,
            'match_priority': r.get('match_priority', 3)
        } for r in results[:15]]
    
    return jsonify(suggestions)


@app.route('/api/cables')
@login_required
def api_cables():
    """Get all cables with connection information for DataTables."""
    db = get_db()
    
    with db._get_connection() as conn:
        cursor = conn.execute('''
            SELECT
                cable_tag AS cable_no,
                cable_type,
                start_equipment_tag AS start_tag,
                start_equipment_description AS start_description,
                start_room_tag AS start_room,
                start_deck,
                dest_equipment_tag AS dest_tag,
                dest_equipment_description AS dest_description,
                dest_room_tag AS dest_room,
                dest_deck,
                start_compartment_description AS start_room_description,
                dest_compartment_description AS dest_room_description
            FROM cable_connections_view
            ORDER BY cable_tag
        ''')
        return jsonify({'data': [dict(row) for row in cursor.fetchall()]})


@app.route('/api/cables/server-side')
@login_required
def api_cables_server_side():
    """
    Server-side processing endpoint for DataTables.
    Supports pagination, sorting, and searching.
    """
    db = get_db()
    
    # DataTables parameters
    draw = request.args.get('draw', type=int, default=1)
    start = request.args.get('start', type=int, default=0)
    length = request.args.get('length', type=int, default=25)
    search_value = request.args.get('search[value]', '').strip()
    
    # Sorting
    order_column_idx = request.args.get('order[0][column]', type=int, default=0)
    order_dir = request.args.get('order[0][dir]', 'asc')
    
    # Map column index to view column
    column_map = {
        0: 'cable_tag',
        1: 'cable_type',
        2: 'start_equipment_tag',
        3: 'start_equipment_description',
        4: 'start_room_tag',
        5: 'dest_equipment_tag',
        6: 'dest_equipment_description',
        7: 'dest_room_tag',
    }

    order_column = column_map.get(order_column_idx, 'cable_tag')
    order_direction = 'DESC' if order_dir == 'desc' else 'ASC'

    with db._get_connection() as conn:
        base_query = 'FROM cable_connections_view'

        search_clause = ''
        search_params = []
        if search_value:
            search_clause = '''
                WHERE cable_tag LIKE ?
                   OR cable_type LIKE ?
                   OR start_equipment_tag LIKE ?
                   OR start_equipment_description LIKE ?
                   OR start_room_tag LIKE ?
                   OR start_deck LIKE ?
                   OR dest_equipment_tag LIKE ?
                   OR dest_equipment_description LIKE ?
                   OR dest_room_tag LIKE ?
                   OR dest_deck LIKE ?
            '''
            search_pattern = f'%{search_value}%'
            search_params = [search_pattern] * 10

        cursor = conn.execute(f'SELECT COUNT(*) {base_query}')
        total_records = cursor.fetchone()[0]

        cursor = conn.execute(
            f'SELECT COUNT(*) {base_query} {search_clause}',
            search_params
        )
        filtered_records = cursor.fetchone()[0]

        data_query = f'''
            SELECT
                cable_tag AS cable_no,
                cable_type,
                start_equipment_tag AS start_tag,
                start_equipment_description AS start_description,
                start_room_tag AS start_room,
                start_deck,
                dest_equipment_tag AS dest_tag,
                dest_equipment_description AS dest_description,
                dest_room_tag AS dest_room,
                dest_deck,
                start_compartment_description AS start_room_description,
                dest_compartment_description AS dest_room_description
            {base_query}
            {search_clause}
            ORDER BY {order_column} {order_direction}
            LIMIT ? OFFSET ?
        '''

        cursor = conn.execute(data_query, search_params + [length, start])

        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': filtered_records,
            'data': [dict(row) for row in cursor.fetchall()]
        })


@app.route('/api/documents')
@login_required
def api_documents():
    """Get all documents/PDFs for DataTables."""
    db = get_db()
    with db._get_connection() as conn:
        cursor = conn.execute('''
            SELECT
                p.pdf_id,
                p.filename,
                p.relative_path,
                p.document_description,
                p.supplier_code,
                p.supplier_name,
                p.supergrandparent,
                p.superparent,
                p.revision,
                p.status,
                p.page_count,
                p.to_be_indexed,
                (p.date_indexed IS NOT NULL) AS indexed,
                (SELECT COUNT(*) FROM equipment_occurrences WHERE pdf_id = p.pdf_id)
                + (SELECT COUNT(*) FROM cable_occurrences WHERE pdf_id = p.pdf_id) AS tag_count
            FROM documents p
            ORDER BY p.filename
        ''')
        return jsonify({'data': [dict(row) for row in cursor.fetchall()]})


@app.route('/api/documents/<int:pdf_id>/index-flag', methods=['PATCH'])
@admin_required
def api_document_index_flag(pdf_id):
    data = request.get_json()
    if data is None or 'to_be_indexed' not in data:
        return jsonify({'error': 'Missing to_be_indexed field'}), 400
    to_be_indexed = bool(data['to_be_indexed'])
    db = get_db()
    with db._get_connection() as conn:
        conn.execute(
            'UPDATE documents SET to_be_indexed = ? WHERE pdf_id = ?',
            (to_be_indexed, pdf_id)
        )
    return jsonify({'success': True})


@app.route('/api/pdf/<int:pdf_id>/tags')
@login_required
def api_pdf_tags(pdf_id):
    """Get all tags found in a specific PDF."""
    db = get_db()
    
    pdf_info = db.get_pdf_by_id(pdf_id)
    if not pdf_info:
        return jsonify({'error': 'PDF not found'}), 404
    
    contents = db.get_pdf_contents_by_id(pdf_id)
    
    return jsonify({
        'pdf': pdf_info,
        'tags': contents
    })


@app.route('/api/search/pdf/<path:query>')
@login_required
def api_search_pdf(query):
    """Search for a PDF by filename, description, supplier_code, or supplier_name."""
    db = get_db()

    # Find the PDF in database
    pdf_info = None
    pdf_id = None
    
    with db._get_connection() as conn:
        # Search by multiple fields
        cursor = conn.execute('''
            SELECT pdf_id, filename, relative_path, document_description,
                   supplier_code, supplier_name, page_count,
                   to_be_indexed, date_indexed
            FROM documents
            WHERE filename = ?
               OR filename LIKE ?
               OR supplier_code = ?
               OR supplier_code LIKE ?
               OR document_description LIKE ?
               OR supplier_name LIKE ?
            LIMIT 1
        ''', (query, f'%{query}%', query, f'%{query}%', f'%{query}%', f'%{query}%'))
        row = cursor.fetchone()

        if row:
            pdf_info = dict(row)
            pdf_id = pdf_info['pdf_id']

        if not pdf_info:
            return jsonify({
                'found': False,
                'query': query,
                'pdf': None,
                'cables': [],
                'equipment': []
            })
        
        pdf_info['category'] = pdf_info.get('supergrandparent', '')
        pdf_info['subcategory'] = pdf_info.get('superparent', '')
        
        cables = []
        equipment = []
        
        # Get tags only if PDF is indexed
        if pdf_id:
            cursor = conn.execute('''
                SELECT DISTINCT e.tag AS tag_name, 'equipment' AS tag_type,
                       e.description, e.room_tag, e.deck, o.page_number
                FROM equipment_occurrences o
                JOIN equipment e ON o.equipment_id = e.equipment_id
                WHERE o.pdf_id = ?
                ORDER BY e.tag, o.page_number
            ''', (pdf_id,))

            for tag_row in cursor.fetchall():
                tag_data = dict(tag_row)
                if tag_data.get('room_tag'):
                    room_key = str(tag_data['room_tag']).split('.')[0]
                    tag_data['room_description'] = db.get_compartment_description(room_key)
                equipment.append(tag_data)

            cursor = conn.execute('''
                SELECT DISTINCT c.tag AS tag_name, 'cable' AS tag_type,
                       c.type AS description, NULL AS room_tag, NULL AS deck, o.page_number
                FROM cable_occurrences o
                JOIN cables c ON o.cable_id = c.cable_id
                WHERE o.pdf_id = ?
                ORDER BY c.tag, o.page_number
            ''', (pdf_id,))

            for tag_row in cursor.fetchall():
                cables.append(dict(tag_row))
        
        # Group by tag name with page numbers
        def group_tags(tags):
            grouped = {}
            for t in tags:
                name = t['tag_name']
                if name not in grouped:
                    grouped[name] = {
                        'tag_name': t['tag_name'],
                        'tag_type': t['tag_type'],
                        'description': t['description'],
                        'room_tag': t.get('room_tag'),
                        'room_description': t.get('room_description'),
                        'deck': t.get('deck'),
                        'pages': []
                    }
                if t.get('page_number'):
                    grouped[name]['pages'].append(t['page_number'])
            
            # Sort pages and convert to list
            result = list(grouped.values())
            for item in result:
                item['pages'] = sorted(set(item['pages']))
            return result
        
        return jsonify({
            'found': True,
            'filename': pdf_info['filename'],
            'pdf': pdf_info,
            'cables': group_tags(cables),
            'equipment': group_tags(equipment)
        })


@app.route('/api/pdfs/search')
@login_required
def api_pdfs_search():
    """Search PDFs by filename, description, or drawing number."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'results': []})
    
    db = get_db()
    results = db.search_pdfs(query)
    
    return jsonify({'results': results})


# =============================================================================
# PDF SERVING
# =============================================================================

@app.route('/pdf/<path:filepath>')
@login_required
def serve_pdf(filepath):
    """Serve a PDF file from the PDF_ROOT directory."""
    if not PDF_ROOT:
        abort(404, description="PDF_ROOT not configured")
    
    # Security: prevent directory traversal
    # Normalize the path and ensure it stays within PDF_ROOT
    safe_path = os.path.normpath(filepath)
    if safe_path.startswith('..') or safe_path.startswith('/'):
        abort(403, description="Invalid path")
    
    full_path = os.path.join(PDF_ROOT, safe_path)
    full_path = os.path.normpath(full_path)
    
    # Verify the path is still within PDF_ROOT
    if not full_path.startswith(os.path.normpath(PDF_ROOT)):
        abort(403, description="Access denied")
    
    if not os.path.exists(full_path):
        abort(404, description="PDF not found")
    
    return send_file(full_path, mimetype='application/pdf')


# =============================================================================
# PWA SUPPORT
# =============================================================================

@app.route('/manifest.json')
def manifest():
    """Serve PWA manifest."""
    return jsonify({
        "name": "Ship Cable Database",
        "short_name": "CableDB",
        "description": "Search cables, equipment, and drawings",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0a0e17",
        "theme_color": "#00d4aa",
        "icons": [
            {
                "src": "/static/icons/icon-dark-bg.svg",
                "sizes": "any",
                "type": "image/svg+xml"
            }
        ]
    })


@app.route('/favicon.ico')
def favicon():
    return redirect('/static/icons/icon-dark-bg.svg', code=301)


@app.route('/sw.js')
def service_worker():
    """Serve service worker from root."""
    return send_file('static/js/sw.js', mimetype='application/javascript')


# =============================================================================
# CONFIGURATION API
# =============================================================================

@app.route('/api/config')
@login_required
def api_config():
    """Return client configuration."""
    db = get_db()
    stats = db.get_stats()
    return jsonify({
        'pdf_root_configured': bool(PDF_ROOT),
        'has_compartments': stats.get('compartments', 0) > 0,
        'has_metadata': True
    })


@app.route('/api/data-version')
@login_required
def api_data_version():
    """Return data version info for cache invalidation."""
    db = get_db()
    stats = db.get_stats()
    
    # Create a version hash based on data counts
    version_string = f"{stats['cables']}_{stats['equipment']}_{stats['documents']}_{stats['equipment_occurrences']}_{stats['cable_occurrences']}_{stats['documents_to_index']}"
    import hashlib
    version_hash = hashlib.md5(version_string.encode()).hexdigest()[:12]
    
    return jsonify({
        'version': version_hash,
        'stats': stats
    })


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Equipment Explorer Web Interface')
    parser.add_argument('--port', '-p', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', '-H', default='127.0.0.1', help='Host to bind to')
    parser.add_argument('--db', default='data/equipment_explorer.db', help='Path to database')
    parser.add_argument('--pdf-root', help='Root directory for PDF files')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Set configuration
    DB_PATH = args.db
    if args.pdf_root:
        PDF_ROOT = args.pdf_root

    # Reload data with new paths
    db = None
    auth_manager = None

    # Initialize auth (creates default admin if needed)
    get_auth()
    
    print(f"\n{'='*60}")
    print("Equipment Explorer - Web Interface")
    print(f"{'='*60}")
    print(f"Database: {DB_PATH}")
    print(f"PDF Root: {PDF_ROOT or '(not configured)'}")

    print(f"{'='*60}")
    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"Default admin login: admin / admin")
    print(f"{'='*60}\n")
    
    app.run(host=args.host, port=args.port, debug=args.debug)
