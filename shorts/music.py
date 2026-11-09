"""Мрачная фоновая музыка, синтезированная ffmpeg (своя, без авторских прав)."""
import random

from .util import run

# низкие ноты (Гц) для «гула»: A1, B1, C2, D2, E2
ROOTS = [55.0, 61.74, 65.41, 73.42, 82.41]


def make_music(duration, out_path):
    f = random.choice(ROOTS)
    minor_third = f * 1.1892
    fifth = f * 1.4983
    lfo = random.uniform(0.05, 0.11)
    d = duration + 1

    def voice(detune):
        return (
            f"0.30*sin(2*PI*{f * detune:.3f}*t)*(0.65+0.35*sin(2*PI*{lfo:.3f}*t))"
            f"+0.16*sin(2*PI*{minor_third * detune:.3f}*t)*(0.5+0.5*sin(2*PI*{lfo * 0.7:.3f}*t+1.3))"
            f"+0.12*sin(2*PI*{fifth * detune:.3f}*t)*(0.5+0.5*sin(2*PI*{lfo * 1.3:.3f}*t+2.1))"
            f"+0.07*sin(2*PI*{f * 2.003 * detune:.3f}*t)*(0.5+0.5*sin(2*PI*0.031*t))"
            f"+0.05*sin(2*PI*{f * 4.01 * detune:.3f}*t)*pow(0.5+0.5*sin(2*PI*0.043*t+0.7),3)"
        )

    drone = f"aevalsrc='{voice(1.0)}|{voice(1.004)}':s=44100:d={d:.2f}"
    noise = f"anoisesrc=color=brown:amplitude=0.25:d={d:.2f}:r=44100"
    fade_out = max(duration - 2.5, 0)
    graph = (
        f"{drone}[dr];"
        f"{noise},lowpass=f=350,highpass=f=40,aformat=channel_layouts=stereo,"
        f"volume='0.5+0.5*sin(2*PI*0.06*t)':eval=frame[nz];"
        f"[dr][nz]amix=inputs=2:normalize=0,"
        f"aecho=0.8:0.6:700|1300:0.35|0.22,lowpass=f=2200,"
        f"afade=t=in:d=2.5,afade=t=out:st={fade_out:.2f}:d=2.5,"
        f"alimiter=limit=0.9[out]"
    )
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-filter_complex", graph, "-map", "[out]",
         "-t", f"{duration:.2f}", "-ar", "44100", "-ac", "2", str(out_path)])
    return out_path
