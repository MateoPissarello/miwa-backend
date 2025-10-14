"""Microkernel bootstrapper that wires FastAPI, infrastructure and plugins."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import Settings, get_settings, set_settings
from database import configure_database, get_db, get_session_factory

from .plugin import ServicePlugin
from .runtime import set_kernel


CapabilityFactory = Callable[["Kernel"], Any]


class Kernel:
    """Application runtime that coordinates shared infrastructure and plugins."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        debug: Optional[bool] = None,
        title: str = "MIWA Backend",
    ) -> None:
        self.settings = settings or get_settings()
        set_settings(self.settings)
        self.debug = bool(debug) if debug is not None else False

        self.app = FastAPI(debug=self.debug, title=title)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
        self._capability_factories: Dict[str, CapabilityFactory] = {}
        self._capability_cache: Dict[str, Any] = {}
        self._capability_singletons: Dict[str, bool] = {}
        self._registered_plugins: Dict[str, ServicePlugin] = {}

        set_kernel(self)
        self._bootstrap_infrastructure()

    # ------------------------------------------------------------------
    # Capability and dependency management
    # ------------------------------------------------------------------
    def register_capability(
        self,
        name: str,
        factory: CapabilityFactory,
        *,
        singleton: bool = True,
    ) -> None:
        """Register a lazily-created capability that other modules can resolve."""

        if name in self._capability_factories:
            raise ValueError(f"Capability '{name}' already registered")
        self._capability_factories[name] = factory
        self._capability_singletons[name] = singleton

    def resolve(self, name: str) -> Any:
        if name not in self._capability_factories:
            raise KeyError(f"Capability '{name}' is not registered")

        if name in self._capability_cache:
            return self._capability_cache[name]

        instance = self._capability_factories[name](self)
        if self._capability_singletons.get(name, True):
            self._capability_cache[name] = instance
        return instance

    # ------------------------------------------------------------------
    # Router helpers
    # ------------------------------------------------------------------
    def include_router(self, router: APIRouter, *, prefix: str = "") -> None:
        self.app.include_router(router, prefix=prefix)

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------
    def register_plugin(self, plugin: ServicePlugin) -> None:
        if plugin.name in self._registered_plugins:
            raise ValueError(f"Plugin '{plugin.name}' already registered")
        plugin.setup(self)
        self._registered_plugins[plugin.name] = plugin

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _bootstrap_infrastructure(self) -> None:
        """Initialise shared infrastructure managed by the kernel."""

        configure_database(self.settings, echo=self.debug)
        # Expose frequently used capabilities
        self.register_capability("settings", lambda _: self.settings)
        self.register_capability("db_session_factory", lambda _: get_session_factory())

    @property
    def get_db_dependency(self) -> Callable[..., Any]:
        """Expose the shared database dependency for FastAPI routers."""

        return get_db


__all__ = ["Kernel"]
