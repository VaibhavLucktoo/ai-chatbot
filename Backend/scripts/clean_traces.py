"""Expire only JSON traces in the application's default private trace directory."""
import argparse
from datetime import datetime, timezone

from app.core.config import CACHE_ROOT


def expire(days=7):
    directory = (CACHE_ROOT / "rag-traces").resolve()
    expected = CACHE_ROOT.resolve() / "rag-traces"
    if directory != expected:
        raise ValueError("Trace directory must not resolve outside the default cache.")
    cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
    count = 0
    for path in directory.glob("*.json"):
        if path.is_symlink() or path.resolve().parent != directory:
            continue
        if path.stat().st_mtime < cutoff:
            path.unlink()
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7, choices=range(1, 366), metavar="1-365")
    args = parser.parse_args()
    print(f"Expired {expire(args.days)} traces.")


if __name__ == "__main__":
    main()
