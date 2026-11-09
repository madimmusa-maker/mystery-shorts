"""Образцы всех голосов: одна и та же короткая фраза каждым голосом -> samples/*.mp3.

Запуск: python voice_samples.py ["свой текст"]
"""
import os
import shutil
import subprocess
import sys
import traceback

from shorts import tts, voices
from shorts.util import log

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "samples")
WORK = os.path.join(ROOT, "work_samples")

DEFAULT_TEXT = ("В 1959 году девять туристов ушли в горы Урала. "
                "Но что они увидели той ночью? Никто не вернулся!")

ORDER = ["aidar", "baya", "kseniya", "xenia", "eugene", "dmitry", "svetlana"]


def phrases_from(text):
    """Режем текст на фразы и даём им настроение, как в обычном ролике."""
    import re
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text) if p.strip()]
    out = []
    for i, p in enumerate(parts):
        mood = "hook" if i == 0 else "question" if p.endswith("?") else "surprise" if p.endswith("!") else "intrigue"
        out.append({"text": p, "mood": mood})
    return out


def main():
    text = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or DEFAULT_TEXT
    phrases = phrases_from(text)
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    report = [f"Текст: {text}", ""]
    ok = 0
    for n, name in enumerate(ORDER, 1):
        engine, _, title = voices.VOICES[name]
        wd = os.path.join(WORK, name)
        os.makedirs(wd)
        wav = os.path.join(wd, "voice.wav")
        mp3 = os.path.join(OUT, f"{n:02d}_{name}_{engine}.mp3")
        try:
            # seed одинаковый — у всех голосов одинаковые паузы и интонации
            tts.synthesize(phrases, wav, wd, voice=name, fallback=False, seed=42, precise_words=False)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", wav, "-af", "apad=pad_dur=0.4",
                            "-c:a", "libmp3lame", "-b:a", "128k", mp3], check=True)
            report.append(f"✅ {os.path.basename(mp3)} — {title}. Чтобы выбрать: VOICE = \"{name}\"")
            ok += 1
        except Exception as e:  # noqa: BLE001
            log(f"{name} FAILED:\n{traceback.format_exc()}")
            report.append(f"❌ {name} — {title}: не получилось ({type(e).__name__}: {e})")
    with open(os.path.join(OUT, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")
    print("\n".join(report))
    shutil.rmtree(WORK, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
