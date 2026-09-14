"""Native Windows inference of MTG models; not the Essentia Python binding."""
import json
import hashlib
from functools import lru_cache
import numpy as np
from setup_essentia import DIRECTORY, MODELS, COMMIT

SR, FRAME, HOP = 16000, 512, 256
PATCHES = {'effnet': (128, 62), 'musicnn': (187, 93)}
LIMITATIONS = [
    'Windows ONNX 适配；25 个帧的频谱前处理已与官方 Essentia.js 0.1.3 核对（最大误差约 8.48e-5）。完整 TensorFlow 推理流水线尚未做等价对照。',
    '分类输出不是已校准置信度；不同模型的分数不能比较准确率。',
    'DEAM 预测音乐的愉悦度与激活程度，不代表听众感受；训练标签标度为 1–9，原始越界值保留。',
    '原生重叠窗口按与展示区间的交集时长加权；末尾补齐与未覆盖时段均保留记录。',
]


def verify_assets(directory=DIRECTORY):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['models'] != MODELS or manifest['reference_commit'] != COMMIT:
        raise ValueError('Essentia manifest version mismatch')
    required = {f'{key}.{ext}' for key in MODELS for ext in ('json', 'onnx')}
    if not required <= manifest['files'].keys():
        raise ValueError('Essentia manifest incomplete')
    for name, record in manifest['files'].items():
        path = directory / name
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Invalid manifest path')
        with path.open('rb') as f:
            actual = hashlib.file_digest(f, 'sha256').hexdigest()
        if path.stat().st_size != record['bytes'] or actual != record['sha256']:
            raise ValueError(f'Essentia integrity failure: {name}')
    return manifest


@lru_cache(maxsize=1)
def mel_filters():
    import librosa
    # Slaney spacing, linear triangular weights and theoretical area normalization.
    return librosa.filters.mel(sr=SR, n_fft=FRAME, n_mels=96, fmin=0,
                              fmax=SR / 2, htk=False, norm='slaney', dtype=np.float64)


