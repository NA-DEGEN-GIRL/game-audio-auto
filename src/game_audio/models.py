from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Name = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")]
Provider = Literal["auto", "elevenlabs", "gemini", "stable_audio", "qwen", "ace_step"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class Export(StrictModel):
    sample_rate: Literal[16000, 22050, 24000, 32000, 44100, 48000, 96000] = 48000
    channels: Literal["preserve", "mono", "stereo"] = "preserve"
    subtype: Literal["PCM_16", "PCM_24", "FLOAT"] = "PCM_24"


class Playback(StrictModel):
    intent: Literal["once", "loop", "sequence", "unspecified"] = "once"
    spatial: Literal["2d", "3d", "unspecified"] = "unspecified"
    avoid_immediate_repeat: bool = True
    pitch_range: tuple[float, float] = (1.0, 1.0)
    gain_range_db: tuple[float, float] = (0.0, 0.0)
    max_voices: int | None = Field(None, ge=1)
    cooldown_ms: int | None = Field(None, ge=0)
    sync_anchor_seconds: float | None = Field(None, ge=0)
    notes: str = ""

    @model_validator(mode="after")
    def ranges(self):
        if self.pitch_range[0] <= 0 or self.pitch_range[0] > self.pitch_range[1]:
            raise ValueError("pitch_range must be positive and increasing")
        if self.gain_range_db[0] > self.gain_range_db[1]:
            raise ValueError("gain_range_db must be increasing")
        return self


class GenerateRequest(StrictModel):
    name: Name
    kind: Literal["sfx", "ambience", "dialogue", "music"]
    prompt: str = Field(min_length=1, max_length=5000)
    provider: Provider = "auto"
    model: str | None = None
    duration_seconds: float | None = Field(None, gt=0, le=600)
    variants: int = Field(1, ge=1, le=100)
    seed: int = Field(42, ge=0, le=4294967295)
    purpose: str = ""
    acceptance: list[str] = Field(default_factory=list)
    playback: Playback = Field(default_factory=Playback)
    export: Export = Field(default_factory=Export)
    # Dialogue prompt contains the exact spoken text, including intentional audio tags.
    voice_id: str | None = None
    language: str = "ko"
    instruction: str = ""
    # Unspecified preserves legacy routing; character means dialogue requiring acting.
    dialogue_role: Literal["unspecified", "character", "narration"] = "unspecified"
    reference_audio: str | None = None
    reference_text: str | None = None
    voice_mode: Literal["custom", "design", "clone"] = "custom"
    speaker: str = "Sohee"
    # Auto keeps other providers untouched and finishes Gemini dialogue.
    dialogue_processing: Literal["auto", "none", "density"] = "auto"
    # Music controls are sent only to backends that support them.
    bpm: int | None = Field(None, ge=30, le=300)
    key: str = ""
    instrumental: bool = True
    # Evidence for this request's actual use; does not grant account-wide music eligibility.
    music_eligibility_evidence: str = ""
    steps: int | None = Field(None, ge=1, le=200)
    prompt_influence: float = Field(0.3, ge=0, le=1)
    # Optional smaller user budget; no automatic additional takes/retries.
    max_credits: int | None = Field(None, ge=1)

    @model_validator(mode="after")
    def applicable_fields(self):
        if self.music_eligibility_evidence and (self.kind != "music" or self.provider not in ("auto", "elevenlabs")):
            raise ValueError("Music eligibility evidence applies to ElevenLabs music or auto music routing")
        if self.kind != "dialogue" and (self.voice_id or self.reference_audio or self.instruction):
            raise ValueError("Voice fields apply only to dialogue")
        if self.kind != "dialogue" and self.dialogue_role != "unspecified":
            raise ValueError("Dialogue role applies only to dialogue")
        if self.kind != "dialogue" and self.dialogue_processing not in ("auto", "none"):
            raise ValueError("Dialogue processing applies only to dialogue")
        if self.kind != "music" and (self.bpm is not None or self.key):
            raise ValueError("BPM/key apply only to music")
        if self.kind == "dialogue" and self.voice_mode == "clone" and not self.reference_audio:
            raise ValueError("Cloning requires a supplied reference_audio")
        if self.kind != "dialogue" and self.duration_seconds is None:
            raise ValueError("Set duration_seconds for effects, ambience and music")
        return self


class EditRequest(StrictModel):
    name: Name
    source: str
    source_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    parent_revision: str | None = None
    start_seconds: float = Field(0, ge=0)
    end_seconds: float | None = Field(None, gt=0)
    gain_db: float = Field(0, ge=-96, le=48)
    fade_in_seconds: float = Field(0, ge=0)
    fade_out_seconds: float = Field(0, ge=0)
    loop_crossfade_seconds: float = Field(0, ge=0)
    export: Export = Field(default_factory=Export)
    playback: Playback | None = None
    notes: str = ""

    @model_validator(mode="after")
    def trim(self):
        if self.end_seconds is not None and self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must follow start_seconds")
        return self


class ImportRequest(StrictModel):
    name: Name
    source: str
    source_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    kind: Literal["sfx", "ambience", "dialogue", "music"]
    provider: str = "supplied"
    model: str = "unknown"
    transport: Literal["supplied", "plugin", "sdk", "local"] = "supplied"
    request_id: str | None = None
    prompt: str = ""
    notes: str = ""
    purpose: str = ""
    export: Export = Field(default_factory=Export)
    playback: Playback = Field(default_factory=Playback)


class FinishDialogueRequest(StrictModel):
    name: Name
    source: str
    source_sha256: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    parent_revision: str | None = None
    preset: Literal["density"] = "density"
    low_shelf_db: float = Field(-2, ge=-6, le=0)
    presence_db: float = Field(1.5, ge=0, le=4.5)
    export: Export = Field(default_factory=Export)
    playback: Playback | None = None
    notes: str = ""


class LocalBackend(StrictModel):
    python: str
    project_root: str | None = None
    device: str = "auto"


class MusicChoice(StrictModel):
    provider: Literal["elevenlabs", "stable_audio", "ace_step"]
    model: str
    evidence_record: str


class Settings(StrictModel):
    mode: Literal["auto", "only_local"] = "auto"
    key_prompt: Literal["not_asked", "requested", "declined", "configured"] = "not_asked"
    elevenlabs_key_file: str = ".secrets/elevenlabs_api_key"
    gemini_key_file: str = ".secrets/gemini_api_key"
    elevenlabs_output_format: str = "mp3_44100_128"
    # This is an eligibility record, not a license grant.
    elevenlabs_music_eligible: bool = False
    elevenlabs_music_evidence: str = ""
    local_backends: dict[Literal["stable_audio", "qwen", "ace_step"], LocalBackend] = Field(
        default_factory=dict)
    music_defaults: dict[str, MusicChoice] = Field(default_factory=dict)
    gpu_lock: str = ".runtime/locks/inference.lock"
    ffmpeg: str | None = None
    huggingface_token_file: str | None = None


class Review(StrictModel):
    audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    listening: Literal["unreviewed", "pass", "needs_repair"] = "unreviewed"
    repetition: Literal["unreviewed", "pass", "needs_repair", "not_applicable"] = "unreviewed"
    integration: Literal["untested", "pass", "needs_repair", "not_applicable"] = "untested"
    method: str = ""
    listened_ranges_seconds: list[tuple[float, float]] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    untested: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def evidence_required(self):
        for start, end in self.listened_ranges_seconds:
            if start < 0 or end <= start:
                raise ValueError("Listening ranges must have 0 <= start < end")
        if self.listening != "unreviewed" and not (self.method and self.listened_ranges_seconds):
            raise ValueError("Listening decisions require actual method and listened ranges")
        if self.repetition in ("pass", "needs_repair") and not self.evidence:
            raise ValueError("Repetition review requires playback evidence")
        if self.integration in ("pass", "needs_repair") and not self.evidence:
            raise ValueError("Integration review requires project/playback evidence")
        return self
