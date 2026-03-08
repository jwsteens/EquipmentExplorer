import sqlite3
import string

import click
import pandas as pd
from rich.console import Console
from rich.table import Table


def _col_letters(n: int) -> list[str]:
    """Generate Excel-style column letters: A, B, ..., Z, AA, AB, ..."""
    letters = []
    for i in range(n):
        label = ""
        idx = i
        while True:
            label = string.ascii_uppercase[idx % 26] + label
            idx = idx // 26 - 1
            if idx < 0:
                break
        letters.append(label)
    return letters


def _build_col_map(df: pd.DataFrame) -> dict[str, object]:
    """Return {letter: column_key, name: column_key} for lookup."""
    letters = _col_letters(len(df.columns))
    col_map: dict[str, object] = {}
    for letter, col in zip(letters, df.columns):
        col_map[letter.upper()] = col
        col_map[str(col)] = col
    return col_map


def _print_columns(df: pd.DataFrame) -> None:
    letters = _col_letters(len(df.columns))
    click.echo("\nAvailable columns:")
    for letter, col in zip(letters, df.columns):
        click.echo(f"  {letter:<4}{col}")


def _resolve_default(default_name: str, col_map: dict, df: pd.DataFrame) -> str | None:
    """Return the letter for default_name if it exists in the DataFrame, else None."""
    if default_name in df.columns:
        letters = _col_letters(len(df.columns))
        for letter, col in zip(letters, df.columns):
            if col == default_name:
                return letter
    return None


def _prompt_column(
    label: str,
    default_name: str,
    col_map: dict,
    df: pd.DataFrame,
    required: bool = True,
) -> object | None:
    """
    Prompt the user to select a column by letter or name.
    Returns the DataFrame column key, or None if skipped (optional only).
    """
    default_letter = _resolve_default(default_name, col_map, df)

    while True:
        if required:
            if default_letter:
                raw = click.prompt(f"  {label}", default=default_letter)
            else:
                raw = click.prompt(f"  {label} (letter or name)")
        else:
            hint = f"{default_letter} = {default_name}" if default_letter else "optional"
            raw = click.prompt(f"  {label} ({hint}, Enter to skip)", default="")

        raw = raw.strip()

        if not raw:
            if required:
                click.echo("    This field is required.")
                continue
            return None

        key = col_map.get(raw.upper()) or col_map.get(raw)
        if key is not None and key in df.columns:
            return key

        click.echo(f"    Column '{raw}' not found. Use a letter (A, B, …) or exact column name.")


def _stale_tags(conn: sqlite3.Connection, table: str, tag_col: str, incoming: set[str]) -> list[str]:
    """Return tags present in the DB table but absent from the incoming set."""
    if not incoming:
        return []
    placeholders = ",".join("?" * len(incoming))
    return [
        r[tag_col]
        for r in conn.execute(
            f"SELECT {tag_col} FROM {table} WHERE {tag_col} NOT IN ({placeholders})",
            list(incoming),
        ).fetchall()
    ]


def _val(row: pd.Series, col: object | None) -> str | None:
    """Extract a stripped string value from a row, returning None for missing/NaN/empty."""
    if col is None:
        return None
    v = row.get(col)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s else None


def _preview_table(records: list[dict]) -> None:
    """Print a bordered, word-wrapping rich table for a list of row dicts."""
    if not records:
        click.echo("  (no records to preview)")
        return
    table = Table(show_header=True, header_style="bold", show_lines=True)
    for col in records[0]:
        table.add_column(col, overflow="fold")
    for record in records:
        table.add_row(*[str(v) if v is not None else "" for v in record.values()])
    Console().print(table)


