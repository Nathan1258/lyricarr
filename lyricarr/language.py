from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException, detect

DetectorFactory.seed = 0


def detect_language(lines: list[tuple[float, str]]) -> str | None:
    text = " ".join(body for _, body in lines if body)
    try:
        return detect(text).split("-")[0]
    except LangDetectException:
        return None


def alignable(lang: str) -> bool:
    from whisperx.alignment import DEFAULT_ALIGN_MODELS_HF, DEFAULT_ALIGN_MODELS_TORCH

    return lang in DEFAULT_ALIGN_MODELS_TORCH or lang in DEFAULT_ALIGN_MODELS_HF
