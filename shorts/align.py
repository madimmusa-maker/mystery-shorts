"""Тайминги слов, когда TTS их не дал: faster-whisper + выравнивание с текстом сценария.

В субтитры всегда идут слова из сценария (без ошибок распознавания),
а из whisper берётся только время, когда каждое слово прозвучало.
"""
import difflib
import os
import re
import wave

import numpy as np

from .util import log

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
LAG = 0.05  # whisper иногда ставит начало слова чуть раньше звука


def _norm(w):
    return re.sub(r"[^\wа-яё0-9]", "", w.lower().replace("ё", "е"))


def whisper_words(wav_path, prompt=""):
    """[(начало, конец, слово)] или None, если faster-whisper не сработал."""
    try:
        from faster_whisper import WhisperModel
    except Exception as e:  # noqa: BLE001
        log(f"Align: faster-whisper не установлен ({e})")
        return None
    try:
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(wav_path, language="ru", word_timestamps=True,
                                       initial_prompt=prompt[:800] or None,
                                       vad_filter=False, beam_size=5)
        words = [(w.start, w.end, w.word.strip()) for seg in segments for w in (seg.words or [])
                 if w.word.strip()]
        log(f"Align: faster-whisper ({WHISPER_MODEL}) нашёл {len(words)} слов")
        return words or None
    except Exception as e:  # noqa: BLE001
        log(f"Align: faster-whisper ошибка: {e}")
        return None


def estimate(tokens, start, end):
    """Примерные тайминги: пропорционально длине слов внутри [start, end]."""
    if not tokens:
        return []
    weights = [len(t) + 1.5 for t in tokens]
    scale = max(end - start, 0.1) / sum(weights)
    out, t = [], start
    for tok, w in zip(tokens, weights):
        d = w * scale
        out.append((t, t + d * 0.95, tok))
        t += d
    return out


def align(phrase_tokens, spans, whisper):
    """Сопоставить слова сценария со словами whisper.

    phrase_tokens: [[слово, ...], ...] по фразам; spans: [(начало, конец)] звука фраз.
    Возвращает [[(начало, конец, слово), ...], ...] по фразам.
    """
    script = [(pi, tok) for pi, toks in enumerate(phrase_tokens) for tok in toks]
    a = [_norm(t) for _, t in script]
    b = [_norm(w) for _, _, w in whisper]
    times = [None] * len(script)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                s, e, _ = whisper[j1 + k]
                times[i1 + k] = (s, e)
        elif op == "replace":
            # разное число слов (например, «1959» и «тысяча девятьсот…»):
            # делим время куска whisper пропорционально длине слов сценария
            s0, e0 = whisper[j1][0], whisper[j2 - 1][1]
            toks = [script[k][1] for k in range(i1, i2)]
            for k, (s, e, _) in enumerate(estimate(toks, s0, e0)):
                times[i1 + k] = (s, e)
    matched = sum(t is not None for t in times)
    log(f"Align: сопоставлено {matched}/{len(script)} слов")

    result = [[] for _ in phrase_tokens]
    k = 0
    for pi, toks in enumerate(phrase_tokens):
        ps, pe = spans[pi]
        idx = list(range(k, k + len(toks)))
        k += len(toks)
        # слова без времени — заполняем между соседями внутри фразы
        filled = [times[i] for i in idx]
        j = 0
        while j < len(idx):
            if filled[j] is not None:
                j += 1
                continue
            j2 = j
            while j2 < len(idx) and filled[j2] is None:
                j2 += 1
            left = filled[j - 1][1] if j > 0 else ps
            right = filled[j2][0] if j2 < len(idx) else pe
            if right <= left:
                right = left + 0.15 * (j2 - j)
            for n, (s, e, _) in enumerate(estimate(toks[j:j2], left, right)):
                filled[j + n] = (s, e)
            j = j2
        for (s, e), tok in zip(filled, toks):
            s = min(max(s + LAG, ps), pe)  # не раньше начала звука фразы
            e = max(min(e + LAG, pe + 0.1), s + 0.05)
            result[pi].append((s, e, tok))
    return result


def sound_onsets(wav_path):
    """Моменты, когда громкость резко растёт (начала слогов/слов), в секундах."""
    with wave.open(wav_path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    win = int(sr * 0.01)
    n = len(x) // win
    if n < 3:
        return []
    db = 20 * np.log10(np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1)) + 1e-6)
    floor = max(db.max() - 30, -50)
    out = []
    for k in range(2, n):
        if db[k] > floor and db[k] - db[k - 2] > 6 and (not out or k * 0.01 - out[-1] > 0.08):
            out.append(k * win / sr)
    return out


def snap_to_onsets(phrase_words, wav_path, spans):
    """Для примерной оценки: каждое слово начинается не раньше ближайшего всплеска звука."""
    onsets = sound_onsets(wav_path)
    result = []
    for words, (ps, pe) in zip(phrase_words, spans):
        out, last = [], ps
        for s, e, w in words:
            near = [o for o in onsets if s - 0.15 <= o <= s + 0.25 and o >= last]
            ns = (near[0] + 0.02) if near else s + 0.10
            ns = min(max(ns, last, ps + 0.02), pe)
            out.append((ns, max(e, ns + 0.05), w))
            last = ns + 0.05
        result.append(out)
    return result
