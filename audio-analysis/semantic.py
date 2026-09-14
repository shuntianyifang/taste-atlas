"""Offline CLAP audio/text matching. Scores are similarities, never probabilities."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import numpy as np
from model_config import ROOT, REPO, REVISION, MODEL_DIR, WEIGHTS, CONFIG_FILES


def availability():
    if any(importlib.util.find_spec(name) is None for name in ('onnxruntime', 'transformers')):
        return False, 'Semantic dependencies missing; install requirements.lock.txt.'
    if any(not (MODEL_DIR / name).is_file() for name in ['manifest.json', *WEIGHTS, *CONFIG_FILES]):
        return False, 'Model not installed; run setup_models.py once with network access.'
    return True, 'ready'


def normalize(values):
    values = np.asarray(values, dtype=np.float32)
    if not np.isfinite(values).all():
        raise ValueError('Model returned nonfinite embeddings')
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    if np.any(norms < 1e-12):
        raise ValueError('Model returned empty embeddings')
    return values / norms


def clap_features(samples):
    """Unfused CLAP frontend using Transformers' NumPy DSP, without PyTorch.

    Same Slaney log-mel and repeatpad settings as the pinned upstream
    ClapFeatureExtractor's non-fusion path. Only <=10s mono windows are accepted.
    """
    os.environ.setdefault('TRANSFORMERS_VERBOSITY', 'error')
    from transformers.audio_utils import mel_filter_bank, spectrogram, window_function
    config = json.loads((MODEL_DIR / 'preprocessor_config.json').read_text(encoding='utf-8'))
    if config['sampling_rate'] != 48000 or config['truncation'] != 'rand_trunc':
        raise ValueError('Unsupported CLAP frontend configuration')
    waveform = np.asarray(samples, dtype=np.float32)
    if waveform.ndim != 1 or not 0 < len(waveform) <= 480000 or not np.isfinite(waveform).all():
        raise ValueError('Invalid CLAP audio window')
    if len(waveform) < 480000:
        waveform = np.tile(waveform, 480000 // len(waveform))
        waveform = np.pad(waveform, (0, 480000 - len(waveform)))
    filters = mel_filter_bank(num_frequency_bins=513, num_mel_filters=64,
                              min_frequency=50, max_frequency=14000, sampling_rate=48000,
                              norm='slaney', mel_scale='slaney')
    mel = spectrogram(waveform, window_function(1024, 'hann'), frame_length=1024,
                      hop_length=480, power=2.0, mel_filters=filters, log_mel='dB')
    return {'input_features': mel.T[None, None].astype(np.float32),
            'is_longer': np.array([[False]], dtype=np.bool_)}


def verify_model():
    manifest = json.loads((MODEL_DIR / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('revision') != REVISION or manifest.get('repo') != REPO:
        raise ValueError('Model manifest version mismatch; reinstall using setup_models.py')
    for name in [*WEIGHTS, *CONFIG_FILES]:
        file = MODEL_DIR / name
        record = manifest['files'][name]
        size, digest = WEIGHTS.get(name, (record['bytes'], record['sha256']))
        with file.open('rb') as handle:
            actual = hashlib.file_digest(handle, 'sha256').hexdigest()
        if file.stat().st_size != size or actual != digest:
            raise ValueError(f'Model integrity check failed: {name}')
    return manifest


class ClapEngine:
    def __init__(self, threads=4):
        ready, reason = availability()
        if not ready:
            raise ValueError(reason)
        self.manifest = verify_model()
        # No remote code, credentials, hub access, telemetry, or audio upload during analysis.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['HF_HOME'] = str(ROOT / '.cache' / 'huggingface')
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        os.environ['USE_TORCH'] = '0'
        os.environ['USE_TF'] = '0'
        os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
        import onnxruntime as ort
        from transformers import AutoTokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self.audio = ort.InferenceSession(str(MODEL_DIR / 'onnx/audio_model.onnx'), options,
                                          providers=['CPUExecutionProvider'])
        self.labels = json.loads((ROOT / 'labels.json').read_text(encoding='utf-8'))
        signature = hashlib.sha256(json.dumps({'revision': REVISION, 'weights': WEIGHTS,
                                               'labels': self.labels, 'pooling': 'normalized-template-mean-v1'},
                                              sort_keys=True).encode()).hexdigest()
        cache = ROOT / '.cache' / f'clap-text-{signature}.npz'
        self.entries = [(group, label) for group, labels in self.labels['groups'].items() for label in labels]
        if cache.is_file():
            with np.load(cache, allow_pickle=False) as stored:
                self.text_vectors = normalize(stored['embeddings'])
            if self.text_vectors.shape != (len(self.entries), 512):
                raise ValueError('Text embedding cache has an invalid shape; remove the named cache and rerun')
        else:
            tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True, trust_remote_code=False)
            model = ort.InferenceSession(str(MODEL_DIR / 'onnx/text_model_quantized.onnx'), options,
                                         providers=['CPUExecutionProvider'])
            texts = [text for _, label in self.entries for text in label['texts']]
            vectors = []
            for offset in range(0, len(texts), 8):
                inputs = tokenizer(texts[offset:offset + 8], padding=True, truncation=True, max_length=77, return_tensors='np')
                feed = {item.name: np.asarray(inputs[item.name], dtype=np.int64) for item in model.get_inputs()}
                vectors.extend(normalize(model.run(['text_embeds'], feed)[0]))
            grouped = []
            offset = 0
            for _, label in self.entries:
                count = len(label['texts'])
                grouped.append(np.mean(vectors[offset:offset + count], axis=0))
                offset += count
            self.text_vectors = normalize(grouped)
            cache.parent.mkdir(parents=True, exist_ok=True)
            temporary = cache.with_suffix('.tmp.npz')
            np.savez_compressed(temporary, embeddings=self.text_vectors)
            temporary.replace(cache)
            del model

    def scores(self, samples, sr=48000):
        if sr != 48000 or len(samples) > 480000:
            raise ValueError('CLAP requires at most 10 seconds of 48000 Hz mono audio')
        inputs = clap_features(samples)
        feed = {}
        for item in self.audio.get_inputs():
            dtype = np.bool_ if item.type == 'tensor(bool)' else np.float32
            feed[item.name] = np.asarray(inputs[item.name], dtype=dtype)
        embedding = normalize(self.audio.run(['audio_embeds'], feed)[0])[0]
        return self.text_vectors @ embedding

    def ranked(self, scores, limit=3):
        output = {}
        for group in self.labels['groups']:
            indexes = [i for i, (g, _) in enumerate(self.entries) if g == group]
            indexes.sort(key=lambda i: float(scores[i]), reverse=True)
            output[group] = [{'id': self.entries[i][1]['id'], 'label': self.entries[i][1]['label'],
                              'cosine_similarity': round(float(scores[i]), 6)} for i in indexes[:limit]]
        return output

    def analyze(self, samples, sr, source_start=0):
        windows, vectors, durations = [], [], []
        for offset in range(0, len(samples), sr * 10):
            chunk = samples[offset:offset + sr * 10]
            length = len(chunk) / sr
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            db = 20 * np.log10(max(rms, 1e-12))
            item = {'start_seconds': source_start + offset / sr, 'end_seconds': source_start + (offset + len(chunk)) / sr,
                    'rms_dbfs': round(float(db), 2)}
            if length < 2 or db < -65:
                item.update(status='insufficient_signal', reason='Shorter than 2 seconds or RMS below -65 dBFS', candidates={})
            else:
                scores = self.scores(chunk, sr)
                item.update(status='analyzed', candidates=self.ranked(scores))
                vectors.append(scores)
                durations.append(length)
            windows.append(item)
        result = {
            'status': 'analyzed' if vectors else 'insufficient_signal',
            'engine': 'CLAP audio-text similarity (CPU ONNX)', 'repo': REPO, 'revision': REVISION,
            'audio_weights': 'float32', 'text_weights': 'int8',
            'sample_rate': sr, 'window_seconds': 10, 'label_bank_version': self.labels['version'],
            'score_type': 'cosine similarity; not a calibrated probability or confidence percentage',
            'aggregation': 'duration-weighted mean over non-silent analyzed windows',
            'analyzed_seconds': round(sum(durations), 3), 'selected_seconds': round(len(samples) / sr, 3),
            'overall_candidates': {}, 'windows': windows,
            'limitations': [
                '候选取决于 labels.json 的词表与英文描述；未列出的乐器不会被识别，合成音色可能与原声乐器混淆。',
                '相似度不是概率。排名靠前不证明乐器存在，低分/近似分数应保留不确定。',
                '情绪是音频与情绪描述的匹配假设，不是听众的真实情绪，也不是歌词含义分析。',
                '声音分析基于 48 kHz 单声道，未做人声/伴奏分轨、精确音符转写或立体声声场测量。',
                '总览只覆盖实际选择的音频时段；每 10 秒的标签可能不同，不应将某一段代表全曲。',
            ],
        }
        if vectors:
            mean = np.average(np.stack(vectors), axis=0, weights=durations)
            overall = self.ranked(mean, 5)
            for group, candidates in overall.items():
                best = candidates[0]['cosine_similarity']
                gap = best - candidates[1]['cosine_similarity']
                result['overall_candidates'][group] = {
                    'assessment': 'weak_match' if best < .1 else ('close_candidates' if gap < .01 else 'candidate_ranking'),
                    'assessment_note': 'Heuristic display flag; 0.10 similarity / 0.01 margin are not calibrated thresholds.',
                    'candidates': candidates,
                }
        return result
