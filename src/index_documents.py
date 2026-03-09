"""
Document Indexer for Equipment Explorer

Scans documents registered in the database (to_be_indexed = 1) for cable and
equipment tags, records occurrences, then marks each document as indexed.

Features:
- Multicore processing: Use --workers N for parallel PDF processing
- Pause/Resume: Press Ctrl+C to pause, state is saved to JSON file

Document metadata (description, supplier) comes from the database — no pickle
files or directory scanning required.
"""

import os
import sys
import re
import json
import signal
import multiprocessing
from pathlib import Path
from datetime import datetime
from typing import Set, List, Tuple, Optional, Dict
from dataclasses import dataclass, field, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    pending_files: List[str] = field(default_factory=list)  # relative_path values
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
        # Drop unknown keys for forward-compat
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

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


# =============================================================================
# WORKER FUNCTIONS FOR MULTIPROCESSING
# =============================================================================

_worker_all_tags: Set[str] = set()
_worker_cable_tags: Set[str] = set()
_worker_equipment_tags: Set[str] = set()
_worker_tag_id_map: Dict[str, int] = {}
_worker_tag_patterns: List[re.Pattern] = []
_worker_pdf_root: str = ""


def _worker_init(all_tags: Set[str], cable_tags: Set[str], equipment_tags: Set[str],
                 tag_id_map: Dict[str, int], pdf_root: str):
    """Initialize worker process with shared data."""
    global _worker_all_tags, _worker_cable_tags, _worker_equipment_tags
    global _worker_tag_id_map, _worker_tag_patterns, _worker_pdf_root

    _worker_all_tags = all_tags
    _worker_cable_tags = cable_tags
    _worker_equipment_tags = equipment_tags
    _worker_tag_id_map = tag_id_map
    _worker_pdf_root = pdf_root

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

    words = re.findall(r'[\w\-\.\/]+', text)
    for word in words:
        if word in _worker_all_tags:
            found_tags.add(word)
        word_upper = word.upper()
        if word_upper in _worker_all_tags:
            found_tags.add(word_upper)

    for pattern in _worker_tag_patterns:
        matches = pattern.findall(text)
        for match in matches:
            match_upper = match.upper()
            if match_upper in _worker_all_tags:
                found_tags.add(match_upper)
            elif match in _worker_all_tags:
                found_tags.add(match)

    return found_tags


def _process_pdf_worker(item: tuple) -> dict:
    """
    Worker function to process a single document.
    item = (pdf_id, relative_path, filename, document_description, supplier_code, supplier_name)
    Returns extracted data without database writes.
    """
    pdf_id, relative_path, filename, document_description, supplier_code, supplier_name = item
    abs_path = Path(_worker_pdf_root) / relative_path

    result = {
        'pdf_id': pdf_id,
        'path': relative_path,
        'filename': filename,
        'supplier_code': supplier_code,
        'supplier_name': supplier_name,
        'document_description': document_description,
        'searchable': False,
        'page_count': 0,
        'file_size': 0,
        'tags_found': 0,
        'cables_found': 0,
        'equipment_found': 0,
        'equipment_occurrences': [],
        'cable_occurrences': [],
        'error': None,
    }

    try:
        import pymupdf
        result['file_size'] = abs_path.stat().st_size

        doc = pymupdf.open(abs_path)
        page_count = len(doc)
        result['page_count'] = page_count

        text_found = False
        for page_num in range(min(3, page_count)):
            page = doc[page_num]
            if page.get_text().strip():
                text_found = True
                break

        result['searchable'] = text_found

        if not text_found:
            doc.close()
            return result

        all_found_tags: Dict[str, Set[int]] = {}
        for page_num in range(page_count):
            page = doc[page_num]
            text = page.get_text()
            if not text.strip():
                continue
            for tag in _find_tags_in_text(text):
                all_found_tags.setdefault(tag, set()).add(page_num + 1)

        doc.close()

        equipment_occurrences = []
        cable_occurrences = []
        cables_found = 0
        equipment_found = 0

        for tag, page_numbers in all_found_tags.items():
            tag_id = _worker_tag_id_map.get(tag)
            if tag_id:
                if tag in _worker_cable_tags:
                    for pn in page_numbers:
                        cable_occurrences.append((tag_id, pn))
                    cables_found += 1
                else:
                    for pn in page_numbers:
                        equipment_occurrences.append((tag_id, pn))
                    equipment_found += 1

        result['equipment_occurrences'] = equipment_occurrences
        result['cable_occurrences'] = cable_occurrences
        result['tags_found'] = len(all_found_tags)
        result['cables_found'] = cables_found
        result['equipment_found'] = equipment_found

    except Exception as e:
        result['error'] = str(e)

    return result


# =============================================================================
# INDEXER CLASS
# =============================================================================

