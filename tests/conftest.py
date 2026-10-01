from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


@pytest.fixture(autouse=True)
def no_real_credentials(monkeypatch):
    for key in ("ELEVENLABS_API_KEY", "ELEVEN_API_KEY", "ELEVENLABS_API_KEY_FILE",
                "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY_FILE"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fixture_audio(tmp_path: Path):
    # Maintenance fixture, not a generated natural sound or listening-quality benchmark.
    sr = 48000
    time = np.arange(sr, dtype=np.float64) / sr
    data = np.column_stack((0.2 * np.sin(time * 2 * np.pi * 200),
                            0.1 * np.cos(time * 2 * np.pi * 300)))
    file = tmp_path / "source.wav"
    sf.write(file, data, sr, subtype="FLOAT")
    return file
