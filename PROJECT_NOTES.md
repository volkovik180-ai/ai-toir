# ai-toir — полный отчёт по проекту

> Создан: 2026-06-02. Этот документ — конспект всех фаз разработки, ошибок,
> решений, команд и архитектурных решений. Используется для повторного
> применения подхода на новых проектах.

## 1. Задача

Семантический поиск похожих дефектов из базы АЭС (~15 500 записей)
по текстовому описанию на русском. Внутренний инструмент ТОиР.

**Вход:** "течь сальникового уплотнения насоса"
**Выход:** топ-K исторически похожих случаев с метаданными (АЭС, оборудование, дата).

**Стек (итоговый):**
- Python 3.13 + FlagEmbedding (BAAI/bge-m3, 1024-dim) — embedding
- numpy — нормализация
- `http.server` (stdlib, ThreadingHTTPServer) — сервер
- Vanilla JS + HTML/CSS (тёмная тема) — UI
- HuggingFace snapshot_download — докачка модели

**Данные:**
- Источник: `Описания_дефектов.csv` (CP1251, `;`, 15 455 строк, 19 с пустым описанием)
- Кэш: `defects_cache.json` (335 МБ, 15 436 записей × 1024-dim, L2-нормализованные)

## 2. Ключевые архитектурные решения

| Решение | Почему |
|---|---|
| **Эмбеддинги предподсчитаны офлайн**, запрос векторизуется на лету | CSV → 33 мин на CPU, но поиск потом за миллисекунды в браузере |
| **Косинусное сходство в браузере** (не в Python) | 15 436 dot-product за ~100 мс в JS — проще, чем тащить numpy на клиент |
| **1024-dim L2-нормированные векторы** → косинус = dot product | Избавляемся от `||a||·||b||` в делении |
| **Сервер с `0.0.0.0:8000`** + правило Firewall | LAN-доступ для коллег |
| **Один source of truth — `config.json`**, фронт получает дефолты через `GET /config` | Изменение порога/порта/topk — без правки кода |
| **Модули плоско в корне** (`config.py`, `embedder.py`, `cache.py`, `handlers.py`, `serve.py`) | Не ломает `python serve.py`, легко grep'ать |
| **GitHub: без `defects_cache.json` (335 МБ) и `Описания_дефектов.csv`** (конфиденциально) | Лёгкий клон, безопасность |
| **`toggle_lan.py`** — управление Firewall + serve.py с автоUAC | Одна команда, не нужно лазить в Windows |

## 3. Финальная структура репо (10 файлов)

```
ai-toir/
├── config.json          # единственный источник правды (server, model, ui)
├── config.py            # dataclass + валидация + @lru_cache
├── embedder.py          # FlagModel wrapper, ленивая загрузка, get_embedder()
├── cache.py             # DefectsCache (заготовка для будущих /api/*)
├── handlers.py          # EmbedHandler: GET /config, /<file>, POST /embed
├── serve.py             # точка входа, 39 строк
├── build_cache.py       # офлайн: CSV → defects_cache.json (≈33 мин CPU)
├── download_bge_m3.py   # докачка модели в HF-кэш (≈2.2 ГБ)
├── toggle_lan.py        # firewall + serve.py start/stop/restart
├── index.html           # UI с fetch /config для дефолтов
├── LICENSE              # MIT
├── README.md            # на русском, со скриншотом
└── .gitignore           # defects_cache.json, csv, *.log, settings.json (Claude Code)
```

**Не в репо:** `defects_cache.json` (335 МБ), `Описания_дефектов.csv` (конфид.)

## 4. config.json (шаблон)

```json
{
  "server":  { "host": "0.0.0.0", "port": 8000 },
  "model":   { "name": "BAAI/bge-m3", "query_instruction": "",
               "use_fp16": false, "max_length": 512, "batch_size": 1 },
  "ui":      { "default_threshold": 0.7, "default_topk": 20, "truncate_at": 16 }
}
```

## 5. Команды жизненного цикла