class DocumentIndexer:
    """Indexes documents for cable and equipment tags with pause/resume support."""

    STATE_FILE = "indexing_state.json"

    def __init__(self, db: ShipCableDB, pdf_root: str, state_file: str = None):
        self.db = db
        self.pdf_root = Path(pdf_root).resolve()
        self.state_file = state_file or self.STATE_FILE

        self._pause_requested = False
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)

        print("Loading tags from database...")
        self.cable_tags = db.get_cable_tags_set()
        self.equipment_tags = db.get_equipment_tags_set()
        self.all_tags = self.cable_tags | self.equipment_tags

        print(f"Loaded {len(self.cable_tags)} cable tags")
        print(f"Loaded {len(self.equipment_tags)} equipment tags")

        self.tag_id_map: Dict[str, int] = {}
        for eq in self.db.get_all_equipment():
            self.tag_id_map[eq['tag']] = eq['equipment_id']
        for cab in self.db.get_all_cables():
            self.tag_id_map[cab['tag']] = cab['cable_id']

        escaped_tags = [re.escape(t) for t in sorted(self.all_tags, key=len, reverse=True)]
        self.tag_patterns = _chunk_patterns(escaped_tags, chunk_size=1000)
        print(f"Created {len(self.tag_patterns)} search patterns")

    # -------------------------------------------------------------------------
    # Signal handling
    # -------------------------------------------------------------------------

    def _setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._handle_interrupt)
        signal.signal(signal.SIGTERM, self._handle_interrupt)

    def _restore_signal_handlers(self):
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handle_interrupt(self, signum, frame):
        print("\n\n" + "=" * 60)
        print("PAUSE REQUESTED - Finishing current batch...")
        print("=" * 60)
        self._pause_requested = True

    # -------------------------------------------------------------------------
    # DB helpers
    # -------------------------------------------------------------------------

    def _get_documents_to_index(self) -> List[Dict]:
        """Query DB for documents where to_be_indexed = 1."""
        return self.db.get_unprocessed_pdfs()

    def _write_result_to_db(self, result: dict) -> None:
        """Write worker result to the database."""
        pdf_id = result['pdf_id']
        self.db.delete_occurrences_for_pdf(pdf_id)
        if result['equipment_occurrences']:
            equip_rows = [(tag_id, pdf_id, pn)
                          for tag_id, pn in result['equipment_occurrences']]
            self.db.add_equipment_occurrences_bulk(equip_rows)
        if result['cable_occurrences']:
            cable_rows = [(tag_id, pdf_id, pn, 1.0)
                          for tag_id, pn in result['cable_occurrences']]
            self.db.add_cable_occurrences_bulk(cable_rows)
        self.db.mark_document_indexed(pdf_id)

    # -------------------------------------------------------------------------
    # Orchestration
    # -------------------------------------------------------------------------

    def _docs_to_items(self, docs: List[Dict]) -> List[tuple]:
        return [
            (d['pdf_id'], d['relative_path'], d['filename'],
             d.get('document_description'), d.get('supplier_code'), d.get('supplier_name'))
            for d in docs
        ]

    def index_all(self, max_workers: int = None, limit: int = None,
                  resume: bool = False) -> dict:
        """
        Index all pending documents using multicore processing.

        Args:
            max_workers: Number of worker processes (default: CPU count)
            limit: Cap the number of documents to process
            resume: If True, resume from saved state
        """
        if max_workers is None:
            max_workers = multiprocessing.cpu_count()

        state = None

        if resume and os.path.exists(self.state_file):
            state = IndexingState.load(self.state_file)
            if state and not state.is_complete:
                print(f"\nResuming from saved state...")
                print(f"   Started: {state.started_at}")
                print(f"   Progress: {state.processed_count}/{state.total_documents}")
                print(f"   Pending: {len(state.pending_files)} files")

                pending_set = set(state.pending_files)
                all_docs = self._get_documents_to_index()
                docs = [d for d in all_docs if d['relative_path'] in pending_set]
                print(f"   Matched {len(docs)} documents still in DB queue")
            else:
                print("Previous indexing was complete. Starting fresh.")
                state = None

        if state is None:
            docs = self._get_documents_to_index()
            print(f"\nFound {len(docs)} document(s) with to_be_indexed = 1")

            if limit:
                docs = docs[:limit]
                print(f"Limited to first {limit} documents")

            state = IndexingState(
                total_documents=len(docs),
                pending_files=[d['relative_path'] for d in docs],
                started_at=datetime.now().isoformat(),
            )

        stats = {
            'total_pdfs': state.total_documents,
            'searchable_pdfs': state.searchable_pdfs,
            'non_searchable_pdfs': state.non_searchable_pdfs,
            'total_tags_found': state.total_tags_found,
            'total_cables_found': state.total_cables_found,
            'total_equipment_found': state.total_equipment_found,
            'errors': state.errors,
        }

        items = self._docs_to_items(docs)

        if not items:
            print("No documents to process.")
            return stats

        if max_workers == 1:
            return self._index_sequential(items, state, stats)
        else:
            return self._index_parallel(items, state, stats, max_workers)

    # -------------------------------------------------------------------------
    # Sequential mode
    # -------------------------------------------------------------------------

    def _index_sequential(self, items: List[tuple], state: IndexingState,
                          stats: dict) -> dict:
        """Process documents one at a time in the main process."""
        self._setup_signal_handlers()

        # Initialise worker globals in the main process
        _worker_init(self.all_tags, self.cable_tags, self.equipment_tags,
                     self.tag_id_map, str(self.pdf_root))

        total = state.total_documents
        print(f"\nIndexing {len(items)} document(s) (sequential mode)...")
        print("-" * 60)

        try:
            for i, item in enumerate(items, state.processed_count + 1):
                if self._pause_requested:
                    state.pending_files = [it[1] for it in items[i - state.processed_count - 1:]]
                    state.save(self.state_file)
                    print(f"\nState saved to: {self.state_file}")
                    print(f"   Processed: {state.processed_count}/{total}")
                    print(f"   Remaining: {len(state.pending_files)}")
                    print("\nTo resume, run with --resume flag")
                    return stats

                result = _process_pdf_worker(item)
                state.processed_count += 1

                if not result['error']:
                    self._write_result_to_db(result)

                self._update_stats_from_result(result, state, stats)
                self._print_result(result, i, total)

                if i % 50 == 0:
                    state.pending_files = [it[1] for it in items[i - state.processed_count:]]
                    state.save(self.state_file)

        finally:
            self._restore_signal_handlers()

        state.is_complete = True
        state.pending_files = []
        state.save(self.state_file)
        return stats

    # -------------------------------------------------------------------------
    # Parallel mode
    # -------------------------------------------------------------------------

    def _index_parallel(self, items: List[tuple], state: IndexingState,
                        stats: dict, max_workers: int) -> dict:
        """Process documents in parallel using multiple worker processes."""
        self._setup_signal_handlers()

        total = state.total_documents
        batch_size = max_workers * 4
        print(f"\nIndexing {len(items)} document(s) ({max_workers} workers)...")
        print("-" * 60)

        items_remaining = list(items)

        init_args = (
            self.all_tags,
            self.cable_tags,
            self.equipment_tags,
            self.tag_id_map,
            str(self.pdf_root),
        )

        try:
            with ProcessPoolExecutor(max_workers=max_workers,
                                     initializer=_worker_init,
                                     initargs=init_args) as executor:

                while items_remaining and not self._pause_requested:
                    batch = items_remaining[:batch_size]

                    future_to_item = {
                        executor.submit(_process_pdf_worker, item): item
                        for item in batch
                    }

                    for future in as_completed(future_to_item):
                        if self._pause_requested:
                            for f in future_to_item:
                                f.cancel()
                            break

                        item = future_to_item[future]

                        try:
                            result = future.result()

                            if not result['error']:
                                self._write_result_to_db(result)

                            state.processed_count += 1
                            self._update_stats_from_result(result, state, stats)
                            self._print_result(result, state.processed_count, total)

                        except Exception as e:
                            state.processed_count += 1
                            stats['errors'] += 1
                            state.errors += 1
                            state.failed_files.append(item[1])
                            print(f"[{state.processed_count}/{total}] ERROR: {item[2]} - {e}")

                        if item in items_remaining:
                            items_remaining.remove(item)

                    if state.processed_count % 50 == 0:
                        state.pending_files = [it[1] for it in items_remaining]
                        state.save(self.state_file)

                if self._pause_requested:
                    state.pending_files = [it[1] for it in items_remaining]
                    state.save(self.state_file)
                    print(f"\nState saved to: {self.state_file}")
                    print(f"   Processed: {state.processed_count}/{total}")
                    print(f"   Remaining: {len(items_remaining)}")
                    print("\nTo resume, run with --resume flag")
                    return stats

        except KeyboardInterrupt:
            state.pending_files = [it[1] for it in items_remaining]
            state.save(self.state_file)
            print(f"\nState saved after interrupt")
            return stats

        finally:
            self._restore_signal_handlers()

        state.is_complete = True
        state.pending_files = []
        state.save(self.state_file)
        return stats

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _update_stats_from_result(self, result: dict, state: IndexingState,
                                  stats: dict):
        if result.get('error'):
            stats['errors'] += 1
            state.errors += 1
            state.failed_files.append(result['path'])
        elif result['searchable']:
            stats['searchable_pdfs'] += 1
            state.searchable_pdfs += 1
            stats['total_tags_found'] += result['tags_found']
            state.total_tags_found += result['tags_found']
            stats['total_cables_found'] += result['cables_found']
            state.total_cables_found += result['cables_found']
            stats['total_equipment_found'] += result['equipment_found']
            state.total_equipment_found += result['equipment_found']
            state.successful_files.append(result['path'])
        else:
            stats['non_searchable_pdfs'] += 1
            state.non_searchable_pdfs += 1
            state.successful_files.append(result['path'])

    def _print_result(self, result: dict, current: int, total: int):
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


