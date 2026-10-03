"""Synchronized source/candidate viewer (week 1 deliverable).

Generates a self-contained viewer.html into a review package: source and
candidate on the same frame clock, frame-exact stepping (rational frame rate,
never decimal), an overlay of the approved edit region, A/B audio toggle, and
findings that seek to their frame ranges. Gaps (missing checks, unknown rates)
are shown as unavailable — never as green.

The page is static HTML+JS with no external dependencies: it opens from disk
without this application or any server running.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any

_UNAVAILABLE = "unavailable"


def _media_copy(path: str | Path, out_dir: Path, name: str) -> str:
    dest = out_dir / f"{name}{Path(path).suffix}"
    shutil.copy2(path, dest)
    return dest.name


def _region_config(intent: dict[str, Any]) -> dict[str, Any]:
    region = intent.get("allowed_edit_region") or {}
    config: dict[str, Any] = {"kind": region.get("kind", _UNAVAILABLE)}
    if region.get("kind") == "bbox_per_frame" and all(
        isinstance(region.get(k), (int, float)) for k in ("x", "y", "width", "height")
    ):
        config["bbox"] = {k: region[k] for k in ("x", "y", "width", "height")}
        config["boxes"] = region.get("boxes", [])
    else:
        config["bbox"] = None  # shown as "region not machine-readable" in the UI
    return config


def generate_viewer(
    report: dict[str, Any],
    intent: dict[str, Any],
    source_path: str | Path,
    candidate_path: str | Path,
    out_dir: str | Path,
) -> dict[str, Any]:
    """Write viewer.html plus media copies. Returns the viewer manifest entry."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    source_name = _media_copy(source_path, out, "viewer_source")
    candidate_name = _media_copy(candidate_path, out, "viewer_candidate")

    rate = intent.get("frame_rate") or {}
    fps = {
        "numerator": rate.get("numerator") if isinstance(rate.get("numerator"), int) else None,
        "denominator": rate.get("denominator") if isinstance(rate.get("denominator"), int) else None,
    }
    if not fps["numerator"] or not fps["denominator"]:
        fps = {"numerator": None, "denominator": None}

    config = {
        "report_id": report["report_id"],
        "run_id": report["run_id"],
        "intent_revision": report["intent_revision"],
        "source": source_name,
        "candidate": candidate_name,
        "frame_rate": fps,
        "frame_range": intent.get("frame_range", {}),
        "edit_region": _region_config(intent),
        "findings": [
            {
                "finding_id": f.get("finding_id"),
                "constraint": (f.get("constraint") or {}).get("kind"),
                "class": (f.get("constraint") or {}).get("class"),
                "severity": f.get("severity"),
                "frame_range": f.get("frame_range"),
                "note": (f.get("uncertainty") or {}).get("note"),
            }
            for f in report.get("findings", [])
        ],
        "missing_checks": report.get("missing_checks", []),
    }
    (out / "viewer-config.json").write_text(json.dumps(config, indent=2, sort_keys=True))
    (out / "viewer.html").write_text(_render_page(config))
    return {
        "status": "exported",
        "path": "viewer.html",
        "media": {"source": source_name, "candidate": candidate_name},
    }


