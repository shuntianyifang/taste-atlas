"""Verify actual codecs and measurement algorithms using generated signals."""
import json
from pathlib import Path
import subprocess
import numpy as np
import soundfile as sf
import imageio_ffmpeg
from analyze import ROOT, analyze, decode, metadata

work = ROOT / 'selftest'
work.mkdir(exist_ok=True)
sr = 44100
time = np.arange(sr * 8) / sr
tone = 0.2 * np.sin(2 * np.pi * 440 * time)
sf.write(work / 'tone.wav', tone, sr)
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
for extension, codec in [('mp3', 'libmp3lame'), ('flac', 'flac')]:
    subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-y', '-i', str(work / 'tone.wav'), '-c:a', codec, str(work / ('tone.' + extension))], check=True)
    decoded, rate = decode(work / ('tone.' + extension), 1, 3)
    assert abs(len(decoded) / rate - 3) < 0.05
    assert metadata(work / ('tone.' + extension))['channels'] == 1
result = analyze(work / 'tone.flac', 1, 3, True, work / 'report', semantic_mode='off')
assert abs(result['estimated_dominant_pitch']['median_hz'] - 440) < 3
assert result['estimated_bpm'] is None  # Do not report a tempo for this short pure-tone test.
assert (work / 'report' / 'analysis.png').stat().st_size > 1000

import librosa
clicks = librosa.clicks(times=np.arange(.5, 20, .5), sr=22050, length=22050 * 20)
tempo, beats = librosa.beat.beat_track(y=clicks, sr=22050)
bpm = float(np.asarray(tempo).reshape(-1)[0])
assert abs(bpm - 120) < 5
summary = {'MP3_encode_decode': 'passed', 'FLAC_encode_decode': 'passed',
           'segment_seek': 'passed', 'metadata': 'passed', 'waveform_spectrogram_CSV_JSON': 'passed',
           'A4_measured_hz': result['estimated_dominant_pitch']['median_hz'],
           '120_BPM_click_measured_bpm': bpm,
           'ffmpeg': subprocess.check_output([ffmpeg, '-version'], text=True).splitlines()[0]}
(work / 'verification.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
