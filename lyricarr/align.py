from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from .tags import TrackMeta

_MODELS: dict[tuple[str, str], tuple] = {}
_BRACKETS = str.maketrans("[]", "()")


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
    track_dir = tmp / "htdemucs" / audio.stem
    (track_dir / "vocals.wav").replace(cache)
    shutil.rmtree(track_dir, ignore_errors=True)
    return cache


def _align_words(text: str, start: float, end: float, model, meta,
                 audio_arr, device: str) -> list[dict]:
    import whisperx

    aligned = whisperx.align([{"start": start, "end": end, "text": text}],
                             model, meta, audio_arr, device,
                             return_char_alignments=False)
    return [w for seg in aligned.get("segments", [])
            for w in seg.get("words", []) if w.get("word", "").strip()]


def _align_model(lang: str, device: str) -> tuple:
    import whisperx

    key = (lang, device)
    if key not in _MODELS:
        if len(_MODELS) >= 2:
            _MODELS.pop(next(iter(_MODELS)))
        _MODELS[key] = whisperx.load_align_model(language_code=lang, device=device)
    return _MODELS[key]


def _header(meta: TrackMeta | None, duration: float) -> list[str]:
    fields = [("ar", meta.artist), ("al", meta.album), ("ti", meta.title)] if meta else []
    out = [f"[{k}:{' '.join(v.translate(_BRACKETS).split())}]"
           for k, v in fields if v and v.strip()]
    m, sec = divmod(int(round(duration)), 60)
    out += [f"[length:{m:02d}:{sec:02d}]", "[tool:lyricarr]"]
    return out


def _render_line(t: float, text: str, words: list[dict],
                 floor: float, spaced: bool) -> tuple[str, float]:
    starts = [w["start"] for w in words if w.get("start") is not None]
    if not starts:
        t = max(t, floor)
        return f"[{_fmt_tag(t)}]{text}", t
    last = max(starts[0], floor)
    chunk = f"[{_fmt_tag(last)}]"
    for w in words:
        ts = w.get("start")
        last = last if ts is None else max(ts, last)
        chunk += f"<{_fmt_tag(last)}>{w['word'].strip()}" + (" " if spaced else "")
    chunk = chunk.rstrip()
    end = words[-1].get("end")
    if end is not None and end > last:
        chunk += f"<{_fmt_tag(end)}>"
    return chunk, last


def generate_elrc(audio: Path, lines: list[tuple[float, str]],
                  device: str, work: Path, lang: str = "en",
                  separate: bool = True, keep_stems: bool = False,
                  meta: TrackMeta | None = None) -> str | None:
    """Align lyric `lines` to `audio` and return an enhanced-LRC string."""
    import whisperx
    from whisperx.alignment import LANGUAGES_WITHOUT_SPACES
    from whisperx.audio import SAMPLE_RATE

    src = separate_vocals(audio, device, work) if separate else audio
    try:
        align_device = "cuda" if device == "cuda" else "cpu"
        audio_arr = whisperx.load_audio(str(src))
        duration = len(audio_arr) / SAMPLE_RATE
        model, align_meta = _align_model(lang, align_device)
        spaced = lang not in LANGUAGES_WITHOUT_SPACES

        out = _header(meta, duration)
        floor = 0.0
        for i, (t, text) in enumerate(lines):
            if not text:
                floor = max(t, floor)
                out.append(f"[{_fmt_tag(floor)}]")
                continue
            end = next((n for n, _ in lines[i + 1:] if n > t), duration)
            words = (_align_words(text, t, end, model, align_meta, audio_arr, align_device)
                     if end > t else [])
            line, floor = _render_line(t, text, words, floor, spaced)
            out.append(line)
        return "\n".join(out) + "\n" if any(text for _, text in lines) else None
    finally:
        if separate and not keep_stems and src != audio:
            try:
                src.unlink()
            except OSError:
                pass
