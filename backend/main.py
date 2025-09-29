import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.auth_service.router import router as auth_router
from services.auth_service.cognito_router import router as cognito_router
from services.s3_service.router import router as s3_router
from services.calendar_service.integration_router import router as calendar_integration_router
from services.calendar_service.calendar_router import router as calendar_router

app = FastAPI(
    debug=os.getenv("DEBUG", False),
    title="MIWA Backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "¡Bienvenido a la API de MIWA!"}


app.include_router(s3_router, prefix="/api")
app.include_router(cognito_router, prefix="/api")
app.include_router(calendar_integration_router, prefix="/api")
app.include_router(calendar_router, prefix="/api")
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
