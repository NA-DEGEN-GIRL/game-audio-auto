import numpy as np
import pytest
import soundfile as sf

from game_audio.audio import audition, export_audio, measure, process_edit
from game_audio.models import EditRequest, Export
from game_audio.storage import digest


def test_trim_gain_and_fades_preserve_stereo_and_source(fixture_audio, tmp_path):
    original_hash = digest(fixture_audio)
    edit = EditRequest(name="edited", source=str(fixture_audio), start_seconds=0.1, end_seconds=0.9,
                       gain_db=-6, fade_in_seconds=0.01, fade_out_seconds=0.01)
    output = tmp_path / "edited.wav"
    report = process_edit(fixture_audio, output, edit)
    data, sr = sf.read(output, always_2d=True)
    assert data.shape == (38400, 2) and sr == 48000
    assert np.max(np.abs(data[[0, -1]])) == 0
    assert 0.09 < np.max(np.abs(data[:, 0])) < 0.11
    assert digest(fixture_audio) == original_hash
    assert report["listening_review"] == "unreviewed"


def test_loop_rotation_shortens_once_and_is_not_an_approval(fixture_audio, tmp_path):
    output = tmp_path / "loop.wav"
    report = process_edit(fixture_audio, output, EditRequest(name="loop", source=str(fixture_audio),
                                                           loop_crossfade_seconds=0.1))
    assert report["frames"] == 43200 and report["duration_seconds"] == 0.9
    assert report["boundary_step"] < 0.02
    assert report["listening_review"] == "unreviewed"


def test_pcm_clipping_is_not_silently_introduced(fixture_audio, tmp_path):
    with pytest.raises(ValueError, match="clip"):
        process_edit(fixture_audio, tmp_path / "bad.wav",
                     EditRequest(name="loud", source=str(fixture_audio), gain_db=30))
    float_file = tmp_path / "loud-float.wav"
    data, sr = sf.read(fixture_audio)
    sf.write(float_file, data * 10, sr, subtype="FLOAT")
    with pytest.raises(ValueError, match="clip"):
        export_audio(float_file, tmp_path / "clipped.wav", Export())


def test_audition_does_not_modify_masters(fixture_audio, tmp_path):
    before = digest(fixture_audio)
    output = tmp_path / "preview.wav"
    report = audition([fixture_audio], output, repeat=3, gap_seconds=0, target_lufs=-18)
    assert digest(fixture_audio) == before
    assert measure(output)["duration_seconds"] == 3
    assert report["labels"][0]["repeat"] == 3
    with pytest.raises(ValueError, match="exists"):
        audition([fixture_audio], output)
