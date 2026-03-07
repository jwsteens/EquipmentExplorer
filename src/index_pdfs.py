"""
PDF Indexer for Ship Cable Database

This script scans PDF files for cable and equipment tags and records their occurrences
in the database.

Features:
- Multicore processing: Use --workers N for parallel PDF processing
- Pause/Resume: Press Ctrl+C to pause, state is saved to JSON file
- Keyword filtering: Filter documents by description (e.g., --keyword diagram)
- Priority indexing: Process documents matching keyword first

Phase 1: Searchable PDFs (text-based)
Phase 2: Non-searchable PDFs (requires OCR - handled by separate script)
"""

import os
import sys
import re
import json
import pickle
import signal
import multiprocessing
from pathlib import Path
from datetime import datetime
from typing import Set, List, Tuple, Optional, Dict
from dataclasses import dataclass, field, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed, Future
import fitz  # PyMuPDF
from database import ShipCableDB


# =============================================================================
# STATE MANAGEMENT FOR PAUSE/RESUME
# =============================================================================

@dataclass
class IndexingState:
    """Tracks the state of indexing for pause/resume functionality."""
    total_documents: int = 0
    processed_count: int = 0
    successful_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    pending_files: List[str] = field(default_factory=list)
    keyword_filter: Optional[str] = None
    started_at: Optional[str] = None
    last_updated: Optional[str] = None
    is_complete: bool = False
    
    # Statistics
    searchable_pdfs: int = 0
    non_searchable_pdfs: int = 0
    total_tags_found: int = 0
    total_cables_found: int = 0
    total_equipment_found: int = 0
    errors: int = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'IndexingState':
        return cls(**data)
    
    def save(self, path: str):
        """Save state to JSON file."""
        self.last_updated = datetime.now().isoformat()
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> Optional['IndexingState']:
        """Load state from JSON file."""
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
                return cls.from_dict(data)
        return None


def load_drawing_metadata(cache_path: str = "drawing_metadata.pkl") -> Dict:
    """Load drawing metadata from cache file."""
    if os.path.exists(cache_path):
        with open(cache_path, 'rb') as f:
            return pickle.load(f)
    return {}


# =============================================================================
# WORKER FUNCTIONS FOR MULTIPROCESSING
# =============================================================================

# Global variables for worker processes (initialized via initializer)
_worker_all_tags: Set[str] = set()
_worker_cable_tags: Set[str] = set()
_worker_equipment_tags: Set[str] = set()
_worker_tag_id_map: Dict[str, int] = {}
_worker_tag_patterns: List[re.Pattern] = []
_worker_drawing_metadata: Dict = {}
_worker_pdf_root: str = ""


def _worker_init(all_tags: Set[str], cable_tags: Set[str], equipment_tags: Set[str],
                 tag_id_map: Dict[str, int], drawing_metadata: Dict, pdf_root: str):
    """Initialize worker process with shared data."""
    global _worker_all_tags, _worker_cable_tags, _worker_equipment_tags
    global _worker_tag_id_map, _worker_tag_patterns, _worker_drawing_metadata, _worker_pdf_root
    
    _worker_all_tags = all_tags
    _worker_cable_tags = cable_tags
    _worker_equipment_tags = equipment_tags
    _worker_tag_id_map = tag_id_map
    _worker_drawing_metadata = drawing_metadata
    _worker_pdf_root = pdf_root
    
    # Build regex patterns in worker
    escaped_tags = [re.escape(tag) for tag in sorted(all_tags, key=len, reverse=True)]
    _worker_tag_patterns = _chunk_patterns(escaped_tags, chunk_size=1000)


def _chunk_patterns(escaped_tags: List[str], chunk_size: int) -> List[re.Pattern]:
    """Split tags into chunks to avoid regex size limits."""
    patterns = []
    for i in range(0, len(escaped_tags), chunk_size):
        chunk = escaped_tags[i:i + chunk_size]
        pattern = re.compile('|'.join(chunk), re.IGNORECASE)
        patterns.append(pattern)
    return patterns


def _find_tags_in_text(text: str) -> Set[str]:
    """Find all matching tags in a text string."""
    found_tags = set()
    
    # Fast path: word-based matching
    words = re.findall(r'[\w\-\.\/]+', text)
    for word in words:
        if word in _worker_all_tags:
            found_tags.add(word)
        word_upper = word.upper()
        if word_upper in _worker_all_tags:
            found_tags.add(word_upper)
    
    # Regex-based matching for complex patterns
    for pattern in _worker_tag_patterns:
        matches = pattern.findall(text)
        for match in matches:
            match_upper = match.upper()
            if match_upper in _worker_all_tags:
                found_tags.add(match_upper)
            elif match in _worker_all_tags:
                found_tags.add(match)
    
    return found_tags


