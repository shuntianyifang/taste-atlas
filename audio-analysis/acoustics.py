"""Measured timbral descriptors, not instrument or emotion classifiers."""
import numpy as np


def timbre_features(y, sr):
    import librosa

    if not len(y) or np.max(np.abs(y)) < 1e-5:
        return {'status': 'silence', 'descriptors': []}
    magnitude = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    power = magnitude ** 2
    energy = power.sum(axis=0)
    valid = energy > max(float(energy.max()) * 1e-4, 1e-12)
    if not valid.any():
        return {'status': 'insufficient_signal', 'descriptors': []}
    centroid = librosa.feature.spectral_centroid(S=magnitude, sr=sr)[0][valid]
    rolloff = librosa.feature.spectral_rolloff(S=magnitude, sr=sr, roll_percent=.85)[0][valid]
    flatness = librosa.feature.spectral_flatness(S=magnitude)[0][valid]
    zcr = librosa.feature.zero_crossing_rate(y, hop_length=512)[0]
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=2048)
    active_power = power[:, valid]
    total = max(float(active_power.sum()), 1e-12)
    low_ratio = float(active_power[frequencies < 250].sum()) / total
    high_ratio = float(active_power[frequencies > 4000].sum()) / total
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    active_rms = rms[rms > max(float(rms.max()) * .01, 1e-6)]
    spread = float(20 * np.log10(max(float(np.percentile(active_rms, 95)), 1e-12)
                                / max(float(np.percentile(active_rms, 10)), 1e-12)))
    # Descriptive thresholds are illustrative and explicitly exposed, not learned labels.
    center = float(np.median(centroid))
    descriptors = []
    if center < 1200:
        descriptors.append('频谱重心偏低，听感可能偏暗或厚；不等同于温暖情绪')
    elif center > 3000:
        descriptors.append('频谱重心偏高，高频质感可能较明亮')
    else:
        descriptors.append('频谱重心处于中间范围')
    if float(np.median(flatness)) < .02:
        descriptors.append('频谱较集中，谐波/有音高成分可能较突出')
    if low_ratio > .5:
        descriptors.append('低于 250 Hz 的能量占比较高')
    return {
        'status': 'measured',
        'median_spectral_centroid_hz': center,
        'median_rolloff_85_hz': float(np.median(rolloff)),
        'median_spectral_flatness': float(np.median(flatness)),
        'mean_zero_crossing_rate': float(np.mean(zcr)),
        'energy_below_250_hz_ratio': low_ratio,
        'energy_above_4000_hz_ratio': high_ratio,
        'active_rms_p95_p10_range_db': spread,
        'descriptors': descriptors,
        'limitations': '22050 Hz mono descriptors; not stereo width, reverberation time, instrument identity, mood, or mastering loudness range (LRA).',
    }
