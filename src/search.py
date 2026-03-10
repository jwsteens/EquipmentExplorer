"""
Ship Cable Database - Search Interface

A simple command-line interface for searching cables and equipment in PDFs.
Includes clickable URLs with Firefox search highlighting.
Shows connected equipment for cables.
"""

import sys
import os
import urllib.parse
from pathlib import Path
from database import ShipCableDB


def load_env(env_path: str = None) -> dict:
    """
    Load environment variables from a .env file.
    Returns a dict of key-value pairs.
    """
    env_vars = {}
    
    # Look for .env in common locations
    if env_path and os.path.exists(env_path):
        dotenv_path = env_path
    else:
        # Try current directory, then script directory
        candidates = [
            Path('.env'),
            Path(__file__).parent / '.env',
        ]
        dotenv_path = None
        for candidate in candidates:
            if candidate.exists():
                dotenv_path = candidate
                break
    
    if dotenv_path and os.path.exists(dotenv_path):
        with open(dotenv_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    env_vars[key] = value
    
    return env_vars


# ANSI escape codes for terminal formatting
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


def make_clickable_url(path: str, tag: str = None, pdf_root: str = None) -> str:
    """
    Create a clickable file:// URL for the terminal.
    Adds #search=<tag> for Firefox PDF highlighting.
    """
    # Normalize path separators to forward slashes
    path = path.replace('\\', '/')
    
    # Build absolute path if pdf_root is provided
    if pdf_root and not os.path.isabs(path):
        # Also normalize pdf_root
        pdf_root = pdf_root.replace('\\', '/')
        full_path = pdf_root.rstrip('/') + '/' + path
    else:
        full_path = path
    
    # Normalize the path (but keep forward slashes)
    full_path = os.path.normpath(full_path).replace('\\', '/')
    
    # Create file:// URL
    # Use 'safe' parameter to preserve characters that shouldn't be encoded
    # Colon is needed for Windows drive letters (C:), slash for path separators
    url = f"file:///{urllib.parse.quote(full_path, safe=':/')}"
    
    # Add search parameter for Firefox
    if tag:
        url += f"#search={urllib.parse.quote(tag)}"
    
    return url


def make_terminal_link(url: str, display_text: str) -> str:
    """
    Create a clickable hyperlink for terminals that support OSC 8.
    Falls back to just showing the URL for unsupported terminals.
    """
    # OSC 8 hyperlink format: \033]8;;URL\033\\TEXT\033]8;;\033\\
    return f"\033]8;;{url}\033\\{Colors.UNDERLINE}{Colors.BLUE}{display_text}{Colors.END}\033]8;;\033\\"


def print_cable_connection(conn: dict):
    """Print cable connection information (from/to equipment)."""
    if not conn:
        return
    
    print(f"\n{Colors.BOLD}Connected Equipment:{Colors.END}")
    print(f"  {Colors.GREEN}FROM:{Colors.END} {Colors.CYAN}{conn['start_equipment_tag']}{Colors.END}")
    if conn.get('start_equipment_description'):
        print(f"        {conn['start_equipment_description']}")
    if conn.get('start_room') or conn.get('start_deck'):
        location = []
        if conn.get('start_room'):
            location.append(f"Room: {conn['start_room']}")
        if conn.get('start_deck'):
            location.append(conn['start_deck'])
        print(f"        {', '.join(location)}")
    
    print(f"  {Colors.RED}TO:  {Colors.END} {Colors.CYAN}{conn['dest_equipment_tag']}{Colors.END}")
    if conn.get('dest_equipment_description'):
        print(f"        {conn['dest_equipment_description']}")
    if conn.get('dest_room') or conn.get('dest_deck'):
        location = []
        if conn.get('dest_room'):
            location.append(f"Room: {conn['dest_room']}")
        if conn.get('dest_deck'):
            location.append(conn['dest_deck'])
        print(f"        {', '.join(location)}")


def print_equipment_cables(cables: list, equipment_tag: str):
    """Print all cables connected to a piece of equipment."""
    if not cables:
        return
    
    print(f"\n{Colors.BOLD}Connected Cables ({len(cables)}):{Colors.END}")
    
    for c in cables[:20]:  # Limit display
        direction = c.get('connection_direction', '')
        if direction == 'from':
            # This equipment is the start, show destination
            arrow = f"{Colors.GREEN}â†’{Colors.END}"
            other = c['dest_equipment_tag']
            other_desc = c.get('dest_equipment_description', '')
        else:
            # This equipment is the destination, show start
            arrow = f"{Colors.RED}â†{Colors.END}"
            other = c['start_equipment_tag']
            other_desc = c.get('start_equipment_description', '')
        
        desc = f" ({other_desc})" if other_desc else ""
        print(f"  {Colors.CYAN}{c['cable_tag']:20}{Colors.END} {arrow} {other}{desc}")
    
    if len(cables) > 20:
        print(f"  ... and {len(cables) - 20} more cables")


def print_results(results: list, tag_name: str, pdf_root: str = None, 
                  cable_connection: dict = None, equipment_cables: list = None):
    """Pretty print search results with clickable URLs."""
    if not results:
        print(f"\nNo PDFs found containing '{tag_name}'")
        # Still show connection info if available
        if cable_connection:
            print_cable_connection(cable_connection)
        if equipment_cables:
            print_equipment_cables(equipment_cables, tag_name)
        return
    
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}Tag: {Colors.CYAN}{tag_name}{Colors.END}")
    print(f"{Colors.BOLD}Type: {Colors.GREEN}{results[0]['tag_type'].upper()}{Colors.END}")
    if results[0]['description']:
        print(f"{Colors.BOLD}Description: {Colors.END}{results[0]['description']}")
    
    # Show cable connection info if this is a cable
    if cable_connection:
        print_cable_connection(cable_connection)
    
    # Show connected cables if this is equipment
    if equipment_cables:
        print_equipment_cables(equipment_cables, tag_name)
    
    # Group by PDF
    pdfs = {}
    for r in results:
        path = r['relative_path']
        if path not in pdfs:
            pdfs[path] = {
                'filename': r['filename'],
                'document_description': r.get('document_description'),
                'drawing_number': r.get('drawing_number'),
                'pages': []
            }
        if r['page_number']:
            pdfs[path]['pages'].append(r['page_number'])
    
    print(f"\n{Colors.BOLD}Found in {len(pdfs)} PDF(s){Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}")
    
    for path, info in pdfs.items():
        pages = sorted(set(info['pages'])) if info['pages'] else []
        pages_str = f" (pages: {', '.join(map(str, pages))})" if pages else ""
        
        # Create display name (prefer document description)
        if info['document_description']:
            display_name = info['document_description']
        else:
            display_name = info['filename']
        
        # Create clickable URL
        url = make_clickable_url(path, tag_name, pdf_root)
        clickable_link = make_terminal_link(url, display_name)
        
        print(f"\n  ðŸ“„ {clickable_link}{pages_str}")
        print(f"     {Colors.YELLOW}Path: {path}{Colors.END}")
        print(f"     {Colors.CYAN}URL:  {url}{Colors.END}")


