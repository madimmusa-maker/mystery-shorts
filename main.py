"""Ежедневный конвейер: тема -> сценарий -> клипы -> озвучка -> субтитры -> видео -> YouTube."""
import datetime as dt
import difflib
import json
import os
import re
import shutil
import sys
import traceback

from shorts import gemini, ghost, music, pixabay, subtitles, tts, video, voices, youtube
from shorts.util import log

ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(ROOT, "history.json")
OUT_DIR = os.path.join(ROOT, "output")
WORK = os.path.join(ROOT, "work")
MAX_TOTAL = 58.5          # жёсткий предел длины ролика
VOICE_DELAY = 0.35        # пауза перед первой фразой
TAIL = 1.0                # тишина после последней фразы
SPEEDS = [0, 4, 8, 12]    # насколько ускорить всю речь (%), если ролик не влезает в 59 с


def load_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            return []


def save_history(items):
    with open(HISTORY, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _norm(s):
    return re.sub(r"[^a-zа-яё0-9 ]", "", (s or "").lower().replace("ё", "е")).strip()


def is_duplicate(topic, used):
    t = _norm(topic)
    for u in used:
        u = _norm(u)
        if not u:
            continue
        if t == u or (len(u) > 5 and (u in t or t in u)):
            return True
        if difflib.SequenceMatcher(None, t, u).ratio() > 0.82:
            return True
    return False


def _guess_mood(text, i, n):
    if i == 0:
        return "hook"
    if text.rstrip().endswith("?"):
        return "question"
    if text.rstrip().endswith("!"):
        return "surprise"
    return "intrigue" if i % 3 == 1 else "fact"


def split_phrases(script):
    """Запасной вариант: если Gemini дал сплошной текст — режем на фразы сами."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", script) if p.strip()]
    return [{"text": p, "mood": _guess_mood(p, i, len(parts))} for i, p in enumerate(parts)]


def validate(story, used):
    for k in ("topic", "title", "description"):
        if not isinstance(story.get(k), str) or not story[k].strip():
            return f"поле {k} пустое"
    phrases = story.get("phrases") or []
    if not phrases and isinstance(story.get("script"), str):
        phrases = split_phrases(story["script"])
    phrases = [p for p in phrases if isinstance(p, dict) and str(p.get("text", "")).strip()]
    if len(phrases) < 6:
        return "нужно 12–20 коротких фраз в поле phrases"
    kws = [k for k in story.get("keywords_en", []) if isinstance(k, str) and k.strip()]
    if len(kws) < 3:
        return "нужно ровно 3 ключевых слова на английском"
    if is_duplicate(story["topic"], used):
        return f"тема «{story['topic']}» уже была, выбери ДРУГОЙ случай"
    script = " ".join(p["text"].strip() for p in phrases)
    n = len(script.split())
    if n < 70:
        return f"сценарий слишком короткий ({n} слов), нужно 80–105"
    if n > 125:
        return f"сценарий слишком длинный ({n} слов), нужно 80–105"
    if "?" not in phrases[-1]["text"] and "?" not in phrases[-2]["text"]:
        return "последняя фраза должна быть вопросом зрителю"
    return None


def normalize(story):
    phrases = story.get("phrases") or split_phrases(story.get("script", ""))
    phrases = [{"text": str(p.get("text", "")).strip(),
                "mood": p.get("mood") if p.get("mood") in tts.PROSODY else "fact"}
               for p in phrases if isinstance(p, dict) and str(p.get("text", "")).strip()]
    reveals = [i for i, p in enumerate(phrases) if p["mood"] == "reveal"]
    for i in reveals[1:]:  # драматическая пауза — только перед одной развязкой
        phrases[i]["mood"] = "surprise"
    story["phrases"] = phrases
    story["script"] = " ".join(p["text"] for p in phrases)
    story["keywords_en"] = [k.strip() for k in story.get("keywords_en", [])
                            if isinstance(k, str) and k.strip()][:3]
    tags = [h.strip().replace(" ", "") for h in story.get("hashtags", []) if isinstance(h, str) and h.strip()]
    story["hashtags"] = [h if h.startswith("#") else "#" + h for h in tags][:8]
    return story


def get_story(used):
    feedback = None
    for attempt in range(5):
        story = gemini.make_story(used, feedback)
        problem = validate(story, used)
        if not problem:
            return normalize(story)
        log(f"Story rejected ({attempt + 1}/5): {problem}")
        feedback = problem
    raise RuntimeError("Gemini 5 раз подряд выдал неподходящий сценарий")


def voice_over(story, used):
    """Озвучить; если не влезает в 59 с — ускорить речь или попросить короче."""
    voice = os.path.join(WORK, "voice.wav")
    for _ in range(3):
        for speed in SPEEDS:
            words, dur = tts.synthesize(story["phrases"], voice, WORK, speed=speed)
            if dur + VOICE_DELAY + TAIL <= MAX_TOTAL:
                return voice, words, dur
            log(f"TTS: {dur:.1f}s is too long at speed {speed:+d}%")
        log("Asking Gemini for a shorter script")
        shorter = gemini.make_story(used, f"сценарий про «{story['topic']}» вышел слишком длинным, "
                                          f"напиши про этот же случай не больше 85 слов")
        if len(shorter.get("phrases") or []) >= 6:
            story.update({k: v for k, v in shorter.items() if v})
            normalize(story)
    raise RuntimeError("Не удалось уложить озвучку в 59 секунд")


def write_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as fh:
            fh.write(f"{name}={value}\n")


def main():
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)
    os.makedirs(OUT_DIR, exist_ok=True)

    history = load_history()
    used = [h.get("topic", "") for h in history] + [h.get("title", "") for h in history]

    log("Step 1-2: topic and script")
    story = get_story(used)
    log(f"Topic: {story['topic']} | Title: {story['title']}")
    for p in story["phrases"]:
        log(f"  [{p['mood']}] {p['text']}")

    log(f"Step 4: voice ({voices.selected()})")
    voice, words, dur = voice_over(story, used)

    log("Step 3: stock clips")
    clips = pixabay.fetch_clips(story["keywords_en"], WORK)
    total = min(dur + VOICE_DELAY + TAIL, MAX_TOTAL)

    log("Step 5: subtitles and music")
    ass = os.path.join(WORK, "subs.ass")
    font = subtitles.build_ass(words, ass, offset=VOICE_DELAY, total=total)
    log(f"Subtitles font: {font}")
    bg = music.make_music(total, os.path.join(WORK, "music.wav"))
    log("Step 5b: ghost narrator")
    ghost_path = None
    try:
        ghost_path = ghost.render(voice, total, os.path.join(WORK, "ghost.mov"), voice_delay=VOICE_DELAY)
    except Exception:  # noqa: BLE001 — без призрака видео всё равно соберётся
        log("Ghost FAILED, continuing without it:\n" + traceback.format_exc())

    log("Step 6: render")
    date = dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime("%Y-%m-%d")
    out = os.path.join(OUT_DIR, f"short_{date}.mp4")
    video.build(clips, voice, bg, ass, out, total, VOICE_DELAY, WORK, ghost_path=ghost_path)

    title = youtube.make_title(story["title"])
    description = story["description"].strip() + "\n\n" + " ".join(story["hashtags"] + ["#shorts"])
    tags = youtube.make_tags(story["hashtags"], story["keywords_en"])
    with open(os.path.join(OUT_DIR, "info.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"ЗАГОЛОВОК:\n{title}\n\nОПИСАНИЕ:\n{description}\n\nТЕГИ:\n{', '.join(tags)}\n\n"
                 "СЦЕНАРИЙ:\n" + "\n".join(f"[{p['mood']}] {p['text']}" for p in story["phrases"]) + "\n")

    record = {"date": date, "topic": story["topic"], "title": story["title"],
              "keywords": story["keywords_en"], "video_id": None}

    log("Step 7: upload")
    upload_ok, attempted = False, False
    if os.environ.get("SKIP_UPLOAD", "").lower() in ("1", "true", "yes"):
        log("Upload skipped (SKIP_UPLOAD)")
    elif not youtube.has_credentials():
        log("Upload skipped: нет секретов YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN")
    else:
        attempted = True
        try:
            record["video_id"] = youtube.upload(out, title, description, tags)
            upload_ok = True
        except Exception:  # noqa: BLE001
            log("YouTube upload FAILED:\n" + traceback.format_exc())

    history.append(record)
    save_history(history)
    write_output("uploaded", "true" if upload_ok else "false")
    if not upload_ok:
        log("Video saved as GitHub Actions artifact (see run page -> Artifacts)")
    # ошибка (красный крестик) только если загрузку пробовали и она сломалась
    return 2 if attempted and not upload_ok else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        log("PIPELINE FAILED:\n" + traceback.format_exc())
        write_output("uploaded", "false")
        sys.exit(1)
