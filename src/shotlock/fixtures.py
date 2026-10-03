"""Deliberately injected defects — labeled TEST FIXTURES.

Per the brief: fixtures validate detectors and must be labeled as test
fixtures, kept separate from actual model outputs. Three canonical injections:

1. duplicated_frame        one frame appears twice (temporal integrity defect)
2. altered_audio           audio replaced with a different tone (audio policy defect)
3. localized_prop_change   a small region changes across a few frames (protected
                           region defect — the exact case the region check must
                           localize)

Each fixture writes a sidecar JSON recording the injected defect so no fixture
can ever be mistaken for real output.
"""
from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 — ffmpeg invoked with fixed argument lists, never a shell
from pathlib import Path
from typing import Any

FIXTURE_KIND = "TEST_FIXTURE_INJECTED_DEFECT"


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not installed; fixture generation unavailable")
    return path


def _run(args: list[str]) -> None:
    subprocess.run([_ffmpeg(), "-v", "error", "-y", *args], check=True, timeout=300)  # nosec B603


def _sidecar(path: Path, defect: str, parameters: dict[str, Any]) -> dict[str, Any]:
    record = {
        "kind": FIXTURE_KIND,
        "defect": defect,
        "parameters": parameters,
        "file": path.name,
        "note": "Detector-validation fixture. Not a model output.",
    }
    path.with_suffix(path.suffix + ".fixture.json").write_text(json.dumps(record, indent=2, sort_keys=True))
    return record


def inject_duplicated_frame(source_path: str | Path, out_dir: str | Path, at_frame: int = 12) -> dict[str, Any]:
    """Insert one duplicated video frame at at_frame (the previous frame repeats)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "fixture_duplicated_frame.mp4"
    filter_complex = (
        f"[0:v]trim=start_frame=0:end_frame={at_frame},setpts=PTS-STARTPTS[a];"
        f"[0:v]trim=start_frame={max(0, at_frame - 1)}:end_frame={at_frame},setpts=PTS-STARTPTS[b];"
        f"[0:v]trim=start_frame={at_frame},setpts=PTS-STARTPTS[c];"
        "[a][b][c]concat=n=3:v=1[outv]"
    )
    _run(["-i", str(source_path), "-filter_complex", filter_complex,
          "-map", "[outv]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac", str(dest)])
    return _sidecar(dest, "duplicated_frame", {"at_frame": at_frame, "repeats_frame": at_frame - 1})


def inject_altered_audio(source_path: str | Path, out_dir: str, tone_hz: int = 880) -> dict[str, Any]:
    """Replace the audio track with a different tone (video untouched)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "fixture_altered_audio.mp4"
    _run(["-i", str(source_path), "-f", "lavfi", "-i", f"sine=frequency={tone_hz}:duration=3600",
          "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", str(dest)])
    return _sidecar(dest, "altered_audio", {"tone_hz": tone_hz})


def inject_localized_prop_change(
    source_path: str | Path,
    out_dir: str | Path,
    *,
    x: int = 10,
    y: int = 10,
    width: int = 24,
    height: int = 24,
    frame_start: int = 12,
    frame_end_exclusive: int = 21,
) -> dict[str, Any]:
    """Paint a small box across a few frames — a localized prop change."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "fixture_localized_prop_change.mp4"
    enable = f"between(n\\,{frame_start}\\,{frame_end_exclusive - 1})"
    _run(["-i", str(source_path),
          "-vf", f"drawbox=x={x}:y={y}:w={width}:h={height}:color=red@1:t=fill:enable='{enable}'",
          "-c:v", "libx264", "-c:a", "copy", str(dest)])
    return _sidecar(dest, "localized_prop_change", {
        "x": x, "y": y, "width": width, "height": height,
        "frame_start": frame_start, "frame_end_exclusive": frame_end_exclusive,
    })


def inject_all(source_path: str | Path, out_dir: str | Path) -> list[dict[str, Any]]:
    """Generate the full labeled fixture set for detector validation."""
    return [
        inject_duplicated_frame(source_path, out_dir),
        inject_altered_audio(source_path, out_dir),
        inject_localized_prop_change(source_path, out_dir),
    ]
