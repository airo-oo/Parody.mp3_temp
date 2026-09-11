"""Shared Pydantic models for the parody API and LLM service."""

from pydantic import BaseModel, Field, field_validator


class ParodyRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=5000)
    theme: str = Field(min_length=1, max_length=200)
    mood: str = Field(min_length=1, max_length=80)
    chaos: int = Field(ge=0, le=100)

    @field_validator("lyrics", "theme", "mood")
    @classmethod
    def cannot_be_blank(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("This field cannot be blank.")
        return cleaned_value


class ParodyResponse(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    parody_lyrics: str = Field(min_length=1, max_length=12000)
    short_description: str = Field(min_length=1, max_length=500)
    generation_mode: str = Field(default="demo", pattern="^(demo|ai)$")


class ServiceStatus(BaseModel):
    status: str
    generation_mode: str = Field(pattern="^(demo|ai)$")
    message: str


class RecognitionRequest(BaseModel):
    lyrics: str = Field(min_length=1, max_length=5000)

    @field_validator("lyrics")
    @classmethod
    def recognition_lyrics_cannot_be_blank(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Lyrics cannot be blank.")
        return cleaned_value


class SongMatch(BaseModel):
    id: str
    title: str
    artist: str
    confidence: float = Field(ge=0, le=1)


class RecognitionResponse(BaseModel):
    matched: bool
    confidence: float = Field(ge=0, le=1)
    song: SongMatch | None = None
    candidates: list[SongMatch] = Field(default_factory=list)


class AudioGenerationRequest(BaseModel):
    parody_lyrics: str = Field(min_length=1, max_length=12000)
    melody_id: str = Field(default="demo-melody-001", min_length=1, max_length=100)
    voice: str = Field(default="default", min_length=1, max_length=80)

    @field_validator("parody_lyrics")
    @classmethod
    def audio_lyrics_cannot_be_blank(cls, value: str) -> str:
        cleaned_value = value.strip()
        if not cleaned_value:
            raise ValueError("Parody lyrics cannot be blank.")
        return cleaned_value


class AudioGenerationResponse(BaseModel):
    success: bool = True
    audio_url: str
    format: str = "wav"
    duration: float = Field(gt=0)
    engine: str = Field(pattern="^(demo|real)$")
