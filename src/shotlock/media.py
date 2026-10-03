"""Media integrity inspection via ffprobe.

Frame count, duration, rational frame rate, and decode validity are HARD
constraints. When a value cannot be determined (e.g. nb_frames is unknown for
some containers), it is reported as "unavailable" — a check that did not run
must never appear as passed. Variable-frame-rate material and intentional
retiming are surfaced for human review rather than auto-failed.
"""
from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — ffprobe is invoked with a fixed argument list, never a shell
from fractions import Fraction
from typing import Any

UNAVAILABLE = "unavailable"


class FfprobeMissing(RuntimeError):
    """ffprobe is not on PATH; media inspection cannot run."""


def _require_ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise FfprobeMissing("ffprobe not found on PATH; install FFmpeg to inspect media")
    return path


def _parse_rate(value: str | None) -> Fraction | None:
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        return Fraction(value)
    except (ZeroDivisionError, ValueError):
        return None


def inspect_media(path: str) -> dict[str, Any]:
    """Inspect a media file. Returns a plain dict with honest 'unavailable' gaps."""
    ffprobe = _require_ffprobe()
    # nosec rationale: fixed argument list, no shell; the path argument is a
    # file name for ffprobe and cannot inject commands without shell interpolation.
    proc = subprocess.run(  # nosec B603
        [
            ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=codec_name,r_frame_rate,avg_frame_rate,nb_frames,duration",
            "-show_entries", "format=duration",
            "-of", "json",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        raise ValueError(f"ffprobe could not decode {path!r}: {proc.stderr.strip()}")

    data = json.loads(proc.stdout or "{}")
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}

    nb_frames = stream.get("nb_frames")
    frame_count: int | str
    if nb_frames in (None, "N/A"):
        frame_count = UNAVAILABLE  # unknown in this container; never guessed
    else:
        frame_count = int(nb_frames)

    duration = stream.get("duration") or fmt.get("duration")
    duration_s: float | str = UNAVAILABLE if duration in (None, "N/A") else float(duration)

    r_rate = _parse_rate(stream.get("r_frame_rate"))
    avg_rate = _parse_rate(stream.get("avg_frame_rate"))
    variable_rate = bool(r_rate and avg_rate and r_rate != avg_rate)

    return {
        "path": path,
        "codec": stream.get("codec_name") or UNAVAILABLE,
        "frame_count": frame_count,
        "duration_seconds": duration_s,
        "frame_rate": {"numerator": r_rate.numerator, "denominator": r_rate.denominator} if r_rate else UNAVAILABLE,
        "avg_frame_rate": {"numerator": avg_rate.numerator, "denominator": avg_rate.denominator} if avg_rate else UNAVAILABLE,
        "variable_frame_rate": variable_rate,
        "decode_valid": True,  # reaching here means ffprobe decoded the header/stream map
    }


def compare_integrity(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare two inspect_media() results against hard constraints.

    Returns {"hard_failures": [...], "review_signals": [...], "unavailable": [...]}.
    A failed hard constraint blocks acceptance. A review signal routes to a
    human. An unavailable measurement is disclosed, never counted as a pass.
    """
    hard_failures: list[str] = []
    review_signals: list[str] = []
    unavailable: list[str] = []

    for key in ("frame_count", "duration_seconds"):
        s, c = source.get(key), candidate.get(key)
        if s == UNAVAILABLE or c == UNAVAILABLE:
            unavailable.append(f"{key}: cannot be compared (unavailable in source or candidate)")
        elif s != c:
            hard_failures.append(f"{key} mismatch: source={s} candidate={c}")

    s_rate, c_rate = source.get("frame_rate"), candidate.get("frame_rate")
    if s_rate == UNAVAILABLE or c_rate == UNAVAILABLE:
        unavailable.append("frame_rate: cannot be compared (unavailable)")
    elif s_rate != c_rate:
        hard_failures.append(f"frame_rate mismatch: source={s_rate} candidate={c_rate}")

    for label, media in (("source", source), ("candidate", candidate)):
        if media.get("variable_frame_rate"):
            review_signals.append(f"{label} has variable frame rate; frame-accurate comparison needs explicit handling")

    return {"hard_failures": hard_failures, "review_signals": review_signals, "unavailable": unavailable}


def main(argv: list[str] | None = None) -> int:
    import sys

    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m shotlock.media <path>", file=sys.stderr)
        return 2
    try:
        print(json.dumps(inspect_media(args[0]), indent=2))
        return 0
    except (FfprobeMissing, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
