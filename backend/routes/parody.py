"""Request validation and HTTP handling for parody generation."""

from fastapi import APIRouter, HTTPException, status
from models import ParodyRequest, ParodyResponse, ServiceStatus
from services.llm import LLMConfigurationError, LLMGenerationError, generate_parody, is_ai_configured

router = APIRouter(prefix="/api", tags=["parody"])


@router.get("/status", response_model=ServiceStatus)
def get_service_status() -> ServiceStatus:
    """Tell the client whether generation uses OpenAI or local preview mode."""
    if is_ai_configured():
        return ServiceStatus(status="ok", generation_mode="ai", message="AI parody generation is ready.")
    return ServiceStatus(
        status="ok",
        generation_mode="demo",
        message="OPENAI_API_KEY is missing. Add it to backend/.env",
    )


@router.post("/parody", response_model=ParodyResponse)
def create_parody(request: ParodyRequest) -> ParodyResponse:
    try:
        return generate_parody(request)
    except LLMConfigurationError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    except LLMGenerationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The parody writer could not finish that request. Please try again.",
        ) from error
