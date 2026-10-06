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

### Одна глава

```bash
python pipeline.py chapter 1 --gender m
python pipeline.py install --gender m
```

### Все главы

```bash
python pipeline.py all --gender m
python pipeline.py install --gender m
```

> WwiseConsole запускается автоматически. Чтобы пропустить (например, Wwise GUI открыт): `--no-wwise`.

### Обновление при выходе нового патча игры

Порядок важен — сначала подмодули, потом извлечение wav, потом генерация:

```bash
# 1. Обнови игру через лаунчер

# 2. Обнови подмодули (AnimeWwise получит актуальный asset map под новый патч, hsr-gamedata — тексты нового патча)
git submodule update --remote

# 3. Заново извлеки английские wav (шаг 5: AnimeWwise -> Extract All -> hsr-dataset\)

# 4. Полный цикл и установка
python pipeline.py all --gender m
python pipeline.py install --gender m
```

> `--update` (например, `python pipeline.py all --gender m --update`) делает то же, что шаг 2, — `git submodule update --remote`. Если подмодули уже обновлены вручную, флаг можно не указывать.
> `generate` пропускает уже существующие файлы — генерируются только новые реплики.
> Без шага 3 новые реплики патча не сгенерируются: wav-референсы появляются в pck игры, а не в подмодулях.

### Откат мода

```bash
python pipeline.py install --uninstall
```

## Структура

| Папка | Назначение |
|-------|-----------|
| `AnimeWwise/` | Извлечение wav (подмодуль) |
| `hsr-dataset/` | EN wav из игры (gitignored) |
| `hsr-gamedata/` | Геймдата (подмодуль) |
| `hsr-run-voice/` | Рабочие файлы (gitignored) |
| `hsr-cosyvoice/` | CosyVoice 3 (Docker) |
| `hsr-wwise/` | Проект Wwise |
| `scripts/` | Отдельные шаги пайплайна |
| `config.py` | Авто-определение путей |
| `config.toml` | Локальные настройки (gitignored) |
| `pipeline.py` | Единая точка входа |

## Требования

- Python 3.12+
- Docker Desktop
- Wwise 2025.1+ (Audiokinetic)
- Honkai: Star Rail
