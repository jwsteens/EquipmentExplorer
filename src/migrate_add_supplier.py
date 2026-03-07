"""
Migration Script: Add supplier columns to existing database

Run this script to add supplier_code and supplier_name columns to an existing
ship_cables.db database without losing data.

Usage:
    python migrate_add_supplier.py [db_path]
"""

import sqlite3
import sys
import os


def migrate_database(db_path: str = "ship_cables.db"):
    """Add supplier columns to existing pdfs table."""
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        return False
    
    print(f"Migrating database: {db_path}")
    print("-" * 50)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if columns already exist
    cursor.execute("PRAGMA table_info(pdfs)")
    columns = {row[1] for row in cursor.fetchall()}
    
    migrations_needed = []
    if 'supplier_code' not in columns:
        migrations_needed.append(('supplier_code', 'TEXT'))
    if 'supplier_name' not in columns:
        migrations_needed.append(('supplier_name', 'TEXT'))
    
    if not migrations_needed:
        print("Database is already up to date. No migration needed.")
        conn.close()
        return True
    
    print(f"Columns to add: {[m[0] for m in migrations_needed]}")
    
    # Add new columns
    for col_name, col_type in migrations_needed:
        try:
            cursor.execute(f"ALTER TABLE pdfs ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added column: {col_name}")
        except sqlite3.OperationalError as e:
            print(f"  ! Column {col_name} may already exist: {e}")
    
    # Add index for supplier lookups
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_pdfs_supplier ON pdfs(supplier_name)")
        print("  ✓ Created index: idx_pdfs_supplier")
    except sqlite3.OperationalError as e:
        print(f"  ! Index may already exist: {e}")
    
    conn.commit()
    conn.close()
    
    print("-" * 50)
    print("Migration complete!")
    return True


def update_supplier_from_metadata(db_path: str = "ship_cables.db", 
                                   metadata_path: str = "drawing_metadata.pkl"):
    """
    Update existing PDF records with supplier information from metadata cache.
    Run this after migration to populate supplier columns for existing records.
    """
    import pickle
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        return False
    
    if not os.path.exists(metadata_path):
        print(f"Error: Metadata cache not found: {metadata_path}")
        print("Run import_drawing_metadata.py first to create the metadata cache.")
        return False
    
    # Load metadata
    print(f"Loading metadata from: {metadata_path}")
    with open(metadata_path, 'rb') as f:
        metadata = pickle.load(f)
    print(f"Loaded metadata for {len(metadata)} files")
    
    # Update database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all PDFs without supplier info
    cursor.execute("""
        SELECT pdf_id, filename 
        FROM pdfs 
        WHERE (supplier_code IS NULL OR supplier_code = '')
           OR (supplier_name IS NULL OR supplier_name = '')
    """)
    pdfs_to_update = cursor.fetchall()
    print(f"Found {len(pdfs_to_update)} PDFs to update")
    
    updated = 0
    for pdf_id, filename in pdfs_to_update:
        key = filename.lower()
        if key in metadata:
            info = metadata[key]
            supplier_code = info.get('supplier_code')
            supplier_name = info.get('supplier_name')
            
            if supplier_code or supplier_name:
                cursor.execute("""
                    UPDATE pdfs 
                    SET supplier_code = ?, supplier_name = ?
                    WHERE pdf_id = ?
                """, (supplier_code, supplier_name, pdf_id))
                updated += 1
    
    conn.commit()
    conn.close()
    
    print(f"Updated {updated} PDF records with supplier information")
    return True


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "ship_cables.db"
    metadata_path = sys.argv[2] if len(sys.argv) > 2 else "drawing_metadata.pkl"
    
    print("=" * 60)
    print("Ship Cable Database - Supplier Migration")
    print("=" * 60)
    
    # Step 1: Add columns
    if migrate_database(db_path):
        print()
        # Step 2: Populate data from metadata
        update_supplier_from_metadata(db_path, metadata_path)
    
    print("\nDone!")
