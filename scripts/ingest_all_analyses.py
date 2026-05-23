"""
Batch-ingest all TRADE-ANALYSIS-*.md files in the CarmenAnalyst directory
into trade_signals.

Usage:
    python scripts/ingest_all_analyses.py
    python scripts/ingest_all_analyses.py --dir /path/to/analyses
    python scripts/ingest_all_analyses.py --tier 3
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Resolve project root so layer imports work regardless of cwd
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from layers.layer2_data.signal_writer import ingest_analysis_file


def main():
    parser = argparse.ArgumentParser(description="Ingest TRADE-ANALYSIS-*.md files into Supabase")
    parser.add_argument("--dir",  default=str(ROOT / "CarmenAnalyst"), help="Directory to scan")
    parser.add_argument("--tier", type=int, default=1, choices=[1, 3], help="Tier to tag signals with")
    args = parser.parse_args()

    scan_dir = Path(args.dir)
    files = sorted(scan_dir.glob("TRADE-ANALYSIS-*.md"))

    if not files:
        print(f"No TRADE-ANALYSIS-*.md files found in {scan_dir}")
        sys.exit(0)

    print(f"Found {len(files)} analysis file(s) in {scan_dir}")
    errors = []

    for f in files:
        try:
            ingest_analysis_file(f, tier=args.tier)
        except Exception as exc:
            print(f"  ✗ {f.name}: {exc}")
            errors.append((f.name, exc))

    print(f"\n{len(files) - len(errors)}/{len(files)} ingested successfully.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
