"""Import a regulator licence registry (АРРФР / egov) into `licensed_entity`.

The АРРФР registry (finreg.kz / data.egov.kz) lists operators by legal name + BIN,
but our content matches on the identifiers that appear in videos — a domain or an
@handle. So the import takes a CSV that maps each such identifier to its licence:

    identifier,kind,operator,bin,license_no,status,source
    profit-x.kz,domain,"ТОО Profit-X",123456789012,0001-БД,active,ardfm
    @legalbroker,handle,"АО LegalBroker",987654321098,0002-БД,active,ardfm
    scam-casino.io,domain,"—",,,revoked,ardfm

Only `identifier` is required; the rest default sensibly. `status` other than
"active" (suspended/revoked) is stored but NOT treated as licensed — a revoked
licence correctly reads as «нелицензионный».

Idempotent: re-running updates existing rows (upsert by normalized identifier).

Run:  python -m scripts.import_licensed_registry path/to/registry.csv [--source ardfm]
"""
from __future__ import annotations

import argparse
import csv
import sys

_FIELDS = ("identifier", "kind", "operator", "bin", "license_no", "status", "source")


def parse_csv(path: str) -> list[dict]:
    """Read the registry CSV into row dicts (only known fields kept)."""
    with open(path, newline="", encoding="utf-8-sig") as fh:   # utf-8-sig: tolerate Excel BOM
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "identifier" not in {(f or "").strip() for f in reader.fieldnames}:
            raise ValueError("CSV must have a header row with at least an 'identifier' column")
        rows: list[dict] = []
        for raw in reader:
            row = {k: (raw.get(k) or "").strip() for k in _FIELDS}
            if row["identifier"]:
                rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Import licensed-operator registry CSV into the DB.")
    ap.add_argument("csv_path", help="Path to the registry CSV (see module docstring for columns)")
    ap.add_argument("--source", default="", help="Default source tag for rows that omit one (e.g. ardfm)")
    args = ap.parse_args()

    try:
        rows = parse_csv(args.csv_path)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    from app.db.licensed_repo import import_rows
    from app.db.session import get_session

    gen = get_session()
    session = next(gen)
    try:
        result = import_rows(session, rows, source=args.source)
    finally:
        gen.close()
    print(f"IMPORT DONE — imported/updated {result['imported']}, skipped {result['skipped']} "
          f"(blank identifier) from {args.csv_path}")


if __name__ == "__main__":
    main()
