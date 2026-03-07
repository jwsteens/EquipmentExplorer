"""
Ship Cable and Equipment PDF Indexing System - Database Module

This module handles all database operations for the cable/equipment PDF indexing system.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from contextlib import contextmanager


class ShipCableDB:
    """Database manager for the Ship Cable PDF Indexing System."""
    
    def __init__(self, db_path: str = "ship_cables.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database with schema if it doesn't exist."""
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        
        with self._get_connection() as conn:
            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    conn.executescript(f.read())
            else:
                # Inline schema if file not found
                self._create_schema_inline(conn)
    
    def _create_schema_inline(self, conn):
        """Create schema directly if schema.sql not found."""
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS pdfs (
                pdf_id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                relative_path TEXT NOT NULL UNIQUE,
                document_description TEXT,
                drawing_number TEXT,
                file_size_bytes INTEGER,
                page_count INTEGER,
                is_searchable BOOLEAN DEFAULT 0,
                ocr_processed BOOLEAN DEFAULT 0,
                date_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS tags (
                tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name TEXT NOT NULL UNIQUE,
                tag_type TEXT NOT NULL CHECK(tag_type IN ('cable', 'equipment')),
                description TEXT,
                room_tag TEXT,
                deck TEXT,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS tag_occurrences (
                occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_id INTEGER NOT NULL,
                pdf_id INTEGER NOT NULL,
                page_number INTEGER,
                confidence REAL DEFAULT 1.0,
                date_found TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                FOREIGN KEY (pdf_id) REFERENCES pdfs(pdf_id) ON DELETE CASCADE,
                UNIQUE(tag_id, pdf_id, page_number)
            );
            
            CREATE TABLE IF NOT EXISTS cable_connections (
                connection_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cable_tag_id INTEGER NOT NULL,
                start_equipment_tag_id INTEGER NOT NULL,
                dest_equipment_tag_id INTEGER NOT NULL,
                date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cable_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                FOREIGN KEY (start_equipment_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                FOREIGN KEY (dest_equipment_tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
                UNIQUE(cable_tag_id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(tag_name);
            CREATE INDEX IF NOT EXISTS idx_tags_type ON tags(tag_type);
            CREATE INDEX IF NOT EXISTS idx_tags_description ON tags(description);
            CREATE INDEX IF NOT EXISTS idx_occurrences_tag ON tag_occurrences(tag_id);
            CREATE INDEX IF NOT EXISTS idx_occurrences_pdf ON tag_occurrences(pdf_id);
            CREATE INDEX IF NOT EXISTS idx_pdfs_path ON pdfs(relative_path);
            CREATE INDEX IF NOT EXISTS idx_pdfs_drawing ON pdfs(drawing_number);
            CREATE INDEX IF NOT EXISTS idx_cable_conn_cable ON cable_connections(cable_tag_id);
            CREATE INDEX IF NOT EXISTS idx_cable_conn_start ON cable_connections(start_equipment_tag_id);
            CREATE INDEX IF NOT EXISTS idx_cable_conn_dest ON cable_connections(dest_equipment_tag_id);
        ''')
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    # =========================================================================
    # TAG OPERATIONS
    # =========================================================================
    
    def add_tag(self, tag_name: str, tag_type: str, description: str = None,
                room_tag: str = None, deck: str = None) -> int:
        """Add a tag (cable or equipment) to the database."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT OR IGNORE INTO tags (tag_name, tag_type, description, room_tag, deck)
                VALUES (?, ?, ?, ?, ?)
            ''', (tag_name, tag_type, description, room_tag, deck))
            
            if cursor.rowcount == 0:
                # Tag already exists, get its ID
                cursor = conn.execute('SELECT tag_id FROM tags WHERE tag_name = ?', (tag_name,))
                return cursor.fetchone()[0]
            return cursor.lastrowid
    
    def add_tags_bulk(self, tags: List[Tuple[str, str, str, str, str]]) -> int:
        """
        Bulk add tags to the database.
        Each tuple: (tag_name, tag_type, description, room_tag, deck)
        Returns number of tags added.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                INSERT OR IGNORE INTO tags (tag_name, tag_type, description, room_tag, deck)
                VALUES (?, ?, ?, ?, ?)
            ''', tags)
            return cursor.rowcount
    
    def get_tag_id(self, tag_name: str) -> Optional[int]:
        """Get tag_id for a given tag name."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT tag_id FROM tags WHERE tag_name = ?', (tag_name,))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def add_tag(self, tag_name: str, tag_type: str, description: str = None,
                room_tag: str = None, deck: str = None) -> int:
        """
        Add a tag to the database or return existing tag_id.
        Returns the tag_id.
        """
        with self._get_connection() as conn:
            # Check if tag exists
            cursor = conn.execute('SELECT tag_id FROM tags WHERE tag_name = ?', (tag_name,))
            row = cursor.fetchone()
            if row:
                # Update existing tag with new info if provided
                updates = []
                params = []
                if description:
                    updates.append('description = ?')
                    params.append(description)
                if room_tag:
                    updates.append('room_tag = ?')
                    params.append(room_tag)
                if deck:
                    updates.append('deck = ?')
                    params.append(deck)
                
                if updates:
                    params.append(row[0])
                    conn.execute(f'UPDATE tags SET {", ".join(updates)} WHERE tag_id = ?', params)
                
                return row[0]
            
            # Insert new tag
            cursor = conn.execute('''
                INSERT INTO tags (tag_name, tag_type, description, room_tag, deck)
                VALUES (?, ?, ?, ?, ?)
            ''', (tag_name, tag_type, description, room_tag, deck))
            return cursor.lastrowid
    
    def delete_tag(self, tag_id: int):
        """Delete a tag and all its occurrences."""
        with self._get_connection() as conn:
            # Delete from cable_connections first (foreign key)
            conn.execute('DELETE FROM cable_connections WHERE cable_tag_id = ?', (tag_id,))
            conn.execute('DELETE FROM cable_connections WHERE start_equipment_tag_id = ?', (tag_id,))
            conn.execute('DELETE FROM cable_connections WHERE dest_equipment_tag_id = ?', (tag_id,))
            # Delete occurrences
            conn.execute('DELETE FROM tag_occurrences WHERE tag_id = ?', (tag_id,))
            # Delete tag
            conn.execute('DELETE FROM tags WHERE tag_id = ?', (tag_id,))
    
    def get_all_tags(self, tag_type: str = None) -> List[Dict]:
        """Get all tags, optionally filtered by type."""
        with self._get_connection() as conn:
            if tag_type:
                cursor = conn.execute(
                    'SELECT * FROM tags WHERE tag_type = ? ORDER BY tag_name',
                    (tag_type,)
                )
            else:
                cursor = conn.execute('SELECT * FROM tags ORDER BY tag_type, tag_name')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_tag_names_set(self, tag_type: str = None) -> set:
        """Get a set of all tag names for fast lookup during indexing."""
        with self._get_connection() as conn:
            if tag_type:
                cursor = conn.execute(
                    'SELECT tag_name FROM tags WHERE tag_type = ?', (tag_type,)
                )
            else:
                cursor = conn.execute('SELECT tag_name FROM tags')
            return {row[0] for row in cursor.fetchall()}
    
    # =========================================================================
    # CABLE CONNECTION OPERATIONS
    # =========================================================================
    
    def add_cable_connection(self, cable_tag, start_equipment_tag, 
                              dest_equipment_tag) -> bool:
        """
        Add a cable connection record.
        Links a cable to its start and destination equipment.
        Accepts either tag names (str) or tag IDs (int).
        Returns True if added, False if connection already exists.
        """
        # Handle both tag names and tag IDs
        if isinstance(cable_tag, str):
            cable_id = self.get_tag_id(cable_tag)
        else:
            cable_id = cable_tag
            
        if isinstance(start_equipment_tag, str):
            start_id = self.get_tag_id(start_equipment_tag)
        else:
            start_id = start_equipment_tag
            
        if isinstance(dest_equipment_tag, str):
            dest_id = self.get_tag_id(dest_equipment_tag)
        else:
            dest_id = dest_equipment_tag
        
        if not all([cable_id, start_id, dest_id]):
            return False
        
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT OR REPLACE INTO cable_connections 
                (cable_tag_id, start_equipment_tag_id, dest_equipment_tag_id)
                VALUES (?, ?, ?)
            ''', (cable_id, start_id, dest_id))
            return cursor.rowcount > 0
    
    def add_cable_connections_bulk(self, connections: List[Tuple[int, int, int]]) -> int:
        """
        Bulk add cable connections.
        Each tuple: (cable_tag_id, start_equipment_tag_id, dest_equipment_tag_id)
        Returns number of connections added.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                INSERT OR IGNORE INTO cable_connections 
                (cable_tag_id, start_equipment_tag_id, dest_equipment_tag_id)
                VALUES (?, ?, ?)
            ''', connections)
            return cursor.rowcount
    
    def get_cable_connection(self, cable_tag: str) -> Optional[Dict]:
        """
        Get the equipment connections for a cable.
        Returns dict with start and destination equipment info, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    c.tag_name AS cable_tag,
                    c.description AS cable_description,
                    s.tag_name AS start_equipment_tag,
                    s.description AS start_equipment_description,
                    s.room_tag AS start_room,
                    s.deck AS start_deck,
                    d.tag_name AS dest_equipment_tag,
                    d.description AS dest_equipment_description,
                    d.room_tag AS dest_room,
                    d.deck AS dest_deck
                FROM cable_connections cc
                JOIN tags c ON cc.cable_tag_id = c.tag_id
                JOIN tags s ON cc.start_equipment_tag_id = s.tag_id
                JOIN tags d ON cc.dest_equipment_tag_id = d.tag_id
                WHERE c.tag_name = ?
            ''', (cable_tag,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_cables_for_equipment(self, equipment_tag: str) -> List[Dict]:
        """
        Get all cables connected to a piece of equipment.
        Returns list of cable connections where this equipment is either start or destination.
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    c.tag_name AS cable_tag,
                    c.description AS cable_description,
                    s.tag_name AS start_equipment_tag,
                    s.description AS start_equipment_description,
                    s.room_tag AS start_room,
                    s.deck AS start_deck,
                    d.tag_name AS dest_equipment_tag,
                    d.description AS dest_equipment_description,
                    d.room_tag AS dest_room,
                    d.deck AS dest_deck,
                    CASE 
                        WHEN s.tag_name = ? THEN 'from'
                        ELSE 'to'
                    END AS connection_direction
                FROM cable_connections cc
                JOIN tags c ON cc.cable_tag_id = c.tag_id
                JOIN tags s ON cc.start_equipment_tag_id = s.tag_id
                JOIN tags d ON cc.dest_equipment_tag_id = d.tag_id
                WHERE s.tag_name = ? OR d.tag_name = ?
                ORDER BY c.tag_name
            ''', (equipment_tag, equipment_tag, equipment_tag))
            return [dict(row) for row in cursor.fetchall()]
    
    # =========================================================================
    # PDF OPERATIONS
    # =========================================================================
    
    def add_pdf(self, filename: str, relative_path: str, file_size_bytes: int = None,
                page_count: int = None, is_searchable: bool = False,
                document_description: str = None, drawing_number: str = None,
                supplier_code: str = None, supplier_name: str = None) -> int:
        """Add a PDF to the database."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT OR IGNORE INTO pdfs 
                (filename, relative_path, file_size_bytes, page_count, is_searchable,
                 document_description, drawing_number, supplier_code, supplier_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (filename, relative_path, file_size_bytes, page_count, is_searchable,
                  document_description, drawing_number, supplier_code, supplier_name))
            
            if cursor.rowcount == 0:
                cursor = conn.execute(
                    'SELECT pdf_id FROM pdfs WHERE relative_path = ?', (relative_path,)
                )
                return cursor.fetchone()[0]
            return cursor.lastrowid
    
    def get_pdf_id(self, relative_path: str) -> Optional[int]:
        """Get pdf_id for a given path."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT pdf_id FROM pdfs WHERE relative_path = ?', (relative_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def update_pdf_searchable(self, pdf_id: int, is_searchable: bool):
        """Update the searchable status of a PDF."""
        with self._get_connection() as conn:
            conn.execute(
                'UPDATE pdfs SET is_searchable = ? WHERE pdf_id = ?',
                (is_searchable, pdf_id)
            )
    
    def update_pdf_ocr_processed(self, pdf_id: int, processed: bool = True):
        """Mark a PDF as OCR processed."""
        with self._get_connection() as conn:
            conn.execute(
                'UPDATE pdfs SET ocr_processed = ? WHERE pdf_id = ?',
                (processed, pdf_id)
            )
    
    def get_unprocessed_pdfs(self, searchable_only: bool = True) -> List[Dict]:
        """Get PDFs that haven't been indexed yet."""
        with self._get_connection() as conn:
            query = '''
                SELECT * FROM pdfs 
                WHERE pdf_id NOT IN (SELECT DISTINCT pdf_id FROM tag_occurrences)
            '''
            if searchable_only:
                query += ' AND is_searchable = 1'
            cursor = conn.execute(query)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_non_searchable_pdfs(self) -> List[Dict]:
        """Get PDFs that are not searchable (need OCR)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM pdfs WHERE is_searchable = 0 AND ocr_processed = 0'
            )
            return [dict(row) for row in cursor.fetchall()]
    
    # =========================================================================
    # TAG OCCURRENCE OPERATIONS
    # =========================================================================
    
    def add_occurrence(self, tag_id: int, pdf_id: int, page_number: int = None,
                       confidence: float = 1.0):
        """Record that a tag was found in a PDF."""
        with self._get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO tag_occurrences 
                (tag_id, pdf_id, page_number, confidence)
                VALUES (?, ?, ?, ?)
            ''', (tag_id, pdf_id, page_number, confidence))
    
    def add_occurrences_bulk(self, occurrences: List[Tuple[int, int, int, float]]):
        """
        Bulk add tag occurrences.
        Each tuple: (tag_id, pdf_id, page_number, confidence)
        """
        with self._get_connection() as conn:
            conn.executemany('''
                INSERT OR IGNORE INTO tag_occurrences 
                (tag_id, pdf_id, page_number, confidence)
                VALUES (?, ?, ?, ?)
            ''', occurrences)
    
    def delete_occurrences_for_pdf(self, pdf_id: int) -> int:
        """
        Delete all tag occurrences for a specific PDF.
        Used when re-indexing a PDF.
        Returns the number of occurrences deleted.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                'DELETE FROM tag_occurrences WHERE pdf_id = ?', (pdf_id,)
            )
            return cursor.rowcount
    
    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================
    
    def search_tag(self, tag_name: str) -> List[Dict]:
        """
        Search for a tag and return all PDFs where it appears.
        Returns list of dicts with pdf info and page numbers.
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    t.tag_name, t.tag_type, t.description,
                    p.filename, p.relative_path, p.document_description, p.drawing_number,
                    p.supplier_code, p.supplier_name,
                    o.page_number, o.confidence
                FROM tags t
                JOIN tag_occurrences o ON t.tag_id = o.tag_id
                JOIN pdfs p ON o.pdf_id = p.pdf_id
                WHERE t.tag_name = ?
                ORDER BY p.filename, o.page_number
            ''', (tag_name,))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_tag_partial(self, partial_tag: str, tag_type: str = None) -> List[Dict]:
        """
        Search for tags containing the partial string in either tag_name or description.
        Useful for autocomplete or fuzzy search.
        Returns results ordered by relevance (tag_name matches first, then description matches).
        """
        with self._get_connection() as conn:
            if tag_type:
                cursor = conn.execute('''
                    SELECT DISTINCT 
                        t.tag_name, 
                        t.tag_type, 
                        t.description,
                        COUNT(DISTINCT o.pdf_id) as pdf_count,
                        CASE 
                            WHEN t.tag_name LIKE ? THEN 1
                            WHEN t.description LIKE ? THEN 2
                            ELSE 3
                        END as match_priority
                    FROM tags t
                    LEFT JOIN tag_occurrences o ON t.tag_id = o.tag_id
                    WHERE (t.tag_name LIKE ? OR t.description LIKE ?) 
                      AND t.tag_type = ?
                    GROUP BY t.tag_id
                    ORDER BY match_priority, t.tag_name
                    LIMIT 50
                ''', (f'%{partial_tag}%', f'%{partial_tag}%', f'%{partial_tag}%', f'%{partial_tag}%', tag_type))
            else:
                cursor = conn.execute('''
                    SELECT DISTINCT 
                        t.tag_name, 
                        t.tag_type, 
                        t.description,
                        COUNT(DISTINCT o.pdf_id) as pdf_count,
                        CASE 
                            WHEN t.tag_name LIKE ? THEN 1
                            WHEN t.description LIKE ? THEN 2
                            ELSE 3
                        END as match_priority
                    FROM tags t
                    LEFT JOIN tag_occurrences o ON t.tag_id = o.tag_id
                    WHERE t.tag_name LIKE ? OR t.description LIKE ?
                    GROUP BY t.tag_id
                    ORDER BY match_priority, t.tag_name
                    LIMIT 50
                ''', (f'%{partial_tag}%', f'%{partial_tag}%', f'%{partial_tag}%', f'%{partial_tag}%'))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_pdf_contents(self, relative_path: str) -> List[Dict]:
        """Get all tags found in a specific PDF."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT t.tag_name, t.tag_type, t.description, o.page_number
                FROM pdfs p
                JOIN tag_occurrences o ON p.pdf_id = o.pdf_id
                JOIN tags t ON o.tag_id = t.tag_id
                WHERE p.relative_path = ?
                ORDER BY t.tag_type, t.tag_name
            ''', (relative_path,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_pdf_contents_by_id(self, pdf_id: int) -> List[Dict]:
        """Get all tags found in a specific PDF by its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT t.tag_name, t.tag_type, t.description, o.page_number
                FROM pdfs p
                JOIN tag_occurrences o ON p.pdf_id = o.pdf_id
                JOIN tags t ON o.tag_id = t.tag_id
                WHERE p.pdf_id = ?
                ORDER BY t.tag_type, t.tag_name
            ''', (pdf_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_pdfs(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Search for PDFs by filename, document description, drawing number, supplier name, or supplier code.
        Returns list of matching PDFs with their metadata.
        """
        with self._get_connection() as conn:
            search_pattern = f'%{query}%'
            cursor = conn.execute('''
                SELECT 
                    pdf_id,
                    filename,
                    relative_path,
                    document_description,
                    drawing_number,
                    supplier_code,
                    supplier_name,
                    page_count,
                    is_searchable,
                    (SELECT COUNT(*) FROM tag_occurrences WHERE pdf_id = pdfs.pdf_id) as tag_count
                FROM pdfs
                WHERE filename LIKE ?
                   OR document_description LIKE ?
                   OR drawing_number LIKE ?
                   OR supplier_name LIKE ?
                   OR supplier_code LIKE ?
                ORDER BY 
                    CASE 
                        WHEN filename LIKE ? THEN 1
                        WHEN drawing_number LIKE ? THEN 2
                        WHEN supplier_code LIKE ? THEN 3
                        WHEN supplier_name LIKE ? THEN 4
                        ELSE 5
                    END,
                    filename
                LIMIT ?
            ''', (search_pattern, search_pattern, search_pattern, search_pattern, search_pattern,
                  search_pattern, search_pattern, search_pattern, search_pattern, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_pdf_by_id(self, pdf_id: int) -> Optional[Dict]:
        """Get PDF metadata by its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    pdf_id,
                    filename,
                    relative_path,
                    document_description,
                    drawing_number,
                    page_count,
                    is_searchable
                FROM pdfs
                WHERE pdf_id = ?
            ''', (pdf_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self._get_connection() as conn:
            stats = {}
            
            cursor = conn.execute('SELECT COUNT(*) FROM tags WHERE tag_type = "cable"')
            stats['cables'] = cursor.fetchone()[0]
            stats['total_cables'] = stats['cables']  # alias for compatibility
            
            cursor = conn.execute('SELECT COUNT(*) FROM tags WHERE tag_type = "equipment"')
            stats['equipment'] = cursor.fetchone()[0]
            stats['total_equipment'] = stats['equipment']  # alias for compatibility
            
            cursor = conn.execute('SELECT COUNT(*) FROM pdfs')
            stats['total_pdfs'] = cursor.fetchone()[0]
            
            cursor = conn.execute('SELECT COUNT(*) FROM pdfs WHERE is_searchable = 1')
            stats['indexed_pdfs'] = cursor.fetchone()[0]
            stats['searchable_pdfs'] = stats['indexed_pdfs']  # alias for compatibility
            
            cursor = conn.execute('SELECT COUNT(*) FROM tag_occurrences')
            stats['occurrences'] = cursor.fetchone()[0]
            stats['total_occurrences'] = stats['occurrences']  # alias for compatibility
            
            cursor = conn.execute('''
                SELECT COUNT(DISTINCT tag_id) FROM tag_occurrences
            ''')
            stats['tags_with_occurrences'] = cursor.fetchone()[0]
            
            # Add cable connection stats
            cursor = conn.execute('SELECT COUNT(*) FROM cable_connections')
            stats['cable_connections'] = cursor.fetchone()[0]
            
            return stats


# Convenience functions for command-line usage
def init_database(db_path: str = "ship_cables.db") -> ShipCableDB:
    """Initialize and return a database instance."""
    return ShipCableDB(db_path)


if __name__ == "__main__":
    # Quick test
    db = ShipCableDB("test_ship_cables.db")
    print("Database initialized successfully.")
    print("Stats:", db.get_stats())
