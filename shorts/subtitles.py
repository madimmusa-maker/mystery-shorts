"""Субтитры по словам (ASS): крупные, белые, с чёрной обводкой, по центру."""
import subprocess

MAX_WORDS = 3
MAX_CHARS = 16


def pick_font():
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        out = ""
    for name in ("Montserrat", "Roboto", "DejaVu Sans"):
        if name in out:
            return name
    return "DejaVu Sans"


def _ts(t):
    t = max(t, 0)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _esc(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")")


def _chunks(words):
    chunks, cur = [], []
    for w in words:
        if cur:
            gap = w[0] - cur[-1][1]
            length = sum(len(x[2]) + 1 for x in cur) + len(w[2])
            if len(cur) >= MAX_WORDS or length > MAX_CHARS or gap > 0.35:
                chunks.append(cur)
                cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    return chunks


def build_ass(words, path, offset=0.0, total=None):
    font = pick_font()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Main,{font},96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,1,0,1,7,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chunks = _chunks(words)
    for ci, chunk in enumerate(chunks):
        chunk_end = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else chunk[-1][1] + 0.6
        chunk_end = min(chunk_end, chunk[-1][1] + 0.6)
        for wi, w in enumerate(chunk):
            start = w[0]
            end = chunk[wi + 1][0] if wi + 1 < len(chunk) else chunk_end
            parts = []
            for wj, other in enumerate(chunk):
                txt = _esc(other[2].upper())
                if wj == wi:
                    parts.append("{\\1a&H00&}" + txt)
                else:
                    parts.append("{\\1a&H70&}" + txt)
            pop = "{\\fscx108\\fscy108\\t(0,90,\\fscx100\\fscy100)}" if wi == 0 else ""
            s, e = start + offset, end + offset
            if total:
                e = min(e, total - 0.05)
            if e - s < 0.04:
                continue
            lines.append(f"Dialogue: 0,{_ts(s)},{_ts(e)},Main,,0,0,0,,{pop}{' '.join(parts)}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header + "\n".join(lines) + "\n")
    return font
