"""HTTP API for local-catalog lyric recognition."""

from fastapi import APIRouter

from models import RecognitionRequest, RecognitionResponse
from services.song_recognizer import SongRecognizer


router = APIRouter(prefix="/api", tags=["recognition"])
recognizer = SongRecognizer()


@router.post("/recognize", response_model=RecognitionResponse)
def recognize_song(request: RecognitionRequest) -> RecognitionResponse:
    return recognizer.recognize(request.lyrics)
