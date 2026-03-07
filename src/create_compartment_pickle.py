"""
Create Compartment Data Pickle

Reads the Compartment_number_plan.csv and creates a pickle file with
room key to room description mappings for use in search.py.

Usage:
    python create_compartment_pickle.py [input_csv] [output_pickle]
"""

import pickle
import csv
import sys
from pathlib import Path


def create_compartment_pickle(csv_path: str, output_path: str = "compartments.pkl"):
    """
    Read compartment CSV and create a pickle file with the mapping.
    
    Args:
        csv_path: Path to the Compartment_number_plan.csv file
        output_path: Path for the output pickle file
    
    Returns:
        dict: The compartment mapping {room_key: room_description}
    """
    compartments = {}
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        # CSV uses semicolon as delimiter
        reader = csv.DictReader(f, delimiter=';')
        
        for row in reader:
            room_key = row['roomKey'].strip()
            room_description = row['roomDescription'].strip()
            compartments[room_key] = room_description
    
    # Save to pickle
    with open(output_path, 'wb') as f:
        pickle.dump(compartments, f)
    
    print(f"Created {output_path} with {len(compartments)} compartment entries")
    
    # Print some sample entries
    print("\nSample entries:")
    sample_keys = list(compartments.keys())[:5]
    for key in sample_keys:
        print(f"  {key}: {compartments[key]}")
    
    return compartments


def main():
    # Default paths
    csv_path = "Compartment_number_plan.csv"
    output_path = "compartments.pkl"
    
    # Override with command line arguments if provided
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]
    
    # Check if CSV exists
    if not Path(csv_path).exists():
        print(f"Error: CSV file not found: {csv_path}")
        print("Usage: python create_compartment_pickle.py [input_csv] [output_pickle]")
        sys.exit(1)
    
    create_compartment_pickle(csv_path, output_path)


if __name__ == "__main__":
    main()
