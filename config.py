"""Настройки робота. Меняйте значения справа от знака «=» и сохраняйте файл (Commit changes)."""

# Голос рассказчика. Послушать все голоса: Actions → «Voice samples» → Run workflow.
#   "dmitry"   — Дмитрий, мужской (edge-tts, Microsoft)
#   "svetlana" — Светлана, женский (edge-tts, Microsoft)
#   "aidar"    — Айдар, мужской (Silero)
#   "eugene"   — Евгений, мужской (Silero)
#   "baya"     — Бая, женский (Silero)
#   "kseniya"  — Ксения, женский (Silero)
#   "xenia"    — Ксения (другая), женский (Silero)
# Можно не трогать этот файл, а создать в GitHub переменную VOICE
# (Settings → Secrets and variables → Actions → Variables) — она важнее этой строки.
VOICE = "dmitry"
