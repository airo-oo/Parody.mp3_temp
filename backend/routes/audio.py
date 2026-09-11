"""HTTP endpoint for demo melody-aligned WAV generation."""

from fastapi import APIRouter, HTTPException, status

from models import AudioGenerationRequest, AudioGenerationResponse
from services.audio.audio_pipeline import AudioConfigurationError, AudioPipelineError, generate_audio


router = APIRouter(prefix="/api/audio", tags=["audio"])


@router.post("/generate", response_model=AudioGenerationResponse)
def generate_parody_audio(request: AudioGenerationRequest) -> AudioGenerationResponse:
    try:
        generated = generate_audio(request.parody_lyrics, request.melody_id, request.voice)
        return AudioGenerationResponse(
            audio_url=generated.url,
            format=generated.format,
            duration=generated.duration,
            engine=generated.engine,
        )
    except AudioConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except AudioPipelineError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The audio file could not be generated.",
        ) from error