def print_partial_results(results: list):
    """Print partial match results."""
    if not results:
        print("No matching tags found.")
        return
    
    print(f"\nFound {len(results)} matching tags:")
    print("-" * 60)
    
    for r in results:
        pdf_count = r['pdf_count'] or 0
        pdf_str = f"({pdf_count} PDFs)" if pdf_count > 0 else "(no PDFs yet)"
        tag_type = r['tag_type'].upper()
        color = Colors.CYAN if tag_type == 'CABLE' else Colors.GREEN
        print(f"  [{color}{tag_type:10}{Colors.END}] {r['tag_name']:30} {pdf_str}")


def print_pdf_search_results(results: list, pdf_root: str = None):
    """Print PDF search results with selection numbers."""
    if not results:
        print("No matching PDFs found.")
        return
    
    print(f"\n{Colors.BOLD}Found {len(results)} matching PDF(s):{Colors.END}")
    print("-" * 70)
    
    for i, pdf in enumerate(results, 1):
        # Display name: prefer description, fall back to filename
        if pdf.get('document_description'):
            display_name = pdf['document_description']
        else:
            display_name = pdf['filename']
        
        tag_count = pdf.get('tag_count', 0)
        tag_str = f"({tag_count} tags)" if tag_count > 0 else "(no tags indexed)"
        
        # Drawing number if available
        drawing = f" [{pdf['drawing_number']}]" if pdf.get('drawing_number') else ""
        
        print(f"\n  {Colors.BOLD}[{i}]{Colors.END} {Colors.CYAN}{display_name}{Colors.END}{drawing}")
        print(f"      {Colors.YELLOW}File: {pdf['filename']}{Colors.END} {tag_str}")
        
        if pdf_root:
            url = make_clickable_url(pdf['relative_path'], pdf_root=pdf_root)
            print(f"      {Colors.BLUE}{url}{Colors.END}")
    
    return results


