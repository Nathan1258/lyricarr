from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def pick_device(requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _fmt_tag(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    centi = int(round(seconds * 100))
    m, centi = divmod(centi, 6000)
    s, centi = divmod(centi, 100)
    return f"{m:02d}:{s:02d}.{centi:02d}"


def separate_vocals(audio: Path, device: str, work: Path) -> Path:
    """Demucs two-stem vocal isolation, cached. Falls back to CPU if the
    requested device is unsupported for Demucs."""
    work.mkdir(parents=True, exist_ok=True)
    cache = work / f"{audio.stem}.vocals.wav"
    if cache.exists():
        return cache
    tmp = work / "_demucs"
    for d in (device, "cpu"):
        try:
            subprocess.run([sys.executable, "-m", "demucs", "--two-stems", "vocals",
                            "-n", "htdemucs", "-d", d, "-o", str(tmp), str(audio)],
                           check=True, capture_output=True)
            break
        except subprocess.CalledProcessError:
            if d == "cpu":
                raise
    (tmp / "htdemucs" / audio.stem / "vocals.wav").replace(cache)
    return cache


def generate_elrc(audio: Path, lines: list[tuple[float | None, str]],
                  device: str, work: Path, lang: str = "en",
                  separate: bool = True) -> str | None:
    """Align lyric `lines` to `audio` and return an enhanced-LRC string."""
    import whisperx

    src = separate_vocals(audio, device, work) if separate else audio
    align_device = device if device in ("cuda", "cpu") else "mps"
    audio_arr = whisperx.load_audio(str(src))
    model, meta = whisperx.load_align_model(language_code=lang, device=align_device)

    segs = []
    for i, (t, text) in enumerate(lines):
        start = t if t is not None else 0.0
        nxt = lines[i + 1][0] if i + 1 < len(lines) else None
        end = nxt if (nxt is not None and nxt > start) else start + 8.0
        segs.append({"start": start, "end": end, "text": text})

    aligned = whisperx.align(segs, model, meta, audio_arr, align_device,
                             return_char_alignments=False)

    out = ["[tool:lyricarr]"]
    for seg in aligned.get("segments", []):
        words = [w for w in seg.get("words", []) if w.get("word")]
        if not words:
            continue
        starts = [w["start"] for w in words if w.get("start") is not None]
        line_start = starts[0] if starts else seg.get("start", 0.0)
        chunk = f"[{_fmt_tag(line_start)}]"
        last = line_start
        for w in words:
            ts = w.get("start")
            ts = last if ts is None else ts
            last = ts
            chunk += f"<{_fmt_tag(ts)}>{w['word']}"
        out.append(chunk)
    return "\n".join(out) + "\n" if len(out) > 1 else None
