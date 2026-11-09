"""Вертикальные стоковые клипы с Pexels."""
import os
import random

import requests

from .util import log, retry

API = "https://api.pexels.com/videos/search"
FALLBACK_QUERIES = ["dark forest", "fog", "night sky", "abandoned building",
                    "stormy sea", "old ruins", "candle dark", "mountains mist"]


def _search(query, key):
    def go():
        r = requests.get(API, headers={"Authorization": key},
                         params={"query": query, "orientation": "portrait",
                                 "per_page": 15, "size": "medium"}, timeout=60)
        if r.status_code in (401, 403):
            raise RuntimeError(f"Pexels отклонил ключ (HTTP {r.status_code})")
        r.raise_for_status()
        return r.json().get("videos", [])
    return retry(go, attempts=3, what=f"Pexels search '{query}'")


def _best_file(video):
    files = [f for f in video.get("video_files", [])
             if f.get("width") and f.get("height") and f["height"] > f["width"]
             and f.get("file_type", "") == "video/mp4"]
    if not files:
        return None
    # ближе всего к 1080x1920, но не меньше 720 по ширине, если возможно
    good = [f for f in files if f["width"] >= 720] or files
    return min(good, key=lambda f: abs(f["width"] - 1080))


def fetch_clips(keywords, workdir, want=5, minimum=3):
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Нет секрета PEXELS_API_KEY")
    chosen, seen = [], set()
    queries = [k for k in keywords if k] + random.sample(FALLBACK_QUERIES, len(FALLBACK_QUERIES))
    per_query = 2
    for i, q in enumerate(queries):
        if len(chosen) >= want:
            break
        if i >= len(keywords) and len(chosen) >= minimum:
            break
        try:
            videos = _search(q, key)
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"Pexels: skip '{q}': {e}")
            continue
        videos = [v for v in videos if v.get("duration", 0) >= 4 and v["id"] not in seen]
        random.shuffle(videos)
        taken = 0
        for v in videos:
            f = _best_file(v)
            if not f:
                continue
            seen.add(v["id"])
            chosen.append((q, v["id"], f["link"]))
            taken += 1
            if taken >= per_query or len(chosen) >= want:
                break
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
            log(f"Pexels: clip {vid} for '{q}'")
        except Exception as e:  # noqa: BLE001
            log(f"Pexels: failed clip {vid}: {e}")
    if len(paths) < minimum:
        raise RuntimeError(f"Удалось скачать только {len(paths)} клипов с Pexels")
    return paths