def print_pdf_contents(pdf_info: dict, contents: list, pdf_root: str = None):
    """Print the tags found in a PDF."""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    
    # Header with PDF info
    if pdf_info.get('document_description'):
        print(f"{Colors.BOLD}Document: {Colors.CYAN}{pdf_info['document_description']}{Colors.END}")
    print(f"{Colors.BOLD}File: {Colors.END}{pdf_info['filename']}")
    if pdf_info.get('drawing_number'):
        print(f"{Colors.BOLD}Drawing #: {Colors.END}{pdf_info['drawing_number']}")
    print(f"{Colors.BOLD}Path: {Colors.END}{pdf_info['relative_path']}")
    
    if pdf_root:
        url = make_clickable_url(pdf_info['relative_path'], pdf_root=pdf_root)
        clickable = make_terminal_link(url, "Open PDF")
        print(f"{Colors.BOLD}Link: {Colors.END}{clickable}")
    
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}")
    
    if not contents:
        print(f"\n{Colors.YELLOW}No tags indexed for this PDF.{Colors.END}")
        if not pdf_info.get('is_searchable'):
            print("(This PDF may need OCR processing)")
        return
    
    cables = [c for c in contents if c['tag_type'] == 'cable']
    equipment = [c for c in contents if c['tag_type'] == 'equipment']
    
    if cables:
        print(f"\n{Colors.CYAN}Cables ({len(cables)}):{Colors.END}")
        for c in cables[:30]:
            page = f" (p.{c['page_number']})" if c['page_number'] else ""
            print(f"  • {c['tag_name']}{page}")
        if len(cables) > 30:
            print(f"  ... and {len(cables) - 30} more")
    
    if equipment:
        print(f"\n{Colors.GREEN}Equipment ({len(equipment)}):{Colors.END}")
        for e in equipment[:30]:
            page = f" (p.{e['page_number']})" if e['page_number'] else ""
            desc = f" - {e['description']}" if e['description'] else ""
            print(f"  • {e['tag_name']}{page}{desc}")
        if len(equipment) > 30:
            print(f"  ... and {len(equipment) - 30} more")


