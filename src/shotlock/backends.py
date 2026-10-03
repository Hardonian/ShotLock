"""Inference backends behind a capability interface.

The reviewer must be useful without live generation: importing an existing
render is a first-class, fully working backend. Model backends (e.g. VOID
where resources and licensing permit) plug in behind the same interface later;
the documented VOID quick-start needs 40 GB+ VRAM, which no single GPU in the
current lab has, so no VOID adapter is shipped until it can be measured.

Capabilities are declared, not assumed: the pipeline validates inputs against
them before submitting anything. Retry limits and compute budgets are enforced
outside the language model (see pipeline.check_budget).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .media import FfprobeMissing, inspect_media


@dataclass(frozen=True)
class BackendCapabilities:
    name: str
    modes: tuple[str, ...]
    supports_masks: bool
    min_vram_gb: int | None
    notes: str = ""


class RenderBackend(Protocol):
    def capabilities(self) -> BackendCapabilities: ...

    def validate_input(self, path: str) -> list[str]:
        """Return problems that would make submission meaningless. Empty = ok."""
        ...

    def submit(self, path: str, intent: dict[str, Any]) -> dict[str, Any]:
        """Produce a candidate descriptor for the run record."""
        ...


class ImportedRenderBackend:
    """Import an existing render (the 'imported_render' run mode)."""

    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            name="imported",
            modes=("imported_render",),
            supports_masks=True,
            min_vram_gb=None,
            notes="no generation; ingests renders produced elsewhere",
        )

    def validate_input(self, path: str) -> list[str]:
        try:
            info = inspect_media(path)
        except FfprobeMissing as exc:
            return [str(exc)]
        except ValueError as exc:
            return [f"candidate is not decodable: {exc}"]
        problems: list[str] = []
        if info["decode_valid"] is not True:
            problems.append("candidate failed to decode")
        return problems

    def submit(self, path: str, intent: dict[str, Any]) -> dict[str, Any]:
        return {
            "backend": self.capabilities().name,
            "mode": "imported_render",
            "path": path,
            "intent_revision": intent["intent_revision"],
        }


REGISTRY: dict[str, RenderBackend] = {
    "imported": ImportedRenderBackend(),
}


def get_backend(name: str) -> RenderBackend:
    try:
        return REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown backend {name!r}; available: {sorted(REGISTRY)}"
        ) from None
