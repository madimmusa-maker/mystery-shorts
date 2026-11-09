"""Silero TTS, русская модель v4_ru (голоса aidar, baya, kseniya, xenia, eugene).

Нужен torch (ставится в workflow только если выбран голос Silero).
Модель (~40 МБ) скачивается один раз и кэшируется в ~/.cache/silero.
Лицензия моделей Silero — CC BY-NC (некоммерческое использование).
"""
import os
import wave

import numpy as np

from .ru_numbers import expand
from .util import log, retry

MODEL_URL = "https://models.silero.ai/models/tts/ru/v4_ru.pt"
CACHE = os.path.expanduser("~/.cache/silero/v4_ru.pt")
SAMPLE_RATE = 48000
_model = None


def _load():
    global _model
    if _model is not None:
        return _model
    import torch

    torch.set_num_threads(max(1, os.cpu_count() or 1))
    if not os.path.exists(CACHE) or os.path.getsize(CACHE) < 1_000_000:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + ".part"
        retry(lambda: torch.hub.download_url_to_file(MODEL_URL, tmp, progress=False),
              attempts=3, delay=5, what="Silero model download")
        os.replace(tmp, CACHE)
    _model = torch.package.PackageImporter(CACHE).load_pickle("tts_models", "model")
    _model.to(torch.device("cpu"))
    log("Silero: model v4_ru loaded")
    return _model


def synth(text, speaker, out_wav):
    """Озвучить фразу в WAV 48 кГц. Числа заранее превращаются в слова."""
    model = _load()
    spoken = expand(text)
    kwargs = dict(text=spoken, speaker=speaker, sample_rate=SAMPLE_RATE, put_accent=True, put_yo=True)
    try:  # ударения и «ё» в омографах (замок/замок) — есть не во всех версиях модели
        audio = model.apply_tts(**kwargs, put_stress_homo=True, put_yo_homo=True)
    except TypeError:
        audio = model.apply_tts(**kwargs)
    x = audio.detach().cpu().numpy() if hasattr(audio, "detach") else np.asarray(audio)
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm.tobytes())
    if len(pcm) < SAMPLE_RATE * 0.2:
        raise RuntimeError("Silero вернул слишком короткий звук")
    return out_wav