def interactive_search(db: ShipCableDB, pdf_root: str = None):
    """Interactive search loop."""
    print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
    print(f"{Colors.BOLD}Ship Cable Database - Search Interface{Colors.END}")
    print(f"{Colors.BOLD}{'=' * 70}{Colors.END}")
    print("\nCommands:")
    print("  <tag>          - Search for exact tag")
    print("  ?<partial>     - Search for tags containing <partial>")
    print("  !pdf <query>   - Search PDFs by filename, description, or drawing #")
    print("  !stats         - Show database statistics")
    print("  !root <path>   - Set PDF root directory for URLs")
    print("  !help          - Show this help")
    print("  !quit          - Exit")
    
    if pdf_root:
        print(f"\n{Colors.GREEN}PDF Root: {pdf_root}{Colors.END}")
    else:
        print(f"\n{Colors.YELLOW}Tip: Use '!root /path/to/pdfs' to enable clickable links{Colors.END}")
    
    print("-" * 70)
    
    while True:
        try:
            query = input(f"\n{Colors.BOLD}Search>{Colors.END} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        
        if not query:
            continue
        
        if query.lower() in ('!quit', '!exit', '!q'):
            print("Goodbye!")
            break
        
        elif query.lower() == '!help':
            print("\nCommands:")
            print("  <tag>          - Search for exact tag")
            print("  ?<partial>     - Search for tags containing <partial>")
            print("  !pdf <query>   - Search PDFs by filename, description, or drawing #")
            print("  !stats         - Show database statistics")
            print("  !root <path>   - Set PDF root directory for URLs")
            print("  !quit          - Exit")
            print("\nExamples:")
            print("  !pdf diagram        - Find PDFs with 'diagram' in description")
            print("  !pdf 0854-40        - Find PDFs matching drawing number")
            print("  !pdf lighting       - Find PDFs about lighting")
        
        elif query.lower() == '!stats':
            stats = db.get_stats()
            print(f"\n{Colors.BOLD}Database Statistics:{Colors.END}")
            print("-" * 40)
            for key, value in stats.items():
                print(f"  {key:25}: {value:>10}")
        
        elif query.lower().startswith('!root '):
            new_root = query[6:].strip()
            if os.path.isdir(new_root):
                pdf_root = os.path.abspath(new_root)
                print(f"{Colors.GREEN}PDF root set to: {pdf_root}{Colors.END}")
            else:
                print(f"{Colors.YELLOW}Warning: Directory not found: {new_root}{Colors.END}")
                print("Setting anyway - URLs may not work correctly.")
                pdf_root = new_root
        
        elif query.lower().startswith('!pdf '):
            pdf_query = query[5:].strip()
            if not pdf_query:
                print("Usage: !pdf <search query>")
                print("Search by filename, document description, or drawing number")
                continue
            
            # Check if it's a selection number from previous search
            if pdf_query.isdigit() and hasattr(interactive_search, 'last_pdf_results'):
                idx = int(pdf_query) - 1
                if 0 <= idx < len(interactive_search.last_pdf_results):
                    pdf = interactive_search.last_pdf_results[idx]
                    contents = db.get_pdf_contents_by_id(pdf['pdf_id'])
                    print_pdf_contents(pdf, contents, pdf_root)
                    continue
                else:
                    print(f"Invalid selection. Enter 1-{len(interactive_search.last_pdf_results)}")
                    continue
            
            # Search for PDFs
            results = db.search_pdfs(pdf_query)
            
            if not results:
                print(f"No PDFs found matching '{pdf_query}'")
            elif len(results) == 1:
                # Single result - show contents directly
                pdf = results[0]
                contents = db.get_pdf_contents_by_id(pdf['pdf_id'])
                print_pdf_contents(pdf, contents, pdf_root)
            else:
                # Multiple results - show list and store for selection
                print_pdf_search_results(results, pdf_root)
                interactive_search.last_pdf_results = results
                print(f"\n{Colors.YELLOW}Enter !pdf <number> to view tags in a specific PDF{Colors.END}")
        
        elif query.startswith('?'):
            # Partial search
            partial = query[1:].strip()
            if len(partial) < 2:
                print("Please enter at least 2 characters for partial search.")
                continue
            
            results = db.search_tag_partial(partial)
            print_partial_results(results)
        
        else:
            # Exact search - try original, then uppercase
            results = db.search_tag(query)
            if not results:
                results = db.search_tag(query.upper())
            
            if not results:
                # Try partial search as fallback
                partial_results = db.search_tag_partial(query)
                if partial_results:
                    print(f"No exact match for '{query}'. Did you mean one of these?")
                    print_partial_results(partial_results[:10])
                else:
                    print(f"No tags found matching '{query}'")
            else:
                tag_name = results[0]['tag_name']
                tag_type = results[0]['tag_type']
                
                # Get connection info based on tag type
                cable_connection = None
                equipment_cables = None
                
                if tag_type == 'cable':
                    cable_connection = db.get_cable_connection(tag_name)
                elif tag_type == 'equipment':
                    equipment_cables = db.get_cables_for_equipment(tag_name)
                
                print_results(results, tag_name, pdf_root, 
                             cable_connection, equipment_cables)


def single_search(db: ShipCableDB, tag: str, pdf_root: str = None):
    """Single search for command-line use."""
    results = db.search_tag(tag)
    search_tag = tag
    
    if not results:
        # Try uppercase
        results = db.search_tag(tag.upper())
        if results:
            search_tag = tag.upper()
    
    if results:
        tag_name = results[0]['tag_name']
        tag_type = results[0]['tag_type']
        
        # Get connection info based on tag type
        cable_connection = None
        equipment_cables = None
        
        if tag_type == 'cable':
            cable_connection = db.get_cable_connection(tag_name)
        elif tag_type == 'equipment':
            equipment_cables = db.get_cables_for_equipment(tag_name)
        
        print_results(results, tag_name, pdf_root, cable_connection, equipment_cables)
    else:
        # No PDF occurrences found - check if tag exists in database
        # Try to get connection info (for cables) or cables connected (for equipment)
        cable_connection = db.get_cable_connection(tag)
        if not cable_connection:
            cable_connection = db.get_cable_connection(tag.upper())
        
        equipment_cables = db.get_cables_for_equipment(tag)
        if not equipment_cables:
            equipment_cables = db.get_cables_for_equipment(tag.upper())
        
        if cable_connection:
            # It's a cable with no PDF occurrences
            print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
            print(f"{Colors.BOLD}Tag: {Colors.CYAN}{cable_connection['cable_tag']}{Colors.END}")
            print(f"{Colors.BOLD}Type: {Colors.GREEN}CABLE{Colors.END}")
            if cable_connection.get('cable_description'):
                print(f"{Colors.BOLD}Description: {Colors.END}{cable_connection['cable_description']}")
            print_cable_connection(cable_connection)
            print(f"\n{Colors.YELLOW}No PDF occurrences found for this cable.{Colors.END}")
        elif equipment_cables:
            # It's equipment with no PDF occurrences
            equip_tag = equipment_cables[0]['start_equipment_tag'] if equipment_cables[0].get('connection_direction') == 'from' else equipment_cables[0]['dest_equipment_tag']
            equip_desc = equipment_cables[0]['start_equipment_description'] if equipment_cables[0].get('connection_direction') == 'from' else equipment_cables[0]['dest_equipment_description']
            
            print(f"\n{Colors.BOLD}{'=' * 70}{Colors.END}")
            print(f"{Colors.BOLD}Tag: {Colors.CYAN}{equip_tag}{Colors.END}")
            print(f"{Colors.BOLD}Type: {Colors.GREEN}EQUIPMENT{Colors.END}")
            if equip_desc:
                print(f"{Colors.BOLD}Description: {Colors.END}{equip_desc}")
            print_equipment_cables(equipment_cables, equip_tag)
            print(f"\n{Colors.YELLOW}No PDF occurrences found for this equipment.{Colors.END}")
        else:
            # Tag truly not found
            print(f"No results found for '{tag}'")
            # Try partial
            partial = db.search_tag_partial(tag)
            if partial:
                print("\nSimilar tags:")
                print_partial_results(partial[:5])


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Ship Cable Database - Search Interface")
    parser.add_argument('tag', nargs='?', help='Tag to search for (omit for interactive mode)')
    parser.add_argument('--db', default=None, help='Path to database')
    parser.add_argument('--root', '-r', help='PDF root directory for clickable URLs (overrides .env)')
    parser.add_argument('--env', help='Path to .env file')
    
    args = parser.parse_args()
    
    # Load environment variables from .env
    env_vars = load_env(args.env)
    
    # PDF root priority: command line > .env > None
    pdf_root = args.root or env_vars.get('PDF_ROOT')
    
    # Database path: CLI arg > .env > default
    db_path = args.db or env_vars.get('DB_PATH', '/data/equipment_explorer.db')
    
    # Check for database
    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        print("Please run import_cable_list.py first.")
        sys.exit(1)
    
    db = ShipCableDB(db_path)
    
    if args.tag:
        # Single search mode
        single_search(db, args.tag, pdf_root)
    else:
        # Interactive mode
        interactive_search(db, pdf_root)


if __name__ == "__main__":
    main()
