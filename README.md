# Lyricarr

**Word-synced lyrics for your self-hosted music library — automatically.**

Point Lyricarr at your music folder and it
generates **word-by-word (enhanced `.lrc`) sidecars** next to your tracks for
Apple-Music-style karaoke lyrics compatible with **Jellyfin, Navidrome, and Plex**.

It gets the lyric *text* from [LRCLIB](https://lrclib.net) (free, no account)
and produces the timing itself by aligning the words to your actual audio.
No paid lyrics API, no scraping, no account tokens.

## How it works

```
your audio  +  LRCLIB lyric text  ──►  Demucs (isolate vocals)
                                   ──►  WhisperX (force-align words)
                                   ──►  <track>.lrc  (word-timed, next to the file)
```

Because the timing is aligned to *your* file, it stays in sync even when other
sources were timed to a different master/remaster. Your media server picks the
sidecars up on its next library scan.

## Quick start (Docker — Linux servers)

Add the service to your compose file (see `docker-compose.yml`), point `/music`
at the same library your server reads, then:

```bash
docker compose run --rm lyricarr            # one pass over the library
```

- CPU by default (works anywhere).
- **NVIDIA GPU**: use the `Dockerfile.cuda` variant and `--gpus all` — Demucs
  goes from minutes to seconds per track.
- Set `LYRICARR_INTERVAL=86400` and `restart: unless-stopped` to keep it topping
  up new music daily..

## Quick start (native — Mac/Linux, uses GPU)

```bash
pipx install .            # or: pip install .
brew install ffmpeg       # Linux: apt install ffmpeg
lyricarr /path/to/music   # auto-detects cuda / mps / cpu
```

## Configuration

Every flag has a `LYRICARR_*` env var (used by the Docker image):

| Flag | Env | Default | Meaning |
|------|-----|---------|---------|
| `library` | `LYRICARR_LIBRARY` | `/music` (Docker) | music library root |
| `--device` | `LYRICARR_DEVICE` | `auto` | `auto`/`cuda`/`mps`/`cpu` |
| `--lang` | `LYRICARR_LANG` | `en` | alignment language |
| `--overwrite` | `LYRICARR_OVERWRITE` | off | regenerate existing sidecars |
| `--no-separate` | `LYRICARR_NO_SEPARATE` | off | skip Demucs (faster, less accurate) |
| `--limit N` | `LYRICARR_LIMIT` | 0 | cap tracks per run |
| `--interval S` | `LYRICARR_INTERVAL` | 0 | seconds between scans; 0 = once |
| `--dry-run` | `LYRICARR_DRY_RUN` | off | report LRCLIB coverage only |

## Try it safely first

```bash
lyricarr /path/to/music --dry-run     # shows which tracks have lyrics available
lyricarr /path/to/music --limit 5     # generate a handful, then check your server
```

## Server support

| Server | Reads `.lrc` sidecar | Word-by-word |
|--------|:--:|:--:|
| Jellyfin | ✅ | ✅ parses into structured word cues |
| Plex | ✅ (after a library scan) | ✅ serves the raw `.lrc` unchanged — a client parses the word timing |
| Navidrome | ✅ | ❌ line-level only — it flattens to `{start, value}` per line (no per-word field) |

Notes:
- The sidecar file Lyricarr writes is always full word-level. Jellyfin and Plex
  preserve it (Jellyfin as parsed cues, Plex as the untouched file); Navidrome
  is the only one that downgrades to line-level, via its API.
- Plex needs a **library file scan** to detect newly-added sidecars, and its own
  apps may render line-level — but the full enhanced file is available to any
  client that reads the raw lyric stream.

## Notes & limits

- Not every track is on LRCLIB (instrumentals/obscure releases are skipped).
- Accuracy dips on dense harmonies, heavy overlap, and non-English without the
  right language model.
- Background/duet labelling isn't detected yet (roadmap).

## License

MIT.
