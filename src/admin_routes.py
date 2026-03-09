"""
Admin Routes for Equipment Explorer

Handles admin interface for user management, database management, and logs.
"""

import os
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, current_app
from werkzeug.utils import secure_filename
from auth import admin_required, editor_required, login_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def get_auth():
    """Get auth manager from app context."""
    from flask import current_app
    return current_app.config.get('AUTH_MANAGER')


def get_db():
    """Get database from app context."""
    from flask import current_app
    return current_app.config.get('DB')


# =============================================================================
# ADMIN DASHBOARD
# =============================================================================

@admin_bp.route('/')
@admin_required
def dashboard():
    """Admin dashboard overview."""
    auth = get_auth()
    db = get_db()
    
    # Get counts
    stats = db.get_stats()
    user_count = len(auth.get_users())
    session_count = len(auth.get_active_sessions())
    recent_errors = auth.get_error_log_count()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         user_count=user_count,
                         session_count=session_count,
                         error_count=recent_errors)


# =============================================================================
# USER MANAGEMENT
# =============================================================================

@admin_bp.route('/users')
@admin_required
def users():
    """List all users."""
    auth = get_auth()
    users = auth.get_users()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_required
def create_user():
    """Create a new user."""
    auth = get_auth()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip() or None
        role = request.form.get('role', 'viewer')
        
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('admin/user_form.html', user=None, mode='create')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('admin/user_form.html', user=None, mode='create')
        
        try:
            user_id = auth.create_user(username, password, email, role, g.user['user_id'])
            auth.log_access(g.user['user_id'], g.user['username'], 'create_user',
                          f'Created user: {username} (role: {role})',
                          request.remote_addr, request.user_agent.string)
            flash(f'User "{username}" created successfully.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            if 'UNIQUE constraint' in str(e):
                flash('Username already exists.', 'error')
            else:
                flash(f'Error creating user: {e}', 'error')
                auth.log_error('user_creation_error', str(e), traceback.format_exc(),
                             request.path, g.user['user_id'], request.remote_addr)
    
    return render_template('admin/user_form.html', user=None, mode='create')


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit an existing user."""
    auth = get_auth()
    user = auth.get_user(user_id)
    
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.users'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip() or None
        role = request.form.get('role', 'viewer')
        is_active = request.form.get('is_active') == '1'
        new_password = request.form.get('new_password', '')
        
        if not username:
            flash('Username is required.', 'error')
            return render_template('admin/user_form.html', user=user, mode='edit')
        
        # Prevent disabling or demoting yourself
        if user_id == g.user['user_id']:
            if not is_active:
                flash('You cannot disable your own account.', 'error')
                return render_template('admin/user_form.html', user=user, mode='edit')
            if role != 'admin':
                flash('You cannot change your own role.', 'error')
                return render_template('admin/user_form.html', user=user, mode='edit')
        
        try:
            auth.update_user(user_id, username=username, email=email, role=role, is_active=is_active)
            
            if new_password:
                if len(new_password) < 6:
                    flash('Password must be at least 6 characters.', 'error')
                    return render_template('admin/user_form.html', user=user, mode='edit')
                auth.change_password(user_id, new_password)
            
            auth.log_access(g.user['user_id'], g.user['username'], 'edit_user',
                          f'Edited user: {username}',
                          request.remote_addr, request.user_agent.string)
            flash(f'User "{username}" updated successfully.', 'success')
            return redirect(url_for('admin.users'))
        except Exception as e:
            flash(f'Error updating user: {e}', 'error')
            auth.log_error('user_update_error', str(e), traceback.format_exc(),
                         request.path, g.user['user_id'], request.remote_addr)
    
    return render_template('admin/user_form.html', user=user, mode='edit')


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete a user."""
    auth = get_auth()
    
    # Prevent self-deletion
    if user_id == g.user['user_id']:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin.users'))
    
    user = auth.get_user(user_id)
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin.users'))
    
    try:
        auth.delete_user(user_id)
        auth.log_access(g.user['user_id'], g.user['username'], 'delete_user',
                      f'Deleted user: {user["username"]}',
                      request.remote_addr, request.user_agent.string)
        flash(f'User "{user["username"]}" deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting user: {e}', 'error')
        auth.log_error('user_deletion_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
    
    return redirect(url_for('admin.users'))


# =============================================================================
# DATABASE MANAGEMENT
# =============================================================================

@admin_bp.route('/database')
@admin_required
def database():
    """Database management page."""
    auth = get_auth()
    db = get_db()
    
    stats = db.get_stats()
    pdf_root = auth.get_setting('pdf_root', os.environ.get('PDF_ROOT', ''))
    metadata_path = auth.get_setting('metadata_path', os.environ.get('METADATA_PATH', 'drawing_metadata.pkl'))
    
    return render_template('admin/database.html',
                         stats=stats,
                         pdf_root=pdf_root,
                         metadata_path=metadata_path)


@admin_bp.route('/database/settings', methods=['POST'])
@admin_required
def update_db_settings():
    """Update database settings."""
    auth = get_auth()
    
    pdf_root = request.form.get('pdf_root', '').strip()
    metadata_path = request.form.get('metadata_path', '').strip()
    
    try:
        if pdf_root:
            auth.set_setting('pdf_root', pdf_root, g.user['user_id'])
        if metadata_path:
            auth.set_setting('metadata_path', metadata_path, g.user['user_id'])
        
        auth.log_access(g.user['user_id'], g.user['username'], 'update_settings',
                      f'PDF root: {pdf_root}, Metadata: {metadata_path}',
                      request.remote_addr, request.user_agent.string)
        flash('Settings updated. Restart the application for changes to take effect.', 'success')
    except Exception as e:
        flash(f'Error updating settings: {e}', 'error')
        auth.log_error('settings_update_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
    
    return redirect(url_for('admin.database'))


@admin_bp.route('/database/cables')
@admin_required
def manage_cables():
    """Manage cables page."""
    return render_template('admin/cables.html')


@admin_bp.route('/database/equipment')
@admin_required  
def manage_equipment():
    """Manage equipment page."""
    return render_template('admin/equipment.html')


@admin_bp.route('/api/cables', methods=['POST'])
@admin_required
def api_add_cable():
    """API endpoint to add a cable."""
    auth = get_auth()
    db = get_db()
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    cable_tag = data.get('cable_tag', '').strip()
    cable_type = data.get('cable_type', '').strip()
    start_tag = data.get('start_tag', '').strip()
    start_desc = data.get('start_description', '').strip()
    start_room = data.get('start_room', '').strip()
    start_deck = data.get('start_deck', '').strip()
    dest_tag = data.get('dest_tag', '').strip()
    dest_desc = data.get('dest_description', '').strip()
    dest_room = data.get('dest_room', '').strip()
    dest_deck = data.get('dest_deck', '').strip()
    
    if not cable_tag or not start_tag or not dest_tag:
        return jsonify({'error': 'Cable tag, start tag, and destination tag are required'}), 400
    
    try:
        # Add or get cable tag
        cable_id = db.add_tag(cable_tag, 'cable', cable_type)
        
        # Add or get start equipment tag
        start_id = db.add_tag(start_tag, 'equipment', start_desc, start_room, start_deck)
        
        # Add or get destination equipment tag
        dest_id = db.add_tag(dest_tag, 'equipment', dest_desc, dest_room, dest_deck)
        
        # Add cable connection
        db.add_cable_connection(cable_id, start_id, dest_id)
        
        auth.log_access(g.user['user_id'], g.user['username'], 'add_cable',
                      f'Added cable: {cable_tag}',
                      request.remote_addr, request.user_agent.string)
        
        return jsonify({'success': True, 'cable_id': cable_id})
    except Exception as e:
        auth.log_error('add_cable_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/equipment', methods=['POST'])
@admin_required
def api_add_equipment():
    """API endpoint to add equipment."""
    auth = get_auth()
    db = get_db()
    
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    tag = data.get('tag', '').strip()
    description = data.get('description', '').strip()
    room = data.get('room', '').strip()
    deck = data.get('deck', '').strip()
    
    if not tag:
        return jsonify({'error': 'Equipment tag is required'}), 400
    
    try:
        tag_id = db.add_tag(tag, 'equipment', description, room, deck)
        
        auth.log_access(g.user['user_id'], g.user['username'], 'add_equipment',
                      f'Added equipment: {tag}',
                      request.remote_addr, request.user_agent.string)
        
        return jsonify({'success': True, 'tag_id': tag_id})
    except Exception as e:
        auth.log_error('add_equipment_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/cables/<int:tag_id>', methods=['DELETE'])
@admin_required
def api_delete_cable(tag_id):
    """API endpoint to delete a cable."""
    auth = get_auth()
    db = get_db()
    
    try:
        # Get cable info before deletion for logging
        with db._get_connection() as conn:
            row = conn.execute('SELECT tag FROM equipment WHERE equipment_id = ?', (tag_id,)).fetchone()
            if not row:
                row = conn.execute('SELECT tag FROM cables WHERE cable_id = ?', (tag_id,)).fetchone()
            tag_name = row[0] if row else 'Unknown'

        db.delete_tag(tag_id)
        
        auth.log_access(g.user['user_id'], g.user['username'], 'delete_cable',
                      f'Deleted cable: {tag_name}',
                      request.remote_addr, request.user_agent.string)
        
        return jsonify({'success': True})
    except Exception as e:
        auth.log_error('delete_cable_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/api/equipment/<int:tag_id>', methods=['DELETE'])
@admin_required
def api_delete_equipment(tag_id):
    """API endpoint to delete equipment."""
    auth = get_auth()
    db = get_db()
    
    try:
        # Get equipment info before deletion for logging
        with db._get_connection() as conn:
            row = conn.execute('SELECT tag FROM equipment WHERE equipment_id = ?', (tag_id,)).fetchone()
            if not row:
                row = conn.execute('SELECT tag FROM cables WHERE cable_id = ?', (tag_id,)).fetchone()
            tag_name = row[0] if row else 'Unknown'

        db.delete_tag(tag_id)
        
        auth.log_access(g.user['user_id'], g.user['username'], 'delete_equipment',
                      f'Deleted equipment: {tag_name}',
                      request.remote_addr, request.user_agent.string)
        
        return jsonify({'success': True})
    except Exception as e:
        auth.log_error('delete_equipment_error', str(e), traceback.format_exc(),
                     request.path, g.user['user_id'], request.remote_addr)
        return jsonify({'error': str(e)}), 500


# =============================================================================
# LOGS
# =============================================================================

@admin_bp.route('/logs/access')
@admin_required
def access_logs():
    """View access logs."""
    auth = get_auth()

    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    logs = auth.get_access_logs(limit=per_page, offset=offset)
    total = auth.get_access_log_count()
    total_pages = (total + per_page - 1) // per_page

    active_sessions = auth.get_active_sessions()

    return render_template('admin/access_logs.html',
                         logs=logs,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         active_sessions=active_sessions)


@admin_bp.route('/api/sessions/<session_id>/terminate', methods=['POST'])
@admin_required
def terminate_session(session_id):
    """Terminate a specific session."""
    auth = get_auth()
    auth.destroy_session(session_id)
    auth.log_access(g.user['user_id'], g.user['username'], 'session_terminated',
                    f'Admin terminated session {session_id[:8]}…',
                    request.remote_addr, request.user_agent.string)
    return redirect(request.referrer or url_for('admin.access_logs'))


@admin_bp.route('/logs/errors')
@admin_required
def error_logs():
    """View error logs."""
    auth = get_auth()
    
    page = request.args.get('page', 1, type=int)
    error_type = request.args.get('type', None)
    per_page = 50
    offset = (page - 1) * per_page
    
    logs = auth.get_error_logs(limit=per_page, offset=offset, error_type=error_type)
    total = auth.get_error_log_count(error_type=error_type)
    total_pages = (total + per_page - 1) // per_page
    
    # Get unique error types for filter
    with auth.db._get_connection() as conn:
        cursor = conn.execute('SELECT DISTINCT error_type FROM error_logs ORDER BY error_type')
        error_types = [row[0] for row in cursor.fetchall()]
    
    return render_template('admin/error_logs.html',
                         logs=logs,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         error_types=error_types,
                         current_type=error_type)


@admin_bp.route('/api/logs/access')
@admin_required
def api_access_logs():
    """API endpoint for access logs (for live updates)."""
    auth = get_auth()
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    logs = auth.get_access_logs(limit=limit, offset=offset)
    total = auth.get_access_log_count()
    
    return jsonify({'logs': logs, 'total': total})


@admin_bp.route('/api/logs/errors')
@admin_required
def api_error_logs():
    """API endpoint for error logs."""
    auth = get_auth()
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    error_type = request.args.get('type', None)
    
    logs = auth.get_error_logs(limit=limit, offset=offset, error_type=error_type)
    total = auth.get_error_log_count(error_type=error_type)
    
    return jsonify({'logs': logs, 'total': total})


@admin_bp.route('/api/logs/errors/<int:log_id>')
@admin_required
def api_error_detail(log_id):
    """API endpoint for error log detail (including stack trace)."""
    auth = get_auth()
    
    with auth.db._get_connection() as conn:
        cursor = conn.execute('''
            SELECT log_id, error_type, error_message, stack_trace, endpoint, user_id, ip_address, timestamp
            FROM error_logs WHERE log_id = ?
        ''', (log_id,))
        row = cursor.fetchone()
        
        if row:
            return jsonify(dict(zip(['log_id', 'error_type', 'error_message', 'stack_trace',
                                    'endpoint', 'user_id', 'ip_address', 'timestamp'], row)))
    
    return jsonify({'error': 'Log not found'}), 404
