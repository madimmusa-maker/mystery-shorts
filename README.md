# 🕯 Mystery Shorts — робот для YouTube Shorts про тайны и загадки

Каждый день в **15:00 по Казахстану** робот сам:

1. придумывает тему (реальный загадочный случай) через **Gemini** — темы не повторяются, список хранится в `history.json`;
2. пишет сценарий на 35–50 секунд (крючок → интрига → вопрос зрителю), заголовок, описание, хэштеги;
3. скачивает 3–5 вертикальных клипов с **Pexels**, добавляет лёгкий зум и затемнение;
4. озвучивает текст голосом **Дмитрия** (edge-tts, чуть медленнее обычного);
5. накладывает крупные белые субтитры по словам и тихую мрачную музыку (её генерирует сам ffmpeg — никаких авторских прав);
6. собирает видео 1080×1920 короче 59 секунд;
7. загружает его на YouTube с `#shorts`. Если загрузить не получилось — видео можно скачать со страницы запуска (раздел **Artifacts**).

Всё бесплатно: GitHub Actions, Gemini (бесплатный ключ), Pexels, edge-tts, YouTube API.

---

## 📱 Настройка с телефона — по шагам

> Совет: страницы GitHub и Google Cloud удобнее открывать в браузере в режиме **«Версия для ПК»**
> (в Chrome: ⋮ → «Версия для ПК»). В приложении GitHub нельзя добавлять секреты.

Всего нужно получить **5 секретов**:

| Секрет | Откуда |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `PEXELS_API_KEY` | Pexels |
| `YT_CLIENT_ID` | Google Cloud |
| `YT_CLIENT_SECRET` | Google Cloud |
| `YT_REFRESH_TOKEN` | блокнот `get_token.ipynb` в Google Colab |


### Шаг 1. Ключ Gemini → `GEMINI_API_KEY`

1. Откройте <https://aistudio.google.com/apikey> и войдите в Google-аккаунт.
2. Нажмите **Create API key** (Создать ключ). Если спросит проект — выберите любой или создайте новый.
3. Скопируйте ключ (длинная строка, начинается с `AIza…`).

### Шаг 2. Ключ Pexels → `PEXELS_API_KEY`

1. Откройте <https://www.pexels.com/api/> → **Get Started**, зарегистрируйтесь (бесплатно).
2. Заполните короткую форму (можно написать: *«Personal project: automatic YouTube Shorts»*).
3. Скопируйте показанный **API Key**.

### Шаг 3. Доступ к YouTube → `YT_CLIENT_ID` и `YT_CLIENT_SECRET`

1. Откройте <https://console.cloud.google.com/> и войдите в аккаунт **того же Google, где ваш YouTube-канал**.
2. Вверху нажмите выбор проекта → **New project / Новый проект** → имя, например `mystery-shorts` → **Create**. Убедитесь, что этот проект выбран.
3. Откройте <https://console.cloud.google.com/apis/library/youtube.googleapis.com> → **Enable / Включить** (это YouTube Data API v3).
4. Откройте <https://console.cloud.google.com/auth/overview> (Google Auth Platform) → **Get started**:
   - App name: `mystery-shorts`, User support email: ваша почта → Next;
   - Audience: **External** → Next;
   - Contact: ваша почта → Next → согласиться → **Create**.
5. Слева **Audience** → нажмите **Publish app** (Опубликовать) → Confirm.
   ⚠️ Это важно: иначе токен перестанет работать через 7 дней. Проверка Google для этого не нужна.
6. Слева **Clients** → **Create client**:
   - Application type: **Desktop app** (Компьютерное приложение), имя любое → **Create**.
7. Скопируйте **Client ID** (заканчивается на `.apps.googleusercontent.com`) и **Client secret** (начинается с `GOCSPX-`). Сохраните их в заметках.

### Шаг 4. Токен YouTube → `YT_REFRESH_TOKEN` (через Google Colab)

