"""Живая озвучка по фразам + точные тайминги слов.

Каждая фраза озвучивается отдельно со своей скоростью и высотой голоса
(в зависимости от настроения фразы), затем фразы склеиваются с паузами.
Мы сами собираем итоговый звук, поэтому точно знаем, где начинается каждая
фраза, и сдвигаем на это место тайминги слов из WordBoundary edge-tts.

Если edge-tts не работает, фразы озвучиваются gTTS, а тайминги слов
берутся из faster-whisper (см. align.py) или, в крайнем случае, считаются
примерно внутри каждой фразы.
"""
import asyncio
import os
import random
import re
import subprocess
import wave

import edge_tts
import numpy as np

from . import align, voices
from .util import log, retry
SR = 24000

# настроение фразы -> (скорость %, высота Гц)
PROSODY = {
    "hook": (-6, -2),
    "intrigue": (-14, -6),
    "fact": (-8, -2),
    "surprise": (6, 4),
    "question": (-6, 3),
    "reveal": (-12, -5),
}
DEFAULT_MOOD = "fact"
PAUSE_MIN, PAUSE_MAX = 0.20, 0.40
PAUSE_BEFORE_REVEAL = 0.80
EDGE_LAG = 0.02  # маленький запас: слово появляется на 20 мс позже начала звука, а не раньше

# Движки, которые уже сломались в этом запуске — к ним больше не обращаемся.
_broken = set()


# ---------- форматы ----------

def fmt_rate(value):
    """'-8%', '-8', -8, '8%' -> '-8%' / '+8%' (формат, который требует edge-tts)."""
    m = re.fullmatch(r"\s*([+-]?)(\d+)\s*%?\s*", str(value))
    if not m:
        raise ValueError(f"Неверная скорость речи: {value!r}")
    return f"{m.group(1) or '+'}{int(m.group(2))}%"


def fmt_pitch(value):
    """'-2Hz', '-2', -2, '2hz' -> '-2Hz' / '+2Hz'."""
    m = re.fullmatch(r"\s*([+-]?)(\d+)\s*(?:hz|Hz|HZ)?\s*", str(value))
    if not m:
        raise ValueError(f"Неверная высота голоса: {value!r}")
    return f"{m.group(1) or '+'}{int(m.group(2))}Hz"


