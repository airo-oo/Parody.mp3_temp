const lyricsInput = document.querySelector("#lyrics");
const count = document.querySelector("#character-count");
const chaos = document.querySelector("#chaos");
const chaosValue = document.querySelector("#chaos-value");
const chaosCaption = document.querySelector("#chaos-caption");
const form = document.querySelector("#parody-form");
const ruinButton = form.querySelector(".ruin-button");
const copyButton = document.querySelector("#copy-button");
const regenerateButton = document.querySelector("#regenerate-button");
const editButton = document.querySelector("#edit-button");
const lyricsDisplay = document.querySelector("#parody-lyrics");
const titleDisplay = document.querySelector("#parody-title");
const descriptionDisplay = document.querySelector("#parody-description");
const toast = document.querySelector("#toast");
const serviceStatus = document.querySelector("#service-status");
const audioStatus = document.querySelector("#audio-status");
const singButton = document.querySelector("#sing-button");
const generatedAudio = document.querySelector("#generated-audio");
const downloadAudioButton = document.querySelector("#download-audio-button");
const identifySongButton = document.querySelector("#identify-song-button");
const detectedLabel = document.querySelector("#detected-label");
const recognizedTitle = document.querySelector("#recognized-title");
const recognizedArtist = document.querySelector("#recognized-artist");
const recognitionCandidates = document.querySelector("#recognition-candidates");
const recognitionNote = document.querySelector("#recognition-note");
const useSongButton = document.querySelector("#use-song-button");
const API_URL = window.PARODY_API_URL || "http://127.0.0.1:8012/api/parody";
const STATUS_URL = API_URL.replace(/\/parody$/, "/status");
const RECOGNITION_URL = API_URL.replace(/\/parody$/, "/recognize");
const AUDIO_URL = API_URL.replace(/\/api\/parody$/, "/api/audio/generate");
const API_ORIGIN = API_URL.replace(/\/api\/parody$/, "");
let hasGenerated = false;
let serviceRetryTimer;
let recognizedSong = null;
let confirmedSong = null;
let audioState = "IDLE";

function setAudioState(nextState, message) {
  audioState = nextState;
  audioStatus.textContent = message;
}

const captions = (value) =>
  value < 25
    ? "surprisingly responsible"
    : value < 50
      ? "mildly concerning"
      : value < 75
        ? "unnecessarily chaotic"
        : "absolutely unnecessary";
const showToast = (message) => {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2500);
};

async function refreshServiceStatus() {
  try {
    const response = await fetch(STATUS_URL);
    if (!response.ok) throw new Error();
    const data = await response.json();
    serviceStatus.textContent = data.message;
    serviceStatus.dataset.mode = data.generation_mode;
    window.clearTimeout(serviceRetryTimer);
    serviceRetryTimer = undefined;
  } catch {
    serviceStatus.textContent = "Parody server is offline — start the backend to generate lyrics.";
    serviceStatus.dataset.mode = "offline";
    if (!serviceRetryTimer) {
      serviceRetryTimer = window.setTimeout(() => {
        serviceRetryTimer = undefined;
        refreshServiceStatus();
      }, 5000);
    }
  }
}

async function generateAudio(parodyLyrics) {
  if (audioState === "PREPARING_MELODY" || audioState === "ALIGNING_LYRICS" || audioState === "GENERATING_SINGING" || audioState === "RENDERING_AUDIO") return;
  const stages = [
    ["PREPARING_MELODY", "🎼 Preparing melody…"],
    ["ALIGNING_LYRICS", "🎤 Preparing vocals…"],
    ["GENERATING_SINGING", "🎵 Singing…"],
    ["RENDERING_AUDIO", "💿 Rendering audio…"],
  ];
  let stageIndex = 0;
  generatedAudio.pause();
  generatedAudio.removeAttribute("src");
  generatedAudio.hidden = true;
  downloadAudioButton.hidden = true;
  singButton.disabled = true;
  singButton.querySelector("span").textContent = "SINGING…";
  setAudioState(...stages[stageIndex]);
  const stageTimer = window.setInterval(() => {
    stageIndex = Math.min(stageIndex + 1, stages.length - 1);
    setAudioState(...stages[stageIndex]);
  }, 700);
  try {
    const response = await fetch(AUDIO_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parody_lyrics: parodyLyrics, melody_id: "demo-melody-001", voice: "default" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.audio_url) throw new Error(data.detail || "AI singing could not be generated. Check the singing engine configuration.");
    const audioUrl = `${API_ORIGIN}${data.audio_url}`;
    generatedAudio.src = audioUrl;
    generatedAudio.load();
    generatedAudio.hidden = false;
    downloadAudioButton.href = audioUrl;
    downloadAudioButton.download = data.audio_url.split("/").pop() || "parody.wav";
    downloadAudioButton.hidden = false;
    const voiceLabel = data.engine === "real" ? "AI Singer" : "Demo Voice";
    setAudioState("AUDIO_READY", `✨ YOUR PARODY IS READY · ${data.duration.toFixed(1)}s WAV · Voice: ${voiceLabel}`);
  } catch (error) {
    setAudioState("ERROR", error.message || "AI singing could not be generated. Check the singing engine configuration.");
  } finally {
    window.clearInterval(stageTimer);
    singButton.disabled = false;
    singButton.querySelector("span").textContent = audioState === "ERROR" ? "TRY AGAIN" : "SING MY PARODY";
  }
}

