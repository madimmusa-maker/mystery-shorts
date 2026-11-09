"""Сборка вертикального видео 1080x1920 в ffmpeg."""
import os
import random

from .util import log, media_duration, run

W, H, FPS = 1080, 1920, 30
# Призрак: верх холста. Субтитры по центру y=860, две строки занимают ~740–980,
# так что призрак (1140–1560) их не перекрывает и остаётся выше интерфейса Shorts.
GHOST_TOP = 1140
LOOK = ("eq=brightness=-0.07:contrast=1.08:saturation=0.70,"
        "colorbalance=bs=0.05:bm=0.03:rh=-0.02,"
        "vignette=angle=PI/4.2")


def _segments(total, n_clips):
    """Разбить ролик на куски по 3.5–5 с, клипы чередуются."""
    segs, t, i = [], 0.0, 0
    order = list(range(n_clips))
    random.shuffle(order)
    while t < total - 0.01:
        length = min(random.uniform(3.5, 5.0), total - t)
        if total - (t + length) < 1.5:  # не оставлять крошечный хвост
            length = total - t
        segs.append((order[i % n_clips], length))
        t += length
        i += 1
    return segs


def _render_segment(src, src_dur, length, out, zoom_in):
    start = 0.0 if src_dur <= length + 0.2 else random.uniform(0, src_dur - length - 0.1)
    frames = int(round(length * FPS))
    z = 0.10  # итоговое приближение 10% за кусок — «лёгкий зум»
    if zoom_in:
        zexpr = f"1+{z}*on/{frames}"
    else:
        zexpr = f"1+{z}-{z}*on/{frames}"
    vf = (
        f"fps={FPS},"
        f"scale={int(W * 1.5)}:{int(H * 1.5)}:force_original_aspect_ratio=increase,"
        f"crop={int(W * 1.5)}:{int(H * 1.5)},"
        f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},"
        f"{LOOK},setsar=1,format=yuv420p"
    )
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    if src_dur <= length + 0.2:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", f"{start:.2f}", "-i", src, "-t", f"{length:.3f}", "-an", "-vf", vf,
            "-frames:v", str(frames),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-r", str(FPS), out]
    run(cmd)


def build(clips, voice_path, music_path, ass_path, out_path, total, voice_delay, workdir,
          ghost_path=None):
    durs = []
    for c in clips:
        try:
            durs.append(media_duration(c))
        except Exception:  # noqa: BLE001
            durs.append(0)
    clips = [c for c, d in zip(clips, durs) if d > 1]
    durs = [d for d in durs if d > 1]
    if not clips:
        raise RuntimeError("Нет пригодных клипов")

    seg_files = []
    for n, (ci, length) in enumerate(_segments(total, len(clips))):
        out = os.path.join(workdir, f"seg_{n:02d}.mp4")
        _render_segment(clips[ci], durs[ci], length, out, zoom_in=(n % 2 == 0))
        seg_files.append(out)
    log(f"Video: {len(seg_files)} segments from {len(clips)} clips")

    list_path = os.path.join(workdir, "segments.txt")
    with open(list_path, "w") as fh:
        for s in seg_files:
            fh.write(f"file '{os.path.basename(s)}'\n")
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", "segments.txt", "-c", "copy", "base.mp4"], cwd=workdir)

    ms = int(voice_delay * 1000)
    if ghost_path:
        ghost_in = ["-i", os.path.abspath(ghost_path)]
        vchain = (f"[3:v]format=rgba[gh];[0:v][gh]overlay=x=(W-w)/2:y={GHOST_TOP}:"
                  f"eof_action=pass:format=auto[bg0];[bg0]")
    else:
        ghost_in, vchain = [], "[0:v]"
    graph = (
        f"{vchain}ass={os.path.basename(ass_path)},"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={total - 0.6:.2f}:d=0.6[v];"
        f"[1:a]aformat=channel_layouts=stereo,adelay={ms}|{ms},"
        f"acompressor=threshold=-18dB:ratio=3:attack=5:release=120,volume=1.6[voice];"
        f"[2:a]volume=0.2[bg];"
        f"[voice][bg]amix=inputs=2:duration=longest:normalize=0,"
        f"afade=t=out:st={total - 0.8:.2f}:d=0.8,alimiter=limit=0.95[a]"
    )
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", "base.mp4", "-i", os.path.abspath(voice_path), "-i", os.path.abspath(music_path),
         *ghost_in, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.2f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
         "-movflags", "+faststart", os.path.abspath(out_path)], cwd=workdir)
    log(f"Video: ready {out_path} ({media_duration(out_path):.1f}s)")
    return out_path
