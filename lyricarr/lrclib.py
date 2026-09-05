"""Fetch lyric TEXT from LRCLIB"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

BASE = "https://lrclib.net/api"
UA = "Lyricarr/0.1 (+https://github.com/zuno-music/lyricarr)"

_LINE = re.compile(r"^\[(\d+):(\d{2})(?:[.:](\d{1,3}))?\]")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


_EXPLICIT = re.compile(
    r"\s*(?:\U0001F174️?|\U0001F150️?|\[explicit\]|\(explicit\)"
    r"|\[clean\]|\(clean\))\s*", re.IGNORECASE)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", _EXPLICIT.sub(" ", s)).strip()


def _parse_synced(text: str) -> list[tuple[float | None, str]]:
    out: list[tuple[float | None, str]] = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        mins, secs, frac = int(m.group(1)), int(m.group(2)), m.group(3)
        t = mins * 60 + secs + (int(frac) / 10 ** len(frac) if frac else 0.0)
        body = line[m.end():].strip()
        if body:
            out.append((t, body))
    return out


def fetch_lines(artist: str, title: str, album: str, duration: float
                ) -> tuple[str, list[tuple[float | None, str]]] | None:
    artist, title, album = _clean(artist), _clean(title), _clean(album)
    payload = None
    try:
        q = urllib.parse.urlencode({"artist_name": artist, "track_name": title,
                                    "album_name": album,
                                    "duration": int(round(duration))})
        payload = _get(f"{BASE}/get?{q}")
    except Exception:
        try:
            q = urllib.parse.urlencode({"q": f"{artist} {title}".strip()})
            results = _get(f"{BASE}/search?{q}")
            payload = next((r for r in results
                            if r.get("syncedLyrics") or r.get("plainLyrics")), None)
        except Exception:
            payload = None
    if not payload:
        return None
    if payload.get("instrumental"):
        return None
    synced = payload.get("syncedLyrics")
    if synced and synced.strip():
        lines = _parse_synced(synced)
        if lines:
            return ("synced", lines)
    plain = payload.get("plainLyrics")
    if plain and plain.strip():
        return ("plain", [(None, l.strip()) for l in plain.splitlines() if l.strip()])
    return None
