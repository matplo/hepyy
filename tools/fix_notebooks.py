#!/usr/bin/env python3
"""
fix_notebooks.py — replace heppyyier references with hepyy in Jupyter notebooks.

Scans recursively for .ipynb files and rewrites cell source in-place.
Skips .ipynb_checkpoints directories.

Usage:
    python fix_notebooks.py [directory]        # default: current directory
    python fix_notebooks.py /path/to/notebooks --dry-run
"""

import argparse
import json
import pathlib
import re
import sys


# ---------------------------------------------------------------------------
# Substitution rules — applied in order to every source line in every cell
# ---------------------------------------------------------------------------
REPLACEMENTS = [
    # Python API: import and method calls
    (r'\bimport heppyyier\b',       'import hepyy'),
    (r'\bheppyyier\.load\b',        'hepyy.load'),
    (r'\bheppyyier\.gSystem_load\b','hepyy.gSystem_load'),
    # CLI commands inside string literals / markdown
    (r'\bheppyyier init\b',         'hepyy init'),
    (r'\bheppyyier install\b',      'hepyy install'),
    (r'\bheppyyier upgrade\b',      'hepyy upgrade'),
    (r'\bheppyyier avail\b',        'hepyy avail'),
    (r'\bheppyyier list\b',         'hepyy list'),
    (r'\bheppyyier info\b',         'hepyy info'),
    (r'\bheppyyier generate-modules\b', 'hepyy generate-modules'),
    # Prose / description strings
    (r'\bheppyyier\b',              'hepyy'),
]

COMPILED = [(re.compile(pat), repl) for pat, repl in REPLACEMENTS]


def fix_source(lines: list[str]) -> tuple[list[str], int]:
    """Apply all substitutions to a list of source lines.  Returns (new_lines, n_changes)."""
    changed = 0
    result = []
    for line in lines:
        new = line
        for pattern, repl in COMPILED:
            new, n = pattern.subn(repl, new)
            changed += n
        result.append(new)
    return result, changed


def fix_notebook(path: pathlib.Path, dry_run: bool) -> int:
    """Fix one notebook. Returns number of substitutions made."""
    try:
        text = path.read_text(encoding="utf-8")
        nb = json.loads(text)
    except Exception as exc:
        print(f"  SKIP  {path}  ({exc})")
        return 0

    total = 0
    for cell in nb.get("cells", []):
        src = cell.get("source", [])
        if not src:
            continue
        # source can be a list of strings or a single string
        if isinstance(src, str):
            new_src, n = fix_source([src])
            cell["source"] = new_src[0]
        else:
            new_src, n = fix_source(src)
            cell["source"] = new_src
        total += n

    if total == 0:
        return 0

    if dry_run:
        print(f"  DRY   {path}  ({total} substitution(s) would be made)")
    else:
        # Preserve trailing newline behaviour of the original file
        new_text = json.dumps(nb, indent=1, ensure_ascii=False)
        if text.endswith("\n"):
            new_text += "\n"
        path.write_text(new_text, encoding="utf-8")
        print(f"  FIXED {path}  ({total} substitution(s))")

    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", nargs="?", default=".",
                        help="Root directory to scan (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would change without writing files")
    args = parser.parse_args()

    root = pathlib.Path(args.directory).resolve()
    if not root.is_dir():
        print(f"Error: '{root}' is not a directory", file=sys.stderr)
        sys.exit(1)

    notebooks = [
        p for p in root.rglob("*.ipynb")
        if ".ipynb_checkpoints" not in p.parts
    ]

    if not notebooks:
        print(f"No .ipynb files found under {root}")
        return

    print(f"Scanning {len(notebooks)} notebook(s) under {root}"
          + (" [DRY RUN]" if args.dry_run else ""))

    total_files = total_subs = 0
    for nb_path in sorted(notebooks):
        n = fix_notebook(nb_path, dry_run=args.dry_run)
        if n:
            total_files += 1
            total_subs += n

    print(f"\n{'Would modify' if args.dry_run else 'Modified'} "
          f"{total_files}/{len(notebooks)} file(s), "
          f"{total_subs} substitution(s) total.")


if __name__ == "__main__":
    main()