def clean_for_speech(text):
    text = re.sub(r"[«»\"“”„*_#<>\[\]{}|~^&]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def display_tokens(text):
    """Слова фразы так, как они пойдут в субтитры (без знаков препинания)."""
    out = []
    for tok in text.split():
        w = re.sub(r"[^\w\-]", "", tok).strip("-")
        if w:
            out.append(w)
    return out


# ---------- звук ----------

def decode(path, tempo=1.0, semitones=0.0):
    """Любой аудиофайл -> numpy float32 mono 24 кГц (с изменением темпа/тона)."""
    filters = []
    if abs(semitones) > 0.01:
        f = 2 ** (semitones / 12)
        filters += [f"asetrate={int(SR * f)}", f"aresample={SR}", f"atempo={1 / f:.4f}"]
    if abs(tempo - 1) > 0.001:
        filters.append(f"atempo={max(0.5, min(2.0, tempo)):.4f}")
    cmd = ["ffmpeg", "-v", "error", "-i", path]
    if filters:
        cmd += ["-af", ",".join(filters)]
    cmd += ["-f", "s16le", "-ac", "1", "-ar", str(SR), "-"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg decode failed: {res.stderr.decode()[-300:]}")
    return np.frombuffer(res.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def sound_bounds(x):
    """(начало, конец) звука в секундах — где громкость выше порога."""
    win = int(SR * 0.01)
    n = len(x) // win
    if n == 0:
        return 0.0, len(x) / SR
    rms = np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    thr = max(rms.max() * 0.06, 10 ** (-48 / 20))
    loud = np.nonzero(rms > thr)[0]
    if len(loud) == 0:
        return 0.0, len(x) / SR
    return loud[0] * win / SR, (loud[-1] + 1) * win / SR


def write_wav(path, x):
    pcm = (np.clip(x, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------- edge-tts ----------

async def _edge(text, out_path, rate, pitch, boundary, voice):
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary=boundary)
    words = []
    with open(out_path, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def _edge_phrase(text, out_path, rate, pitch, voice):
    """Несколько вариантов запроса: обычный, без сдвига тона, без таймингов слов."""
    variants = [(rate, pitch, "WordBoundary"),
                (rate, "+0Hz", "WordBoundary"),
                (rate, "+0Hz", "SentenceBoundary")]
    last = None
    for r, p, b in variants:
        try:
            words = retry(lambda r=r, p=p, b=b: asyncio.run(_edge(text, out_path, r, p, b, voice)),
                          attempts=2, delay=4, what=f"edge-tts ({r}, {p}, {b})")
            if os.path.getsize(out_path) > 1000:
                return words
            last = RuntimeError("edge-tts вернул пустой звук")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


# ---------- gTTS ----------

def _gtts_phrase(text, out_path):
    from gtts import gTTS  # нужен только в запасном варианте

    def go():
        gTTS(text=text, lang="ru", tld="com", slow=False).save(out_path)
        if os.path.getsize(out_path) < 500:
            raise RuntimeError("gTTS вернул пустой звук")
    retry(go, attempts=4, delay=5, what="gTTS")


# ---------- сборка ----------

def _prosody(mood, speed):
    rate, pitch = PROSODY.get(mood, PROSODY[DEFAULT_MOOD])
    rate += speed + random.randint(-2, 2)
    pitch += random.randint(-1, 1)
    return rate, pitch


def _render_phrases(phrases, workdir, speed, engine, engine_voice, male):
    """Озвучить все фразы одним движком. Возвращает список (audio, words|None, text, mood)."""
    # сдвиг тона в Гц -> полутона: у мужского голоса (~120 Гц) 1 полутон ≈ 7 Гц, у женского ≈ 12 Гц
    hz_per_semitone = 7 if male else 12
    out = []
    for i, ph in enumerate(phrases):
        text = clean_for_speech(ph["text"])
        rate, pitch = _prosody(ph.get("mood"), speed)
        base = os.path.join(workdir, f"phrase_{i:02d}")
        if engine == "edge":
            words = _edge_phrase(text, base + ".mp3", fmt_rate(rate), fmt_pitch(pitch), engine_voice)
            audio = decode(base + ".mp3")
        elif engine == "silero":
            from . import silero  # torch нужен только для Silero
            silero.synth(text, engine_voice, base + ".wav")
            # Silero не умеет менять темп и тон по фразам — делаем это ffmpeg
            audio = decode(base + ".wav", tempo=1 + rate / 100, semitones=pitch / hz_per_semitone)
            words = None
        else:
            _gtts_phrase(text, base + ".mp3")
            audio = decode(base + ".mp3", tempo=1 + rate / 100, semitones=pitch / hz_per_semitone)
            words = None
        out.append((audio, words, text, ph.get("mood")))
    return out


def _engine_chain(voice, fallback):
    """Выбранный голос, затем запасные: Дмитрий (edge-tts), затем gTTS."""
    chain = [voice]
    if fallback:
        chain += [v for v in ("dmitry", "gtts") if v != voice]
    return chain


def synthesize(phrases, out_wav, workdir, speed=0, seed=None, voice=None, fallback=True,
               precise_words=True):
    """Озвучить фразы и склеить их с паузами.

    voice — имя из voices.VOICES (по умолчанию — из config.py / переменной VOICE).
    fallback=False — не переключаться на другие голоса (для образцов голосов).
    precise_words=False — не запускать faster-whisper (когда субтитры не нужны).
    Возвращает (words, duration): words — список (начало, конец, слово) в секундах
    от начала out_wav; слово никогда не начинается раньше, чем оно звучит.
    """
    random.seed(seed)
    voice = voice or voices.selected()
    rendered, engine = None, None
    errors = []
    for name in _engine_chain(voice, fallback):
        if name in _broken:
            continue
        if name == "gtts":
            eng, eng_voice, male = "gtts", None, False
        else:
            eng, eng_voice, _ = voices.VOICES[name]
            male = name in voices.MALE
        try:
            rendered = _render_phrases(phrases, workdir, speed, eng, eng_voice, male)
            engine = f"{eng}:{name}"
            break
        except Exception as e:  # noqa: BLE001
            _broken.add(name)
            errors.append(f"{name}: {type(e).__name__}: {e}")
            log(f"TTS: голос {name} не сработал ({type(e).__name__}: {e})"
                + (" — пробую запасной" if fallback else ""))
    if rendered is None:
        raise RuntimeError("Ни один голос не сработал: " + " | ".join(errors))

    pieces, spans, per_phrase = [], [], []
    pos = 0.0
    for i, (audio, pw, text, mood) in enumerate(rendered):
        if i > 0:
            pause = PAUSE_BEFORE_REVEAL if mood == "reveal" else random.uniform(PAUSE_MIN, PAUSE_MAX)
            pieces.append(np.zeros(int(SR * pause), dtype=np.float32))
            pos += pause
        on, off = sound_bounds(audio)
        lead = max(on - 0.03, 0.0)
        tail = min(off + 0.08, len(audio) / SR)
        clip = audio[int(lead * SR): int(tail * SR)]
        start_sound, end_sound = pos + (on - lead), pos + (off - lead)
        spans.append((start_sound, end_sound))
        if pw and len(pw) >= len(display_tokens(text)) * 0.6:
            # если звук начался позже, чем говорит WordBoundary (задержка декодера),
            # сдвигаем все слова фразы — субтитры не должны опережать голос
            shift = max(0.0, on - pw[0][0]) + EDGE_LAG
            per_phrase.append([(max(pos + s + shift - lead, start_sound),
                                pos + e + shift - lead, w) for (s, e, w) in pw])
        else:
            per_phrase.append(None)
        pieces.append(clip)
        pos += len(clip) / SR

    full = np.concatenate(pieces) if pieces else np.zeros(1, dtype=np.float32)
    peak = float(np.abs(full).max()) or 1.0
    write_wav(out_wav, full * (0.89 / peak))
    duration = len(full) / SR

    missing = [i for i, w in enumerate(per_phrase) if w is None]
    if missing:
        fallback = _fallback_words(rendered, spans, out_wav, use_whisper=precise_words)
        for i in missing:
            per_phrase[i] = fallback[i]
        log(f"TTS: {len(missing)} phrases without WordBoundary timings")
    words = _monotonic([w for ph in per_phrase for w in ph])
    log(f"TTS: {engine}, {len(phrases)} phrases, {duration:.1f}s, {len(words)} words, speed {speed:+d}%")
    return words, duration


def _fallback_words(rendered, spans, wav_path, use_whisper=True):
    """Тайминги без WordBoundary: faster-whisper, иначе — примерная оценка внутри фраз."""
    phrase_tokens = [display_tokens(t) for (_, _, t, _) in rendered]
    wh = align.whisper_words(wav_path, " ".join(t for (_, _, t, _) in rendered)) if use_whisper else None
    if wh:
        return align.align(phrase_tokens, spans, wh)
    log("TTS: faster-whisper недоступен — тайминги слов считаются примерно по фразам")
    rough = [align.estimate(toks, s, e) for toks, (s, e) in zip(phrase_tokens, spans)]
    return align.snap_to_onsets(rough, wav_path, spans)


def _monotonic(words):
    out, last = [], 0.0
    for s, e, w in sorted(words, key=lambda x: x[0]):
        s = max(s, last)
        e = max(e, s + 0.05)
        out.append((s, e, w))
        last = s
    return out
