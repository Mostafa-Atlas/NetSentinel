"""Create a consistent SQLite copy for backup or stopped-service restoration."""

import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def copy_database(source: Path, target: Path, *, replace: bool = False) -> None:
    source = source.resolve(strict=True)
    target = target.resolve()
    if source == target:
        raise ValueError("Source and target must differ")
    if target.exists() and not replace:
        raise FileExistsError(f"Target already exists: {target}; use --replace only while stopped")
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, staging = tempfile.mkstemp(
        prefix=".netsentinel-backup-", suffix=".db", dir=target.parent
    )
    os.close(handle)
    try:
        with closing(sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(staging)) as copied:
                original.backup(copied)
                if copied.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise RuntimeError("SQLite integrity check failed")
        os.replace(staging, target)
    finally:
        if os.path.exists(staging):
            os.unlink(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--replace", action="store_true", help="Replace target after stopping the app"
    )
    arguments = parser.parse_args()
    copy_database(arguments.source, arguments.target, replace=arguments.replace)
    print(f"Verified SQLite copy: {arguments.target}")
