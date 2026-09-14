from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = 'Xenova/clap-htsat-unfused'
REVISION = 'c28f2883575e590e04d3146ff0713c2448d691ba'
MODEL_DIR = ROOT / 'models' / 'clap-htsat-unfused'
WEIGHTS = {
    'onnx/audio_model.onnx': (117528416, 'a1c2b43c44f71e0fa841a4b86700886c199bf87699ea45632c4d831bc6c88957'),
    'onnx/text_model_quantized.onnx': (126603263, '1a3df8b197e249816e08415fd040434c44762b2eea7eb7bf8a48a0f0bf3c14e5'),
}
CONFIG_FILES = ['config.json', 'preprocessor_config.json', 'tokenizer.json',
                'tokenizer_config.json', 'special_tokens_map.json', 'merges.txt', 'vocab.json', 'README.md']
