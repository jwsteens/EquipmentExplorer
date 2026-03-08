import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        h.update(f.read(8192))
        f.seek(-min(8192, path.stat().st_size), 2)
        h.update(f.read(8192))
    return h.hexdigest()


def import_documents(conn: sqlite3.Connection, documents_dir: str) -> None:
    """Scan a documents directory and register PDFs in the database."""

    documents_dir = documents_dir.replace("\\", "/")
    root = Path(documents_dir)

    if not root.is_dir():
        click.echo(f"  Directory not found: {documents_dir}")
        return

    # ── Scan ─────────────────────────────────────────────────────────────────
    click.echo(f"  Scanning {root} for PDF files…")
    pdf_files = [p for p in root.rglob("*") if p.suffix.lower() == ".pdf"]

    if not pdf_files:
        click.echo("  No PDF files found.")
        return

    click.echo(f"  Found {len(pdf_files)} PDF file(s).")

    # ── Build records ─────────────────────────────────────────────────────────
    records = []
    for p in pdf_files:
        stat = p.stat()
        relative_path = p.relative_to(root).as_posix()
        records.append({
            "filename":        p.name,
            "relative_path":   relative_path,
            "file_size_bytes": stat.st_size,
            "content_hash":    _md5(p),
            "date_modified":   datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds"),
        })

    # ── Preview ───────────────────────────────────────────────────────────────
    click.echo("\nFirst 5 files:")
    table = Table(show_header=True, header_style="bold", show_lines=True)
    for col in ("filename", "relative_path", "file_size_bytes", "content_hash", "date_modified"):
        table.add_column(col, overflow="fold")
    for r in records[:5]:
        table.add_row(r["filename"], r["relative_path"], str(r["file_size_bytes"]),
                      r["content_hash"], r["date_modified"])
    Console().print(table)

    if not click.confirm(f"\nImport all {len(records)} file(s) into the database?", default=True):
        click.echo("  Import cancelled.")
        return

    # ── Sync: find stale DB rows not present in the scanned directory ─────────
    incoming_paths = {r["relative_path"] for r in records}
    db_rows = conn.execute("SELECT relative_path FROM documents").fetchall()
    stale = [r["relative_path"] for r in db_rows if r["relative_path"] not in incoming_paths]

    delete_paths: list[str] = []
    if stale:
        click.echo(f"\n{len(stale)} document(s) in the database were not found in the scanned directory:")
        for p in stale:
            click.echo(f"  - {p}")
        click.echo("  Warning: deleting these will also remove all their indexed occurrences"
                   " (cable_occurrences, equipment_occurrences).")
        if click.confirm("Delete these from the database?", default=False):
            delete_paths = stale

    # ── Insert (+ optional delete) in one transaction ─────────────────────────
    existing_before = conn.execute("SELECT count(*) FROM documents").fetchone()[0]

    with conn:
        if delete_paths:
            ph = ",".join("?" * len(delete_paths))
            conn.execute(
                f"DELETE FROM documents WHERE relative_path IN ({ph})", delete_paths
            )

        conn.executemany(
            """INSERT OR IGNORE INTO documents
               (filename, relative_path, file_size_bytes, content_hash, date_modified)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (r["filename"], r["relative_path"], r["file_size_bytes"],
                 r["content_hash"], r["date_modified"])
                for r in records
            ],
        )

    existing_after = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
    added   = existing_after - (existing_before - len(delete_paths))
    skipped = len(records) - added

    click.echo(f"\nImport complete: {added} file(s) added, {skipped} already existed, {len(delete_paths)} deleted.")
