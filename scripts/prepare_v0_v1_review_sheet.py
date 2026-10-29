"""Prepare a blinded paired review CSV from selected live V0/V1 runs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_v0_v1_evaluation import ComparisonError, _rows, _select_run, _check_metadata, DIMENSIONS
from scripts.safe_paths import UnsafePathError, ensure_directory, safe_write_text


def prepare(m0, rows0, m1, rows1):
    if m0.get("mode") != "live" or m1.get("mode") != "live":
        raise ComparisonError("Blind quality review sheets require live artifacts; offline text is mock evidence.")
    _check_metadata(m0, m1)
    a, b = _rows(rows0, "V0"), _rows(rows1, "V1")
    shared = sorted(set(a) & set(b))
    if not shared:
        raise ComparisonError("No matching scenario turns are available to review.")
    fields = ["scenario_id", "turn", "customer_message", "response_A", "response_B", "reviewer_id",
              *DIMENSIONS, "critical_violations", "reviewer_notes"]
    review, key = io.StringIO(newline=""), io.StringIO(newline="")
    writer, key_writer = csv.DictWriter(review, fieldnames=fields), csv.DictWriter(
        key, fieldnames=["scenario_id", "turn", "version_A", "version_B"])
    writer.writeheader(); key_writer.writeheader()
    for scenario, turn in shared:
        # Stable pseudo-random ordering by pair; the answer key is stored separately.
        v0_first = int(hashlib.sha256(f"{scenario}:{turn}".encode()).hexdigest()[-1], 16) % 2 == 0
        first, second = (a[(scenario, turn)], b[(scenario, turn)]) if v0_first else (b[(scenario, turn)], a[(scenario, turn)])
        writer.writerow({
            "scenario_id": scenario, "turn": turn,
            "customer_message": first.get("customer_message", ""),
            "response_A": first.get("assistant_response", ""),
            "response_B": second.get("assistant_response", ""),
        })
        key_writer.writerow({"scenario_id": scenario, "turn": turn,
                             "version_A": "V0" if v0_first else "V1",
                             "version_B": "V1" if v0_first else "V0"})
    return review.getvalue(), key.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v0-dir", type=Path, required=True)
    parser.add_argument("--v1-dir", type=Path, required=True)
    parser.add_argument("--v0-run-id")
    parser.add_argument("--v1-run-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        m0, r0, _ = _select_run(args.v0_dir, args.v0_run_id)
        m1, r1, _ = _select_run(args.v1_dir, args.v1_run_id)
        sheet, key = prepare(m0, r0, m1, r1)
        output = args.output if args.output.is_absolute() else ROOT / args.output
        parent = ensure_directory(output.parent, create=True)
        output = parent / output.name
        safe_write_text(output, sheet, overwrite=True)
        safe_write_text(output.with_name(output.stem + "_answer_key.csv"), key, overwrite=True)
    except (OSError, UnsafePathError, ComparisonError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"Could not prepare paired review sheet: {exc}", file=sys.stderr)
        return 2
    print(f"Blinded sheet: {output}")
    print(f"Version key: {output.with_name(output.stem + '_answer_key.csv')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
