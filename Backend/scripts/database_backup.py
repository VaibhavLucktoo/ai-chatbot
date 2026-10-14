"""Back up Compose PostgreSQL or restore into a new database, never overwrite one."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from app.core.config import CACHE_ROOT


def backup(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as target:
        try:
            subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c",
                            'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'],
                           stdout=target, check=True)
        except BaseException:
            target.close()
            path.unlink()
            raise
    print(f"Backup saved: {path.resolve()}")


def restore(path, target_database):
    if not re.fullmatch(r"restore_[a-z0-9_]{1,48}", target_database):
        raise ValueError("Restore target must start with restore_ and contain lowercase letters, digits or underscores.")
    with path.open("rb") as source:
        # createdb fails if the database already exists. No --clean or DROP.
        subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c",
                        'exec createdb -U "$POSTGRES_USER" -T template0 "$1"', "sh", target_database], check=True)
        subprocess.run(["docker", "compose", "exec", "-T", "db", "sh", "-c",
                        'exec pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error --single-transaction',
                        "sh", target_database], stdin=source, check=True)
    print(f"Restored into {target_database}. Verify document counts and RAG before switching configuration.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dump = commands.add_parser("backup")
    dump.add_argument("--output", type=Path, default=CACHE_ROOT / "backups" /
                      (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".dump"))
    load = commands.add_parser("restore")
    load.add_argument("backup", type=Path)
    load.add_argument("--database", required=True)
    args = parser.parse_args()
    try:
        if args.command == "backup":
            backup(args.output)
        else:
            restore(args.backup, args.database)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Database operation failed ({type(exc).__name__}); verify Docker and the target.\n")


if __name__ == "__main__":
    main()