### Первичная настройка
```bash
# 0. Зависимости
pip install FlagEmbedding
# FlagEmbedding тянет torch, transformers, huggingface_hub

# 1. Докачка модели (≈2.2 ГБ, ≈30-60 мин в зависимости от канала)
python download_bge_m3.py
# Модель: ~/.cache/huggingface/models--BAAI--bge-m3/
# pytorch_model.bin, config.json, tokenizer.*, vocab.txt и т.д.

# 2. Сборка кэша (≈33 мин на CPU, batch=16)
python build_cache.py
# Читает Описания_дефектов.csv (CP1251, ;), кодирует поле "Описание дефекта"
# Сохраняет defects_cache.json (~335 МБ)

# 3. Запуск сервера
python serve.py
# → http://localhost:8000/index.html
```

### Управление (повседневное)
```bash
# Только firewall (без UAC: status; с UAC: on/off/toggle)
python toggle_lan.py status    # общее
python toggle_lan.py on        # открыть порт
python toggle_lan.py off       # закрыть порт
python toggle_lan.py toggle    # переключить

# Только serve.py
python toggle_lan.py serve-on      # запустить
python toggle_lan.py serve-off     # остановить
python toggle_lan.py serve-status  # без UAC
python toggle_lan.py restart       # kill + start

# Все write-команды требуют админа — скрипт сам запрашивает UAC
```

### Git
```bash
cd "C:/Users/VVolkov/claude/ai-toir"
git add <files>
git -c user.name=VVolkov -c user.email=vvolkov@users.noreply.github.com commit -m "..."
git push
# remote: https://github.com/volkovik180-ai/ai-toir.git
```

### gh CLI
```bash
export PATH="/c/Program Files/GitHub CLI:$PATH"
gh auth status
gh repo view ai-toir --json name,visibility,url
```

## 6. Ошибки и их решения

### Ошибка 1: `FlagEmbedding` + `show_progress_bar=True` падает
```
TypeError: PreTrainedTokenizerBase.pad() got an unexpected keyword argument 'show_progress_bar'
```
**Причина:** FlagEmbedding в `inference/embedder/encoder_only/base.py:235` прокидывает `**kwargs` напрямую в `self.tokenizer.pad(...)`. Современные `transformers`/`tokenizers` метод `pad()` больше не принимают `show_progress_bar`.

**Решение:** Не передавать `show_progress_bar=True` в `model.encode(...)`. Если нужен прогресс — делить на chunks и `print(f"... {i}/{len(texts)}")` руками.

**Применимо к:** любой проект с FlagEmbedding + новый transformers.

### Ошибка 2: HF-кэш в v2-формате
HF v2 создаёт пустой `hub/models--BAAI--bge-m3/` — это не ошибка, нормальное поведение, не путаться.

**Докачка через `download_bge_m3.py`:** `snapshot_download(repo_id=..., cache_dir=Path.home() / ".cache/huggingface", allow_patterns=FILES, max_workers=2, resume_download=True)`.

### Ошибка 3: CSV в кодировке CP1251
```python
# Правильно:
with open(path, "r", encoding="cp1251", newline="") as f:
    reader = csv.DictReader(f, delimiter=";")
```
**Не utf-8** — будет `UnicodeDecodeError`.

### Ошибка 4: PowerShell 5.1 — нет `&&` и `??`
- `A && B` — ошибка парсера, использовать `A; if ($?) { B }`
- `cmd1 || cmd2` — нет, использовать `if ($?) { ... }`
- `2>&1` для native — избегать (ErrorRecord)

**Запуск фонового процесса:**
```powershell
$env:PYTHONIOENCODING='utf-8'
Start-Process python -ArgumentList "serve.py" `
  -RedirectStandardOutput "serve.log" `
  -RedirectStandardError "serve.err" `
  -WindowStyle Hidden -PassThru | Select-Object Id, StartTime
