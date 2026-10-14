# -*- coding: utf-8 -*-
"""
config.py — единый источник путей проекта HSR RU Voiceover.
Автоматически определяет ROOT по местоположению файла.
Машинно-специфичные пути — из config.toml (в .gitignore).
"""
import os
import sys

# Авто-определение корня проекта (папка, где лежит config.py)
ROOT = os.path.dirname(os.path.abspath(__file__))

# Пути внутри проекта (не меняются при клонировании)
DATASET   = os.path.join(ROOT, "hsr-dataset")
RUN       = os.path.join(ROOT, "hsr-run-voice")
GAMEDATA  = os.path.join(ROOT, "hsr-gamedata")
AWWISE    = os.path.join(ROOT, "AnimeWwise")
WPROJ     = os.path.join(ROOT, "hsr-wwise", "hsr-wwise.wproj")
SCRIPTS   = os.path.join(ROOT, "scripts")
LOGS      = os.path.join(ROOT, "logs")

# Пути внутри hsr-run-voice
REPACK    = os.path.join(RUN, "repack")
PCK_BACKUP = os.path.join(RUN, "pck_backup_en")

# hsr-generate — дорогие результаты (часы GPU): распознавание и озвучка.
# Должна быть на одном диске с hsr-run-voice: staging Wwise — жёсткие ссылки на output_ru.
GEN           = os.path.join(ROOT, "hsr-generate")
AUDIT         = os.path.join(GEN, "audit")          # audit_report.csv, audit_auto.csv
ASR           = os.path.join(AUDIT, "asr")          # asr_*.csv — результаты Whisper
OUTPUT_RU     = os.path.join(GEN, "output_ru")      # <категория>\*.wav, gen_report.csv, gen_text.csv
WHISPER_CACHE = os.path.join(GEN, "whisper_cache")  # модель Whisper

# Машинно-специфичные настройки (из config.toml)
_config_toml = os.path.join(ROOT, "config.toml")
_game_dir = None
_wwise_console = None
_cosyvoice_url = "http://localhost:8020"
_audit_runners = 3

if os.path.exists(_config_toml):
    try:
        import tomllib
    except ImportError:
        # Python < 3.11 fallback
        import tomli as tomllib
    with open(_config_toml, "rb") as f:
        _cfg = tomllib.load(f)
    _game_dir      = _cfg.get("game_dir")
    _wwise_console = _cfg.get("wwise_console")
    _cosyvoice_url = _cfg.get("cosyvoice_url", _cosyvoice_url)
    _audit_runners = _cfg.get("audit_runners", _audit_runners)

if not isinstance(_audit_runners, int) or isinstance(_audit_runners, bool) or _audit_runners < 1:
    sys.exit(f"config.toml: audit_runners должен быть целым числом от 1, сейчас: {_audit_runners!r}")

def _find_game_dir():
    """Автопоиск папки с игрой по типичным путям."""
    # HoYoPlay: <Star Rail>\Games\StarRail.exe
    # Проверяем как сами пути, так и родительские папки (Games -> Star Rail)
    candidates = [
        # HoYoPlay стандартные
        r"C:\Program Files\Star Rail\Games",
        r"D:\Program Files\Star Rail\Games",
        r"C:\Program Files\Honkai Star Rail\Games",
        r"D:\Program Files\Honkai Star Rail\Games",
        # Старый лаунчер / кастомные
        r"C:\Games\Star Rail Games",
        r"D:\Games\Star Rail Games",
        r"E:\Games\Star Rail Games",
        r"C:\Star Rail\Games",
        r"D:\Star Rail\Games",
    ]
    for c in candidates:
        if os.path.isdir(c) and os.path.exists(os.path.join(c, "StarRail.exe")):
            return c
        # Проверяем родителя (Games -> Star Rail)
        parent = os.path.dirname(c)
        if os.path.isdir(parent) and os.path.exists(os.path.join(parent, "Games", "StarRail.exe")):
            return parent
    return None

def _find_wwise_console():
    """Автопоиск WwiseConsole.exe."""
    import glob
    # 1. Через переменную окружения WWISEROOT (стандартный способ)
    wwise_root = os.environ.get("WWISEROOT")
    if wwise_root:
        candidate = os.path.join(wwise_root, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe")
        if os.path.isfile(candidate):
            return candidate
    # 2. Поиск по типичным путям установки
    patterns = [
        r"C:\Program Files\Audiokinetic\Wwise*\Authoring\x64\Release\bin\WwiseConsole.exe",
        r"C:\Program Files (x86)\Audiokinetic\Wwise*\Authoring\x64\Release\bin\WwiseConsole.exe",
        r"D:\Audiokinetic\Wwise*\Authoring\x64\Release\bin\WwiseConsole.exe",
        r"C:\Projects\Audiokinetic\Wwise*\Authoring\x64\Release\bin\WwiseConsole.exe",
    ]
    for p in patterns:
        matches = glob.glob(p)
        if matches:
            return sorted(matches)[-1]  # последняя версия
    return None

GAME_DIR = _game_dir or _find_game_dir()
if GAME_DIR:
    GAME_AUDIO = os.path.join(GAME_DIR, "StarRail_Data", "Persistent", "Audio", "AudioPackage", "Windows", "English")
else:
    GAME_AUDIO = None

WWISE_CONSOLE = _wwise_console or _find_wwise_console()
COSYVOICE_URL = _cosyvoice_url
AUDIT_RUNNERS = _audit_runners

def category_csvs():
    """Имена csv категорий в hsr-run-voice (результат 02_scan.py): все csv, кроме mapping.csv."""
    return sorted(f for f in os.listdir(RUN)
                  if f.lower().endswith(".csv") and f.lower() != "mapping.csv"
                  and os.path.isfile(os.path.join(RUN, f)))

def ensure_dirs():
    """Создаёт рабочие папки, если их нет."""
    for d in (RUN, REPACK, PCK_BACKUP, LOGS, GEN, ASR, OUTPUT_RU, WHISPER_CACHE):
        os.makedirs(d, exist_ok=True)

def check_env():
    """Проверка окружения. Возвращает список (ok, message)."""
    checks = []
    checks.append((os.path.isdir(DATASET),   f"hsr-dataset: {DATASET}"))
    checks.append((os.path.isdir(GAMEDATA),  f"hsr-gamedata: {GAMEDATA}"))
    checks.append((os.path.isdir(AWWISE),    f"AnimeWwise: {AWWISE}"))
    checks.append((os.path.isfile(WPROJ),    f"hsr-wwise.wproj: {WPROJ}"))
    checks.append((GAME_DIR is not None,     f"Игра: {GAME_DIR or 'НЕ НАЙДЕНА'}"))
    checks.append((WWISE_CONSOLE is not None, f"WwiseConsole: {WWISE_CONSOLE or 'НЕ НАЙДЕН'}"))
    checks.append((os.path.isfile(os.path.join(GAMEDATA, "ExcelOutput", "VoiceConfig.json")),
                   f"VoiceConfig.json"))
    checks.append((os.path.isfile(os.path.join(GAMEDATA, "TextMap", "TextMapRU_0.json")),
                   f"TextMapRU_0.json"))
    return checks

if __name__ == "__main__":
    print("ROOT:", ROOT)
    print("GAME_DIR:", GAME_DIR)
    print("WWISE_CONSOLE:", WWISE_CONSOLE)
    print("COSYVOICE_URL:", COSYVOICE_URL)
    print()
    for ok, msg in check_env():
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