const confidenceLabel = (confidence) => `${Math.round(confidence * 100)}% match`;

function resetRecognition(note = "Paste user-supplied lyrics, then search the local demo catalog.") {
  recognizedSong = null;
  confirmedSong = null;
  detectedLabel.textContent = "READY TO IDENTIFY";
  recognizedTitle.textContent = "Waiting for lyrics";
  recognizedArtist.textContent = "Your local catalog is ready.";
  recognitionNote.textContent = note;
  recognitionCandidates.replaceChildren();
  useSongButton.hidden = true;
  useSongButton.disabled = true;
}

function selectRecognizedSong(song, label = "SONG DETECTED") {
  recognizedSong = song;
  confirmedSong = null;
  detectedLabel.textContent = label;
  recognizedTitle.textContent = song.title;
  recognizedArtist.textContent = `${song.artist} · ${confidenceLabel(song.confidence)}`;
  recognitionNote.textContent = "Confirm this match, or keep generating from the lyrics you entered.";
  recognitionCandidates.replaceChildren();
  useSongButton.hidden = false;
  useSongButton.disabled = false;
}

function showCandidateChoices(candidates) {
  detectedLabel.textContent = "POSSIBLE MATCHES";
  recognizedTitle.textContent = "Choose a song";
  recognizedArtist.textContent = "The catalog found close results.";
  recognitionNote.textContent = "Pick one to confirm it, or continue without a recognized song.";
  recognitionCandidates.replaceChildren();
  candidates.forEach((song) => {
    const button = document.createElement("button");
    const text = document.createElement("span");
    const confidence = document.createElement("b");
    button.type = "button";
    button.className = "candidate-button";
    text.textContent = `${song.title} — ${song.artist}`;
    confidence.textContent = confidenceLabel(song.confidence);
    button.append(text, confidence);
    button.addEventListener("click", () => selectRecognizedSong(song, "POSSIBLE MATCH SELECTED"));
    recognitionCandidates.append(button);
  });
}

async function recognizeSong() {
  const lyrics = lyricsInput.value.trim();
  if (!lyrics) {
    showToast("Paste some lyrics before searching the catalog.");
    lyricsInput.focus();
    return;
  }
  identifySongButton.disabled = true;
  identifySongButton.querySelector("span").textContent = "SEARCHING…";
  detectedLabel.textContent = "SEARCHING CATALOG";
  recognitionNote.textContent = "Searching local songs from the project catalog…";
  try {
    const response = await fetch(RECOGNITION_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lyrics }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error();
    if (data.matched && data.song) {
      selectRecognizedSong(data.song);
      showToast("Song detected from the local catalog.");
    } else if (data.candidates?.length) {
      recognizedSong = null;
      confirmedSong = null;
      showCandidateChoices(data.candidates);
      showToast("The catalog found a few possible matches.");
    } else {
      resetRecognition("Couldn't confidently identify this song. You can still make a parody from your lyrics.");
      detectedLabel.textContent = "NO CONFIDENT MATCH";
      recognizedTitle.textContent = "No match found";
      recognizedArtist.textContent = data.confidence ? confidenceLabel(data.confidence) : "Try a longer lyric excerpt.";
      showToast("No confident catalog match found.");
    }
  } catch {
    resetRecognition("The local recognition service is unavailable. You can still make a parody.");
    detectedLabel.textContent = "RECOGNITION UNAVAILABLE";
    showToast("Couldn't search the song catalog right now.");
  } finally {
    identifySongButton.disabled = false;
    identifySongButton.querySelector("span").textContent = "IDENTIFY SONG";
  }
}

