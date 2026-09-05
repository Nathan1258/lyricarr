"""Lyricarr — generate word-synced (.lrc) lyric sidecars for a music library.

Point it at a folder, for every track missing a sidecar it fetches the lyric
text from LRCLIB and force-aligns it to the audio, writing `<track>.lrc` next
to the file. Any media server that reads .lrc sidecars (Jellyfin, Navidrome,
Plex) then picks them up.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import lrclib
from .tags import read_meta, scan_library


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes", "on")


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="lyricarr", description=__doc__)
    ap.add_argument("library", nargs="?", type=Path,
                    default=os.environ.get("LYRICARR_LIBRARY"),
                    help="path to the music library root (env LYRICARR_LIBRARY)")
    ap.add_argument("--device", default=os.environ.get("LYRICARR_DEVICE", "auto"),
                    help="auto|cuda|mps|cpu (env LYRICARR_DEVICE)")
    ap.add_argument("--lang", default=os.environ.get("LYRICARR_LANG", "en"),
                    help="alignment language code (env LYRICARR_LANG)")
    ap.add_argument("--overwrite", action="store_true", default=_env_bool("LYRICARR_OVERWRITE"),
                    help="regenerate existing sidecars (env LYRICARR_OVERWRITE)")
    ap.add_argument("--no-separate", action="store_true", default=_env_bool("LYRICARR_NO_SEPARATE"),
                    help="skip Demucs vocal isolation (env LYRICARR_NO_SEPARATE)")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LYRICARR_LIMIT", "0")),
                    help="process at most N tracks (env LYRICARR_LIMIT)")
    ap.add_argument("--interval", type=int, default=int(os.environ.get("LYRICARR_INTERVAL", "0")),
                    help="seconds between repeated scans; 0 = run once (env LYRICARR_INTERVAL)")
    ap.add_argument("--dry-run", action="store_true", default=_env_bool("LYRICARR_DRY_RUN"),
                    help="scan + check LRCLIB coverage only; no alignment or writes")
    ap.add_argument("--work", type=Path,
                    default=Path(os.environ.get("LYRICARR_WORK", "/tmp/lyricarr")),
                    help="scratch dir for vocal stems (env LYRICARR_WORK)")
    return ap


def _run_once(args, generate_elrc, device: str) -> None:
    files = scan_library(args.library)
    todo = [f for f in files if args.overwrite or not f.with_suffix(".lrc").exists()]
    have = len(files) - len(todo)
    print(f"Found {len(files)} audio files; {have} already have sidecars; "
          f"{len(todo)} to process" + (f" (limit {args.limit})" if args.limit else ""),
          flush=True)
    if args.limit:
        todo = todo[:args.limit]

    done = nolyrics = failed = 0
    for i, path in enumerate(todo, 1):
        meta = read_meta(path)
        if not meta or not meta.title:
            print(f"[{i}/{len(todo)}] ? no tags: {path.name}", flush=True)
            failed += 1
            continue
        found = lrclib.fetch_lines(meta.artist, meta.title, meta.album, meta.duration)
        label = f"{meta.artist} — {meta.title}"
        if not found:
            print(f"[{i}/{len(todo)}] – no lyrics: {label}", flush=True)
            nolyrics += 1
            continue
        kind, lines = found
        if args.dry_run:
            print(f"[{i}/{len(todo)}] ✓ {kind:6} {label} ({len(lines)} lines)", flush=True)
            done += 1
            continue
        try:
            elrc = generate_elrc(path, lines, device, args.work, args.lang,
                                 separate=not args.no_separate)
            if not elrc:
                print(f"[{i}/{len(todo)}] – align empty: {label}", flush=True)
                failed += 1
                continue
            meta.sidecar.write_text(elrc, encoding="utf-8")
            print(f"[{i}/{len(todo)}] ✓ {label}", flush=True)
            done += 1
        except Exception as e:
            print(f"[{i}/{len(todo)}] ✗ {label}: {e}", flush=True)
            failed += 1

    verb = "would generate" if args.dry_run else "generated"
    print(f"Done. {verb} {done}; {nolyrics} without lyrics; {failed} failed.", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.library:
        print("No library path (positional arg or LYRICARR_LIBRARY).", file=sys.stderr)
        return 2
    args.library = Path(args.library)
    if not args.library.is_dir():
        print(f"Not a directory: {args.library}", file=sys.stderr)
        return 2

    generate_elrc = None
    device = "auto"
    if not args.dry_run:
        from .align import pick_device, generate_elrc as _gen
        generate_elrc = _gen
        device = pick_device(args.device)
        print(f"Lyricarr device: {device}", flush=True)

    while True:
        _run_once(args, generate_elrc, device)
        if args.interval <= 0:
            return 0
        print(f"Sleeping {args.interval}s before next scan...", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
