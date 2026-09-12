# Parody Maker

## Deploy to Render

`render.yaml` deploys the entire application as one Python web service: it serves
the existing static frontend and the FastAPI API from the same public URL.

1. In Render, create a Blueprint from this repository.
2. Keep the configured free plan, then provide `OPENAI_API_KEY` only in Render's
   encrypted environment-variable form. Do not commit it.
3. Deploy. Render runs `pip install -r requirements.txt` from `backend/` and
   starts `uvicorn main:app --host 0.0.0.0 --port $PORT`.

The service health check is `/health`; the frontend is `/`; API documentation is
`/docs`. `SINGING_ENGINE=demo` is set for deployment because the optional real
DiffSinger engine needs an authorized local model and cannot run on Render's
free web-service plan.

## Local lyric recognition

The optional song-recognition step compares lyrics entered by the user with the project-owned local catalog in `backend/data/songs.json`. It never fetches lyrics or song data from the internet.

Each catalog entry can reference a lyric file inside `backend/data/lyrics/`:

```json
{
  "id": "my-song",
  "title": "My Song",
  "artist": "My Artist",
  "lyrics_file": "my_song.txt"
}
```

The supplied catalog keeps its original demo entries and includes metadata for `barbie_girl.txt` and `baby.txt`. Add only lyric files you have the right to use; missing, empty, malformed, duplicate, or path-escaping entries are skipped safely. Restart the backend after editing the catalog.

`POST /api/recognize` accepts:

```json
{ "lyrics": "an excerpt entered by the user" }
```

It normalizes case, punctuation, apostrophe variants, whitespace, and Unicode formatting. The matcher compares the excerpt against precomputed line windows using phrase similarity (38%), fuzzy token coverage (30%), character trigrams (20%), and distinctive-token overlap (12%).

- `>= 0.85`: confirmed match, unless another song is within 0.06 confidence.
- `0.70–0.849`: possible candidates for the user to choose from.
- `< 0.70`: no confident match.

Run the backend from `backend/`:

```powershell
.\.venv311\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8012
```

The recognition result is metadata only. The lyrics the user entered remain the source for the existing parody-generation endpoint.

## Audio generation

After a parody is generated, the frontend requests `POST /api/audio/generate` with its parody lyrics and the local `demo-melody-001` timing plan. The backend loads `backend/data/demo_melody.json`, splits the parody into estimated syllables, aligns every syllable to the available notes, creates a neutral synthetic vowel voice, and renders a WAV in `backend/generated/`.

```json
{
  "parody_lyrics": "Exam week is calling\nCoffee keeps me going",
  "melody_id": "demo-melody-001"
}
```

The response contains a safe `/generated/parody_<id>.wav` URL, WAV format, and duration. FastAPI serves only files from `backend/generated/`; generated WAVs are ignored by Git.

The demo engine is deliberately lightweight and does not clone or imitate artists. It follows the demo melody's pitch and timing with a neutral, robotic vowel voice.

## Real AI singing setup

The optional real engine uses [DiffSinger](https://github.com/MoonInTheRiver/DiffSinger)'s singing-voice-synthesis workflow: a score with lyrics, MIDI pitch, onset, and note duration is given to an authorized local DiffSinger-compatible model. It was selected because it is specifically built for lyric + MIDI singing rather than speech TTS. The web project does not ship a model or voice; use an English-capable checkpoint you are licensed to use.

The integration is local (no API key is sent to the browser). DiffSinger itself normally needs a substantial model/checkpoint and is best run with a GPU; CPU inference may be possible but is much slower. Internet access is needed only to obtain the model and its dependencies, not while serving the application.

1. Install and verify an authorized DiffSinger-compatible model and a small wrapper command that reads the JSON score and writes 16-bit PCM WAV.
2. In `backend/.env`, keep the existing OpenAI setting and add:

```dotenv
SINGING_ENGINE=real
DIFFSINGER_COMMAND="C:\\path\\to\\python.exe C:\\path\\to\\diffsinger_wrapper.py --score {score_path} --output {output_path}"
```

`DIFFSINGER_COMMAND` must contain both placeholders exactly. Its wrapper receives JSON shaped like this, so it has all melody control data without receiving only prose:

```json
{
  "tempo": 100,
  "voice": "default",
  "notes": [{"syllable": "ex", "lyric": "Exam tomorrow", "pitch": 60, "start": 0.0, "duration": 0.4, "phrase": 0}]
}
```

Set `SINGING_ENGINE=demo` to use the bundled fallback. With `real`, missing or invalid local configuration returns a clear error; it never silently substitutes the robotic demo voice. There are no additional Python dependencies for the adapter itself. DiffSinger's own dependencies belong to the separate, authorized model installation.

Start the backend:

```powershell
cd C:\Users\USER\Downloads\Parody.mp3\Parody.mp3\backend
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8012
```

Generate or regenerate lyrics in the UI, then click **SING MY PARODY**. The API accepts the existing request plus optional `voice`:

```json
{"parody_lyrics":"Exam week is calling", "melody_id":"demo-melody-001", "voice":"default"}
```

Known limitation: this repository cannot include a general-purpose, human-like singing checkpoint or license it on your behalf. Configure a compatible authorized model before claiming a real-singer result. A higher-quality licensed English checkpoint, GPU inference, and an authorized instrumental mix will produce more realistic output.
