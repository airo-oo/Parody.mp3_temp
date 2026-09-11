"""FastAPI entry point for Parody Maker's lyrics-only Phase 1 API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routes.audio import router as audio_router
from routes.parody import router as parody_router
from routes.recognition import router as recognition_router
from services.audio.audio_pipeline import GENERATED_DIRECTORY

app = FastAPI(title="Parody Maker API", version="0.1.0")

# Keep development origins explicit. Add a deployed frontend origin here later.
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(parody_router)
app.include_router(recognition_router)
app.include_router(audio_router)
GENERATED_DIRECTORY.mkdir(parents=True, exist_ok=True)
app.mount("/generated", StaticFiles(directory=GENERATED_DIRECTORY), name="generated")


@app.get("/health")
def health_check() -> dict[str, str]:
    """Small endpoint useful for checking that the API is running."""
    return {"status": "ok"}
