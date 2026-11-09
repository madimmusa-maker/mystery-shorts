"""Озвучка edge-tts (ru-RU-DmitryNeural) с таймингом каждого слова."""
import asyncio
import re

import edge_tts

from .util import log, media_duration, retry

VOICE = "ru-RU-DmitryNeural"


def clean_for_speech(text):
    text = re.sub(r"[«»\"“”„*_#<>\[\]{}|~^]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


async def _synth(text, out_path, rate, pitch):
    comm = edge_tts.Communicate(text, VOICE, rate=rate, pitch=pitch, boundary="WordBoundary")
    words = []
    with open(out_path, "wb") as fh:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                dur = chunk["duration"] / 1e7
                words.append((start, start + dur, chunk["text"]))
    return words


def _estimate_words(text, duration):
    """Запасной вариант, если сервис не прислал тайминги слов."""
    tokens = text.split()
    weights = [len(t) + 2 for t in tokens]
    total = sum(weights)
    t, out = 0.15, []
    span = max(duration - 0.3, 1)
    for tok, w in zip(tokens, weights):
        d = span * w / total
        out.append((t, t + d * 0.9, re.sub(r"[^\w\-]", "", tok)))
        t += d
    return [w for w in out if w[2]]


def synthesize(text, out_path, rate="-8%", pitch="-2Hz"):
    text = clean_for_speech(text)
    words = retry(lambda: asyncio.run(_synth(text, out_path, rate, pitch)),
                  attempts=4, delay=5, what="edge-tts")
    duration = media_duration(out_path)
    if len(words) < len(text.split()) * 0.5:
        log("TTS: word timings missing, estimating")
        words = _estimate_words(text, duration)
    log(f"TTS: {duration:.1f}s, {len(words)} words, rate {rate}")
    return words, duration
