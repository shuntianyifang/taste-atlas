"""Local, bounded audio inspection. Never modifies the input or uploads audio."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('NUMBA_CACHE_DIR', str(ROOT / '.cache' / 'numba'))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.cache' / 'matplotlib'))

import numpy as np
import soundfile as sf
import mutagen
import imageio_ffmpeg


def metadata(source):
    result = {'file': source.name, 'bytes': source.stat().st_size}
    audio = mutagen.File(source)
    if audio is not None:
        for name in ('length', 'sample_rate', 'channels', 'bitrate', 'bits_per_sample'):
            value = getattr(audio.info, name, None)
            if value is not None:
                result[name] = value
        result['decoder_metadata_type'] = type(audio).__name__
    try:
        info = sf.info(str(source))
        result.update(format=info.format, subtype=info.subtype,
                      channels=info.channels, sample_rate=info.samplerate,
                      length=info.duration)
    except (RuntimeError, sf.LibsndfileError):
        pass
    return result


def decode(source, start, duration, sample_rate=22050):
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
               '-nostdin', '-ss', str(start), '-i', str(source), '-t', str(duration),
               '-vn', '-ac', '1', '-ar', str(sample_rate), '-f', 'f32le', 'pipe:1']
    decoded = subprocess.run(command, capture_output=True, timeout=180, check=False)
    if decoded.returncode:
        raise ValueError('Audio decoding failed. Verify the file format and that the file is readable.')
    samples = np.frombuffer(decoded.stdout, dtype='<f4').copy()
    if samples.size < sample_rate // 4:
        raise ValueError('Selected segment is empty or shorter than 0.25 seconds.')
    if not np.isfinite(samples).all():
        raise ValueError('Decoded signal contains invalid samples.')
    return samples, sample_rate


def analyze(source, start, duration, pitch, output, semantic_mode='auto', threads=4):
    import librosa
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    y, sr = decode(source, start, duration)
    hop = 512
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    active = bool(np.max(np.abs(y)) > 1e-5)
    if active and np.any(onset > 0):
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=hop)
        bpm = float(np.asarray(tempo).reshape(-1)[0])
        if len(y) / sr < 4 or len(beats) < 4:
            bpm = None  # Too little evidence for a useful tempo report.
    else:
        bpm, beats = None, np.array([], dtype=int)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    stft = librosa.stft(y, hop_length=hop)
    db = librosa.amplitude_to_db(np.abs(stft), ref=np.max)
    result = {'source': metadata(source), 'segment': {'start_seconds': start,
              'duration_seconds': len(y) / sr, 'analysis_sample_rate': sr, 'channels': 'mono downmix'},
              'rms_dbfs': float(20 * np.log10(max(float(np.sqrt(np.mean(y**2))), 1e-12))),
              'peak_dbfs': float(20 * np.log10(max(float(np.max(np.abs(y))), 1e-12))),
              'estimated_bpm': bpm, 'detected_beats': len(beats),
              'mean_spectral_centroid_hz': float(np.mean(centroid)),
              'limitations': ['Tempo can be half/double the perceived beat.',
                'Measurements use a 22050 Hz mono downmix; not a mastering-quality or stereo analysis.',
                'Pitch tracking is an estimate for dominant monophonic material, not polyphonic transcription.',
                'Numerical audio features do not determine genre, emotion or aesthetic preference.']}
    from acoustics import timbre_features
    result['acoustic_timbre'] = timbre_features(y, sr)
    result['report_schema_version'] = 2
    if semantic_mode not in ('auto', 'on', 'off'):
        raise ValueError('semantic_mode must be auto, on or off')
    if not 1 <= threads <= 8:
        raise ValueError('Use 1 to 8 CPU threads')
    if semantic_mode == 'off':
        result['semantic'] = {'status': 'disabled', 'reason': 'Explicit --semantic off; measured features only.'}
    else:
        from semantic import availability, ClapEngine
        ready, reason = availability()
        if not ready and semantic_mode == 'on':
            raise ValueError(reason)
        if not ready:
            result['semantic'] = {'status': 'unavailable', 'reason': reason}
            print('Semantic analysis unavailable: ' + reason, file=sys.stderr)
        else:
            print('Running local CLAP instrument/timbre/mood analysis...', file=sys.stderr, flush=True)
            semantic_y, semantic_sr = decode(source, start, duration, sample_rate=48000)
            try:
                result['semantic'] = ClapEngine(threads=threads).analyze(semantic_y, semantic_sr, start)
            except Exception as exc:
                # A broken installed model is an error, never silently replaced by heuristic moods.
                raise ValueError(f'Semantic inference failed ({type(exc).__name__}): {exc}') from exc
    frequencies = None
    if pitch and active:
        frequencies = librosa.yin(y, fmin=65.4, fmax=2093, sr=sr, hop_length=hop)
        valid = rms[:len(frequencies)] > max(1e-4, float(rms.max()) * 0.05)
        frequencies = np.where(valid, frequencies, np.nan)
        if np.isfinite(frequencies).any():
            hz = float(np.nanmedian(frequencies))
            result['estimated_dominant_pitch'] = {'median_hz': hz, 'nearest_note': librosa.hz_to_note(hz), 'algorithm': 'YIN'}
    output.mkdir(parents=True, exist_ok=True)
    # Unique output directories prevent accidental replacement of earlier reports.
    with (output / 'report.json').open('w', encoding='utf-8') as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    with (output / 'features.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['source_time_seconds', 'rms', 'spectral_centroid_hz', 'estimated_f0_hz'])
        for i in range(min(len(rms), len(centroid))):
            f0 = float(frequencies[i]) if frequencies is not None and i < len(frequencies) and np.isfinite(frequencies[i]) else ''
            writer.writerow([start + i * hop / sr, float(rms[i]), float(centroid[i]), f0])
    with (output / 'beats.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['estimated_beat_source_time_seconds'])
        writer.writerows([[float(start + beat * hop / sr)] for beat in beats])
    fig, axes = plt.subplots(3 if pitch else 2, 1, figsize=(11, 8 if pitch else 6), constrained_layout=True)
    stride = max(1, len(y) // 15000)
    axes[0].plot(start + np.arange(0, len(y), stride) / sr, y[::stride], linewidth=.5)
    axes[0].set(ylabel='Amplitude', title='Decoded waveform (mono)')
    axes[1].imshow(db, origin='lower', aspect='auto', extent=[start, start + len(y) / sr, 0, sr / 2], vmin=-80, vmax=0, cmap='magma')
    axes[1].set(ylabel='Frequency (Hz)', title='Spectrogram (dB relative to segment maximum)')
    if pitch:
        if frequencies is not None:
            axes[2].plot(start + np.arange(len(frequencies)) * hop / sr, frequencies, linewidth=.8)
        axes[2].set(ylabel='Estimated F0 (Hz)', title='YIN pitch estimate; unreliable on polyphonic mixes')
    axes[-1].set_xlabel('Source time (seconds)')
    fig.savefig(output / 'analysis.png', dpi=140)
    plt.close(fig)
    from reporting import write_report
    write_report(result, output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--info', action='store_true', help='Only inspect file metadata')
    parser.add_argument('--start', type=float, default=0, help='Segment start in seconds')
    parser.add_argument('--duration', type=float, default=60, help='Segment duration, 0.25–600 seconds (default 60)')
    parser.add_argument('--pitch', action='store_true', help='Estimate monophonic pitch using YIN')
    parser.add_argument('--semantic', choices=['auto', 'on', 'off'], default='auto',
                        help='Local CLAP instrument/timbre/mood candidates (auto uses installed model; on requires it)')
    parser.add_argument('--threads', type=int, default=4, choices=range(1, 9), help='CPU inference threads, 1-8')
    parser.add_argument('--whole-file', action='store_true', help='Analyze the whole file if no longer than 600 seconds')
    args = parser.parse_args()
    source = args.file.resolve(strict=True)
    if not source.is_file():
        parser.error('Input must be a file')
    if not 0.25 <= args.duration <= 600 or not np.isfinite(args.start) or args.start < 0:
        parser.error('Use a nonnegative finite start and duration between 0.25 and 600 seconds')
    if args.whole_file:
        if args.start != 0:
            parser.error('--whole-file cannot be combined with a nonzero --start')
        length = metadata(source).get('length')
        if length is None or not np.isfinite(length) or not .25 <= length <= 600:
            parser.error('--whole-file requires known duration between 0.25 and 600 seconds; otherwise select a segment')
        args.duration = length
    if args.info:
        print(json.dumps(metadata(source), ensure_ascii=False, indent=2))
    else:
        from datetime import datetime
        import uuid
        output = ROOT / 'results' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
        result = analyze(source, args.start, args.duration, args.pitch, output, args.semantic, args.threads)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print('Output:', output)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f'Analysis failed: {exc}', file=sys.stderr)
        sys.exit(1)