def _process_pdf_worker(pdf_path_str: str) -> dict:
    """
    Worker function to process a single PDF.
    Returns extracted data without database writes.
    """
    pdf_path = Path(pdf_path_str)
    filename = pdf_path.name
    
    # Get metadata
    key = filename.lower()
    metadata = _worker_drawing_metadata.get(key, {})
    document_description = metadata.get('document_description')
    supplier_code = metadata.get('supplier_code')
    supplier_name = metadata.get('supplier_name')
    
    # Determine relative path
    if metadata.get('relative_path_unix'):
        relative_path = metadata['relative_path_unix']
    else:
        try:
            relative_path = str(pdf_path.resolve().relative_to(Path(_worker_pdf_root).resolve()))
        except ValueError:
            relative_path = str(pdf_path.resolve())
    
    result = {
        'pdf_path': pdf_path_str,
        'path': relative_path,
        'filename': filename,
        'drawing_number': supplier_code,
        'supplier_code': supplier_code,
        'supplier_name': supplier_name,
        'document_description': document_description,
        'searchable': False,
        'page_count': 0,
        'file_size': 0,
        'tags_found': 0,
        'cables_found': 0,
        'equipment_found': 0,
        'occurrences': [],  # List of (tag_id, page_num) tuples
        'error': None
    }
    
    try:
        result['file_size'] = pdf_path.stat().st_size
        
        # Open and check PDF
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        result['page_count'] = page_count
        
        # Check if searchable
        text_found = False
        for page_num in range(min(3, page_count)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_found = True
                break
        
        result['searchable'] = text_found
        
        if not text_found:
            doc.close()
            return result
        
        # Extract text and find tags
        all_found_tags = {}
        
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            if not text.strip():
                continue
            
            tags = _find_tags_in_text(text)
            for tag in tags:
                if tag not in all_found_tags:
                    all_found_tags[tag] = set()
                all_found_tags[tag].add(page_num + 1)  # 1-indexed pages
        
        doc.close()
        
        # Build occurrences list
        occurrences = []
        cables_found = 0
        equipment_found = 0
        
        for tag, page_numbers in all_found_tags.items():
            tag_id = _worker_tag_id_map.get(tag)
            if tag_id:
                for page_num in page_numbers:
                    occurrences.append((tag_id, page_num))
                
                if tag in _worker_cable_tags:
                    cables_found += 1
                else:
                    equipment_found += 1
        
        result['occurrences'] = occurrences
        result['tags_found'] = len(all_found_tags)
        result['cables_found'] = cables_found
        result['equipment_found'] = equipment_found
        
    except Exception as e:
        result['error'] = str(e)
    
    return result


class PDFIndexer:
    """Indexes PDF files for cable and equipment tags with pause/resume support."""
    
    STATE_FILE = "indexing_state.json"
    
    def __init__(self, db: ShipCableDB, pdf_root: str, metadata_path: str = None,
                 state_file: str = None):
        self.db = db
        self.pdf_root = Path(pdf_root).resolve()
        self.state_file = state_file or self.STATE_FILE
        
        # Pause handling
        self._pause_requested = False
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        
        # Load drawing metadata (for document descriptions)
        # Metadata is keyed by lowercase filename
        if metadata_path:
            self.drawing_metadata = load_drawing_metadata(metadata_path)
        else:
            # Try default location (same directory as database)
            default_metadata = Path(db.db_path).parent / "drawing_metadata.pkl"
            self.drawing_metadata = load_drawing_metadata(str(default_metadata))
        
        if self.drawing_metadata:
            print(f"Loaded metadata for {len(self.drawing_metadata)} drawings")
        else:
            print("No drawing metadata loaded (run import_drawing_metadata.py first)")
            print("Document descriptions won't be available.")
        
        # Load all tags into memory for fast lookup
        print("Loading tags from database...")
        self.cable_tags = db.get_tag_names_set('cable')
        self.equipment_tags = db.get_tag_names_set('equipment')
        self.all_tags = self.cable_tags | self.equipment_tags
        
        print(f"Loaded {len(self.cable_tags)} cable tags")
        print(f"Loaded {len(self.equipment_tags)} equipment tags")
        
        # Build tag lookup dict (tag_name -> tag_id)
        self.tag_id_map = {}
        for tag in self.db.get_all_tags():
            self.tag_id_map[tag['tag_name']] = tag['tag_id']
        
        # Build regex pattern for efficient tag detection (for single-file mode)
        escaped_tags = [re.escape(tag) for tag in sorted(self.all_tags, key=len, reverse=True)]
        self.tag_patterns = self._chunk_patterns(escaped_tags, chunk_size=1000)
        print(f"Created {len(self.tag_patterns)} search patterns")
    
    def _setup_signal_handlers(self):
        """Install signal handlers for graceful pause."""
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)
    
    def _restore_signal_handlers(self):
        """Restore original signal handlers."""
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)
    
    def _handle_interrupt(self, signum, frame):
        """Handle interrupt signals for graceful pause."""
        print("\n\n" + "=" * 60)
        print("â¸ï¸  PAUSE REQUESTED - Finishing current batch...")
        print("=" * 60)
        self._pause_requested = True
    
    def _chunk_patterns(self, escaped_tags: List[str], chunk_size: int) -> List[re.Pattern]:
        """Split tags into chunks to avoid regex size limits."""
        patterns = []
        for i in range(0, len(escaped_tags), chunk_size):
            chunk = escaped_tags[i:i + chunk_size]
            pattern = re.compile('|'.join(chunk), re.IGNORECASE)
            patterns.append(pattern)
        return patterns
    
    def discover_pdfs(self) -> List[Path]:
        """Find all PDF files in the root directory."""
        print(f"\nScanning for PDFs in: {self.pdf_root}")
        pdfs = list(self.pdf_root.rglob("*.pdf"))
        print(f"Found {len(pdfs)} PDF files")
        return pdfs
    
    def filter_by_keyword(self, pdf_paths: List[Path], keyword: str) -> Tuple[List[Path], List[Path]]:
        """
        Filter PDFs by keyword in their document description from metadata.
        
        Returns:
            Tuple of (matching_pdfs, non_matching_pdfs)
        """
        keyword_lower = keyword.lower()
        matching = []
        non_matching = []
        
        for pdf_path in pdf_paths:
            filename = pdf_path.name.lower()
            metadata = self.drawing_metadata.get(filename, {})
            description = metadata.get('document_description', '') or ''
            
            if keyword_lower in description.lower():
                matching.append(pdf_path)
            else:
                non_matching.append(pdf_path)
        
        return matching, non_matching
    
    def get_documents_by_keyword(self, keyword: str) -> List[Dict]:
        """
        Get all documents from metadata that match a keyword in their description.
        Useful for previewing what will be indexed.
        """
        keyword_lower = keyword.lower()
        matches = []
        
        for filename, metadata in self.drawing_metadata.items():
            description = metadata.get('document_description', '') or ''
            if keyword_lower in description.lower():
                matches.append(metadata)
        
        return matches
    
    def check_pdf_searchable(self, pdf_path: Path) -> Tuple[bool, int, str]:
        """Check if a PDF has extractable text."""
        try:
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            
            text_found = False
            sample_text = ""
            
            for page_num in range(min(3, page_count)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_found = True
                    sample_text = text[:200]
                    break
            
            doc.close()
            return text_found, page_count, sample_text
            
        except Exception as e:
            print(f"Error checking PDF {pdf_path}: {e}")
            return False, 0, ""
    
    def extract_text_from_pdf(self, pdf_path: Path) -> List[Tuple[int, str]]:
        """Extract text from each page of a PDF."""
        pages = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    pages.append((page_num + 1, text))
            doc.close()
        except Exception as e:
            print(f"Error extracting text from {pdf_path}: {e}")
        return pages
    
    def find_tags_in_text(self, text: str) -> Set[str]:
        """Find all matching tags in a text string."""
        found_tags = set()
        
        words = re.findall(r'[\w\-\.\/]+', text)
        for word in words:
            if word in self.all_tags:
                found_tags.add(word)
            word_upper = word.upper()
            if word_upper in self.all_tags:
                found_tags.add(word_upper)
        
        for pattern in self.tag_patterns:
            matches = pattern.findall(text)
            for match in matches:
                match_upper = match.upper()
                if match_upper in self.all_tags:
                    found_tags.add(match_upper)
                elif match in self.all_tags:
                    found_tags.add(match)
        
        return found_tags
    
    def get_metadata_for_file(self, filename: str) -> Dict:
        """Get metadata for a PDF file by its filename (case-insensitive)."""
        key = filename.lower()
        return self.drawing_metadata.get(key, {})
    
    def index_pdf(self, pdf_path: Path) -> dict:
        """Index a single PDF file (single-threaded, for compatibility)."""
        filename = pdf_path.name
        
        metadata = self.get_metadata_for_file(filename)
        document_description = metadata.get('document_description')
        supplier_code = metadata.get('supplier_code')
        supplier_name = metadata.get('supplier_name')
        
        if metadata.get('relative_path_unix'):
            relative_path = metadata['relative_path_unix']
        else:
            try:
                relative_path = str(pdf_path.resolve().relative_to(self.pdf_root))
            except ValueError:
                relative_path = str(pdf_path.resolve())
        
        result = {
            'path': relative_path,
            'filename': filename,
            'drawing_number': supplier_code,
            'supplier_code': supplier_code,
            'supplier_name': supplier_name,
            'document_description': document_description,
            'searchable': False,
            'page_count': 0,
            'tags_found': 0,
            'cables_found': 0,
            'equipment_found': 0,
            'error': None
        }
        
        try:
            is_searchable, page_count, _ = self.check_pdf_searchable(pdf_path)
            result['searchable'] = is_searchable
            result['page_count'] = page_count
            
            file_size = pdf_path.stat().st_size
            pdf_id = self.db.add_pdf(
                filename=filename,
                relative_path=relative_path,
                file_size_bytes=file_size,
                page_count=page_count,
                is_searchable=is_searchable,
                document_description=document_description,
                drawing_number=supplier_code,
                supplier_code=supplier_code,
                supplier_name=supplier_name
            )
            
            self.db.delete_occurrences_for_pdf(pdf_id)
            
            if not is_searchable:
                return result
            
            pages = self.extract_text_from_pdf(pdf_path)
            all_found_tags = {}
            
            for page_num, text in pages:
                tags = self.find_tags_in_text(text)
                for tag in tags:
                    if tag not in all_found_tags:
                        all_found_tags[tag] = set()
                    all_found_tags[tag].add(page_num)
            
            occurrences = []
            for tag, page_numbers in all_found_tags.items():
                tag_id = self.tag_id_map.get(tag)
                if tag_id:
                    for page_num in page_numbers:
                        occurrences.append((tag_id, pdf_id, page_num, 1.0))
                    
                    if tag in self.cable_tags:
                        result['cables_found'] += 1
                    else:
                        result['equipment_found'] += 1
            
            if occurrences:
                self.db.add_occurrences_bulk(occurrences)
            
            result['tags_found'] = len(all_found_tags)
            
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def _write_result_to_db(self, result: dict) -> int:
        """
        Write a worker result to the database.
        Returns the pdf_id.
        """
        pdf_id = self.db.add_pdf(
            filename=result['filename'],
            relative_path=result['path'],
            file_size_bytes=result['file_size'],
            page_count=result['page_count'],
            is_searchable=result['searchable'],
            document_description=result['document_description'],
            drawing_number=result['drawing_number'],
            supplier_code=result.get('supplier_code'),
            supplier_name=result.get('supplier_name')
        )
        
        # Delete existing occurrences (for re-indexing)
        self.db.delete_occurrences_for_pdf(pdf_id)
        
        # Add new occurrences
        if result['occurrences']:
            occurrences = [(tag_id, pdf_id, page_num, 1.0) 
                          for tag_id, page_num in result['occurrences']]
            self.db.add_occurrences_bulk(occurrences)
        
        return pdf_id
    
    def index_all(self, max_workers: int = None, limit: int = None, 
                  keyword: str = None, keyword_only: bool = False,
                  resume: bool = False) -> dict:
        """
        Index all PDFs in the root directory using multicore processing.
        
        Args:
            max_workers: Number of worker processes (default: CPU count)
            limit: Limit number of PDFs to process
            keyword: Filter/prioritize documents by description keyword
            keyword_only: If True, only index documents matching keyword
            resume: If True, resume from saved state
        """
        # Default to CPU count if not specified
        if max_workers is None:
            max_workers = multiprocessing.cpu_count()
        
        state = None
        
        if resume and os.path.exists(self.state_file):
            state = IndexingState.load(self.state_file)
            if state and not state.is_complete:
                print(f"\nðŸ“‚ Resuming from saved state...")
                print(f"   Started: {state.started_at}")
                print(f"   Progress: {state.processed_count}/{state.total_documents}")
                print(f"   Pending: {len(state.pending_files)} files")
                if state.keyword_filter:
                    print(f"   Keyword filter: '{state.keyword_filter}'")
                
                pdfs = [Path(p) for p in state.pending_files]
            else:
                print("Previous indexing was complete. Starting fresh.")
                state = None
        
        if state is None:
            pdfs = self.discover_pdfs()
            
            if keyword:
                matching, non_matching = self.filter_by_keyword(pdfs, keyword)
                print(f"\nðŸ” Keyword filter: '{keyword}'")
                print(f"   Matching documents: {len(matching)}")
                print(f"   Non-matching documents: {len(non_matching)}")
                
                if keyword_only:
                    pdfs = matching
                    print(f"   Mode: Keyword-only (processing {len(matching)} files)")
                else:
                    pdfs = matching + non_matching
                    print(f"   Mode: Priority (matching documents first)")
            
            if limit:
                pdfs = pdfs[:limit]
                print(f"Limited to first {limit} PDFs")
            
            state = IndexingState(
                total_documents=len(pdfs),
                pending_files=[str(p) for p in pdfs],
                keyword_filter=keyword,
                started_at=datetime.now().isoformat()
            )
        
        stats = {
            'total_pdfs': state.total_documents,
            'searchable_pdfs': state.searchable_pdfs,
            'non_searchable_pdfs': state.non_searchable_pdfs,
            'total_tags_found': state.total_tags_found,
            'total_cables_found': state.total_cables_found,
            'total_equipment_found': state.total_equipment_found,
            'errors': state.errors
        }
        
        if not state.pending_files:
            print("No files to process.")
            return stats
        
        # Choose processing mode
        if max_workers == 1:
            return self._index_sequential(state, stats)
        else:
            return self._index_parallel(state, stats, max_workers)
    
    def _index_sequential(self, state: IndexingState, stats: dict) -> dict:
        """Sequential indexing (original behavior)."""
        self._setup_signal_handlers()
        
        print(f"\nIndexing {len(state.pending_files)} PDFs (sequential mode)...")
        print("-" * 60)
        
        pdfs_to_process = [Path(p) for p in state.pending_files]
        total = state.total_documents
        
        try:
            for i, pdf_path in enumerate(pdfs_to_process, state.processed_count + 1):
                if self._pause_requested:
                    state.pending_files = [str(p) for p in pdfs_to_process[i - state.processed_count - 1:]]
                    state.save(self.state_file)
                    
                    print(f"\nâœ… State saved to: {self.state_file}")
                    print(f"   Processed: {state.processed_count}/{total}")
                    print(f"   Remaining: {len(state.pending_files)}")
                    print("\nTo resume, run with --resume flag")
                    
                    return stats
                
                result = self.index_pdf(pdf_path)
                state.processed_count += 1
                
                self._update_stats_from_result(result, state, stats, pdf_path)
                self._print_result(result, i, total)
                
                if state.pending_files:
                    state.pending_files.pop(0)
                
                if i % 50 == 0:
                    state.save(self.state_file)
        finally:
            self._restore_signal_handlers()
        
        state.is_complete = True
        state.pending_files = []
        state.save(self.state_file)
        
        return stats
    
    def _index_parallel(self, state: IndexingState, stats: dict, max_workers: int) -> dict:
        """Parallel indexing using multiple processes."""
        self._setup_signal_handlers()
        
        print(f"\nIndexing {len(state.pending_files)} PDFs ({max_workers} workers)...")
        print("-" * 60)
        
        pdfs_to_process = list(state.pending_files)  # Keep as strings for workers
        total = state.total_documents
        batch_size = max_workers * 4  # Process in batches for better pause handling
        
        # Prepare initializer arguments
        init_args = (
            self.all_tags,
            self.cable_tags,
            self.equipment_tags,
            self.tag_id_map,
            self.drawing_metadata,
            str(self.pdf_root)
        )
        
        try:
            with ProcessPoolExecutor(max_workers=max_workers, 
                                    initializer=_worker_init,
                                    initargs=init_args) as executor:
                
                while pdfs_to_process and not self._pause_requested:
                    # Take a batch
                    batch = pdfs_to_process[:batch_size]
                    
                    # Submit batch
                    future_to_path = {
                        executor.submit(_process_pdf_worker, pdf_path): pdf_path 
                        for pdf_path in batch
                    }
                    
                    # Process results as they complete
                    completed_in_batch = 0
                    for future in as_completed(future_to_path):
                        if self._pause_requested:
                            # Cancel remaining futures
                            for f in future_to_path:
                                f.cancel()
                            break
                        
                        pdf_path = future_to_path[future]
                        
                        try:
                            result = future.result()
                            
                            # Write to database (single-threaded)
                            if not result['error']:
                                self._write_result_to_db(result)
                            
                            state.processed_count += 1
                            completed_in_batch += 1
                            
                            self._update_stats_from_result(result, state, stats, Path(pdf_path))
                            self._print_result(result, state.processed_count, total)
                            
                            # Remove from pending
                            if pdf_path in pdfs_to_process:
                                pdfs_to_process.remove(pdf_path)
                            
                        except Exception as e:
                            state.processed_count += 1
                            stats['errors'] += 1
                            state.errors += 1
                            state.failed_files.append(pdf_path)
                            print(f"[{state.processed_count}/{total}] ERROR: {Path(pdf_path).name} - {e}")
                            
                            if pdf_path in pdfs_to_process:
                                pdfs_to_process.remove(pdf_path)
                    
                    # Save state periodically
                    if state.processed_count % 50 == 0:
                        state.pending_files = pdfs_to_process
                        state.save(self.state_file)
                
                if self._pause_requested:
                    state.pending_files = pdfs_to_process
                    state.save(self.state_file)
                    
                    print(f"\nâœ… State saved to: {self.state_file}")
                    print(f"   Processed: {state.processed_count}/{total}")
                    print(f"   Remaining: {len(pdfs_to_process)}")
                    print("\nTo resume, run with --resume flag")
                    
                    return stats
        
        except KeyboardInterrupt:
            # Handle case where Ctrl+C happens during executor shutdown
            state.pending_files = pdfs_to_process
            state.save(self.state_file)
            print(f"\nâœ… State saved after interrupt")
            return stats
        
        finally:
            self._restore_signal_handlers()
        
        state.is_complete = True
        state.pending_files = []
        state.save(self.state_file)
        
        return stats
    
    def _update_stats_from_result(self, result: dict, state: IndexingState, 
                                   stats: dict, pdf_path: Path):
        """Update stats and state from a processing result."""
        if result.get('error'):
            stats['errors'] += 1
            state.errors += 1
            state.failed_files.append(str(pdf_path))
        elif result['searchable']:
            stats['searchable_pdfs'] += 1
            state.searchable_pdfs += 1
            stats['total_tags_found'] += result['tags_found']
            state.total_tags_found += result['tags_found']
            stats['total_cables_found'] += result['cables_found']
            state.total_cables_found += result['cables_found']
            stats['total_equipment_found'] += result['equipment_found']
            state.total_equipment_found += result['equipment_found']
            state.successful_files.append(str(pdf_path))
        else:
            stats['non_searchable_pdfs'] += 1
            state.non_searchable_pdfs += 1
            state.successful_files.append(str(pdf_path))
    
    def _print_result(self, result: dict, current: int, total: int):
        """Print processing result."""
        if result.get('error'):
            print(f"[{current}/{total}] ERROR: {result['filename']} - {result['error']}")
        elif result['searchable']:
            if result['tags_found'] > 0:
                print(f"[{current}/{total}] {result['filename']}: "
                      f"{result['cables_found']} cables, {result['equipment_found']} equipment")
            else:
                print(f"[{current}/{total}] {result['filename']}: No tags found (searchable)")
        else:
            print(f"[{current}/{total}] {result['filename']}: Not searchable (needs OCR)")


def index_single_file(pdf_path: str, pdf_root: str, db: ShipCableDB) -> dict:
    """Index a single PDF file."""
    pdf_path = Path(pdf_path).resolve()
    pdf_root = Path(pdf_root).resolve()
    
    if not pdf_path.exists():
        return {'error': f"File not found: {pdf_path}"}
    
    if not pdf_path.suffix.lower() == '.pdf':
        return {'error': f"Not a PDF file: {pdf_path}"}
    
    indexer = PDFIndexer(db, str(pdf_root))
    result = indexer.index_pdf(pdf_path)
    
    return result


def print_single_result(result: dict, db: ShipCableDB):
    """Pretty print the result of indexing a single file."""
    print("\n" + "=" * 60)
    print("Single File Indexing Result")
    print("=" * 60)
    
    if result.get('error'):
        print(f"ERROR: {result['error']}")
        return
    
    print(f"File:        {result['filename']}")
    print(f"Path:        {result['path']}")
    print(f"Searchable:  {'Yes' if result['searchable'] else 'No (needs OCR)'}")
    print(f"Pages:       {result['page_count']}")
    
    if result['searchable']:
        print(f"\nTags Found:  {result['tags_found']}")
        print(f"  - Cables:     {result['cables_found']}")
        print(f"  - Equipment:  {result['equipment_found']}")
        
        if result['tags_found'] > 0:
            print("\n" + "-" * 60)
            print("Tags found in this PDF:")
            print("-" * 60)
            
            contents = db.get_pdf_contents(result['path'])
            
            cables = [c for c in contents if c['tag_type'] == 'cable']
            equipment = [c for c in contents if c['tag_type'] == 'equipment']
            
            if cables:
                print(f"\nCables ({len(cables)}):")
                for c in cables[:30]:
                    page = f" (page {c['page_number']})" if c['page_number'] else ""
                    print(f"  â€¢ {c['tag_name']}{page}")
                if len(cables) > 30:
                    print(f"  ... and {len(cables) - 30} more")
            
            if equipment:
                print(f"\nEquipment ({len(equipment)}):")
                for e in equipment[:30]:
                    page = f" (page {e['page_number']})" if e['page_number'] else ""
                    desc = f" - {e['description']}" if e['description'] else ""
                    print(f"  â€¢ {e['tag_name']}{page}{desc}")
                if len(equipment) > 30:
                    print(f"  ... and {len(equipment) - 30} more")
    else:
        print("\nThis PDF contains non-selectable text (scanned/image-based).")
        print("It will need OCR processing to extract tags.")


def preview_keyword_matches(metadata_path: str, keyword: str):
    """Preview documents that match a keyword filter."""
    print(f"\nðŸ” Previewing documents with '{keyword}' in description...")
    print("-" * 60)
    
    metadata = load_drawing_metadata(metadata_path)
    if not metadata:
        print("Error: Could not load metadata. Run import_drawing_metadata.py first.")
        return
    
    keyword_lower = keyword.lower()
    matches = []
    
    for filename, info in metadata.items():
        description = info.get('document_description', '') or ''
        if keyword_lower in description.lower():
            matches.append(info)
    
    print(f"Found {len(matches)} documents matching '{keyword}':\n")
    
    by_category = {}
    for m in matches:
        cat = m.get('supergrandparent', 'Unknown')
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(m)
    
    for category, docs in sorted(by_category.items()):
        print(f"\n{category} ({len(docs)} documents):")
        for doc in docs[:5]:
            print(f"  â€¢ {doc['filename']}: {doc.get('document_description', 'N/A')}")
        if len(docs) > 5:
            print(f"  ... and {len(docs) - 5} more")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ship Cable Database - PDF Indexer with Multicore Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Index all PDFs using all CPU cores:
    python index_pdfs.py --dir /path/to/pdf/drawings

  Index using 4 workers:
    python index_pdfs.py --dir /path/to/pdfs --workers 4

  Index sequentially (single core):
    python index_pdfs.py --dir /path/to/pdfs --workers 1

  Index only documents with "diagram" in description:
    python index_pdfs.py --dir /path/to/pdfs --keyword diagram --keyword-only

  Prioritize "diagram" documents (process them first):
    python index_pdfs.py --dir /path/to/pdfs --keyword diagram

  Resume interrupted indexing:
    python index_pdfs.py --dir /path/to/pdfs --resume

  Preview which documents match a keyword:
    python index_pdfs.py --preview-keyword diagram --metadata drawing_metadata.pkl

  Index with a limit (for testing):
    python index_pdfs.py --dir /path/to/pdfs --limit 50

Pause/Resume:
  Press Ctrl+C during indexing to pause. The state is saved to
  indexing_state.json and can be resumed with --resume.

Performance:
  Multicore processing can significantly speed up indexing.
  Default is to use all available CPU cores.
  Use --workers 1 for sequential processing (original behavior).
        """
    )
    
    parser.add_argument('--file', '-f', type=str, 
                        help='Path to a single PDF file to index (for testing)')
    parser.add_argument('--dir', '-d', type=str,
                        help='Directory containing PDF files to index')
    parser.add_argument('--root', '-r', type=str,
                        help='Root directory for relative paths (used with --file)')
    parser.add_argument('--db', type=str, default='ship_cables.db',
                        help='Path to SQLite database (default: ship_cables.db)')
    parser.add_argument('--metadata', '-m', type=str, default='drawing_metadata.pkl',
                        help='Path to metadata pickle file (default: drawing_metadata.pkl)')
    parser.add_argument('--limit', '-l', type=int,
                        help='Limit number of PDFs to process (for testing)')
    
    # Multicore options
    parser.add_argument('--workers', '-w', type=int, default=None,
                        help=f'Number of worker processes (default: {multiprocessing.cpu_count()} = all CPUs)')
    
    # Keyword filtering options
    parser.add_argument('--keyword', '-k', type=str,
                        help='Filter/prioritize documents by description keyword (e.g., "diagram")')
    parser.add_argument('--keyword-only', action='store_true',
                        help='Only index documents matching the keyword')
    parser.add_argument('--preview-keyword', type=str,
                        help='Preview documents matching a keyword (no indexing)')
    
    # Pause/Resume options
    parser.add_argument('--resume', action='store_true',
                        help='Resume from saved state')
    parser.add_argument('--state-file', type=str, default='indexing_state.json',
                        help='Path to state file for pause/resume')
    parser.add_argument('--clear-state', action='store_true',
                        help='Clear saved state and start fresh')
    
    # Legacy positional arguments for backwards compatibility
    parser.add_argument('legacy_dir', nargs='?', help=argparse.SUPPRESS)
    parser.add_argument('legacy_db', nargs='?', help=argparse.SUPPRESS)
    parser.add_argument('legacy_limit', nargs='?', type=int, help=argparse.SUPPRESS)
    
    args = parser.parse_args()
    
    # Handle legacy positional arguments
    if args.legacy_dir and not args.dir and not args.file:
        args.dir = args.legacy_dir
    if args.legacy_db:
        args.db = args.legacy_db
    if args.legacy_limit:
        args.limit = args.legacy_limit
    
    # Preview mode
    if args.preview_keyword:
        preview_keyword_matches(args.metadata, args.preview_keyword)
        return
    
    # Clear state if requested
    if args.clear_state and os.path.exists(args.state_file):
        os.remove(args.state_file)
        print(f"Cleared saved state: {args.state_file}")
    
    # Validate arguments
    if not args.file and not args.dir:
        parser.print_help()
        print("\nError: Either --file or --dir is required")
        sys.exit(1)
    
    if args.file and args.dir:
        print("Error: Cannot use both --file and --dir. Choose one.")
        sys.exit(1)
    
    # Check database exists
    if not os.path.exists(args.db):
        print(f"Error: Database not found: {args.db}")
        print("Please run import_cable_list.py first to create the database.")
        sys.exit(1)
    
    db = ShipCableDB(args.db)
    
    # Single file mode
    if args.file:
        if not os.path.exists(args.file):
            print(f"Error: File not found: {args.file}")
            sys.exit(1)
        
        pdf_root = args.root if args.root else str(Path(args.file).parent)
        
        print("=" * 60)
        print("Ship Cable Database - Single File Indexer")
        print("=" * 60)
        print(f"File: {args.file}")
        print(f"Root: {pdf_root}")
        print(f"Database: {args.db}")
        
        result = index_single_file(args.file, pdf_root, db)
        print_single_result(result, db)
        
    # Directory mode
    else:
        if not os.path.exists(args.dir):
            print(f"Error: Directory not found: {args.dir}")
            sys.exit(1)
        
        # Determine worker count
        worker_count = args.workers if args.workers else multiprocessing.cpu_count()
        
        print("=" * 60)
        print("Ship Cable Database - PDF Indexer")
        print("=" * 60)
        print(f"PDF Directory: {args.dir}")
        print(f"Database: {args.db}")
        print(f"Metadata: {args.metadata}")
        print(f"Workers: {worker_count}" + (" (sequential)" if worker_count == 1 else " (parallel)"))
        if args.keyword:
            mode = "keyword-only" if args.keyword_only else "priority"
            print(f"Keyword filter: '{args.keyword}' ({mode})")
        if args.limit:
            print(f"Limit: {args.limit} PDFs")
        if args.resume:
            print("Mode: Resume from saved state")
        
        print("\nðŸ’¡ Tip: Press Ctrl+C to pause and save progress")
        
        indexer = PDFIndexer(db, args.dir, metadata_path=args.metadata,
                            state_file=args.state_file)
        
        stats = indexer.index_all(
            max_workers=worker_count,
            limit=args.limit,
            keyword=args.keyword,
            keyword_only=args.keyword_only,
            resume=args.resume
        )
        
        print("\n" + "=" * 60)
        print("Indexing Complete!")
        print("=" * 60)
        print(f"Total PDFs processed:    {stats['total_pdfs']}")
        print(f"Searchable PDFs:         {stats['searchable_pdfs']}")
        print(f"Non-searchable PDFs:     {stats['non_searchable_pdfs']} (need OCR)")
        print(f"Errors:                  {stats['errors']}")
        print(f"Total tags found:        {stats['total_tags_found']}")
        print(f"  - Cables:              {stats['total_cables_found']}")
        print(f"  - Equipment:           {stats['total_equipment_found']}")
    
    # Show final database stats
    print("\n" + "-" * 60)
    print("Database Statistics:")
    db_stats = db.get_stats()
    for key, value in db_stats.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
