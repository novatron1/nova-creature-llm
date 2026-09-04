#!/usr/bin/env python3
"""Recover a Nova portable encrypted backup without starting the web app."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_backup_vault import BackupVault, VaultError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decrypt a .novavault file into its verified Nova backup ZIP."
    )
    parser.add_argument("vault", help="Path to the .novavault file")
    parser.add_argument("destination", help="Where to write the recovered .zip file")
    args = parser.parse_args()

    source = Path(args.vault).expanduser().resolve()
    destination = Path(args.destination).expanduser().resolve()
    if destination.exists():
        print("Destination already exists; choose a new path so no file is overwritten.", file=sys.stderr)
        return 2
    passphrase = getpass("Backup passphrase: ")
    try:
        result = BackupVault(ROOT).decrypt(source, destination, passphrase)
    except VaultError as error:
        print(f"Recovery failed: {error}", file=sys.stderr)
        return 1
    finally:
        passphrase = ""
    print(f"Recovered {result['bytes']} bytes to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
