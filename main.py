"""Ежедневный конвейер: тема -> сценарий -> клипы -> озвучка -> субтитры -> видео -> YouTube."""
import datetime as dt
import difflib
import json
import os
import re
import shutil
import sys
import traceback

from shorts import gemini, music, pexels, subtitles, tts, video, youtube
from shorts.util import log

ROOT = os.path.dirname(os.path.abspath(__file__))
HISTORY = os.path.join(ROOT, "history.json")
OUT_DIR = os.path.join(ROOT, "output")
WORK = os.path.join(ROOT, "work")
MAX_TOTAL = 58.5          # жёсткий предел длины ролика
VOICE_DELAY = 0.35        # пауза перед первой фразой
TAIL = 1.0                # тишина после последней фразы
RATES = ["-8%", "-3%", "+3%", "+8%"]


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


def validate(story, used):
    for k in ("topic", "title", "script", "description"):
        if not isinstance(story.get(k), str) or not story[k].strip():
            return f"поле {k} пустое"
    kws = [k for k in story.get("keywords_en", []) if isinstance(k, str) and k.strip()]
    if len(kws) < 3:
        return "нужно ровно 3 ключевых слова на английском"
    if is_duplicate(story["topic"], used):
        return f"тема «{story['topic']}» уже была, выбери ДРУГОЙ случай"
    n = len(story["script"].split())
    if n < 75:
        return f"сценарий слишком короткий ({n} слов), нужно 85–115"
    if n > 130:
        return f"сценарий слишком длинный ({n} слов), нужно 85–115"
    if "?" not in story["script"][-200:]:
        return "в конце сценария должен быть вопрос зрителю"
    return None


def normalize(story):
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
    voice = os.path.join(WORK, "voice.mp3")
    for _ in range(3):
        for rate in RATES:
            words, dur = tts.synthesize(story["script"], voice, rate=rate)
            if dur + VOICE_DELAY + TAIL <= MAX_TOTAL:
                return voice, words, dur
            log(f"TTS: {dur:.1f}s is too long at {rate}")
        log("Asking Gemini for a shorter script")
        shorter = gemini.make_story(used, f"сценарий про «{story['topic']}» вышел слишком длинным, "
                                          f"напиши про этот же случай не больше 95 слов")
        if shorter.get("script") and len(shorter["script"].split()) >= 60:
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
    log(f"Script: {story['script']}")

    log("Step 4: voice")
    voice, words, dur = voice_over(story, used)

    log("Step 3: stock clips")
    clips = pexels.fetch_clips(story["keywords_en"], WORK)
    total = min(dur + VOICE_DELAY + TAIL, MAX_TOTAL)

    log("Step 5: subtitles and music")
    ass = os.path.join(WORK, "subs.ass")
    font = subtitles.build_ass(words, ass, offset=VOICE_DELAY, total=total)
    log(f"Subtitles font: {font}")
    bg = music.make_music(total, os.path.join(WORK, "music.wav"))

    log("Step 6: render")
    date = dt.datetime.now(dt.timezone(dt.timedelta(hours=5))).strftime("%Y-%m-%d")
    out = os.path.join(OUT_DIR, f"short_{date}.mp4")
    video.build(clips, voice, bg, ass, out, total, VOICE_DELAY, WORK)

    title = youtube.make_title(story["title"])
    description = story["description"].strip() + "\n\n" + " ".join(story["hashtags"] + ["#shorts"])
    tags = youtube.make_tags(story["hashtags"], story["keywords_en"])
    with open(os.path.join(OUT_DIR, "info.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"ЗАГОЛОВОК:\n{title}\n\nОПИСАНИЕ:\n{description}\n\nТЕГИ:\n{', '.join(tags)}\n\n"
                 f"СЦЕНАРИЙ:\n{story['script']}\n")

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
