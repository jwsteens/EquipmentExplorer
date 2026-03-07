"""
Import Tags from Excel Cable List

This script reads the cable list Excel file and imports all cable and equipment tags
into the database, including the cable-to-equipment connection relationships.
"""

import pandas as pd
import os
import sys
from database import ShipCableDB


def import_cable_list(excel_path: str, db: ShipCableDB) -> dict:
    """
    Import cable and equipment tags from the Excel cable list.
    Also imports the cable-to-equipment connection relationships.
    
    Returns statistics about the import.
    """
    print(f"Reading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)
    
    print(f"Found {len(df)} rows in cable list")
    
    stats = {
        'cables_added': 0,
        'equipment_added': 0,
        'cables_total': 0,
        'equipment_total': 0,
        'connections_added': 0,
        'connections_total': 0
    }
    
    # Extract cable tags
    print("\nExtracting cable tags...")
    cable_tags = df['cableNo'].dropna().unique()
    stats['cables_total'] = len(cable_tags)
    
    cable_data = []
    for tag in cable_tags:
        # Get first row with this cable for any additional info
        row = df[df['cableNo'] == tag].iloc[0]
        cable_type = f"{row.get('cableType1', '')} {row.get('cableType2', '')}".strip()
        cable_data.append((str(tag), 'cable', cable_type if cable_type else None, None, None))
    
    print(f"Found {len(cable_data)} unique cable tags")
    stats['cables_added'] = db.add_tags_bulk(cable_data)
    
    # Extract equipment tags (both start and destination)
    print("\nExtracting equipment tags...")
    
    # Start equipment
    start_equipment = df[['equipmentStartTag', 'equipmentStartDescription', 
                          'equipmentStartRoomTag', 'equipmentStartDeck']].dropna(subset=['equipmentStartTag'])
    start_equipment = start_equipment.drop_duplicates(subset=['equipmentStartTag'])
    
    # Destination equipment
    dest_equipment = df[['equipmentDestinationTag', 'equipmentDestinationDescription',
                         'equipmentDestinationRoomTag', 'equipmentDestinationDeck']].dropna(subset=['equipmentDestinationTag'])
    dest_equipment = dest_equipment.drop_duplicates(subset=['equipmentDestinationTag'])
    
    # Combine and deduplicate
    equipment_dict = {}
    
    for _, row in start_equipment.iterrows():
        tag = str(row['equipmentStartTag'])
        if tag not in equipment_dict:
            equipment_dict[tag] = {
                'description': row.get('equipmentStartDescription'),
                'room_tag': row.get('equipmentStartRoomTag'),
                'deck': row.get('equipmentStartDeck')
            }
    
    for _, row in dest_equipment.iterrows():
        tag = str(row['equipmentDestinationTag'])
        if tag not in equipment_dict:
            equipment_dict[tag] = {
                'description': row.get('equipmentDestinationDescription'),
                'room_tag': row.get('equipmentDestinationRoomTag'),
                'deck': row.get('equipmentDestinationDeck')
            }
    
    stats['equipment_total'] = len(equipment_dict)
    
    equipment_data = []
    for tag, info in equipment_dict.items():
        desc = info['description'] if pd.notna(info['description']) else None
        room = str(info['room_tag']) if pd.notna(info['room_tag']) else None
        deck = info['deck'] if pd.notna(info['deck']) else None
        equipment_data.append((tag, 'equipment', desc, room, deck))
    
    print(f"Found {len(equipment_data)} unique equipment tags")
    stats['equipment_added'] = db.add_tags_bulk(equipment_data)
    
    # Import cable connections (cable -> start equipment -> dest equipment)
    print("\nImporting cable connections...")
    
    # Build tag_id lookup map
    tag_id_map = {}
    for tag_row in db.get_all_tags():
        tag_id_map[tag_row['tag_name']] = tag_row['tag_id']
    
    # Process connections
    connections = []
    seen_cables = set()  # Track cables we've already added connections for
    
    for _, row in df.iterrows():
        cable_tag = row.get('cableNo')
        start_tag = row.get('equipmentStartTag')
        dest_tag = row.get('equipmentDestinationTag')
        
        # Skip if any value is missing
        if pd.isna(cable_tag) or pd.isna(start_tag) or pd.isna(dest_tag):
            continue
        
        cable_tag = str(cable_tag)
        start_tag = str(start_tag)
        dest_tag = str(dest_tag)
        
        # Skip if we've already processed this cable
        if cable_tag in seen_cables:
            continue
        seen_cables.add(cable_tag)
        
        # Get tag IDs
        cable_id = tag_id_map.get(cable_tag)
        start_id = tag_id_map.get(start_tag)
        dest_id = tag_id_map.get(dest_tag)
        
        if cable_id and start_id and dest_id:
            connections.append((cable_id, start_id, dest_id))
    
    stats['connections_total'] = len(connections)
    
    if connections:
        stats['connections_added'] = db.add_cable_connections_bulk(connections)
    
    print(f"Found {stats['connections_total']} cable connections")
    
    return stats


def main():
    # Configuration
    excel_path = sys.argv[1] if len(sys.argv) > 1 else "Cable_list.xlsx"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "ship_cables.db"
    
    if not os.path.exists(excel_path):
        print(f"Error: Excel file not found: {excel_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("Ship Cable Database - Import Cable List")
    print("=" * 60)
    
    # Initialize database
    db = ShipCableDB(db_path)
    
    # Import tags
    stats = import_cable_list(excel_path, db)
    
    print("\n" + "=" * 60)
    print("Import Complete!")
    print("=" * 60)
    print(f"Cable tags:       {stats['cables_total']:>8} found, {stats['cables_added']:>8} new")
    print(f"Equipment tags:   {stats['equipment_total']:>8} found, {stats['equipment_added']:>8} new")
    print(f"Cable connections:{stats['connections_total']:>8} found, {stats['connections_added']:>8} new")
    
    # Show database stats
    print("\nDatabase Statistics:")
    db_stats = db.get_stats()
    for key, value in db_stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
