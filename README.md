# HSR RU Voiceover

Русская озвучка диалогов Honkai: Star Rail. Генерация — CosyVoice 3, тексты — русский TextMap из дампа геймдаты ([Dimbreath/turnbasedgamedata](https://gitlab.com/Dimbreath/turnbasedgamedata)).

> Катсцены (предрендеренные .usm) не озвучиваются. Только диалоги.

## Установка

### 1. Клонирование

```bash
git clone --recursive https://github.com/VadimDeeptech/hsr-ru-voiceover.git
cd hsr-ru-voiceover
```

### 2. Python и зависимости

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Настройка путей

```bash
copy config.example.toml config.toml
```

При необходимости отредактируй `config.toml` (раскомментируй и заполни `game_dir` / `wwise_console`). Если оставить всё закомментированным — скрипты найдут игру и Wwise автоматически.

### 4. Wwise (Audiokinetic)

1. Скачай **Audiokinetic Launcher** с [audiokinetic.com/download](https://www.audiokinetic.com/download/)
2. Установи Launcher, войди в аккаунт (или создай бесплатный)
3. В Launcher выбери **Wwise** → версию **2025.1+** → Install
4. Убедись, что выбран компонент **Authoring** (включает WwiseConsole.exe)
5. После установки Launcher создаст переменную окружения `WWISEROOT`
6. Путь к `WwiseConsole.exe` пропиши в `config.toml` или скрипты найдут автоматически

> WwiseConsole.exe находится по пути: `%WWISEROOT%\Authoring\x64\Release\bin\WwiseConsole.exe`

### 5. Извлечение английских wav из игры

```bash
cd AnimeWwise
python app.py
cd ..
```

В окне AnimeWwise (вкладка **Config** под меню, таб **Extract audio package (.pck)**):

> ⚠️ Игра должна быть закрыта — pck читаются напрямую из папки игры.

1. **What to load:** `Folder`, включи галочку **Include subfolders ?**
2. **Asset map:** выбери из списка `Honkai: Star Rail - v<X.X>` (мап `hkrpg.map` подставляется автоматически)
3. Нажми **Load file(s)** и выбери папку `<игра>\StarRail_Data\Persistent\Audio\AudioPackage\Windows\English`
4. Дождись загрузки (оба прогресс-бара 100%, в логе `Done !`). Предупреждения `[WARNING] invalid didx signature at VoBanks9.pck@...` — норма, игнорируй
5. Меню **Extract** → **Output format** → `wav (fast)`; галочка **Retain folder structure** — включена
6. **Extract** → **Extract All** → выбери папку `hsr-dataset\`

> ⚠️ AnimeWwise перезаписывает существующие файлы без предупреждения — убедись, что `hsr-dataset\` пуст или содержит только старую выгрузку, которую можно заменить.

> Подробнее: `AnimeWwise\README.md`

### 6. Docker (CosyVoice)

#### 6.1 Скачивание модели

Модель **не скачивается автоматически** при запуске контейнера — её нужно скачать заранее на хост:

```bash
cd hsr-cosyvoice
python download_model.py
```

Скрипт скачает `FunAudioLLM/Fun-CosyVoice3-0.5B` с HuggingFace в `hsr-cosyvoice\models\Fun-CosyVoice3-0.5B`.

#### 6.2 Запуск

```bash
cd hsr-cosyvoice
docker compose up -d
cd ..
```

Подробнее: [CosyVoice](https://github.com/FunAudioLLM/CosyVoice)

### 7. Проверка

```bash
python pipeline.py doctor
```

Все пункты должны быть `[OK]`.

## Генерация озвучки

### Весь контент (рекомендуется)

```bash
python pipeline.py all --gender m
python pipeline.py install --gender m
```

> Команда `all` обрабатывает **всё**: главы + side + companion + vo + ambient + archive + событийные главы.

### Одна глава

```bash
python pipeline.py chapter 1 --gender m
python pipeline.py install --gender m
```

### Все главы

```bash
python pipeline.py chapter --gender m
python pipeline.py install --gender m
```

### Одна побочная категория

```bash
python pipeline.py extra side0 --gender m
python pipeline.py install --gender m
```

### Весь побочный контент (без глав)

```bash
python pipeline.py extra --gender m
python pipeline.py install --gender m
```

### Отдельные шаги (отладка)

```bash
python pipeline.py map                                # 1. wav -> mapping.csv
python pipeline.py scan --all-categories              # 2. фильтр по всем категориям
python pipeline.py scan --category side0              #    ...или по одной
python pipeline.py audit                              # 3-4. сверка звука оригинала с текстом
python pipeline.py generate --all-categories          # 5. TTS для всех категорий
python pipeline.py generate --category vo --limit 50  #    ...тест на 50 репликах vo
python pipeline.py build                              # 6. repack_list.csv
python pipeline.py findpck                            # 7. id_to_pck.csv
python pipeline.py wwise --gender m                   # 8. staging + wsources
python pipeline.py collect --gender m                 # 9. сбор wem
python pipeline.py repack --gender m                  # 10. сборка pck
```

> WwiseConsole запускается автоматически. Чтобы пропустить (например, Wwise GUI открыт): `--no-wwise`.
> `generate` резюмируемый: существующие wav пропускаются, так что прерванный прогон можно продолжить той же командой. Если текст реплики изменился (решение `join`/`next`, правка перевода в патче), её wav генерируется заново — тексты озвученного хранятся в `output_ru\<категория>\gen_text.csv`.

### Сверка звука с текстом (audit)

Перед генерацией полные циклы (`all`, `chapter`, `extra`) распознают английскую речь в оригинальных wav (Whisper в контейнерах на образе CosyVoice) и сравнивают её с субтитром из данных игры. Так находятся реплики, где текст не тот, разбит на несколько строк или в записи вообще нет речи.

- Результаты распознавания кэшируются в `hsr-run-voice\asr\`: первый прогон по всему датасету идёт часы, после обновления игры распознаются только новые записи.
- Отчёт пишется в `hsr-run-voice\audit_report.csv`, неразобранные расхождения идут первыми.
- Если есть неразобранные расхождения, пайплайн останавливается до генерации. Решения вписываются в `audit_decisions.csv` в корне проекта, после чего та же команда запускается снова:

| action | Что делает |
|---|---|
| `accept` | расхождение известно, озвучивать текст как есть |
| `join` + `lines` | текст продолжается: своя строка + следующие N строк субтитров |
| `next` + `lines` | своя строка — ремарка: взять только следующие N строк |
| `keep` | не озвучивать, оставить в игре оригинал |

Решение `keep` действует и на уже сгенерированные реплики: в сборку они не попадают.

У части записей (в основном фоновые приветствия NPC, `vo_ambient_*`) связь звука с субтитром в данных игры ненадёжна: звучит короткая фраза, а строка диалога другая. Источник текста каждой записи пишется в колонку `text_source` файла `mapping.csv`. Записи из ненадёжных источников (`sentence_other`, `sentence_samenum`, `multivoice`) озвучиваются, только если распознавание подтвердило текст; остальные автоматически остаются с оригинальным звуком и попадают в `hsr-run-voice\audit_auto.csv`. Чтобы всё же озвучить такую запись, впиши для неё `accept` в `audit_decisions.csv`.

> Пропустить сверку: `--no-audit` (автоматические решения берутся из прошлой сверки). Только отчёт без остановки: `python scripts\04_audit_report.py --no-gate`.
> Во время сверки видеопамять занята распознаванием — CosyVoice-генерацию параллельно не запускать.

### Утилиты

```bash
python pipeline.py utils find-missing-text            # диагностика: какие таблицы содержат текст для voiceid без текста
```

> Полезно после обновления геймдаты, когда появляются новые реплики без текста. Скрипт покажет, в каких таблицах `ExcelOutput` искать текст и какие колонки содержат хэш.

### Обновление при выходе нового патча игры

Порядок важен — сначала подмодули, потом извлечение wav, потом генерация:

```bash
# 1. Обнови игру через лаунчер

# 2. Обнови подмодули (AnimeWwise получит актуальный asset map под новый патч, hsr-gamedata — тексты нового патча)
git submodule update --remote

# 3. Заново извлеки английские wav (шаг 5: AnimeWwise -> Extract All -> hsr-dataset\)

# 4. Диагностика: появились ли новые таблицы с текстом?
python pipeline.py utils find-missing-text

# 5. Если скрипт нашёл новые таблицы — добавь их в 01_mapper.py (строки load_extra)

# 6. Полный цикл и установка
python pipeline.py all --gender m
python pipeline.py install --gender m
```

> `--update` (например, `python pipeline.py all --gender m --update`) делает то же, что шаг 2, — `git submodule update --remote`. Если подмодули уже обновлены вручную, флаг можно не указывать.
> `generate` пропускает уже существующие файлы — генерируются только новые реплики патча.
> Без шага 3 новые реплики патча не сгенерируются: wav-референсы появляются в pck игры, а не в подмодулях.

### Установка в игру

- Игра должна быть закрыта — `install` проверяет это и не запускается при работающей игре.
- Мод заменяет английскую озвучку: в настройках игры язык озвучки должен быть **English**.
- Если игра обновила pck после сборки мода, `install` такие файлы не ставит и просит сначала выполнить `python pipeline.py repack --gender m`.

### Откат мода

```bash
python pipeline.py install --uninstall
```

## Структура

| Папка | Назначение |
|-------|-----------|
| `AnimeWwise/` | Извлечение wav (подмодуль) |
| `hsr-cosyvoice/` | CosyVoice 3 (Docker) |
| `hsr-dataset/` | EN wav из игры (gitignored) |
| `hsr-gamedata/` | Геймдата (подмодуль) |
| `hsr-run-voice/` | Рабочие файлы (gitignored) |
| `hsr-wwise/` | Проект Wwise |
| `scripts/` | Отдельные шаги пайплайна |
| `scripts/utils/` | Диагностические утилиты |
| `config.py` | Авто-определение путей |
| `config.toml` | Локальные настройки (gitignored) |
| `pipeline.py` | Единая точка входа |

## Требования

- Python 3.12+
- Docker Desktop
- Wwise 2025.1+ (Audiokinetic)
- Honkai: Star Rail
