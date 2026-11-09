"""Озвучка: edge-tts (ru-RU-DmitryNeural) с таймингом слов, запасной вариант — gTTS.

Если edge-tts не работает (например, NoAudioReceived на серверах GitHub),
текст озвучивается через gTTS (Google, русский), а тайминги слов
рассчитываются примерно — по длине слов и паузам на знаках препинания.
"""
import asyncio
import os
import re

import edge_tts

from .util import log, media_duration, retry, run

VOICE = "ru-RU-DmitryNeural"

# После первой неудачи edge-tts в этом запуске сразу идём в gTTS,
# чтобы не тратить время на повторы при подборе скорости речи.
_edge_broken = False


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


def rate_to_tempo(rate):
    """'-8%' -> 0.92 (множитель скорости для ffmpeg atempo)."""
    pct = int(fmt_rate(rate).rstrip("%"))
    return max(0.5, min(2.0, 1 + pct / 100))


def clean_for_speech(text):
    text = re.sub(r"[«»\"“”„*_#<>\[\]{}|~^&]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------- edge-tts ----------

async def _edge(text, out_path, rate, pitch, boundary):
    comm = edge_tts.Communicate(text, VOICE, rate=rate, pitch=pitch, boundary=boundary)
    words = []
    with open(out_path, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def _edge_synth(text, out_path, rate, pitch):
    """Несколько вариантов запроса: обычный, без сдвига тона, без таймингов слов."""
    variants = [(rate, pitch, "WordBoundary"),
                (rate, "+0Hz", "WordBoundary"),
                (rate, "+0Hz", "SentenceBoundary")]
    last = None
    for r, p, b in variants:
        try:
            words = retry(lambda r=r, p=p, b=b: asyncio.run(_edge(text, out_path, r, p, b)),
                          attempts=2, delay=4, what=f"edge-tts ({r}, {p}, {b})")
            if os.path.getsize(out_path) > 1000:
                return words
            last = RuntimeError("edge-tts вернул пустой звук")
        except Exception as e:  # noqa: BLE001
            last = e
    raise last


# ---------- gTTS (запасной вариант) ----------

def _gtts_synth(text, out_path, rate):
    from gtts import gTTS  # импорт здесь: нужен только при запасном варианте

    raw = out_path + ".gtts.mp3"

    def go():
        gTTS(text=text, lang="ru", tld="com", slow=False).save(raw)
        if os.path.getsize(raw) < 1000:
            raise RuntimeError("gTTS вернул пустой звук")
    retry(go, attempts=4, delay=5, what="gTTS")

    # gTTS не умеет менять скорость — делаем это ffmpeg; заодно обрезаем
    # тишину в начале и в конце, чтобы тайминги субтитров были точнее.
    tempo = rate_to_tempo(rate)
    af = (f"silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          f"areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,"
          f"atempo={tempo:.3f}")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw,
         "-af", af, "-ar", "24000", "-c:a", "libmp3lame", "-b:a", "96k", out_path])
    os.remove(raw)


def estimate_words(text, duration, start=0.0):
    """Примерные тайминги слов: пропорционально длине + паузы на знаках препинания."""
    tokens = text.split()
    if not tokens:
        return []
    weights = []
    for tok in tokens:
        w = len(re.sub(r"[^\w]", "", tok)) + 1.5
        pause = 0.0
        if re.search(r"[.!?…]$", tok):
            pause = 5.0
        elif re.search(r"[,;:—–-]$", tok):
            pause = 2.5
        weights.append((w, pause))
    total = sum(w + p for w, p in weights)
    scale = max(duration - start, 0.5) / total
    t, out = start, []
    for tok, (w, p) in zip(tokens, weights):
        d = w * scale
        word = re.sub(r"[^\w\-]", "", tok).strip("-")
        if word:
            out.append((t, t + d * 0.95, word))
        t += d + p * scale
    return out


# ---------- общий вход ----------

def synthesize(text, out_path, rate="-8%", pitch="-2Hz"):
    global _edge_broken
    text = clean_for_speech(text)
    rate, pitch = fmt_rate(rate), fmt_pitch(pitch)

    words, engine = None, None
    if not _edge_broken:
        try:
            words = _edge_synth(text, out_path, rate, pitch)
            engine = "edge-tts"
        except Exception as e:  # noqa: BLE001
            _edge_broken = True
            log(f"TTS: edge-tts не сработал ({type(e).__name__}: {e}) — переключаюсь на gTTS")
    if engine is None:
        _gtts_synth(text, out_path, rate)
        words, engine = [], "gTTS"

    duration = media_duration(out_path)
    if len(words) < len(text.split()) * 0.5:
        log("TTS: тайминги слов рассчитываются примерно")
        words = estimate_words(text, duration)
    log(f"TTS: {engine}, {duration:.1f}s, {len(words)} words, rate {rate}")
    return words, duration