```

### Ошибка 5: `Invoke-WebRequest` зависает
PowerShell 5.1 `Invoke-WebRequest` иногда зависает на localhost. **Альтернатива:** `HttpWebRequest` с явным потоком:
```powershell
$req = [System.Net.HttpWebRequest]::Create($url)
$req.Method = "POST"
$req.ContentType = "application/json; charset=utf-8"
$bodyBytes = [Text.Encoding]::UTF8.GetBytes($body)
$req.ContentLength = $bodyBytes.Length
$reqStream = $req.GetRequestStream()
$reqStream.Write($bodyBytes, 0, $bodyBytes.Length)
$reqStream.Close()
$resp = $req.GetResponse()
$reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
$reader.ReadToEnd()
```

### Ошибка 6: `New-NetFirewallRule` — PermissionDenied
Не из обычной PS. Нужен **PowerShell от админа** (Win+X → "Windows PowerShell (администратор)"). Или через `Start-Process -Verb RunAs`:
```powershell
Start-Process powershell -Verb RunAs -ArgumentList "..."
```
**В скрипте Python:** `ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 0)` — перезапуск себя с UAC.

### Ошибка 7: native `<select>` вылезает за границы колонки
Chrome рендерит `<select>` шире родителя, чтобы вместить выбранное значение. Ни `width: 100%`, ни `max-width`, ни `text-overflow: ellipsis` не помогают для `textContent` option'а.

**Решение:** обрезать **в JS** при заполнении:
```js
const TRUNCATE_AT = 16;  // из config.json → APP_CONFIG.ui.truncate_at
function truncate(s, n = TRUNCATE_AT) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}
o.textContent = truncate(v);  // короткое — в select
o.value = v;                   // полное — в value
o.title = v;                   // и в tooltip
```
Лимит подбирается эмпирически: 16 символов вписался в колонку 200px.

### Ошибка 8: фильтры «АЭС/Оборудование» — независимые, неудобно
Изначально оба фильтра всегда показывали все уникальные значения из кэша. После поиска с порогом 0.7 в таблице может быть 5 АЭС, а в фильтре — все 340.

**Решение: зависимые фильтры** по `scored`:
```js
function updateFiltersFromResults(scored) {
  // АЭС — уникальные среди записей, прошедших фильтр по Оборудованию
  // Оборудование — уникальные среди записей, прошедших фильтр по АЭС
  // fillFilterOptions сам восстановит выбор, если значение ещё в списке.
  // Если нет — сбросит на "__ALL__". Ловим это и перезапускаем поиск.
  if (plantReset || equipReset) return find();
}
```

### Ошибка 9: `settings.json` в проекте — это statusline Claude Code
В `C:\Users\VVolkov\claude\ai-toir\` лежит **не наш** `settings.json` (это конфиг statusline для Claude Code CLI). Не путать с `config.json`! Добавить в `.gitignore`:
```gitignore
# Claude Code statusline (не наш конфиг)
settings.json
```

### Ошибка 10: `find_serve_pids` ищет `python.exe`, а процесс называется `python3.13.exe`
WMI фильтр по `Name='python.exe'` не находил процессы `python3.13.exe` (WindowsApps alias). Фильтр должен быть:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='python3.13.exe'"
```

### Ошибка 11: `gh` не в PATH после установки
`winget install GitHub.cli` ставит в `C:\Program Files\GitHub CLI\gh.exe`, но не добавляет в PATH. Использовать полный путь или `export PATH="/c/Program Files/GitHub CLI:$PATH"`.

### Ошибка 12: `gh auth login --web` в фоне — фоновый процесс может не отдать вывод
`ShellExecuteW("runas", ...)` запускает ребёнка в **новом окне**. Если родитель — фоновый, мы не видим child output. Решение: пользователь смотрит в браузер (one-time code), подтверждает, родитель проверяет `gh auth status`.

### Ошибка 13: `git push` failed — remote ahead
Если параллельно (или через web UI) на GitHub появились новые коммиты, локальная ветка отстаёт:
```
! [rejected] main -> main (fetch first)
hint: Updates were rejected because the remote contains work that you do not
```
**Решение:** `git pull --rebase`, затем `git push`. Сейчас на репо был `3b4da34 Update README.md` (сделан владельцем через web) и `ceae8cb Delete docs directory` — пришлось rebase.

### Ошибка 14: `time` в C#-стиле PowerShell — body с кириллицей через `-d` curl
`curl -d "{\"text\":\"тест\"}"` отправляет в **cp1251** на Windows → сервер ждёт utf-8 → 400. **Альтернатива:** `Invoke-WebRequest` с `[Text.Encoding]::UTF8.GetBytes($body)` или указать `--data-raw` с явной кодировкой.

## 7. Сценарий развёртывания «с нуля» (повторяемый)