def import_equipment_and_cables(conn: sqlite3.Connection, filepath: str) -> None:
    """Import cables and equipment from an Excel or CSV cable list."""

    # ── Step 1: load file ────────────────────────────────────────────────────
    filepath = filepath.replace("\\", "/")

    header_row = click.prompt(
        "  Header row (1 = first row is header, 2 = second row is header, 0 = no header)",
        default=1,
        type=int,
    )
    pandas_header = None if header_row == 0 else header_row - 1

    ext = filepath.rsplit(".", 1)[-1].lower()
    try:
        if ext in ("xlsx", "xls"):
            df = pd.read_excel(filepath, header=pandas_header)
        elif ext == "csv":
            df = pd.read_csv(filepath, header=pandas_header)
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

    cable_tag_col  = _prompt_column("cableTag   [required]", "cableNo",                       col_map, df, required=True)
    cable_type1_col = _prompt_column("cableType1", "cableType1",                                col_map, df, required=False)
    cable_type2_col = _prompt_column("cableType2",            "cableType2",                   col_map, df, required=False)
    start_tag_col  = _prompt_column("startTag   [required]", "equipmentStartTag",              col_map, df, required=True)
    start_desc_col = _prompt_column("startDesc",             "equipmentStartDescription",      col_map, df, required=False)
    start_room_col = _prompt_column("startRoom",             "equipmentStartRoomTag",          col_map, df, required=False)
    start_deck_col = _prompt_column("startDeck",             "equipmentStartDeck",             col_map, df, required=False)
    dest_tag_col   = _prompt_column("destTag    [required]", "equipmentDestinationTag",        col_map, df, required=True)
    dest_desc_col  = _prompt_column("destDesc",              "equipmentDestinationDescription", col_map, df, required=False)
    dest_room_col  = _prompt_column("destRoom",              "equipmentDestinationRoomTag",    col_map, df, required=False)
    dest_deck_col  = _prompt_column("destDeck",              "equipmentDestinationDeck",       col_map, df, required=False)

    # ── Step 3: preview ──────────────────────────────────────────────────────
    def make_cable_type(row: pd.Series) -> str | None:
        t1 = _val(row, cable_type1_col) or ""
        t2 = _val(row, cable_type2_col) or ""
        joined = ", ".join(filter(None, [t1, t2]))
        return joined if joined else None

    preview_rows = []
    for _, row in df.head(5).iterrows():
        preview_rows.append({
            "cableTag":   _val(row, cable_tag_col),
            "cableType":  make_cable_type(row),
            "startTag":   _val(row, start_tag_col),
            "startDesc":  _val(row, start_desc_col),
            "startRoom":  _val(row, start_room_col),
            "startDeck":  _val(row, start_deck_col),
            "destTag":    _val(row, dest_tag_col),
            "destDesc":   _val(row, dest_desc_col),
            "destRoom":   _val(row, dest_room_col),
            "destDeck":   _val(row, dest_deck_col),
        })

    click.echo("\nFirst 5 rows of mapped data:")
    _preview_table(preview_rows)

    if not click.confirm("\nProceed with import?", default=True):
        click.echo("Import cancelled.")
        return

    # ── Sync: find stale DB rows not present in the incoming file ────────────
    incoming_cable_tags: set[str] = set()
    for _, row in df.iterrows():
        tag = _val(row, cable_tag_col)
        if tag:
            incoming_cable_tags.add(tag)

    incoming_equip_tags: set[str] = set()
    for _, row in df.iterrows():
        for col in (start_tag_col, dest_tag_col):
            tag = _val(row, col)
            if tag:
                incoming_equip_tags.add(tag)

    stale_cables = _stale_tags(conn, "cables", "tag", incoming_cable_tags)
    stale_equip  = _stale_tags(conn, "equipment", "tag", incoming_equip_tags)

    delete_cables: list[str] = []
    delete_equip:  list[str] = []

    if stale_cables:
        click.echo(f"\n{len(stale_cables)} cable(s) not found in the new file:")
        for t in stale_cables:
            click.echo(f"  - {t}")
        if click.confirm("Delete these from the database?", default=False):
            delete_cables = stale_cables

    if stale_equip:
        click.echo(f"\n{len(stale_equip)} equipment item(s) not found in the new file:")
        for t in stale_equip:
            click.echo(f"  - {t}")
        if click.confirm("Delete these from the database?", default=False):
            delete_equip = stale_equip

    # ── Steps 4–6: import inside a single transaction ────────────────────────
    with conn:
        # Deletions first — cables before equipment (FK order)
        if delete_cables:
            ph = ",".join("?" * len(delete_cables))
            conn.execute(f"DELETE FROM cables WHERE tag IN ({ph})", delete_cables)

        if delete_equip:
            ph = ",".join("?" * len(delete_equip))
            conn.execute(f"DELETE FROM equipment WHERE tag IN ({ph})", delete_equip)
        # Equipment
        equipment_dict: dict[str, dict] = {}

        for _, row in df.iterrows():
            tag = _val(row, start_tag_col)
            if tag and tag not in equipment_dict:
                equipment_dict[tag] = {
                    "description": _val(row, start_desc_col),
                    "room_tag":    _val(row, start_room_col),
                    "deck":        _val(row, start_deck_col),
                }

        for _, row in df.iterrows():
            tag = _val(row, dest_tag_col)
            if tag and tag not in equipment_dict:
                equipment_dict[tag] = {
                    "description": _val(row, dest_desc_col),
                    "room_tag":    _val(row, dest_room_col),
                    "deck":        _val(row, dest_deck_col),
                }

        conn.executemany(
            "INSERT OR REPLACE INTO equipment (tag, description, room_tag, deck) VALUES (?,?,?,?)",
            [
                (tag, d["description"], d["room_tag"], d["deck"])
                for tag, d in equipment_dict.items()
            ],
        )

        # Tag → id lookup
        tag_to_id: dict[str, int] = {
            r["tag"]: r["equipment_id"]
            for r in conn.execute("SELECT equipment_id, tag FROM equipment").fetchall()
        }

        # Cables
        cable_rows: list[tuple] = []
        seen_cables: set[str] = set()

        for _, row in df.iterrows():
            cable_tag = _val(row, cable_tag_col)
            if not cable_tag or cable_tag in seen_cables:
                continue
            seen_cables.add(cable_tag)

            start_tag = _val(row, start_tag_col)
            dest_tag  = _val(row, dest_tag_col)

            cable_rows.append((
                cable_tag,
                make_cable_type(row),
                tag_to_id.get(start_tag) if start_tag else None,
                tag_to_id.get(dest_tag)  if dest_tag  else None,
            ))

        conn.executemany(
            "INSERT OR REPLACE INTO cables (tag, type, start_equipment_id, dest_equipment_id)"
            " VALUES (?,?,?,?)",
            cable_rows,
        )

    # ── Step 7: summary + verification ──────────────────────────────────────
    click.echo(f"\nImport complete: {len(equipment_dict)} equipment inserted/updated, {len(delete_equip)} deleted")
    click.echo(f"Import complete: {len(cable_rows)} cables inserted/updated, {len(delete_cables)} deleted")

    rows = conn.execute(
        """
        SELECT c.tag AS cable_tag, c.type AS cable_type,
               s.tag AS start_tag, d.tag AS dest_tag
        FROM cables c
        LEFT JOIN equipment s ON c.start_equipment_id = s.equipment_id
        LEFT JOIN equipment d ON c.dest_equipment_id  = d.equipment_id
        LIMIT 5
        """
    ).fetchall()

    click.echo("\nFirst imported cables:")
    _preview_table([dict(r) for r in rows])
