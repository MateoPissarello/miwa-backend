# -*- coding: utf-8 -*-
"""Translation service plugin for handling video translations."""

from __future__ import annotations

from kernel import Kernel
from kernel.plugin import ServicePlugin

from .router import router


class TranslationPlugin(ServicePlugin):
    """Plugin for video translation functionality."""

    name = "translations"

    def setup(self, kernel: Kernel) -> None:
        """Register the translation service routes with the kernel."""
        # El router ya define su propio prefix/tags; solo lo registramos.
        kernel.include_router(router)


__all__ = ["TranslationPlugin"]
