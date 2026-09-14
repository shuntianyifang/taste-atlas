"""Pinned offline MuQ-MuLan adapter using the same label bank as CLAP."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from semantic import ClapEngine, normalize

ROOT = Path(__file__).resolve().parent


class MuQEngine(ClapEngine):
    def __init__(self, threads=4):
        for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_HUB_DISABLE_TELEMETRY'):
            os.environ[name] = '1'
        os.environ['HF_HOME'] = str(ROOT / '.cache' / 'muq-hf')
        os.environ['USE_TORCH'] = '1'
        os.environ['USE_TF'] = '0'
        os.environ['TOKENIZERS_PARALLELISM'] = 'false'
        import torch
        from muq import MuQMuLan, MuQ
        from transformers import XLMRobertaConfig, XLMRobertaModel, AutoTokenizer
        from muq.muq_mulan.models.audio import AudioSpectrogramTransformerPretrained
        from muq.muq_mulan.models.text import TextTransformerPretrained
        from unittest.mock import patch
        self.torch = torch
        torch.set_num_threads(threads)
        torch.manual_seed(0)
        self.manifest = json.loads((ROOT / 'models/muq-manifest.json').read_text())
        from setup_muq import SPECS
        if set(self.manifest) != set(SPECS):
            raise ValueError('MuQ manifest model set mismatch')
        for folder, record in self.manifest.items():
            repo, revision, files = SPECS[folder]
            if record['repo'] != repo or record['revision'] != revision or set(record['files']) != set(files):
                raise ValueError('MuQ manifest version mismatch')
            for name, expected in record['files'].items():
                path = ROOT / 'models' / folder / name
                with path.open('rb') as f:
                    actual = hashlib.file_digest(f, 'sha256').hexdigest()
                if path.stat().st_size != expected['bytes'] or actual != expected['sha256']:
                    raise ValueError(f'MuQ integrity failure: {folder}/{name}')
        config = json.loads((ROOT / 'models/muq-mulan/config.json').read_text())
        config['audio_model']['name'] = str(ROOT / 'models/muq-backbone')
        config['text_model']['name'] = str(ROOT / 'models/xlm-roberta-base')
        # Only fixed local configs/weights; installed package implements the architecture.
        # The full MuLan state includes both towers. Instantiate their official
        # architectures from local configs instead of redundantly downloading
        # base checkpoints that the full state immediately replaces.
        def audio_from_config(instance, model_name):
            instance.model = MuQ(json.loads((ROOT / 'models/muq-backbone/config.json').read_text()))

        def text_from_config(instance):
            return XLMRobertaModel(XLMRobertaConfig.from_json_file(str(ROOT / 'models/xlm-roberta-base/config.json')))

        with patch.object(AudioSpectrogramTransformerPretrained, '_init_pretrained_model', audio_from_config), \
             patch.object(TextTransformerPretrained, '_init_pretrained_model', text_from_config):
            self.model = MuQMuLan(config).float().eval()
        state = torch.load(ROOT / 'models/muq-mulan/pytorch_model.bin', map_location='cpu', weights_only=True, mmap=True)
        self.model.load_state_dict(state, strict=True)
        del state
        self.model.mulan.text._tokenizer = AutoTokenizer.from_pretrained(
            str(ROOT / 'models/xlm-roberta-base'), local_files_only=True, trust_remote_code=False)
        self.labels = json.loads((ROOT / 'labels.json').read_text(encoding='utf-8'))
        self.entries = [(g, label) for g, labels in self.labels['groups'].items() for label in labels]
        signature = hashlib.sha256(json.dumps({'models': self.manifest, 'labels': self.labels,
            'pooling': 'normalized-template-mean-single-text-v1'}, sort_keys=True).encode()).hexdigest()
        cache = ROOT / '.cache' / f'muq-text-{signature}.npz'
        if cache.exists():
            with np.load(cache, allow_pickle=False) as data:
                self.text_vectors = normalize(data['embeddings'])
        else:
            vectors = []
            with torch.inference_mode():
                for _, label in self.entries:
                    # Upstream pools padded tokens; single-text calls avoid batch-dependent padding.
                    templates = [normalize(self.model(texts=[text]).cpu().numpy())[0] for text in label['texts']]
                    vectors.append(np.mean(templates, axis=0))
            self.text_vectors = normalize(vectors)
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache, embeddings=self.text_vectors)
        if self.text_vectors.shape != (len(self.entries), 512):
            raise ValueError('Invalid MuQ text embedding shape')

    def scores(self, samples, sr=24000):
        samples = np.asarray(samples, dtype=np.float32)
        if sr != 24000 or samples.ndim != 1 or not 0 < len(samples) <= 240000 or not np.isfinite(samples).all():
            raise ValueError('MuQ requires finite mono audio <=10 seconds at 24 kHz')
        # Explicit repeat-to-length avoids the upstream short-clip edge case.
        if len(samples) < 240000:
            samples = np.tile(samples, int(np.ceil(240000 / len(samples))))[:240000]
        with self.torch.inference_mode():
            audio = self.model(wavs=self.torch.from_numpy(samples.copy())[None]).cpu().numpy()
        return self.text_vectors @ normalize(audio)[0]

    def analyze(self, samples, sr, source_start=0):
        result = super().analyze(samples, sr, source_start)
        result.update(engine='MuQ-MuLan (CPU PyTorch FP32)',
                      repo=self.manifest['muq-mulan']['repo'], revision=self.manifest['muq-mulan']['revision'],
                      audio_weights='float32', text_weights='float32',
                      model_manifest=self.manifest)
        result['limitations'] = [
            '候选相似度不是概率；不同模型的绝对分数不能比较准确率。',
            '只使用共同英文词表，没有用中文提示、文件名、游戏名或用户偏好增强某一个模型。',
            '24 kHz 单声道、10 秒窗口；末尾有效短窗口重复到 10 秒，汇总只计原始时长。',
            '复杂混音和合成音色需要复听；情绪标签没有人工真值，不能判断模型胜负。']
        for group in result['overall_candidates'].values():
            group['assessment'] = 'candidate_ranking'
            group['assessment_note'] = 'No calibrated confidence thresholds for MuQ.'
        return result