lyricsInput.addEventListener("input", () => {
  count.textContent = `${lyricsInput.value.length} / 5000`;
  if (recognizedSong || confirmedSong || recognitionCandidates.childElementCount) {
    resetRecognition("Lyrics changed. Search the catalog again when you are ready.");
  }
});
chaos.addEventListener("input", () => {
  const value = chaos.value;
  chaosValue.textContent = `${value}%`;
  chaosCaption.textContent = captions(value);
  chaos.style.background = `linear-gradient(to right, var(--cyan) ${value}%, #303947 ${value}%)`;
});
async function requestParody() {
  const lyrics = lyricsInput.value.trim();
  const theme = document.querySelector("#theme").value.trim();
  if (!lyrics || !theme) {
    showToast("Add both lyrics and a parody theme first.");
    return;
  }
  ruinButton.disabled = true;
  regenerateButton.disabled = true;
  ruinButton.querySelector(".button-text").textContent = "GENERATING...";
  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lyrics, theme, mood: document.querySelector("#mood").value, chaos: Number(chaos.value) }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Something went wrong while generating.");
    titleDisplay.textContent = data.title;
    descriptionDisplay.textContent = data.short_description;
    lyricsDisplay.textContent = data.parody_lyrics;
    lyricsDisplay.contentEditable = "false";
    editButton.innerHTML = "✎ <span>Edit</span>";
    hasGenerated = true;
    generatedAudio.pause();
    generatedAudio.removeAttribute("src");
    generatedAudio.hidden = true;
    downloadAudioButton.hidden = true;
    singButton.hidden = false;
    singButton.disabled = false;
    singButton.querySelector("span").textContent = "SING MY PARODY";
    setAudioState("PARODY_READY", "Parody lyrics are ready. Choose SING MY PARODY to create the audio.");
    if (data.generation_mode === "demo") {
      showToast("Preview parody ready. Add an OpenAI key for an AI-written version.");
    } else {
      showToast("Your masterpiece is ready. Taste not included.");
    }
    refreshServiceStatus();
    document.querySelector("#result").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (error) {
    showToast(error.message || "Could not reach the parody server. Please try again.");
  } finally {
    ruinButton.disabled = false;
    regenerateButton.disabled = false;
    ruinButton.querySelector(".button-text").textContent = "RUIN THIS SONG";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  requestParody();
});
copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(lyricsDisplay.innerText);
    showToast("Parody lyrics copied to clipboard.");
  } catch {
    showToast("Select the lyrics to copy them.");
  }
});
regenerateButton.addEventListener("click", async () => {
  regenerateButton.innerHTML = "◌ <span>Thinking...</span>";
  await requestParody();
  regenerateButton.innerHTML = "↻ <span>Regenerate</span>";
});

singButton.addEventListener("click", () => {
  if (hasGenerated) void generateAudio(lyricsDisplay.innerText);
});

identifySongButton.addEventListener("click", recognizeSong);
useSongButton.addEventListener("click", () => {
  if (!recognizedSong) return;
  confirmedSong = recognizedSong;
  detectedLabel.textContent = "SONG CONFIRMED";
  recognitionNote.textContent = "Confirmed for this session. Your entered lyrics remain the parody source.";
  useSongButton.hidden = true;
  showToast(`${confirmedSong.title} confirmed. Ready to ruin it.`);
});

editButton.addEventListener("click", () => {
  if (!hasGenerated) {
    lyricsInput.focus();
    showToast("Generate a parody first, then you can edit it here.");
    return;
  }
  const editing = lyricsDisplay.contentEditable === "true";
  lyricsDisplay.contentEditable = String(!editing);
  editButton.innerHTML = editing ? "✎ <span>Edit</span>" : "✓ <span>Done</span>";
  if (!editing) {
    lyricsDisplay.focus();
    showToast("Edit your parody directly, then choose Done.");
  } else {
    showToast("Your edits are ready to copy.");
  }
});

refreshServiceStatus();
