import glob
import os
import readline

import click
from dotenv import load_dotenv

load_dotenv()

from setup.db import get_connection, init_db
from setup.import_equipment_and_cables import import_equipment_and_cables
from setup.import_compartments import import_compartments
from setup.import_documents import import_documents
from setup.import_metadata import import_metadata

DB_PATH = os.getenv("DB_PATH", "data/equipment_explorer.db")

_SEP = "=" * 60


def _path_completer(text, state):
    matches = glob.glob(os.path.expanduser(text) + "*")
    matches = [m + os.sep if os.path.isdir(m) else m for m in matches]
    return matches[state] if state < len(matches) else None


def prompt_path(message: str) -> str:
    """Prompt for a filesystem path with tab completion."""
    readline.set_completer(_path_completer)
    readline.set_completer_delims(" \t\n")
    readline.parse_and_bind("tab: complete")
    try:
        return click.prompt(message)
    finally:
        readline.set_completer(None)


# ---------------------------------------------------------------------------
# Guided step helpers — reused by both `setup` and the individual commands
# ---------------------------------------------------------------------------

def _run_cables(conn):
    click.echo(
        "\n  This is the master register of all cables and equipment on board.\n"
        "  Expected file: Excel (.xlsx) or CSV with cable tags, equipment tags,\n"
        "  cable types, and connection details."
    )
    cable_file = prompt_path("\n  Path to cable list file")
    import_equipment_and_cables(conn, cable_file)


def _run_documents(conn):
    click.echo(
        "\n  Scans a directory tree for PDF documents and registers them in the\n"
        "  database so they can be indexed and searched later.\n"
        "  Expected input: path to the root folder containing the PDF documents."
    )
    import_documents(conn)


def _run_metadata(conn):
    click.echo(
        "\n  Enriches registered documents with drawing descriptions, supplier\n"
        "  information, revision status, and document hierarchy.\n"
        "  Expected file: Excel (.xlsx) or CSV with a column containing the\n"
        "  relative file path matching the scanned documents."
    )
    meta_file = prompt_path("\n  Path to metadata file")
    import_metadata(conn, meta_file)


def _run_compartments(conn):
    click.echo(
        "\n  Maps compartment/room tags to human-readable descriptions so equipment\n"
        "  locations are shown by name rather than code.\n"
        "  Expected file: Excel (.xlsx) or CSV with compartment tag and description\n"
        "  columns."
    )
    comp_file = prompt_path("\n  Path to compartment list file")
    import_compartments(conn, comp_file)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Equipment Explorer management CLI."""


# ---------------------------------------------------------------------------
# setup — full guided flow
# ---------------------------------------------------------------------------

@cli.command()
def setup():
    """Run the full setup flow for Equipment Explorer."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Setup")
    click.echo(_SEP)

    # Initialise database (not a numbered step)
    click.echo("\nInitialising database...")
    init_db(DB_PATH)
    click.echo(f"Database ready at: {DB_PATH}")

    conn = get_connection(DB_PATH)
    completed = []
    skipped = []

    # ------------------------------------------------------------------
    # Step 1: Cable List (required)
    # ------------------------------------------------------------------
    click.echo(f"\n{_SEP}")
    click.echo("  Step 1: Cable List  (required)")
    click.echo(_SEP)
    _run_cables(conn)
    completed.append("Step 1: Cable List")

    # ------------------------------------------------------------------
    # Step 2: Documents (optional)
    # ------------------------------------------------------------------
    click.echo(f"\n{_SEP}")
    click.echo("  Step 2: Documents  (optional)")
    click.echo(_SEP)
    if click.confirm("\nDo you want to scan a documents directory?", default=False):
        _run_documents(conn)
        completed.append("Step 2: Documents")
    else:
        click.echo("  Skipped.")
        skipped.append("Step 2: Documents")

    # ------------------------------------------------------------------
    # Step 3: Drawing Metadata (optional)
    # ------------------------------------------------------------------
    click.echo(f"\n{_SEP}")
    click.echo("  Step 3: Drawing Metadata  (optional)")
    click.echo(_SEP)
    if click.confirm("\nDo you want to import document metadata?", default=False):
        _run_metadata(conn)
        completed.append("Step 3: Drawing Metadata")
    else:
        click.echo("  Skipped.")
        skipped.append("Step 3: Drawing Metadata")

    # ------------------------------------------------------------------
    # Step 4: Compartment List (optional)
    # ------------------------------------------------------------------
    click.echo(f"\n{_SEP}")
    click.echo("  Step 4: Compartment List  (optional)")
    click.echo(_SEP)
    if click.confirm("\nDo you want to import a compartment list?", default=False):
        _run_compartments(conn)
        completed.append("Step 4: Compartment List")
    else:
        click.echo("  Skipped.")
        skipped.append("Step 4: Compartment List")

    conn.close()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    click.echo(f"\n{_SEP}")
    click.echo("  Setup complete!")
    click.echo("")
    if completed:
        click.echo("  Completed:")
        for step in completed:
            click.echo(f"    \u2713 {step}")
    if skipped:
        click.echo("")
        click.echo("  Skipped:")
        for step in skipped:
            click.echo(f"    - {step}")
    click.echo(_SEP)


# ---------------------------------------------------------------------------
# Individual import commands
# ---------------------------------------------------------------------------

@cli.command("import-cables")
def import_cables_cmd():
    """Import (or re-import) the cable and equipment list."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Import Cable List")
    click.echo(_SEP)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    _run_cables(conn)
    conn.close()
    click.echo("\nDone.")


@cli.command("import-documents")
def import_documents_cmd():
    """Scan a directory and register PDF documents."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Import Documents")
    click.echo(_SEP)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    _run_documents(conn)
    conn.close()
    click.echo("\nDone.")


@cli.command("import-metadata")
def import_metadata_cmd():
    """Update document records with drawing metadata."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Import Drawing Metadata")
    click.echo(_SEP)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    _run_metadata(conn)
    conn.close()
    click.echo("\nDone.")


@cli.command("import-compartments")
def import_compartments_cmd():
    """Import (or re-import) the compartment/room list."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Import Compartment List")
    click.echo(_SEP)
    init_db(DB_PATH)
    conn = get_connection(DB_PATH)
    _run_compartments(conn)
    conn.close()
    click.echo("\nDone.")


# ---------------------------------------------------------------------------
# resetdb
# ---------------------------------------------------------------------------

@cli.command()
def resetdb():
    """Delete all data from the database and start fresh."""
    click.echo(_SEP)
    click.echo("  Equipment Explorer — Reset Database")
    click.echo(_SEP)
    click.echo(
        "\n  WARNING: This will permanently delete ALL data —\n"
        "  equipment, cables, documents, compartments, and the\n"
        "  entire document occurrence index.\n"
        "\n  This cannot be undone.\n"
    )
    if not click.confirm("Are you sure you want to reset the database?", default=False):
        click.echo("Cancelled.")
        return

    conn = get_connection(DB_PATH)
    conn.execute("DELETE FROM equipment_occurrences")
    conn.execute("DELETE FROM cable_occurrences")
    conn.execute("DELETE FROM cables")
    conn.execute("DELETE FROM equipment")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM compartments")
    conn.execute(
        "DELETE FROM sqlite_sequence WHERE name IN "
        "('equipment_occurrences','cable_occurrences','cables','equipment','documents','compartments')"
    )
    conn.commit()
    conn.close()

    click.echo("\nDatabase reset. Run 'manage.py setup' to import new data.")


if __name__ == "__main__":
    cli()
