"""Призрак-рассказчик: оригинальный персонаж, нарисованный кодом (Pillow).

Рисуем несколько спрайтов (6 степеней открытия рта x 3 состояния глаз),
а затем покадрово собираем прозрачное видео: призрак покачивается,
моргает и открывает рот в такт громкости голоса.
"""
import math
import random
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FPS = 30
CANVAS_W, CANVAS_H = 360, 420   # размер прозрачного холста с призраком
SS = 3                          # сглаживание: рисуем в 3 раза крупнее
MOUTH_LEVELS = 6
BOB_AMPLITUDE = 14              # пикселей вверх-вниз
BOB_PERIOD = 2.6                # секунд


def _sprite(mouth, eyes):
    """mouth: 0..MOUTH_LEVELS-1; eyes: 0 — открыты, 1 — прикрыты, 2 — закрыты."""
    W, H = CANVAS_W * SS, (CANVAS_H - 2 * BOB_AMPLITUDE) * SS
    cx = W // 2
    body_w, head_r = int(W * 0.62), int(W * 0.31)
    top = int(H * 0.10)
    bottom = int(H * 0.80)
    left, right = cx - body_w // 2, cx + body_w // 2

    # силуэт: купол-голова + тело + волнистый «хвост»
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([cx - head_r, top, cx + head_r, top + 2 * head_r], fill=255)
    d.rectangle([left, top + head_r, right, bottom], fill=255)
    waves = 4
    wave_w = body_w / waves
    for i in range(waves):  # круглые «язычки» хвоста, выступают вниз
        x0 = left + i * wave_w
        d.ellipse([x0, bottom - wave_w * 0.5, x0 + wave_w, bottom + wave_w * 0.5], fill=255)
    for i in range(waves - 1):  # маленькие выемки между язычками
        x0 = left + (i + 1) * wave_w
        r = wave_w * 0.16
        d.ellipse([x0 - r, bottom + wave_w * 0.30, x0 + r, bottom + wave_w * 0.30 + 2 * r], fill=0)
    # маленькие ручки
    arm = int(W * 0.09)
    ay = top + head_r + int(H * 0.10)
    d.ellipse([left - arm, ay, left + arm // 2, ay + int(arm * 1.3)], fill=255)
    d.ellipse([right - arm // 2, ay + arm // 3, right + arm, ay + arm // 3 + int(arm * 1.3)], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(SS * 0.8))

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # мягкое свечение вокруг
    glow = mask.filter(ImageFilter.GaussianBlur(SS * 14)).point(lambda v: int(v * 0.55))
    img.paste((200, 225, 255, 255), (0, 0), glow)
    # полупрозрачное белое тело с лёгким голубым оттенком снизу
    grad = Image.linear_gradient("L").resize((W, H))
    body = Image.merge("RGBA", (
        Image.new("L", (W, H), 255),
        grad.point(lambda v: 255 - v // 14),
        Image.new("L", (W, H), 255),
        mask.point(lambda v: int(v * 0.80)),
    ))
    img = Image.alpha_composite(img, body)

    d = ImageDraw.Draw(img)
    eye_y = top + int(head_r * 1.05)
    eye_dx = int(head_r * 0.42)
    eye_w, eye_h = int(head_r * 0.36), int(head_r * 0.50)
    dark = (28, 22, 45, 255)
    for ex in (cx - eye_dx, cx + eye_dx):
        if eyes == 0:
            d.ellipse([ex - eye_w // 2, eye_y - eye_h // 2, ex + eye_w // 2, eye_y + eye_h // 2], fill=dark)
            r1 = int(eye_w * 0.20)
            d.ellipse([ex - eye_w * 0.22 - r1, eye_y - eye_h * 0.22 - r1,
                       ex - eye_w * 0.22 + r1, eye_y - eye_h * 0.22 + r1], fill=(255, 255, 255, 255))
            r2 = int(eye_w * 0.09)
            d.ellipse([ex + eye_w * 0.15 - r2, eye_y + eye_h * 0.12 - r2,
                       ex + eye_w * 0.15 + r2, eye_y + eye_h * 0.12 + r2], fill=(255, 255, 255, 230))
        elif eyes == 1:
            h = eye_h // 4
            d.ellipse([ex - eye_w // 2, eye_y - h // 2, ex + eye_w // 2, eye_y + h], fill=dark)
        else:
            d.arc([ex - eye_w // 2, eye_y - eye_h // 4, ex + eye_w // 2, eye_y + eye_h // 4],
                  start=10, end=170, fill=dark, width=SS * 4)
    # румянец
    blush = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    by = eye_y + int(eye_h * 0.62)
    br = int(eye_w * 0.42)
    for ex in (cx - eye_dx - int(eye_w * 0.55), cx + eye_dx + int(eye_w * 0.55)):
        bd.ellipse([ex - br, by - br // 2, ex + br, by + br // 2], fill=(255, 140, 170, 120))
    img = Image.alpha_composite(img, blush.filter(ImageFilter.GaussianBlur(SS * 3)))
    # ротик
    d = ImageDraw.Draw(img)
    my = eye_y + int(eye_h * 0.80)
    if mouth == 0:
        mw = int(eye_w * 0.55)
        d.arc([cx - mw // 2, my - mw // 3, cx + mw // 2, my + mw // 3],
              start=20, end=160, fill=dark, width=SS * 4)
    else:
        k = mouth / (MOUTH_LEVELS - 1)
        mw = int(eye_w * (0.45 + 0.35 * k))
        mh = int(eye_w * (0.20 + 0.80 * k))
        d.ellipse([cx - mw // 2, my - mh // 3, cx + mw // 2, my + mh * 2 // 3], fill=(60, 20, 45, 255))
        if mouth >= 3:  # язычок
            tw = int(mw * 0.55)
            d.ellipse([cx - tw // 2, my + mh * 2 // 3 - tw // 2, cx + tw // 2, my + mh * 2 // 3],
                      fill=(240, 120, 150, 255))
    return img.resize((CANVAS_W, CANVAS_H - 2 * BOB_AMPLITUDE), Image.LANCZOS)


def _voice_levels(wav_path, n_frames, delay):
    """Громкость голоса для каждого кадра видео -> уровень рта 0..MOUTH_LEVELS-1."""
    with wave.open(wav_path) as w:
        sr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() > 1:
            x = x.reshape(-1, w.getnchannels()).mean(axis=1)
    hop = sr / FPS
    rms = np.zeros(n_frames)
    for f in range(n_frames):
        a = int((f / FPS - delay) * sr)
        if a < 0 or a >= len(x):
            continue
        seg = x[a: a + int(hop)]
        rms[f] = float(np.sqrt((seg ** 2).mean())) if len(seg) else 0
    ref = np.percentile(rms[rms > 0], 90) if (rms > 0).any() else 1.0
    levels, smooth = [], 0.0
    for v in rms / (ref or 1.0):
        # быстро открывается, чуть медленнее закрывается
        smooth = v if v > smooth else smooth * 0.55 + v * 0.45
        lvl = 0 if smooth < 0.12 else min(MOUTH_LEVELS - 1, 1 + int(smooth * (MOUTH_LEVELS - 1)))
        levels.append(lvl)
    return levels


def _blinks(n_frames):
    """Номера состояний глаз для каждого кадра: изредка моргает."""
    eyes = [0] * n_frames
    f = int(FPS * random.uniform(1.0, 2.5))
    pattern = [1, 2, 2, 1]
    while f < n_frames:
        for k, e in enumerate(pattern):
            if f + k < n_frames:
                eyes[f + k] = e
        if random.random() < 0.2:  # иногда двойное моргание
            f += len(pattern) + 3
        else:
            f += int(FPS * random.uniform(2.5, 5.0))
    return eyes


def render(voice_wav, duration, out_path, voice_delay=0.0, seed=None):
    """Сделать прозрачное видео с призраком (mov, qtrle с альфа-каналом)."""
    random.seed(seed)
    n = int(math.ceil(duration * FPS))
    sprites = {(m, e): _sprite(m, e) for m in range(MOUTH_LEVELS) for e in range(3)}
    mouth = _voice_levels(voice_wav, n, voice_delay)
    eyes = _blinks(n)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba",
         "-s", f"{CANVAS_W}x{CANVAS_H}", "-r", str(FPS), "-i", "-",
         "-c:v", "qtrle", "-pix_fmt", "argb", out_path],
        stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    phase = random.uniform(0, 2 * math.pi)
    try:
        for f in range(n):
            t = f / FPS
            y = BOB_AMPLITUDE + BOB_AMPLITUDE * math.sin(2 * math.pi * t / BOB_PERIOD + phase)
            frame = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
            frame.alpha_composite(sprites[(mouth[f], eyes[f])], (0, int(round(y))))
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    if proc.wait() != 0:
        raise RuntimeError("ghost render failed: " + proc.stderr.read().decode()[-300:])
    return out_path