1. **Подготовка данных**: `Описания_дефектов.csv` → `build_cache.py` → `defects_cache.json`
2. **Докачка модели**: `download_bge_m3.py` → `~/.cache/huggingface/...`
3. **Запуск сервера**: `python serve.py` → `http://localhost:8000/index.html`
4. **LAN-доступ** (если нужно коллегам):
   - `serve.py` уже слушает `0.0.0.0`
   - **Один раз**: добавить правило Firewall (от админа)
     ```powershell
     New-NetFirewallRule -DisplayName "ai-toir serve.py" -Direction Inbound `
       -Action Allow -Protocol TCP -LocalPort 8000 -Profile Domain,Private -Enabled True
     ```
   - Дальше: `python toggle_lan.py on` / `off` / `toggle`
5. **GitHub**: см. секцию "Команды Git"

## 8. Ключевые числа и тайминги

| Операция | Время / размер |
|---|---|
| Докачка bge-m3 (≈2.2 ГБ) | 30-60 мин (зависит от канала) |
| `build_cache.py` на CPU (15 436 описаний, batch 16) | ≈33 мин |
| `defects_cache.json` | 335 МБ |
| `defects_cache.json` загрузка в браузер | ≈2-3 сек (335 МБ) |
| Косинусный поиск в браузере (15 436 записей) | ≈100 мс |
| `/embed` после прогрева модели | < 100 мс |
| Первая загрузка модели в RAM | ≈10-20 сек |

## 9. Шаблон config.json для нового проекта

```json
{
  "server":  { "host": "0.0.0.0", "port": 8000 },
  "model":   { "name": "BAAI/bge-m3", "query_instruction": "",
               "use_fp16": false, "max_length": 512, "batch_size": 1 },
  "ui":      { "default_threshold": 0.7, "default_topk": 20, "truncate_at": 16 }
}
```

## 10. Шаблон .gitignore

```gitignore
# Кэш эмбеддингов (большой)
defects_cache.json

# Исходные данные (конфиденциальные)
Описания_дефектов.csv

# Локальные логи
*.log
*.err

# Личный конфиг Claude
CLAUDE.md
.claude/

# Скриншоты рабочего процесса
scrins/

# Python
__pycache__/
*.pyc
.venv/
.env

# Claude Code statusline (не наш конфиг)
settings.json
```

## 11. Команды диагностики

```bash
# Сервер
curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://localhost:8000/index.html
curl -s http://localhost:8000/config
curl -X POST http://localhost:8000/embed -H "Content-Type: application/json; charset=utf-8" -d '{"text":"тест"}'

# Процессы
powershell -NoProfile -Command "Get-Process python"
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python3.13.exe'\" | Where-Object { \$_.CommandLine -like '*serve.py*' }"

# Firewall
powershell -NoProfile -Command "Get-NetFirewallRule -DisplayName 'ai-toir*'"