# =============================================================================
# PUBLIC API
# =============================================================================

def run_indexing(
    db_path: str,
    pdf_root: str,
    workers: int = None,
    resume: bool = False,
    limit: int = None,
    state_file: str = "indexing_state.json",
) -> dict:
    """
    Index all documents marked to_be_indexed = 1 in the database.

    Args:
        db_path:    Path to the SQLite database.
        pdf_root:   Root directory where PDFs are stored.
        workers:    Worker process count (default: all CPUs).
        resume:     Resume from a saved state file.
        limit:      Cap the number of documents processed (for testing).
        state_file: Path to the JSON state file for pause/resume.

    Returns:
        dict with keys: total_pdfs, searchable_pdfs, non_searchable_pdfs,
        total_tags_found, total_cables_found, total_equipment_found, errors.
    """
    db = ShipCableDB(db_path)
    indexer = DocumentIndexer(db, pdf_root, state_file=state_file)
    return indexer.index_all(max_workers=workers, limit=limit, resume=resume)


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Equipment Explorer — Document Indexer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Index all pending documents (all CPUs):
    python index_documents.py --pdf-root /path/to/docs

  Use 4 workers:
    python index_documents.py --pdf-root /path/to/docs --workers 4

  Sequential mode:
    python index_documents.py --pdf-root /path/to/docs --workers 1

  Resume interrupted run:
    python index_documents.py --pdf-root /path/to/docs --resume

  Limit for testing:
    python index_documents.py --pdf-root /path/to/docs --limit 10

