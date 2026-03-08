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


@click.group()
def cli():
    """Equipment Explorer management CLI."""


@cli.command()
def setup():
    """Run the full setup flow for Equipment Explorer."""
    click.echo("=" * 60)
    click.echo("  Equipment Explorer — Setup")
    click.echo("=" * 60)

    # Step 1: initialise database
    click.echo("\n[1/5] Initialising database...")
    init_db(DB_PATH)
    click.echo(f"      Database ready at: {DB_PATH}")

    conn = get_connection(DB_PATH)

    # Step 2: cable list (required)
    click.echo("\n[2/5] Import cable list")
    cable_file = prompt_path("      Path to cable list Excel file")
    import_equipment_and_cables(conn, cable_file)

    # Step 3: documents directory (optional)
    click.echo("\n[3/5] Import documents")
    if click.confirm("      Import document directory?", default=False):
        docs_dir = prompt_path("      Path to documents root directory")
        import_documents(conn, docs_dir)
    else:
        click.echo("      Skipped.")

    # Step 4: drawing metadata (optional)
    click.echo("\n[4/5] Import drawing metadata")
    if click.confirm("      Import drawing metadata?", default=False):
        meta_file = prompt_path("      Path to metadata Excel file")
        import_metadata(conn, meta_file)
    else:
        click.echo("      Skipped.")

    # Step 5: compartment list (optional)
    click.echo("\n[5/5] Import compartment list")
    if click.confirm("      Import compartment list?", default=False):
        comp_file = prompt_path("      Path to compartment list Excel file")
        import_compartments(conn, comp_file)
    else:
        click.echo("      Skipped.")

    conn.close()
    click.echo("\nSetup complete.")


if __name__ == "__main__":
    cli()
