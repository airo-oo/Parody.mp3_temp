"""Compatibility entry point for deterministic local parody previews."""

from models import ParodyRequest, ParodyResponse
from services.parody_generator import generate_preview_parody


def generate_demo_parody(request: ParodyRequest) -> ParodyResponse:
    return generate_preview_parody(request)