def logmel(samples):
    y = np.asarray(samples, dtype=np.float32)
    if y.ndim != 1 or not len(y) or not np.isfinite(y).all():
        raise ValueError('Expected finite nonempty mono samples')
    # Zero-centred first frame; retain silence rather than add upstream noise.
    centers = np.arange(0, int(np.ceil(len(y) / HOP)) * HOP + 1, HOP)
    padded = np.pad(y, (FRAME // 2, FRAME))
    frames = np.lib.stride_tricks.sliding_window_view(padded, FRAME)[centers]
    power = np.abs(np.fft.rfft(frames * np.hanning(FRAME), axis=1)) ** 2
    return np.log10(1.0 + 10000.0 * (power @ mel_filters().T)).astype(np.float32)


def patches(mel, samples, kind, source_start=0):
    size, step = PATCHES[kind]
    duration = len(samples) / SR
    for begin in range(0, len(mel), step):
        end = min(begin + size, len(mel))
        chunk = mel[begin:end]
        left = max(0, (begin * HOP - FRAME // 2) / SR)
        right = min(duration, ((end - 1) * HOP + FRAME // 2) / SR)
        signal = samples[round(left * SR):round(right * SR)]
        db = float(20 * np.log10(max(float(np.sqrt(np.mean(signal.astype(np.float64) ** 2))), 1e-12)))
        item = {'start_seconds': source_start + left, 'end_seconds': source_start + right,
                'frame_start': begin, 'frame_count': len(chunk), 'required_frames': size,
                'padded_frames': size - len(chunk), 'padding': 'repeat mel frames' if len(chunk) < size else 'none',
                'rms_dbfs': db, 'status': 'analyzed' if right - left >= 2 and db >= -65 else 'insufficient_signal'}
        if len(chunk) < size:
            chunk = np.tile(chunk, (int(np.ceil(size / len(chunk))), 1))[:size]
        yield chunk, item
        if end == len(mel):
            break


def overlap(a, b, x, y):
    return max(0.0, min(b, y) - max(a, x))


def summarize(native, start, end, key):
    records = [p for p in native if p['status'] == 'analyzed' and key in p
               and overlap(start, end, p['start_seconds'], p['end_seconds']) > 0]
    if not records:
        return None
    weights = [overlap(start, end, p['start_seconds'], p['end_seconds']) for p in records]
    keys = records[0][key].keys()
    return {k: float(np.average([p[key][k] for p in records], weights=weights)) for k in keys}


def covered_seconds(native, start, end):
    intervals = sorted((max(start, p['start_seconds']), min(end, p['end_seconds'])) for p in native
                       if p['status'] == 'analyzed' and overlap(start, end, p['start_seconds'], p['end_seconds']) > 0)
    total, cursor = 0., start
    for left, right in intervals:
        total += max(0., right - max(cursor, left))
        cursor = max(cursor, right)
    return total


class EssentiaEngine:
    def __init__(self, threads=4):
        import onnxruntime as ort
        self.manifest = verify_assets()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.sessions = {k: ort.InferenceSession(str(DIRECTORY / f'{k}.onnx'), options,
            providers=['CPUExecutionProvider']) for k in MODELS}
        self.metadata = {k: json.loads((DIRECTORY / f'{k}.json').read_text()) for k in MODELS}
        self.labels = {'version': 1, 'groups': {k: self.metadata[k]['classes'] for k in ('instrument', 'moodtheme')}}
        if len(self.labels['groups']['instrument']) != 40 or len(self.labels['groups']['moodtheme']) != 56:
            raise ValueError('Unexpected Essentia label count')
        if self.metadata['deam']['classes'] != ['valence', 'arousal']:
            raise ValueError('Unexpected DEAM dimension order')
        self.schema = {k: {'inputs': [{'name': n.name, 'shape': n.shape, 'type': n.type} for n in s.get_inputs()],
                           'outputs': [{'name': n.name, 'shape': n.shape} for n in s.get_outputs()]} for k, s in self.sessions.items()}

    def run(self, key, data, output):
        session = self.sessions[key]
        inputs = session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != 'tensor(float)':
            raise ValueError(f'Unexpected inputs for {key}')
        # The official ONNX exports rename TF nodes; explicit aliases verified
        # against the downloaded graphs, never inferred from output position.
        aliases = {'effnet': 'embeddings', 'musicnn': 'embeddings',
                   'instrument': 'activations', 'moodtheme': 'activations'}
        output = aliases.get(key, output)
        candidates = [n.name for n in session.get_outputs() if n.name == output or n.name == output + ':0']
        if len(candidates) != 1:
            raise ValueError(f'Missing documented output for {key}: {output}')
        x = np.asarray(data, dtype=np.float32)
        if x.ndim != len(inputs[0].shape):
            raise ValueError(f'Unexpected input rank for {key}')
        y = session.run(candidates, {inputs[0].name: x})[0]
        if not np.isfinite(y).all():
            raise ValueError(f'Nonfinite output: {key}')
        return y

    def analyze(self, samples, sr=SR, source_start=0):
        if sr != SR or not np.isfinite(source_start) or source_start < 0:
            raise ValueError('Essentia requires 16 kHz mono and a valid start time')
        samples = np.asarray(samples, dtype=np.float32)
        if samples.ndim != 1 or not 0 < len(samples) <= SR * 600 or not np.isfinite(samples).all():
            raise ValueError('Invalid Essentia audio input')
        mel = logmel(samples)
        native = {'effnet': [], 'musicnn': []}
        for kind in native:
            for chunk, item in patches(mel, samples, kind, source_start):
                if item['status'] == 'analyzed':
                    if kind == 'effnet':
                        vector = self.run(kind, chunk[None], 'PartitionedCall:1')
                        if vector.shape != (1, 1280):
                            raise ValueError('EffNet embedding dimension mismatch')
                        for head in ('instrument', 'moodtheme'):
                            scores = self.run(head, vector, 'model/Sigmoid').reshape(-1)
                            labels = self.labels['groups'][head]
                            if len(scores) != len(labels) or np.any((scores < 0) | (scores > 1)):
                                raise ValueError('Classifier output mismatch')
                            item[head] = dict(zip(labels, map(float, scores)))
                    else:
                        vector = self.run(kind, chunk[None], 'model/dense/BiasAdd')
                        scores = self.run('deam', vector, 'model/Identity').reshape(-1)
                        if len(scores) != 2:
                            raise ValueError('DEAM output mismatch')
                        item['deam'] = dict(zip(('valence', 'arousal'), map(float, scores)))
                        item['out_of_training_range'] = bool(np.any((scores < 1) | (scores > 9)))
                native[kind].append(item)
        duration = len(samples) / SR
        windows = []
        for offset in np.arange(0, duration, 10):
            start, end = source_start + float(offset), source_start + min(float(offset) + 10, duration)
            segment = samples[round(offset * SR):round((end - source_start) * SR)]
            db = 20 * np.log10(max(float(np.sqrt(np.mean(segment.astype(np.float64) ** 2))), 1e-12))
            item = {'start_seconds': start, 'end_seconds': end, 'status': 'insufficient_signal'}
            if end - start >= 2 and db >= -65:
                for key, kind in [('instrument', 'effnet'), ('moodtheme', 'effnet'), ('deam', 'musicnn')]:
                    item[key] = summarize(native[kind], start, end, key)
                if item.get('instrument') or item.get('deam'):
                    item['status'] = 'analyzed'
            item['covered_seconds'] = {k: covered_seconds(v, start, end) for k, v in native.items()}
            windows.append(item)
        end = source_start + duration
        overall = {key: summarize(native[kind], source_start, end, key)
                   for key, kind in [('instrument', 'effnet'), ('moodtheme', 'effnet'), ('deam', 'musicnn')]}
        return {'status': 'analyzed' if any(v is not None for v in overall.values()) else 'insufficient_signal',
                'engine': 'Essentia model family / native ONNX CPU FP32', 'sample_rate': SR,
                'selected_seconds': duration, 'source_start': source_start, 'windows': windows,
                'native_windows': native, 'overall': overall, 'model_manifest': self.manifest,
                'tensor_schema': self.schema, 'limitations': LIMITATIONS,
                'preprocessing': {'fft': FRAME, 'hop': HOP, 'mel_bands': 96, 'window': 'symmetric Hann, unnormalized',
                    'compression': 'log10(1 + 10000 * Slaney area-normalized mel power)',
                    'frame_padding': 'zero-centered, zeros at boundaries; silent frames retained',
                    'native_patches': PATCHES, 'reference_runtime_parity': 'full_pipeline_not_verified',
                    'per_frame_reference': 'Essentia.js 0.1.3; 25 frames; max abs error 8.4758e-5; see selftest/essentia-reference/wasm-verification.json'}}
