"""OpenAI integration. This module is the only place that knows about the SDK."""

import os

from dotenv import load_dotenv
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI

from models import ParodyRequest, ParodyResponse
from services.demo import generate_demo_parody
from services.parody_generator import ParodyDraft, generate_with_llm

load_dotenv()


class LLMConfigurationError(Exception):
    """Raised when the server is missing its OpenAI configuration."""


class LLMGenerationError(Exception):
    """Raised when OpenAI cannot provide a valid parody response."""


def is_ai_configured() -> bool:
    """Return whether this process can call OpenAI."""
    api_key = os.getenv("OPENAI_API_KEY")
    return bool(api_key and api_key != "your_key_here")


def generate_parody(request: ParodyRequest) -> ParodyResponse:
    """Generate and validate structured parody content through the Responses API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise LLMConfigurationError("OPENAI_API_KEY is missing. Add it to backend/.env")

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        def request_draft(messages: list[dict[str, str]]) -> ParodyDraft:
            response = client.responses.parse(model=model, input=messages, text_format=ParodyDraft)
            result = response.output_parsed
            if result is None:
                raise LLMGenerationError("OpenAI returned no structured parody result.")
            return result

        return generate_with_llm(request, request_draft)
    except (APIConnectionError, AuthenticationError, APIError) as error:
        raise LLMGenerationError("OpenAI request failed.") from error
    except Exception as error:
        if isinstance(error, LLMGenerationError):
            raise
        raise LLMGenerationError("OpenAI returned an invalid parody result.") from error
