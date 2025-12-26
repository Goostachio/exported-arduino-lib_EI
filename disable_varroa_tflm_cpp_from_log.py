#!/usr/bin/env python3
"""
Disable (rename) duplicate Edge Impulse / TFLM .cpp units inside the varoa_mite_detection_inferencing
Arduino library by parsing an Arduino linker error log.

Typical use:
  python3 disable_varroa_tflm_cpp_from_log.py errors.txt --dry-run
  python3 disable_varroa_tflm_cpp_from_log.py errors.txt --apply

Recommended scope (default): only disables files under:
  .../varoa_mite_detection_inferencing/src/edge-impulse-sdk/tensorflow/lite/micro/

You can broaden with:
  --scope any   (disables any .cpp under varoa library that appears in log)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import List, Set, Tuple


VARROA_KEY = "varoa_mite_detection_inferencing"


def find_cpp_paths_in_log(text: str) -> List[Path]:
    """
    Extract .cpp file paths from the log.
    Handles patterns like:
      /Users/.../varoa_mite_detection_inferencing/src/.../micro_time.cpp:43: multiple definition...
    We capture up to ".cpp" then validate the file exists later.
    """
    # Capture unix-like absolute paths ending with .cpp
    # Avoid grabbing trailing :line:col by stopping at ".cpp"
    pattern = re.compile(r"(/[^ \n\t:]+?\.cpp)")
    hits = pattern.findall(text)
    return [Path(h) for h in hits]


def filter_varroa_paths(paths: List[Path]) -> List[Path]:
    return [p for p in paths if VARROA_KEY in str(p)]


def filter_scope(paths: List[Path], scope: str) -> List[Path]:
    """
    scope:
      - micro: only TFLM micro directory
      - tflm:  tensorflow/lite/micro anywhere
      - any:   any .cpp under varoa lib that appears in log
    """
    if scope == "any":
        return paths

    # Normalize to forward slashes for matching
    def norm(p: Path) -> str:
        return str(p).replace("\\", "/")

    if scope == "micro":
        # Strict: match exact segment used in your errors
        needle = f"{VARROA_KEY}/src/edge-impulse-sdk/tensorflow/lite/micro/"
        return [p for p in paths if needle in norm(p)]
    elif scope == "tflm":
        needle = f"{VARROA_KEY}/src/edge-impulse-sdk/tensorflow/lite/micro/"
        # same as micro now, kept as separate knob in case you extend later
        return [p for p in paths if needle in norm(p)]
    else:
        raise ValueError(f"Unknown scope: {scope}")


def unique_existing(paths: List[Path]) -> List[Path]:
    uniq: List[Path] = []
    seen: Set[str] = set()
    for p in paths:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and p.is_file():
            uniq.append(p)
    return uniq


def compute_target(p: Path) -> Path:
    # Only rename *.cpp (not already disabled)
    if p.suffix.lower() != ".cpp":
        raise ValueError(f"Not a .cpp file: {p}")
    if p.name.endswith(".cpp.disabled"):
        return p
    return p.with_name(p.name + ".disabled")  # micro_time.cpp -> micro_time.cpp.disabled


def rename_file(src: Path, dst: Path, apply: bool) -> Tuple[bool, str]:
    """
    Returns (changed?, message)
    """
    if src.name.endswith(".cpp.disabled"):
        return (False, f"SKIP already disabled: {src}")

    if dst.exists():
        return (False, f"SKIP target exists: {dst}")

    if not apply:
        return (True, f"DRY-RUN would rename:\n  {src}\n  -> {dst}")

    try:
        src.rename(dst)
        return (True, f"RENAMED:\n  {src}\n  -> {dst}")
    except Exception as e:
        return (False, f"ERROR renaming {src} -> {dst}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Parse Arduino linker error log and disable duplicate varoa EI/TFLM .cpp files by renaming to .cpp.disabled"
    )
    ap.add_argument("logfile", help="Path to the text file containing the full Arduino build/linker error log.")
    ap.add_argument(
        "--scope",
        choices=["micro", "tflm", "any"],
        default="micro",
        help="Which varoa .cpp paths to disable. Default: micro (recommended).",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Actually rename files. If omitted, script runs in dry-run mode.",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print extra info (counts, non-existing paths, etc.)",
    )

    args = ap.parse_args()

    log_path = Path(args.logfile).expanduser().resolve()
    if not log_path.exists():
        print(f"ERROR: logfile does not exist: {log_path}", file=sys.stderr)
        return 2

    text = log_path.read_text(errors="ignore")

    all_cpp = find_cpp_paths_in_log(text)
    if args.verbose:
        print(f"Found {len(all_cpp)} total .cpp path(s) in log")

    varoa_cpp = filter_varroa_paths(all_cpp)
    if args.verbose:
        print(f"Found {len(varoa_cpp)} varoa-related .cpp path(s) in log")

    scoped = filter_scope(varoa_cpp, args.scope)
    if args.verbose:
        print(f"After scope='{args.scope}', {len(scoped)} .cpp path(s) remain")

    existing = unique_existing(scoped)
    if args.verbose:
        print(f"{len(existing)} file(s) exist on disk and are unique")

    if not existing:
        print("No matching existing varoa .cpp files found to disable.")
        print("Tip: run with --verbose and check that your log contains absolute paths.")
        return 1

    # Execute plan
    changed = 0
    skipped = 0
    errors = 0

    print("=== PLAN ===")
    print(f"Mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    print(f"Scope: {args.scope}")
    print(f"Targets: {len(existing)} file(s)")
    print("============\n")

    for src in existing:
        dst = compute_target(src)
        did_change, msg = rename_file(src, dst, apply=args.apply)
        print(msg)
        print()
        if "ERROR" in msg:
            errors += 1
        elif did_change:
            changed += 1
        else:
            skipped += 1

    print("=== SUMMARY ===")
    print(f"Changed: {changed}")
    print(f"Skipped: {skipped}")
    print(f"Errors:  {errors}")
    print("===============")

    if errors:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
