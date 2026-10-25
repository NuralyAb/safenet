"""Audio/frame extraction from collected video (ffmpeg).

Runs in the network-isolated processing-worker (untrusted media, no egress).
Command builders are pure (unit-tested); the actual ffmpeg run is integration.
Best-effort: extraction failure never breaks the pipeline — the stage just
proceeds without that modality.
"""
from __future__ import annotations

import os
import subprocess
import tempfile


def ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def ffmpeg_audio_cmd(src: str, dst: str) -> list[str]:
    # strip video (-vn), encode mp3 for Whisper
    return ["ffmpeg", "-y", "-i", src, "-vn", "-acodec", "libmp3lame", "-q:a", "4", dst]


def ffmpeg_frame_cmd(src: str, dst: str, at: float = 1.0) -> list[str]:
    # single representative frame at `at` seconds
    return ["ffmpeg", "-y", "-ss", str(at), "-i", src, "-frames:v", "1", dst]


# Default sampling offsets (seconds) for multi-frame analysis of short social
# videos. A banner / wallet shown anywhere in the clip — not just at 1.0s — must
# be caught, so we sample several points across the timeline.
def frame_offsets(count: int, step: float = 3.0, start: float = 1.0) -> list[float]:
    return [round(start + i * step, 3) for i in range(max(1, count))]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, capture_output=True, check=True)


def extract_audio(video: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.mp4"), os.path.join(d, "out.mp3")
        with open(src, "wb") as fh:
            fh.write(video)
        _run(ffmpeg_audio_cmd(src, dst))
        with open(dst, "rb") as fh:
            return fh.read()


def extract_frame(video: bytes, at: float = 1.0) -> bytes:
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "in.mp4"), os.path.join(d, "frame.jpg")
        with open(src, "wb") as fh:
            fh.write(video)
        _run(ffmpeg_frame_cmd(src, dst, at))
        with open(dst, "rb") as fh:
            return fh.read()


def extract_frames(video: bytes, *, count: int = 4, offsets: list[float] | None = None) -> list[bytes]:
    """Extract several representative frames across the clip (best-effort per offset).

    The video is written once; each offset is grabbed independently so a frame
    past the clip's end (or a decode hiccup) is skipped rather than failing the lot.
    """
    offs = offsets if offsets is not None else frame_offsets(count)
    frames: list[bytes] = []
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in.mp4")
        with open(src, "wb") as fh:
            fh.write(video)
        for i, at in enumerate(offs):
            dst = os.path.join(d, f"frame_{i}.jpg")
            try:
                _run(ffmpeg_frame_cmd(src, dst, at))
                with open(dst, "rb") as fh:
                    frames.append(fh.read())
            except Exception:  # noqa: BLE001 — offset past end / decode error -> skip
                continue
    return frames


def enrich_with_media(collected: dict, fetch_media=None, *, at: float = 1.0,
                      frames: int = 1) -> dict:
    """Add audio + frame(s) to `collected` from the stored original (best-effort).

    `fetch_media(raw_key) -> bytes` reads the original from MinIO. No-op if ffmpeg
    is unavailable or the needed modalities are already present. When `frames` > 1
    a list of frames lands in `images` (and `image` stays the first frame for the
    single-frame consumers, e.g. biometrics).
    """
    have_frames = bool(collected.get("image")) and (frames <= 1 or bool(collected.get("images")))
    if collected.get("audio") and have_frames:
        return collected
    if not ffmpeg_available():
        return collected

    media = collected.get("media")            # inline (ad-hoc upload) ...
    if not media and fetch_media is not None:
        media = fetch_media(collected["raw_key"])   # ... or fetched from MinIO (pipeline)
    if not media:
        return collected
    out = dict(collected)
    if not out.get("audio"):
        try:
            out["audio"] = extract_audio(media)
        except Exception:  # noqa: BLE001
            pass
    if frames > 1 and not out.get("images"):
        try:
            imgs = extract_frames(media, count=frames)
        except Exception:  # noqa: BLE001
            imgs = []
        if imgs:
            out["images"] = imgs
            out.setdefault("image", imgs[0])
    if not out.get("image"):
        try:
            out["image"] = extract_frame(media, at)
        except Exception:  # noqa: BLE001
            pass
    return out
