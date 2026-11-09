"""Тема и сценарий через Gemini API (бесплатный ключ Google AI Studio)."""
import json
import os
import random
import re
import time

import requests

from .util import log

API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.0-flash",
]

CATEGORIES = [
    "пропавшая экспедиция или исчезнувшая группа людей",
    "странная археологическая находка",
    "необъяснимое природное явление",
    "загадочное исчезновение корабля или самолёта",
    "нераскрытая загадочная история XX века",
    "таинственный артефакт или древний документ",
    "загадочное место на карте",
    "странный сигнал, звук или радиопередача",
    "необъяснимое происшествие в СССР или России",
    "древняя загадка исчезнувшей цивилизации",
    "загадка из истории мореплавания",
    "необъяснимая находка во льдах, пустыне или пещере",
]

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "topic": {"type": "STRING"},
        "title": {"type": "STRING"},
        "script": {"type": "STRING"},
        "description": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "keywords_en": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["topic", "title", "script", "description", "hashtags", "keywords_en"],
}


def _prompt(used_topics, category, feedback):
    used = "\n".join(f"- {t}" for t in used_topics[-300:]) or "- (пока нет)"
    fb = f"\n\nВАЖНО, исправь прошлую попытку: {feedback}" if feedback else ""
    return f"""Ты автор русскоязычного YouTube-канала коротких видео (Shorts) про тайны и загадки.

Выбери ОДИН реальный, хорошо задокументированный случай. Направление на сегодня: {category}.
Это должен быть случай, о котором есть статьи в энциклопедиях и серьёзных источниках.

Темы, которые УЖЕ были (их и очень похожие НЕ бери):
{used}

Напиши сценарий озвучки на русском языке длиной 85–115 слов (35–50 секунд речи):
- Первая фраза — сильный крючок, который цепляет за 2 секунды (без «Привет», без «В этом видео»).
- Дальше — интрига: конкретные факты (год, место, имена), нарастание напряжения.
- Только реальные события и проверенные факты. Ничего не выдумывай: если не уверен в детали — не упоминай её.
- Гипотезы, легенды и слухи подавай ТОЛЬКО как версии: «по одной из версий», «некоторые считают», «есть легенда».
- В конце — вопрос зрителю (например: «А как думаете вы, что там произошло?»).
- Пиши для озвучки: короткие предложения, без эмодзи, без списков, без ремарок, без кавычек-ёлочек внутри слов, числа можно цифрами.

Также дай:
- topic: короткое название случая (например «Перевал Дятлова»), для учёта повторов;
- title: цепляющий заголовок до 70 символов, без хэштегов;
- description: описание 2–4 предложения, факты без выдумок, в конце призыв подписаться;
- hashtags: 5–8 хэштегов на русском и английском, каждый начинается с #;
- keywords_en: ровно 3 коротких ключевых фразы на английском (1–2 слова) для поиска атмосферных стоковых видео
  по теме (например "snowy mountains", "old ship", "dark forest"). Без имён людей и названий — только то, что можно снять.

Ответ — строго JSON по схеме.{fb}"""


def _call(model, key, prompt, use_schema):
    cfg = {"temperature": 0.9, "responseMimeType": "application/json"}
    if use_schema:
        cfg["responseSchema"] = SCHEMA
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg}
    r = requests.post(f"{API}/models/{model}:generateContent",
                      params={"key": key}, json=body, timeout=180)
    return r


def _list_flash_models(key):
    try:
        r = requests.get(f"{API}/models", params={"key": key, "pageSize": 200}, timeout=60)
        r.raise_for_status()
        names = []
        for m in r.json().get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                n = m["name"].split("/", 1)[-1]
                if "flash" in n and "image" not in n and "tts" not in n and "live" not in n:
                    names.append(n)
        return names
    except Exception as e:  # noqa: BLE001
        log(f"Gemini: could not list models: {e}")
        return []


def _parse(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def generate(prompt):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Нет секрета GEMINI_API_KEY")
    models = [m for m in [os.environ.get("GEMINI_MODEL", "").strip()] if m] + DEFAULT_MODELS
    tried, discovered = set(), False
    errors = []
    while True:
        queue = [m for m in models if m not in tried]
        if not queue:
            if discovered:
                break
            discovered = True
            models += _list_flash_models(key)
            continue
        model = queue[0]
        tried.add(model)
        use_schema = True
        for attempt in range(4):
            try:
                r = _call(model, key, prompt, use_schema)
            except requests.RequestException as e:
                errors.append(f"{model}: {e}")
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 200:
                try:
                    data = r.json()
                    text = "".join(p.get("text", "") for p in
                                   data["candidates"][0]["content"]["parts"])
                    log(f"Gemini: answer from {model}")
                    return _parse(text)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{model}: bad answer {e}")
                    time.sleep(3)
                    continue
            msg = r.text[:300]
            errors.append(f"{model}: HTTP {r.status_code} {msg}")
            if r.status_code == 400 and use_schema and "schema" in msg.lower():
                use_schema = False
                continue
            if r.status_code in (400, 401, 403) and "API key" in msg:
                raise RuntimeError(f"Gemini отклонил ключ: {msg}")
            if r.status_code in (404, 400):
                break  # модель недоступна — пробуем следующую
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(15 * (attempt + 1))
                continue
            break
    raise RuntimeError("Gemini не ответил:\n" + "\n".join(errors[-8:]))


def make_story(used_topics, feedback=None):
    category = random.choice(CATEGORIES)
    log(f"Gemini: category = {category}")
    return generate(_prompt(used_topics, category, feedback))
