"""Стоковые клипы с Pixabay (https://pixabay.com/api/docs/#api_search_videos).

У Pixabay нет фильтра ориентации для видео, поэтому сначала берём вертикальные
ролики, а если их мало — горизонтальные (их потом обрезает по центру video.py).
"""
import os
import random

import requests

from .util import log, retry

API = "https://pixabay.com/api/videos/"
FALLBACK_QUERIES = ["dark forest", "fog", "night sky", "abandoned building",
                    "stormy sea", "ruins", "candle", "mountains mist"]
SIZES = ["large", "medium", "small"]


def _search(query, key):
    def go():
        r = requests.get(API, params={"key": key, "q": query[:100], "per_page": 50,
                                      "safesearch": "true", "video_type": "film"},
                         timeout=60)
        if r.status_code in (400, 401, 403) and "key" in r.text.lower():
            raise PermissionError(f"Pixabay отклонил ключ (HTTP {r.status_code}): {r.text[:200]}")
        r.raise_for_status()
        return r.json().get("hits", [])
    try:
        return retry(go, attempts=3, what=f"Pixabay search '{query}'")
    except PermissionError:
        raise
    except Exception as e:  # noqa: BLE001
        log(f"Pixabay: skip '{query}': {e}")
        return []


def _best_file(hit):
    """Вернуть (url, vertical) — файл, ближайший к 1080 по ширине кадра в 9:16."""
    files = [v for s in SIZES if (v := hit.get("videos", {}).get(s)) and v.get("url")
             and v.get("width") and v.get("height")]
    if not files:
        return None
    vertical = files[0]["height"] > files[0]["width"]
    # вертикальное: ближе к 1920 по высоте; горизонтальное: ближе к 1080 (без 4K-гигантов)
    target = 1920 if vertical else 1080
    good = [f for f in files if f["height"] >= min(target, 1080)] or files
    best = min(good, key=lambda f: abs(f["height"] - target))
    return best["url"], vertical


def fetch_clips(keywords, workdir, want=5, minimum=3):
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Нет секрета PIXABAY_API_KEY")
    queries = [k for k in keywords if k] + random.sample(FALLBACK_QUERIES, len(FALLBACK_QUERIES))
    vertical, horizontal, seen = [], [], set()
    for i, q in enumerate(queries):
        if len(vertical) >= want:
            break
        if i >= len(keywords) and len(vertical) + len(horizontal) >= want:
            break
        hits = [h for h in _search(q, key) if h.get("duration", 0) >= 4 and h["id"] not in seen]
        random.shuffle(hits)
        v_taken = h_taken = 0
        for h in hits:
            best = _best_file(h)
            if not best:
                continue
            url, is_vert = best
            if is_vert and v_taken < 2:
                vertical.append((q, h["id"], url))
                v_taken += 1
                seen.add(h["id"])
            elif not is_vert and h_taken < 2:
                horizontal.append((q, h["id"], url))
                h_taken += 1
                seen.add(h["id"])
    chosen = (vertical + horizontal)[:want]
    log(f"Pixabay: {len(vertical)} vertical, {len(horizontal)} horizontal candidates")

    paths = []
    for n, (q, vid, link) in enumerate(chosen):
        path = os.path.join(workdir, f"clip_{n}.mp4")

        def dl(link=link, path=path):
            with requests.get(link, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(path, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
        try:
            retry(dl, attempts=3, what=f"download clip {vid}")
            paths.append(path)
            log(f"Pixabay: clip {vid} for '{q}'")
        except Exception as e:  # noqa: BLE001
            log(f"Pixabay: failed clip {vid}: {e}")
    if len(paths) < minimum:
        raise RuntimeError(f"Удалось скачать только {len(paths)} клипов с Pixabay")
    return paths
