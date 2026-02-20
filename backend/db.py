"""
Database CLI — thin wrapper around Alembic.

Usage (run from the backend/ directory):
    python db.py status               show current revision and pending migrations
    python db.py push                 apply all pending migrations  (upgrade head)
    python db.py pull                 stamp DB as current without running DDL
                                      use this when the DB already matches the models
    python db.py migrate "message"    auto-generate a new migration from model changes
    python db.py rollback [N]         undo the last N migrations (default: 1)
    python db.py history              show full migration history
    python db.py reset                !! destructive: downgrade to base then upgrade head
"""

import subprocess
import sys
from pathlib import Path

# Always run Alembic from the backend/ directory so it finds alembic.ini
ROOT = Path(__file__).parent


def _alembic(*args: str) -> int:
    """Run an alembic sub-command and return the exit code."""
    cmd = [sys.executable, "-m", "alembic", *args]
    result = subprocess.run(cmd, cwd=ROOT)
    return result.returncode


def cmd_status() -> None:
    print("=== Current revision ===")
    _alembic("current", "--verbose")
    print("\n=== Pending migrations ===")
    _alembic("history", "--indicate-current")


def cmd_push() -> None:
    print("Applying all pending migrations...")
    code = _alembic("upgrade", "head")
    if code == 0:
        print("Done — database is up to date.")
    else:
        print("Migration failed. Check the output above.")
        sys.exit(code)


def cmd_pull() -> None:
    """
    Stamp the DB as fully up-to-date without running any DDL.
    Use this when the database already matches the current models
    (e.g. an existing deployment that pre-dates Alembic tracking).
    """
    print("Stamping database as current (no DDL will be executed)...")
    code = _alembic("stamp", "head")
    if code == 0:
        print("Done — database marked as up to date.")
    else:
        sys.exit(code)


def cmd_migrate(message: str) -> None:
    if not message:
        print("Error: provide a description, e.g.  python db.py migrate \"add user table\"")
        sys.exit(1)
    print(f'Generating migration: "{message}"')
    code = _alembic("revision", "--autogenerate", "-m", message)
    if code == 0:
        print("Migration file created in alembic/versions/. Review it before running push.")
    else:
        sys.exit(code)


def cmd_rollback(steps: int = 1) -> None:
    print(f"Rolling back {steps} migration(s)...")
    code = _alembic("downgrade", f"-{steps}")
    if code == 0:
        print("Done.")
    else:
        sys.exit(code)


def cmd_history() -> None:
    _alembic("history", "--verbose")


def cmd_reset() -> None:
    confirm = input(
        "WARNING: this will downgrade to base then upgrade head, potentially dropping data.\n"
        "Type 'yes' to continue: "
    )
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        return
    print("Downgrading to base...")
    _alembic("downgrade", "base")
    print("Upgrading to head...")
    code = _alembic("upgrade", "head")
    if code == 0:
        print("Done.")
    else:
        sys.exit(code)


COMMANDS = {
    "status": cmd_status,
    "push": cmd_push,
    "pull": cmd_pull,
    "migrate": cmd_migrate,
    "rollback": cmd_rollback,
    "history": cmd_history,
    "reset": cmd_reset,
}

HELP = """
Usage: python db.py <command> [args]

Commands:
  status               show current revision and migration history
  push                 apply all pending migrations
  pull                 stamp DB as current (for existing DBs without migration history)
  migrate "message"    auto-generate migration from model changes
  rollback [N]         undo last N migrations (default 1)
  history              show full migration history
  reset                downgrade to base + upgrade head  !! destructive
"""


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(HELP)
        return

    command = args[0]
    if command not in COMMANDS:
        print(f"Unknown command: {command}\n{HELP}")
        sys.exit(1)

    fn = COMMANDS[command]

    if command == "migrate":
        message = " ".join(args[1:])
        fn(message)
    elif command == "rollback":
        steps = int(args[1]) if len(args) > 1 else 1
        fn(steps)
    else:
        fn()


if __name__ == "__main__":
    main()