Pause/Resume:
  Press Ctrl+C during indexing to pause. State is saved to
  indexing_state.json and resumed with --resume.
        """,
    )

    parser.add_argument('--pdf-root', '-r', type=str, required=True,
                        help='Root directory containing the PDF files')
    parser.add_argument('--db', type=str, default='data/equipment_explorer.db',
                        help='Path to SQLite database (default: data/equipment_explorer.db)')
    parser.add_argument('--workers', '-w', type=int, default=None,
                        help=f'Number of worker processes (default: {multiprocessing.cpu_count()} = all CPUs)')
    parser.add_argument('--limit', '-l', type=int,
                        help='Limit number of documents to process (for testing)')
    parser.add_argument('--resume', action='store_true',
                        help='Resume from saved state')
    parser.add_argument('--state-file', type=str, default='indexing_state.json',
                        help='Path to state file for pause/resume (default: indexing_state.json)')
    parser.add_argument('--clear-state', action='store_true',
                        help='Clear saved state and start fresh')

    args = parser.parse_args()

    if args.clear_state and os.path.exists(args.state_file):
        os.remove(args.state_file)
        print(f"Cleared saved state: {args.state_file}")

    if not os.path.exists(args.db):
        print(f"Error: Database not found: {args.db}")
        sys.exit(1)

    if not os.path.isdir(args.pdf_root):
        print(f"Error: PDF root directory not found: {args.pdf_root}")
        sys.exit(1)

    worker_count = args.workers if args.workers else multiprocessing.cpu_count()

    print("=" * 60)
    print("Equipment Explorer — Document Indexer")
    print("=" * 60)
    print(f"PDF Root:  {args.pdf_root}")
    print(f"Database:  {args.db}")
    print(f"Workers:   {worker_count}" + (" (sequential)" if worker_count == 1 else " (parallel)"))
    if args.limit:
        print(f"Limit:     {args.limit} documents")
    if args.resume:
        print("Mode:      Resume from saved state")
    print("\nTip: Press Ctrl+C to pause and save progress")

    stats = run_indexing(
        db_path=args.db,
        pdf_root=args.pdf_root,
        workers=worker_count,
        resume=args.resume,
        limit=args.limit,
        state_file=args.state_file,
    )

    print("\n" + "=" * 60)
    print("Indexing Complete!")
    print("=" * 60)
    print(f"Total documents processed: {stats['total_pdfs']}")
    print(f"Searchable PDFs:           {stats['searchable_pdfs']}")
    print(f"Non-searchable PDFs:       {stats['non_searchable_pdfs']} (need OCR)")
    print(f"Errors:                    {stats['errors']}")
    print(f"Total tags found:          {stats['total_tags_found']}")
    print(f"  - Cables:                {stats['total_cables_found']}")
    print(f"  - Equipment:             {stats['total_equipment_found']}")


if __name__ == "__main__":
    main()
