# HSR RU Voiceover

Русская озвучка диалогов Honkai: Star Rail. Генерация — CosyVoice 3, образцы голосов — английские wav из игры (извлекаются с помощью [AnimeWwise](https://github.com/Escartem/AnimeWwise)), тексты — русский TextMap из дампа геймдаты ([Dimbreath/turnbasedgamedata](https://gitlab.com/Dimbreath/turnbasedgamedata)).

> Катсцены (предрендеренные .usm) не озвучиваются. Только диалоги.

> ⚠️ Неофициальный фанатский проект, не связан с HoYoverse. Озвучка сгенерирована нейросетью. Изменение файлов игры может нарушать её пользовательское соглашение — подробнее в разделе [Дисклеймер](#дисклеймер).

Готовая озвучка для игроков и обсуждение — [Playground](https://users.playground.ru/8181259/). Ошибки и предложения по коду — GitHub Issues.

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

> «Главы» — сюжетные `chapterN`; событийные `chapterfate`, `chapterfinality1`, `chaptersummer01` входят в побочный контент.

```bash
python pipeline.py extra --gender m
python pipeline.py install --gender m
```

### Отдельные шаги (отладка)

```bash
python pipeline.py unmapped                           # 1-2. узнать файлы из unmapped по речи
python pipeline.py map                                # 3. wav -> mapping.csv
python pipeline.py scan --all-categories              # 4. фильтр по всем категориям
python pipeline.py scan --category side0              #    ...или по одной
python pipeline.py audit                              # 5-6. сверка звука оригинала с текстом
python pipeline.py generate --all-categories          # 7. TTS для всех категорий
python pipeline.py generate --extra-categories        #    ...для всех, кроме глав chapterN
python pipeline.py generate --category vo --limit 50  #    ...тест на 50 репликах vo
python pipeline.py build                              # 8. repack_list.csv
python pipeline.py findpck                            # 9. id_to_pck.csv
python pipeline.py wwise --gender m                   # 10. staging + wsources + конвертация WwiseConsole
python pipeline.py collect --gender m                 # 11. сбор wem
python pipeline.py repack --gender m                  # 12. сборка pck
```

> WwiseConsole запускается автоматически. Чтобы пропустить (например, Wwise GUI открыт): `--no-wwise`.
> `generate` резюмируемый: существующие wav пропускаются, так что прерванный прогон можно продолжить той же командой. Если текст реплики изменился (решение `join`/`next`, правка перевода в патче), её wav генерируется заново — тексты озвученного хранятся в `hsr-generate\output_ru\<категория>\gen_text.csv`.

### Сверка звука с текстом (audit)

Перед генерацией полные циклы (`all`, `chapter`, `extra`) распознают английскую речь в оригинальных wav (Whisper в контейнерах на образе CosyVoice) и сравнивают её с субтитром из данных игры. Так находятся реплики, где текст не тот, разбит на несколько строк или в записи вообще нет речи.

- Результаты распознавания кэшируются в `hsr-generate\audit\asr\`: первый прогон по всему датасету идёт часы, после обновления игры распознаются только новые записи. Повторный запуск ничего не затирает — дописываются только новые записи.
- Число параллельных контейнеров распознавания — `audit_runners` в `config.toml` (по умолчанию 3; каждый грузит свою копию модели в видеопамять).
- Отчёт пишется в `hsr-generate\audit\audit_report.csv`, неразобранные расхождения идут первыми.
- Если есть неразобранные расхождения, пайплайн останавливается до генерации. Решения вписываются в `audit_decisions.csv` в корне проекта, после чего та же команда запускается снова:

| action | Что делает |
|---|---|
| `accept` | расхождение известно, озвучивать текст как есть |
| `join` + `lines` | текст продолжается: своя строка + следующие N строк субтитров |
| `next` + `lines` | своя строка — ремарка: взять только следующие N строк |
| `keep` | не озвучивать, оставить в игре оригинал |

Решение `keep` действует и на уже сгенерированные реплики: в сборку они не попадают.

Большую часть расхождений сверка разбирает сама:
- «нет речи» и «текст не тот» с похожестью ниже 0,3 — остаётся оригинал. Это существа, которые говорят звуками (Мем, химеры), пересказ субтитра в английской записи, приветствия NPC и короткие возгласы.
- «текст не тот» с похожестью от 0,3 — озвучивается: обычно это тот же текст, а распознавание ошиблось в именах.
- «звука больше» — вручную, через `audit_decisions.csv`.

Автоматические решения пишутся в `hsr-generate\audit\audit_auto.csv`; ручное решение в `audit_decisions.csv` всегда важнее.

У части записей (в основном фоновые приветствия NPC, `vo_ambient_*`) связь звука с субтитром в данных игры ненадёжна: звучит короткая фраза, а строка диалога другая. Источник текста каждой записи пишется в колонку `text_source` файла `mapping.csv`. Записи из ненадёжных источников (`sentence_other`, `sentence_samenum`, `multivoice`) озвучиваются, только если распознавание подтвердило текст; остальные автоматически остаются с оригинальным звуком и попадают в `hsr-generate\audit\audit_auto.csv`. Чтобы всё же озвучить такую запись, впиши для неё `accept` в `audit_decisions.csv`.

> Пропустить сверку: `--no-audit` (автоматические решения берутся из прошлой сверки). Только отчёт без остановки: `python scripts\06_audit_report.py --no-gate`.
> Во время сверки видеопамять занята распознаванием — CosyVoice-генерацию параллельно не запускать.

### Файлы без имени (unmapped)

AnimeWwise кладёт в `<pck>\unmapped\` файлы, которых нет в его карте. Имя такого файла — хэш пути, он же wem_id в pck; сам путь из хэша не восстановить. Полные циклы начинаются с шага `unmapped` (`scripts\01_unmapped.py`): Whisper распознаёт речь, а распознанное сравнивается с английскими субтитрами записей VoiceConfig.

- Запись без своего файла (новые квесты, которых ещё нет в карте) попадает в `mapping.csv` под виртуальным путём `<pck>\voice\...\<voicepath>.wav`. Настоящий файл записан в колонке `src`: из него берётся образец голоса, а его имя служит wem_id.
- Копия строки, файл которой уже есть: в сборку идёт та же озвучка и под этим wem_id.
- В `External_del_*.pck` файлы лежат по алфавиту имени, поэтому там помогает и порядок: файлы между двумя известными соседями — записи, лежащие между ними по алфавиту. Так различаются повторяющиеся реплики и варианты `_m`/`_f` с одинаковым текстом (`_f` всегда раньше `_m`). Если файлов в промежутке столько же, сколько записей, сопоставление однозначно и принимается, даже когда английская запись расходится с субтитром. Но если запись уверенно узнана по тексту в другом pck, а по порядку ей достался файл с непохожей речью, такой файл не берётся.
- Сомнительные совпадения пропускаются: похожесть ниже 0,9 (ниже 0,8 — всегда; от 0,8 — если остальные записи хуже на 0,2), для копий — ниже 0,95 или короче 4 слов; несколько записей с тем же текстом; не различить варианты `_m`/`_f`.
- При сверке (`audit`) расхождение речи с текстом у записей из unmapped не списывается на распознавание имён: при похожести ниже 0,3 остаётся оригинал.
- `VoBanks*.pck` не берутся: там звук внутри саундбанков, а сборка меняет только externals pck.

Итог по каждому файлу — `hsr-generate\audit\unmapped\match.csv` (колонка `status`), распознавание кэшируется там же. С `--no-audit` сопоставление идёт по уже распознанному.

### Утилиты

```bash
python pipeline.py utils find-missing-text            # диагностика: какие таблицы содержат текст для voiceid без текста (--apply — дописать их)
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

# 5. Если скрипт нашёл новые таблицы (отмечены «+»), добавь их в scripts\utils\extra_tables.csv:
python pipeline.py utils find-missing-text --apply
#    Таблицы с «?» (колонка — название/заголовок, список VoiceID или нет русского текста)
#    автоматически не добавляются: проверь пример текста и при необходимости впиши строку сам

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

## Пакет для игроков

`install` копирует в игру полные pck из `pck_out_<пол>` — в них вся английская озвучка игры, поэтому для публикации они не годятся. Для игроков собирается пакет только с нашими wem и установщиком, который патчит pck в игре самого игрока.

```bash
python pipeline.py wwise --gender m && python pipeline.py collect --gender m
python pipeline.py wwise --gender f && python pipeline.py collect --gender f
python pipeline.py package --zip
```

Результат — `dist\HSR-RU-Voiceover-<версия>\` (и `.zip`): `HSR-RU-Voiceover.exe`, `README.txt` (инструкция для игрока), `LICENSE.txt` и `data\`:

| Файл | Что внутри |
|---|---|
| `common.bin` | wem, побайтно одинаковые в сборках m и f |
| `m.bin`, `f.bin` | wem, которые различаются по полу (реплики с тегами пола в тексте) |
| `index.csv` | `pck;wem_id;variant;offset;size` в порядке `repack_list.csv` |
| `package.txt` | формат, версия, полы, размер и sha256 каждого `.bin` |

- Версия пакета — `<Version>` в `installer\HSR-RU-Voiceover.csproj` (или `--version`).
- Для сборки установщика нужен .NET SDK (`winget install Microsoft.DotNet.SDK.10`). Установщик написан под .NET Framework 4.8: он есть в Windows 10/11, игроку ничего ставить не нужно.

Установщик (`installer\`) делает тот же патч, что `12_repack_pck.py`: дописывает wem в конец pck (выравнивание 16) и правит size/offset в записях — результат побайтно совпадает с `pck_out_<пол>`. Для отката хранит в `%LOCALAPPDATA%\HSR-RU-Voiceover\` только исходную длину pck и исходные 24-байтные записи. Повторная установка ничего не дописывает; pck, который заменила игра (обновление, проверка файлов), распознаётся по хэшу индекса pck и ставится заново; прерванная установка откатывается при следующем запуске. Есть окно для игрока и командная строка (`HSR-RU-Voiceover.exe --help`).

Тесты установщика — на подставной папке игры (настоящая игра только читается):

```bash
dotnet build installer -c Release
python installer\tests\test_installer.py --work <пустая папка вне проекта>
```

## Структура

| Папка | Назначение |
|-------|-----------|
| `AnimeWwise/` | Извлечение wav (подмодуль) |
| `hsr-cosyvoice/` | CosyVoice 3 (Docker) |
| `hsr-dataset/` | EN wav из игры (gitignored) |
| `hsr-gamedata/` | Геймдата (подмодуль) |
| `hsr-run-voice/` | Рабочие файлы, пересоздаются пайплайном (gitignored); кроме `pck_backup_en/` — оригиналы pck для отката |
| `hsr-generate/` | Дорогие результаты (gitignored): `audit/` — распознавание и отчёты сверки, `output_ru/` — озвучка, `whisper_cache/` — модель Whisper. Должна быть на одном диске с `hsr-run-voice/` |
| `hsr-wwise/` | Проект Wwise |
| `scripts/` | Отдельные шаги пайплайна |
| `installer/` | Установщик для игроков (C#, .NET Framework 4.8) и его тесты |
| `dist/` | Собранные пакеты для игроков (gitignored) |
| `scripts/utils/` | Общие модули (`texts.py` и `extra_tables.csv` — таблицы с текстом по VoiceID, `decisions.py` — решения сверки) и диагностика |
| `config.py` | Авто-определение путей |
| `config.toml` | Локальные настройки (gitignored) |
| `pipeline.py` | Единая точка входа |

## Требования

- Python 3.12+
- Docker Desktop
- Wwise 2025.1+ (Audiokinetic)
- .NET SDK 8+ — только для сборки пакета для игроков (`package`)
- Honkai: Star Rail

## Используется

| Проект | Для чего | Лицензия |
|---|---|---|
| [CosyVoice](https://github.com/FunAudioLLM/CosyVoice) (FunAudioLLM) | синтез речи с клонированием голоса | Apache-2.0 |
| [Fun-CosyVoice3-0.5B](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) (FunAudioLLM) | модель синтеза речи | Apache-2.0 |
| [cosyvoice-tts-api](https://github.com/x0152/cosyvoice-tts-api) (x0152) | HTTP-сервер поверх CosyVoice; клонируется при сборке образа в `hsr-cosyvoice/Dockerfile` | не указана |
| [openai-whisper](https://github.com/openai/whisper) (OpenAI) | распознавание английской речи: сверка с текстом, unmapped | MIT (код и веса) |
| [AnimeWwise](https://github.com/Escartem/AnimeWwise) (Escartem) | извлечение wav из pck игры; подмодуль, код не распространяется | CC BY-NC-SA 4.0 |
| [turnbasedgamedata](https://gitlab.com/Dimbreath/turnbasedgamedata) (Dimbreath) | тексты реплик и данные игры; подмодуль | не указана |
| [Wwise](https://www.audiokinetic.com/) (Audiokinetic) | конвертация в wem; ставится отдельно | лицензия Audiokinetic |

Спасибо авторам этих проектов. Отдельное спасибо Dimbreath за дампы данных игры.

## Лицензия

Код репозитория распространяется под лицензией [MIT](LICENSE).

Лицензия не распространяется на сторонние проекты из таблицы выше и на готовую озвучку. Озвучка распространяется бесплатно и только для некоммерческого использования. Права на игру, персонажей и оригинальную озвучку принадлежат их владельцам.

## Дисклеймер

- Неофициальный фанатский проект. Не связан с HoYoverse / COGNOSPHERE и не одобрен ими. Honkai: Star Rail и все связанные с ней материалы принадлежат их правообладателям.
- Русская озвучка сгенерирована нейросетью по образцам голосов из оригинальной английской озвучки игры. Это не работа актёров озвучки и не их голоса.
- Изменение файлов клиента игры может нарушать пользовательское соглашение. Устанавливая мод, вы делаете это на свой страх и риск: ответственность за возможные последствия для аккаунта лежит на вас.
- Проверка целостности файлов в лаунчере игры (или обновление игры) вернёт оригинальные файлы озвучки. В этом случае установку мода нужно повторить.
- Проект предоставляется «как есть», без каких-либо гарантий.
