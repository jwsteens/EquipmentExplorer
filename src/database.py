"""
Ship Cable and Equipment PDF Indexing System - Database Module

This module handles all database operations for the cable/equipment PDF indexing system.
"""

import sqlite3
import os
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
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())

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
    # EQUIPMENT OPERATIONS
    # =========================================================================

    def add_equipment_bulk(self, rows: List[Tuple[str, str, str, str]]) -> int:
        """
        Bulk add equipment to the database.
        Each tuple: (tag, description, room_tag, deck)
        Returns number of rows inserted.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                INSERT OR IGNORE INTO equipment (tag, description, room_tag, deck)
                VALUES (?, ?, ?, ?)
            ''', rows)
            return cursor.rowcount

    def get_all_equipment(self) -> List[Dict]:
        """Get all equipment rows."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM equipment ORDER BY tag')
            return [dict(row) for row in cursor.fetchall()]

    def get_equipment_id(self, tag: str) -> Optional[int]:
        """Get equipment_id for a given tag."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT equipment_id FROM equipment WHERE tag = ?', (tag,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_equipment_tags_set(self) -> set:
        """Get a set of all equipment tags for fast lookup."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT tag FROM equipment')
            return {row[0] for row in cursor.fetchall()}

    # =========================================================================
    # CABLE OPERATIONS
    # =========================================================================

    def add_cables_bulk(self, rows: List[Tuple[str, str, Optional[int], Optional[int]]]) -> int:
        """
        Bulk add cables to the database.
        Each tuple: (tag, type, start_equipment_id, dest_equipment_id)
        Returns number of rows inserted.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                INSERT OR IGNORE INTO cables (tag, type, start_equipment_id, dest_equipment_id)
                VALUES (?, ?, ?, ?)
            ''', rows)
            return cursor.rowcount

    def get_all_cables(self) -> List[Dict]:
        """Get all cable rows."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT * FROM cables ORDER BY tag')
            return [dict(row) for row in cursor.fetchall()]

    def get_cable_id(self, tag: str) -> Optional[int]:
        """Get cable_id for a given tag."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT cable_id FROM cables WHERE tag = ?', (tag,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_cable_tags_set(self) -> set:
        """Get a set of all cable tags for fast lookup."""
        with self._get_connection() as conn:
            cursor = conn.execute('SELECT tag FROM cables')
            return {row[0] for row in cursor.fetchall()}

    def update_cable_connections_bulk(self, connections: List[Tuple[int, int, int]]) -> int:
        """
        Bulk update cable start/dest equipment links.
        Each tuple: (start_equipment_id, dest_equipment_id, cable_id)
        Returns number of rows updated.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                UPDATE cables SET start_equipment_id = ?, dest_equipment_id = ?
                WHERE cable_id = ?
            ''', connections)
            return cursor.rowcount

    # =========================================================================
    # CABLE CONNECTION QUERIES (via view)
    # =========================================================================

    def get_cable_connection(self, cable_tag: str) -> Optional[Dict]:
        """
        Get the equipment connections for a cable.
        Returns dict from cable_connections_view, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM cable_connections_view WHERE cable_tag = ?', (cable_tag,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_cables_for_equipment(self, equipment_tag: str) -> List[Dict]:
        """
        Get all cables connected to a piece of equipment.
        Returns rows from cable_connections_view where this equipment is start or destination.
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM cable_connections_view
                WHERE start_equipment_tag = ? OR dest_equipment_tag = ?
                ORDER BY cable_tag
            ''', (equipment_tag, equipment_tag))
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # COMPARTMENT OPERATIONS
    # =========================================================================

    def add_compartments_bulk(self, rows: List[Tuple[str, str]]) -> int:
        """
        Bulk add compartments to the database.
        Each tuple: (tag, description)
        Returns number of rows inserted.
        """
        with self._get_connection() as conn:
            cursor = conn.executemany('''
                INSERT OR IGNORE INTO compartments (tag, description)
                VALUES (?, ?)
            ''', rows)
            return cursor.rowcount

    def get_compartment_description(self, tag: str) -> Optional[str]:
        """Get description for a compartment tag."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT description FROM compartments WHERE tag = ?', (tag,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    # =========================================================================
    # DOCUMENT OPERATIONS
    # =========================================================================

    def add_document(self, filename: str, relative_path: str,
                     document_description: str = None, supplier_code: str = None,
                     supplier_name: str = None, supergrandparent: str = None,
                     superparent: str = None, revision: str = None,
                     status: str = None, file_size_bytes: int = None,
                     page_count: int = None, content_hash: str = None,
                     to_be_indexed: bool = False,
                     date_modified: str = None) -> int:
        """Add a document to the database. Returns pdf_id."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                INSERT OR IGNORE INTO documents
                (filename, relative_path, document_description, supplier_code,
                 supplier_name, supergrandparent, superparent, revision, status,
                 file_size_bytes, page_count, content_hash, to_be_indexed, date_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (filename, relative_path, document_description, supplier_code,
                  supplier_name, supergrandparent, superparent, revision, status,
                  file_size_bytes, page_count, content_hash, to_be_indexed, date_modified))

            if cursor.rowcount == 0:
                cursor = conn.execute(
                    'SELECT pdf_id FROM documents WHERE relative_path = ?', (relative_path,)
                )
                return cursor.fetchone()[0]
            return cursor.lastrowid

    def get_document_id(self, relative_path: str) -> Optional[int]:
        """Get pdf_id for a given relative path."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT pdf_id FROM documents WHERE relative_path = ?', (relative_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_unprocessed_pdfs(self) -> List[Dict]:
        """Get documents that are marked to_be_indexed but not yet indexed."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT * FROM documents
                WHERE date_indexed IS NULL AND to_be_indexed = 1
            ''')
            return [dict(row) for row in cursor.fetchall()]

    def get_pdf_by_id(self, pdf_id: int) -> Optional[Dict]:
        """Get document metadata by its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM documents WHERE pdf_id = ?', (pdf_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def mark_document_indexed(self, pdf_id: int):
        """Mark a document as indexed by setting date_indexed to now."""
        with self._get_connection() as conn:
            conn.execute('''
                UPDATE documents SET date_indexed = CURRENT_TIMESTAMP
                WHERE pdf_id = ?
            ''', (pdf_id,))

    def search_pdfs(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Search documents by filename, document_description, supplier_code, or supplier_name.
        Returns list of matching documents ordered by relevance.
        """
        with self._get_connection() as conn:
            pattern = f'%{query}%'
            cursor = conn.execute('''
                SELECT
                    pdf_id,
                    filename,
                    relative_path,
                    document_description,
                    supplier_code,
                    supplier_name,
                    page_count,
                    to_be_indexed,
                    date_indexed,
                    (SELECT COUNT(*) FROM equipment_occurrences WHERE pdf_id = documents.pdf_id)
                    + (SELECT COUNT(*) FROM cable_occurrences WHERE pdf_id = documents.pdf_id)
                        AS tag_count
                FROM documents
                WHERE filename LIKE ?
                   OR document_description LIKE ?
                   OR supplier_code LIKE ?
                   OR supplier_name LIKE ?
                ORDER BY
                    CASE
                        WHEN filename LIKE ? THEN 1
                        WHEN supplier_code LIKE ? THEN 2
                        WHEN supplier_name LIKE ? THEN 3
                        ELSE 4
                    END,
                    filename
                LIMIT ?
            ''', (pattern, pattern, pattern, pattern,
                  pattern, pattern, pattern, limit))
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # OCCURRENCE OPERATIONS
    # =========================================================================

    def add_equipment_occurrences_bulk(self, rows: List[Tuple[int, int, int]]):
        """
        Bulk add equipment occurrences.
        Each tuple: (equipment_id, pdf_id, page_number)
        """
        with self._get_connection() as conn:
            conn.executemany('''
                INSERT OR IGNORE INTO equipment_occurrences (equipment_id, pdf_id, page_number)
                VALUES (?, ?, ?)
            ''', rows)

    def add_cable_occurrences_bulk(self, rows: List[Tuple[int, int, int, float]]):
        """
        Bulk add cable occurrences.
        Each tuple: (cable_id, pdf_id, page_number, confidence)
        """
        with self._get_connection() as conn:
            conn.executemany('''
                INSERT OR IGNORE INTO cable_occurrences (cable_id, pdf_id, page_number, confidence)
                VALUES (?, ?, ?, ?)
            ''', rows)

    def delete_occurrences_for_pdf(self, pdf_id: int) -> int:
        """
        Delete all occurrences for a specific PDF from both occurrence tables.
        Used when re-indexing a PDF.
        Returns total number of occurrences deleted.
        """
        with self._get_connection() as conn:
            c1 = conn.execute(
                'DELETE FROM equipment_occurrences WHERE pdf_id = ?', (pdf_id,)
            )
            c2 = conn.execute(
                'DELETE FROM cable_occurrences WHERE pdf_id = ?', (pdf_id,)
            )
            return c1.rowcount + c2.rowcount

    # =========================================================================
    # DOCUMENT CONTENTS (via view)
    # =========================================================================

    def get_pdf_contents(self, relative_path: str) -> List[Dict]:
        """Get all tags found in a specific PDF by its path."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                'SELECT * FROM document_contents_view WHERE pdf_path = ?',
                (relative_path,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pdf_contents_by_id(self, pdf_id: int) -> List[Dict]:
        """Get all tags found in a specific PDF by its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT dcv.*
                FROM document_contents_view dcv
                JOIN documents d ON dcv.pdf_path = d.relative_path
                WHERE d.pdf_id = ?
                ORDER BY dcv.tag_type, dcv.tag
            ''', (pdf_id,))
            return [dict(row) for row in cursor.fetchall()]

    # =========================================================================
    # SEARCH OPERATIONS
    # =========================================================================

    def search_tag(self, tag_name: str) -> List[Dict]:
        """
        Search for a tag (equipment or cable) and return all documents where it appears.
        Returns list of dicts with document info and page numbers.
        """
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT
                    'equipment' AS tag_type,
                    e.tag AS tag_name,
                    e.description,
                    d.filename,
                    d.relative_path,
                    d.document_description,
                    d.supplier_code,
                    d.supplier_name,
                    o.page_number,
                    NULL AS confidence
                FROM equipment e
                JOIN equipment_occurrences o ON e.equipment_id = o.equipment_id
                JOIN documents d ON o.pdf_id = d.pdf_id
                WHERE e.tag = ?

                UNION ALL

                SELECT
                    'cable' AS tag_type,
                    c.tag AS tag_name,
                    NULL AS description,
                    d.filename,
                    d.relative_path,
                    d.document_description,
                    d.supplier_code,
                    d.supplier_name,
                    o.page_number,
                    o.confidence
                FROM cables c
                JOIN cable_occurrences o ON c.cable_id = o.cable_id
                JOIN documents d ON o.pdf_id = d.pdf_id
                WHERE c.tag = ?

                ORDER BY filename, page_number
            ''', (tag_name, tag_name))
            return [dict(row) for row in cursor.fetchall()]

    def search_tag_partial(self, partial_tag: str, tag_type: str = None) -> List[Dict]:
        """
        Search for tags containing the partial string in tag or description.
        Returns results ordered by relevance (tag matches first, then description).
        tag_type can be 'equipment' or 'cable' to filter results.
        """
        pattern = f'%{partial_tag}%'

        with self._get_connection() as conn:
            results = []

            if tag_type != 'cable':
                cursor = conn.execute('''
                    SELECT
                        e.tag AS tag_name,
                        'equipment' AS tag_type,
                        e.description,
                        COUNT(DISTINCT o.pdf_id) AS pdf_count,
                        CASE
                            WHEN e.tag LIKE ? THEN 1
                            WHEN e.description LIKE ? THEN 2
                            ELSE 3
                        END AS match_priority
                    FROM equipment e
                    LEFT JOIN equipment_occurrences o ON e.equipment_id = o.equipment_id
                    WHERE e.tag LIKE ? OR e.description LIKE ?
                    GROUP BY e.equipment_id
                    ORDER BY match_priority, e.tag
                    LIMIT 50
                ''', (pattern, pattern, pattern, pattern))
                results.extend([dict(row) for row in cursor.fetchall()])

            if tag_type != 'equipment':
                cursor = conn.execute('''
                    SELECT
                        c.tag AS tag_name,
                        'cable' AS tag_type,
                        c.type AS description,
                        COUNT(DISTINCT o.pdf_id) AS pdf_count,
                        CASE
                            WHEN c.tag LIKE ? THEN 1
                            ELSE 2
                        END AS match_priority
                    FROM cables c
                    LEFT JOIN cable_occurrences o ON c.cable_id = o.cable_id
                    WHERE c.tag LIKE ?
                    GROUP BY c.cable_id
                    ORDER BY match_priority, c.tag
                    LIMIT 50
                ''', (pattern, pattern))
                results.extend([dict(row) for row in cursor.fetchall()])

            # Sort combined results by match_priority then tag_name, cap at 50
            results.sort(key=lambda r: (r['match_priority'], r['tag_name']))
            return results[:50]

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self._get_connection() as conn:
            stats = {}

            cursor = conn.execute('SELECT COUNT(*) FROM equipment')
            stats['equipment'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM cables')
            stats['cables'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM compartments')
            stats['compartments'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM documents')
            stats['documents'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM documents WHERE to_be_indexed = 1')
            stats['documents_to_index'] = cursor.fetchone()[0]

            cursor = conn.execute(
                'SELECT COUNT(*) FROM documents WHERE date_indexed IS NOT NULL'
            )
            stats['documents_indexed'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM equipment_occurrences')
            stats['equipment_occurrences'] = cursor.fetchone()[0]

            cursor = conn.execute('SELECT COUNT(*) FROM cable_occurrences')
            stats['cable_occurrences'] = cursor.fetchone()[0]

            return stats


def init_database(db_path: str = "ship_cables.db") -> ShipCableDB:
    """Initialize and return a database instance."""
    return ShipCableDB(db_path)


if __name__ == "__main__":
    db = ShipCableDB("test_ship_cables.db")
    print("Database initialized successfully.")
    print("Stats:", db.get_stats())
