"""Global runtime registry that exposes the active kernel instance."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .kernel import Kernel


_kernel: Optional["Kernel"] = None


def set_kernel(kernel: "Kernel") -> None:
    """Register the bootstrapped kernel so other modules can access it lazily."""

    global _kernel
    _kernel = kernel


def get_kernel() -> "Kernel":
    """Return the active kernel instance."""

    if _kernel is None:
        raise RuntimeError("Kernel has not been initialised yet")
    return _kernel


__all__ = ["get_kernel", "set_kernel"]