# GitHub
gh auth status
gh repo view ai-toir --json name,visibility,url,diskUsage
gh api repos/<user>/ai-toir/contents --jq '.[].name'
```

## 12. Шпаргалка: PowerShell 5.1 → Bash

| Bash | PowerShell 5.1 |
|---|---|
| `cmd1 && cmd2` | `cmd1; if ($?) { cmd2 }` |
| `cmd1 \|\| cmd2` | `cmd1; if (-not $?) { cmd2 }` |
| `VAR=value cmd` | `$env:VAR = 'value'; cmd` |
| `head -n` | `Get-Content file -TotalCount N` |
| `tail -n` | `Get-Content file -Tail N` |
| `which` | `(Get-Command name).Source` |
| `mkdir -p` | `New-Item -ItemType Directory -Force path` |
| `rm -rf` | `Remove-Item -Recurse -Force path` |
| `cat` | `Get-Content` |
| `2>/dev/null` | `2>$null` |
| `export PATH=...` | `$env:PATH = "...;$env:PATH"` |
| `find` | `Get-ChildItem -Recurse` (или Glob tool) |
| `grep` | `Select-String` (или Grep tool) |

## 13. Извлечённые паттерны (для повторного использования)

### 13.1. Паттерн: «один source of truth + frontend defaults через эндпоинт»
- Python читает `config.json` в `config.py` (dataclass + `@lru_cache`)
- Сервер отдаёт `GET /config` с **только тем, что нужно UI** (без серверных секретов)
- Фронт на старте fetch'ит `/config`, fallback на локальные дефолты в `APP_CONFIG`
- Изменение настроек — без правки кода и без редеплоя

### 13.2. Паттерн: «модули плоско + точка входа»
- `config.py`, `embedder.py`, `cache.py`, `handlers.py` — каждый одна ответственность
- `serve.py` — точка входа, ~40 строк
- Запуск: `python serve.py` (без `python -m package.module`)
- Singleton через `get_*()` функции с `global _x`

### 13.3. Паттерн: «скрипт управления с автоUAC»
- `ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0)`
- В `main()` проверка `is_admin()` через `ctypes.windll.shell32.IsUserAnAdmin()`
- Read-only команды (status) — без UAC, write-команды — с перезапуском
- WMI для поиска процессов: `Get-CimInstance Win32_Process` (показывает `CommandLine`)

### 13.4. Паттерн: «сборка модели → кэш → быстрый поиск»
- **Офлайн**: тяжёлая часть (33 мин) — один раз
- **Кэш**: 335 МБ JSON (или бинарный для скорости)
- **Онлайн**: лёгкая часть (≈100 мс) — каждый запрос
- Frontend делает финальное ранжирование сам (косинус в JS) — экономит CPU сервера

### 13.5. Паттерн: «зависимые фильтры по результатам поиска»
- Фильтры не от полного кэша, а от `scored` (прошедших порог)
- Перекрёстное влияние: АЭС ← фильтр Оборудования → список АЭС
- Если выбранное значение пропало из обновлённого списка — сброс на «Все» + автоперезапуск поиска
- Защита от зацикливания: `scored.length === 0` → оба фильтра в «Все», таблица пустая

### 13.6. Паттерн: «что НЕ коммитить в публичный репо»
- Большие файлы (≥100 МБ) — `defects_cache.json`, модели
- Конфиденциальные данные — `*.csv` с персональными данными
- Служебные артефакты — `*.log`, `*.err`, `scrins/`
- Личные конфиги — `CLAUDE.md`, `.claude/`, `settings.json` (statusline)
- Секреты — `.env`, ключи, токены

## 14. Контрольный список для нового проекта по этому шаблону

- [ ] Создать `config.json` со всеми настройками
- [ ] Создать `config.py` (dataclass + валидация + `@lru_cache`)
- [ ] Создать `<model>.py` (singleton-обёртка над ML-моделью, ленивая загрузка)
- [ ] Создать `<cache>.py` (если есть кэш — ленивое чтение)
- [ ] Создать `handlers.py` (`GET /<file>`, `GET /config`, `POST /<action>`)
- [ ] Создать `serve.py` (точка входа, ~40 строк)
- [ ] `index.html` — fetch `/config` для дефолтов + `APP_CONFIG` fallback
- [ ] `toggle.py` — управление сервисом (firewall, start/stop, status, автоUAC)
- [ ] `build_<data>.py` — офлайн-сборка кэша (≈30 мин)
- [ ] `download_<model>.py` — докачка модели через `snapshot_download`
- [ ] `LICENSE` (MIT)
- [ ] `README.md` (на русском, со скриншотом, инструкции)
- [ ] `.gitignore` (кэш, csv, логи, `settings.json`)
- [ ] Git: `init`, `add`, `commit`, GitHub `repo create --public --push`

## 15. Известные ограничения

- **Модель в RAM**: bge-m3 ≈ 4 ГБ fp32. На 8 ГБ машине — запас есть, но не развернёшь 2 инстанса.
- **`use_fp16=False`**: на CPU fp16 медленнее fp32. На GPU — наоборот.
- **CSV читается целиком в RAM**: при миллионах записей нужно стримить.
- **Кэш перечитывается браузером каждый раз**: при `cache: "no-store"` — да, можно через IndexedDB.
- **Поиск в JS линейный**: 15 436 × 1024-dim = ~63 млн операций — пока укладываемся в 100 мс, но при ×10 нужен FAISS/HNSW.
- **Нет авторизации**: всё открыто. В LAN это нормально, для публичного интернета — нет.
- **Кириллица в URL**: не используется (эндпоинты — `/embed`, `/config`), но статика отдаётся с правильным `charset=utf-8`.

## 16. Ссылки

- Репо: https://github.com/volkovik180-ai/ai-toir
- Модель: https://huggingface.co/BAAI/bge-m3
- FlagEmbedding: https://github.com/FlagOpen/FlagEmbedding
