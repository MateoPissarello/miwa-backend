"""Application entry point bootstrapping the microkernel and plugins."""

from __future__ import annotations

import os

from fastapi import FastAPI

from kernel import Kernel
from services.auth_service.plugin import AuthPlugin
from services.calendar_service.plugin import CalendarPlugin
from services.s3_service.plugin import S3Plugin


def _env_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.lower() in {"1", "true", "yes", "on"}


def create_kernel() -> Kernel:
    debug = _env_flag(os.getenv("DEBUG"))
    kernel = Kernel(debug=debug)
    kernel.register_plugin(S3Plugin())
    kernel.register_plugin(AuthPlugin())
    kernel.register_plugin(CalendarPlugin())
    return kernel


kernel = create_kernel()
app: FastAPI = kernel.app


@app.get("api/")
def root():
    return {"message": "¡Bienvenido a la API de MIWA!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
