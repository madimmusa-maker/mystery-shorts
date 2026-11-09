"""Список голосов и выбор голоса из config.py / переменной окружения VOICE.

Запуск `python -m shorts.voices --needs-silero` завершается с кодом 0,
если выбранному голосу нужен Silero (тогда workflow ставит torch).
"""
import os
import sys

# имя -> (движок, голос движка, описание)
VOICES = {
    "dmitry": ("edge", "ru-RU-DmitryNeural", "Дмитрий, мужской (edge-tts)"),
    "svetlana": ("edge", "ru-RU-SvetlanaNeural", "Светлана, женский (edge-tts)"),
    "aidar": ("silero", "aidar", "Айдар, мужской (Silero)"),
    "eugene": ("silero", "eugene", "Евгений, мужской (Silero)"),
    "baya": ("silero", "baya", "Бая, женский (Silero)"),
    "kseniya": ("silero", "kseniya", "Ксения, женский (Silero)"),
    "xenia": ("silero", "xenia", "Ксения-2, женский (Silero)"),
}
DEFAULT = "dmitry"
# мужские голоса ниже, поэтому сдвиг тона в Гц переводим в полутона по-разному
MALE = {"dmitry", "aidar", "eugene"}


def selected():
    """Имя выбранного голоса: переменная VOICE важнее config.py."""
    name = os.environ.get("VOICE", "").strip().lower()
    if not name:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import config
            name = str(getattr(config, "VOICE", "")).strip().lower()
        except ImportError:
            name = ""
    for key, (_, engine_voice, _) in VOICES.items():
        if name in (key, engine_voice.lower()):
            return key
    if name:
        print(f"[voices] Неизвестный голос {name!r}, использую {DEFAULT!r}. "
              f"Доступны: {', '.join(VOICES)}", file=sys.stderr)
    return DEFAULT


if __name__ == "__main__":
    if "--needs-silero" in sys.argv:
        sys.exit(0 if VOICES[selected()][0] == "silero" else 1)
    print(selected())
