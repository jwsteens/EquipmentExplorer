#!/usr/bin/env python3
"""
Migration: Add index on tags.description for improved search performance

This migration adds an index to the description column to speed up
description-based searches.

Usage:
    python migrate_add_description_index.py [--db PATH]
"""

import sys
import os
import argparse
import sqlite3
from pathlib import Path


def add_description_index(db_path: str) -> bool:
    """
    Add index on tags.description if it doesn't exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        print(f"Opening database: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_tags_description'
        """)
        
        if cursor.fetchone():
            print("✓ Index 'idx_tags_description' already exists")
            conn.close()
            return True
        
        print("Creating index on tags.description...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tags_description ON tags(description)
        """)
        
        conn.commit()
        
        # Verify index was created
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND name='idx_tags_description'
        """)
        
        if cursor.fetchone():
            print("✓ Successfully created index 'idx_tags_description'")
            
            # Get some stats
            cursor.execute("SELECT COUNT(*) FROM tags WHERE description IS NOT NULL")
            desc_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tags")
            total_count = cursor.fetchone()[0]
            
            print(f"\nDatabase statistics:")
            print(f"  Total tags: {total_count}")
            print(f"  Tags with descriptions: {desc_count} ({desc_count*100//total_count if total_count > 0 else 0}%)")
            
            result = True
        else:
            print("❌ Failed to create index")
            result = False
        
        conn.close()
        return result
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Add description index to ship cables database'
    )
    parser.add_argument(
        '--db',
        default='ship_cables.db',
        help='Path to database file (default: ship_cables.db)'
    )
    
    args = parser.parse_args()
    
    # Check if database exists
    if not os.path.exists(args.db):
        print(f"❌ Database not found: {args.db}")
        print("\nPlease specify the correct database path:")
        print(f"  python {sys.argv[0]} --db /path/to/ship_cables.db")
        return 1
    
    print("="*70)
    print("Migration: Add Description Index")
    print("="*70)
    print()
    
    success = add_description_index(args.db)
    
    print()
    print("="*70)
    if success:
        print("✓ Migration completed successfully!")
    else:
        print("❌ Migration failed!")
    print("="*70)
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
