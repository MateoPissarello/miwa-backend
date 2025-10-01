"""Plugin contract definition for services that participate in the kernel."""

from __future__ import annotations

from abc import ABC, abstractmethod

if False:  # pragma: no cover - imported for type checking only
    from .kernel import Kernel


class ServicePlugin(ABC):
    """Base contract that every service plugin must implement."""

    name: str

    @abstractmethod
    def setup(self, kernel: "Kernel") -> None:
        """Hook invoked by the kernel during bootstrapping."""


__all__ = ["ServicePlugin"]
