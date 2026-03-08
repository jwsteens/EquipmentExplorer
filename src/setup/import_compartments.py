import sqlite3

import click
import pandas as pd

from setup.import_equipment_and_cables import (
    _build_col_map,
    _preview_table,
    _print_columns,
    _prompt_column,
    _stale_tags,
    _val,
)


def import_compartments(conn: sqlite3.Connection, filepath: str) -> None:
    """Import compartment descriptions from an Excel or CSV file."""

    # ── Step 1: load file ────────────────────────────────────────────────────
    filepath = filepath.replace("\\", "/")

    header_row = click.prompt(
        "  Header row (1 = first row is header, 4 = fourth row is header, 0 = no header)",
        default=4,
        type=int,
    )
    pandas_header = None if header_row == 0 else header_row - 1

    ext = filepath.rsplit(".", 1)[-1].lower()
    try:
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(filepath, header=pandas_header)
        elif ext == "csv":
            df = pd.read_csv(filepath, header=pandas_header, sep=None, engine="python")
        else:
            click.echo(f"Unsupported file type: .{ext}  (expected .xlsx, .xls, or .csv)")
            return
    except Exception as e:
        click.echo(f"Failed to load file: {e}")
        return

    click.echo(f"  Loaded {len(df)} rows.")

    # ── Step 2: column mapping ───────────────────────────────────────────────
    _print_columns(df)
    col_map = _build_col_map(df)

    click.echo("\nMap fields to columns (Enter to accept default, letter or name to override):")

    tag_col  = _prompt_column("tag         [required]", "roomKey",         col_map, df, required=True)
    desc_col = _prompt_column("description [required]", "roomDescription", col_map, df, required=True)

    # ── Step 3: preview ──────────────────────────────────────────────────────
    preview_rows = []
    for _, row in df.head(5).iterrows():
        preview_rows.append({
            "tag":         _val(row, tag_col),
            "description": _val(row, desc_col),
        })

    click.echo("\nFirst 5 rows of mapped data:")
    _preview_table(preview_rows)

    if not click.confirm("\nProceed with import?", default=True):
        click.echo("Import cancelled.")
        return

    # ── Step 4: build records and sync in a single transaction ───────────────
    records: list[tuple] = []
    for _, row in df.iterrows():
        tag = _val(row, tag_col)
        if not tag:
            continue
        records.append((tag, _val(row, desc_col)))

    incoming_tags = {r[0] for r in records}
    stale = _stale_tags(conn, "compartments", "tag", incoming_tags)

    with conn:
        if stale:
            ph = ",".join("?" * len(stale))
            conn.execute(f"DELETE FROM compartments WHERE tag IN ({ph})", stale)

        conn.executemany(
            """
            INSERT INTO compartments (tag, description)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET description = excluded.description
            """,
            records,
        )

    # ── Step 5: summary ──────────────────────────────────────────────────────
    skipped = len(df) - len(records)
    click.echo(f"\nImport complete: {len(records)} inserted/updated, {len(stale)} removed, {skipped} row(s) skipped.")