def _render_page(config: dict[str, Any]) -> str:
    payload = html.escape(json.dumps(config), quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>ShotLock synchronized review — {html.escape(str(config['report_id']))}</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 1rem; background: #111; color: #eee; }}
 .pane {{ position: relative; display: inline-block; width: 49%; vertical-align: top; }}
 .pane h3 {{ margin: .3rem 0; font-size: .95rem; font-weight: 600; }}
 video {{ width: 100%; background: #000; display: block; }}
 canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: auto; pointer-events: none; }}
 .bar {{ margin: .8rem 0; display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }}
 button {{ padding: .45rem .9rem; font-size: .95rem; cursor: pointer; }}
 .badge {{ padding: .25rem .6rem; border-radius: .4rem; font-size: .8rem; }}
 .ok {{ background: #12401b; }} .fail {{ background: #5c1a1a; }} .unavail {{ background: #5b4a16; }}
 #frame {{ font-variant-numeric: tabular-nums; min-width: 11rem; }}
 .warn {{ background: #5b4a16; padding: .6rem .8rem; margin: .6rem 0; border-radius: .4rem; }}
 .findings li {{ cursor: pointer; }} .findings li:hover {{ text-decoration: underline; }}
 .meta {{ color: #aaa; font-size: .8rem; }}
</style></head><body>
<h2 style="margin:.2rem 0">ShotLock synchronized review</h2>
<p class="meta">run {html.escape(str(config['run_id']))} · intent revision {html.escape(str(config['intent_revision']))}</p>
<div id="gaps" class="warn" hidden></div>
<div class="bar">
 <button id="play">Play / Pause</button>
 <button id="prev">◀ 1 frame</button>
 <button id="next">1 frame ▶</button>
 <button id="ab">A/B audio: <b id="abstate">source</b></button>
 <span id="frame">frame —</span>
 <span id="rate" class="badge unavail">frame rate unknown</span>
 <span id="region" class="badge ok">edit region shown</span>
</div>
<div class="pane"><h3>Source</h3><video id="vsrc" preload="auto"></video><canvas id="csrc"></canvas></div>
<div class="pane"><h3>Candidate</h3><video id="vcand" preload="auto" muted></video><canvas id="ccand"></canvas></div>
<h3>Findings (click to seek)</h3>
<ul class="findings" id="findings"></ul>
<h3>Checks that did NOT run</h3>
<ul id="missing"></ul>

<script type="application/json" id="cfg">{payload}</script>
<script>
"use strict";
const cfg = JSON.parse(document.getElementById("cfg").textContent);
const vsrc = document.getElementById("vsrc"), vcand = document.getElementById("vcand");
vsrc.src = cfg.source; vcand.src = cfg.candidate;

// frame clock: rational frame rate only; unknown rate degrades to time display
const fr = cfg.frame_rate;
const hasRate = fr.numerator && fr.denominator;
const frameDur = hasRate ? fr.denominator / fr.numerator : null;
const rateBadge = document.getElementById("rate");
if (hasRate) {{ rateBadge.textContent = fr.numerator + "/" + fr.denominator + " fps"; rateBadge.className = "badge ok"; }}

const gaps = document.getElementById("gaps");
const missing = document.getElementById("missing");
(cfg.missing_checks || []).forEach(m => {{
  const li = document.createElement("li");
  li.textContent = m.check + ": " + m.reason;
  missing.appendChild(li);
}});
if ((cfg.missing_checks || []).length) {{
  gaps.hidden = false;
  gaps.textContent = (cfg.missing_checks.length) + " check(s) did not run — nothing here is a pass: "
    + cfg.missing_checks.map(m => m.check).join(", ");
}}

// findings list
const flist = document.getElementById("findings");
(cfg.findings || []).forEach(f => {{
  const li = document.createElement("li");
  const r = f.frame_range || {{}};
  li.textContent = (f.finding_id || "?") + " · " + (f.constraint || "") + " [" + (f.class || "") + "] · frames "
    + (r.start ?? "?") + "–" + (r.end_exclusive ?? "?") + " · " + (f.severity || "") + " — " + (f.note || "");
  li.onclick = () => {{
    if (hasRate && r.start != null) seekToFrame(r.start);
    else if (r.start != null) vsrc.currentTime = r.start * 0.5; // best effort, labeled below
  }};
  flist.appendChild(li);
}});

function currentFrame() {{ return hasRate ? Math.round(vsrc.currentTime / frameDur) : null; }}
function seekToFrame(n) {{ if (hasRate) {{ vsrc.currentTime = n * frameDur; vcand.currentTime = n * frameDur; }} }}

document.getElementById("frame").textContent = hasRate ? "frame —" : "frame — (rate unknown: time only)";

// synchronization loop: bind candidate to source at sub-frame tolerance
let playing = false;
function sync() {{
  if (!vsrc.paused && vcand.paused) vcand.play().catch(() => {{}});
  const drift = Math.abs(vsrc.currentTime - vcand.currentTime);
  if (drift > (frameDur ? frameDur / 2 : 0.04)) vcand.currentTime = vsrc.currentTime;
  drawOverlay("csrc"); drawOverlay("ccand");
  const n = currentFrame();
  document.getElementById("frame").textContent = hasRate
    ? ("frame " + n + "  (" + vsrc.currentTime.toFixed(3) + "s)")
    : ("time " + vsrc.currentTime.toFixed(3) + "s (rate unknown: frame index unavailable)");
  requestAnimationFrame(sync);
}}
requestAnimationFrame(sync);

document.getElementById("play").onclick = () => {{
  if (vsrc.paused) {{ vsrc.play(); vcand.play().catch(() => {{}}); }}
  else {{ vsrc.pause(); vcand.pause(); }}
}};
document.getElementById("prev").onclick = () => step(-1);
document.getElementById("next").onclick = () => step(1);
function step(d) {{
  vsrc.pause(); vcand.pause();
  if (hasRate) seekToFrame(currentFrame() + d);
  else {{ vsrc.currentTime = Math.max(0, vsrc.currentTime + d * 0.5); vcand.currentTime = vsrc.currentTime; }}
}}
document.addEventListener("keydown", e => {{
  if (e.key === "ArrowLeft") step(-1);
  if (e.key === "ArrowRight") step(1);
  if (e.key === " ") {{ e.preventDefault(); document.getElementById("play").click(); }}
}});

// A/B audio toggle
let audioSide = "source";
document.getElementById("ab").onclick = () => {{
  audioSide = audioSide === "source" ? "candidate" : "source";
  vsrc.muted = audioSide !== "source";
  vcand.muted = audioSide !== "candidate";
  document.getElementById("abstate").textContent = audioSide;
}};

// approved edit region overlay
const regionBadge = document.getElementById("region");
if (!cfg.edit_region || !cfg.edit_region.bbox) {{
  regionBadge.textContent = "edit region: not machine-readable (shown as unavailable)";
  regionBadge.className = "badge unavail";
}}
function drawOverlay(id) {{
  const canvas = document.getElementById(id);
  const video = id === "csrc" ? vsrc : vcand;
  if (!video.videoWidth) return;
  if (canvas.width !== video.videoWidth) {{ canvas.width = video.videoWidth; canvas.height = video.videoHeight; }}
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const reg = cfg.edit_region;
  if (!reg || !reg.bbox) return;
  let box = reg.bbox;
  for (const b of (reg.boxes || [])) {{
    const n = currentFrame();
    if (n != null && b.frame_start <= n && n < b.frame_end_exclusive) box = b;
  }}
  ctx.strokeStyle = "#38f"; ctx.lineWidth = Math.max(2, canvas.width / 320);
  ctx.strokeRect(box.x, box.y, box.width, box.height);
  ctx.fillStyle = "rgba(56,136,255,0.12)";
  ctx.fillRect(box.x, box.y, box.width, box.height);
}}
</script></body></html>"""