1. Откройте блокнот в Colab по ссылке:
   <https://colab.research.google.com/github/madimmusa-maker/mystery-shorts/blob/main/get_token.ipynb>
   *(Если репозиторий приватный и ссылка не открывается: скачайте файл `get_token.ipynb` из репозитория, откройте <https://colab.research.google.com> → «Загрузить» и выберите файл.)*
2. Нажмите ▶ у **Шага 1** (если спросит «Запустить всё равно?» — Да).
3. В **Шаге 2** вставьте Client ID и Client Secret в поля и нажмите ▶. Появится ссылка — откройте её.
4. Войдите в аккаунт с вашим каналом. Если увидите «Приложение не проверено» → **Дополнительно** → **Перейти на страницу mystery-shorts**. Разрешите доступ.
5. Откроется страница `localhost`, которая **не загрузится** — так и должно быть. Скопируйте **весь адрес** из адресной строки (начинается с `http://localhost:8080/?state=…&code=…`).
6. Вернитесь в Colab, вставьте адрес в поле **Шага 3** и нажмите ▶. Скопируйте показанный токен (начинается с `1//`).

### Шаг 5. Добавить секреты в GitHub

1. Откройте ваш репозиторий: <https://github.com/madimmusa-maker/mystery-shorts>
2. **Settings** (Настройки) → слева **Secrets and variables** → **Actions**.
3. Нажмите **New repository secret**, в поле **Name** введите имя, в **Secret** — значение, затем **Add secret**.
   Повторите для всех пяти:
   - `GEMINI_API_KEY`
   - `PEXELS_API_KEY`
   - `YT_CLIENT_ID`
   - `YT_CLIENT_SECRET`
   - `YT_REFRESH_TOKEN`

   Имена пишите точно так же, заглавными буквами, без пробелов.
4. Проверьте разрешения: **Settings** → **Actions** → **General** → внизу **Workflow permissions** → **Read and write permissions** → **Save**. (Нужно, чтобы робот мог сохранять `history.json`.)

### Шаг 6. Запустить вручную (проверка)

1. В репозитории откройте вкладку **Actions**. Если GitHub спросит — нажмите **I understand my workflows, go ahead and enable them**.
2. Слева выберите **Daily mystery short** → справа **Run workflow**.
   - Галочка **«Загрузить на YouTube?»**: снимите её для пробного запуска без публикации.
   - Нажмите зелёную кнопку **Run workflow**.
3. Через 5–10 минут обновите страницу. Откройте запуск:
   - ✅ зелёная галочка — видео загружено (ссылка есть в логе шага *Make and upload the short*);
   - если видео не загружалось — внизу страницы запуска в разделе **Artifacts** будет архив с видео и файлом `info.txt` (заголовок, описание, теги).

Дальше робот будет работать сам каждый день в 15:00 (GitHub иногда запускает расписание с опозданием на 5–30 минут — это нормально).

---

## ❓ Частые проблемы

- **Видео загрузилось, но оно «Ограниченный доступ / Private».** YouTube делает так со всеми видео, загруженными через API из новых непроверенных проектов Google Cloud. Решения:
  1. Бесплатно пройти проверку YouTube API: форма <https://support.google.com/youtube/contact/yt_api_form> (выберите «аудит»/«API Services Audit and Quota Extension»). После одобрения видео будут публичными сразу.
  2. Пока проверки нет — открывайте приложение **YouTube Studio** и меняйте доступ на «Открытый доступ» вручную (10 секунд).
- **Ошибка `invalid_grant` при загрузке.** Токен устарел или отозван. Убедитесь, что в Шаге 3 приложение опубликовано (**Publish app**), и получите токен заново (Шаг 4), затем обновите секрет `YT_REFRESH_TOKEN`.
- **`quotaExceeded` / `uploadLimitExceeded`.** Превышен дневной лимит YouTube — на следующий день пройдёт само.
- **Ошибка Gemini про модель.** Робот сам перебирает доступные бесплатные модели. Если хотите указать модель вручную: **Settings → Secrets and variables → Actions → вкладка Variables → New repository variable**, имя `GEMINI_MODEL`, значение например `gemini-2.5-flash`.
- **Хочу загружать без публикации** (сначала смотреть сам): добавьте переменную (Variables) `YT_PRIVACY` со значением `private` или `unlisted`.
- **Расписание перестало работать.** GitHub отключает расписание в репозиториях без активности 60 дней. Робот каждый день сохраняет `history.json`, так что обычно этого не происходит; если всё же отключилось — **Actions → Daily mystery short → Enable workflow**.
- **Красный крестик в Actions.** Откройте запуск → шаг *Make and upload the short* → в конце лога будет понятное сообщение об ошибке (например, «Нет секрета PEXELS_API_KEY»).

---

## 🗂 Что где лежит

| Файл | Что делает |
|---|---|
| `main.py` | главный сценарий, запускает все шаги по очереди |
| `shorts/gemini.py` | тема и сценарий (Gemini) |
| `shorts/pexels.py` | поиск и скачивание вертикальных клипов |
| `shorts/tts.py` | озвучка edge-tts с таймингом слов |
| `shorts/subtitles.py` | субтитры по словам |
| `shorts/music.py` | генерация мрачной фоновой музыки |
| `shorts/video.py` | монтаж в ffmpeg |
| `shorts/youtube.py` | загрузка на YouTube |
| `history.json` | список уже использованных тем |
| `.github/workflows/daily-short.yml` | расписание GitHub Actions |
| `get_token.ipynb` | блокнот для получения `YT_REFRESH_TOKEN` |
