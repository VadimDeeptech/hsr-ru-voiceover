# -*- coding: utf-8 -*-
"""
pipeline.py — единая точка входа для всех шагов пайплайна HSR RU Voiceover.

Использование:
    python pipeline.py doctor                     — проверка окружения
    python pipeline.py chapter N [--gender m|f]   — полный цикл для главы N (без установки)
    python pipeline.py all [--gender m|f]         — полный цикл для всех глав (без установки)
    python pipeline.py install --gender m|f       — установка в игру (отдельно!)
    python pipeline.py install --uninstall        — откат

    # Отладка/разработка (отдельные шаги):
    python pipeline.py map
    python pipeline.py scan [--chapter N|--all]
    python pipeline.py audit                      — сверка звука оригинала с текстом
    python pipeline.py generate [--chapter N|--all] [--limit N]
    python pipeline.py build
    python pipeline.py findpck
    python pipeline.py wwise --gender m|f
    python pipeline.py collect --gender m|f
    python pipeline.py repack --gender m|f
"""
import argparse
import csv
import datetime
import glob
import os
import subprocess
import sys
import threading

# UTF-8 для консоли Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import config


class _Tee:
    """Дублирует всё, что пишется в поток, в файл лога."""

    def __init__(self, stream, log):
        self._stream = stream
        self._log = log

    def write(self, s):
        self._stream.write(s)
        self._stream.flush()
        self._log.write(s)
        return len(s)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def setup_logging(cmd_name):
    """Направляет вывод в консоль и в logs/pipeline_<дата>_<время>_<команда>.log."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(config.LOGS, f"pipeline_{stamp}_{cmd_name}.log")
    log = open(path, "w", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, log)
    sys.stderr = _Tee(sys.stderr, log)
    print(f"Лог: {path}\n")


def run_cmd(cmd, encoding="utf-8"):
    """Запускает процесс, дублируя его вывод в консоль и лог. Возвращает код возврата."""
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    p = subprocess.Popen(cmd, cwd=config.ROOT, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         encoding=encoding, errors="replace")
    for line in p.stdout:
        print(line, end="")
    return p.wait()


def run_script(name, args_list=None):
    """Запускает scripts/<name> с переданными аргументами."""
    script = os.path.join(config.SCRIPTS, name)
    cmd = [sys.executable, script] + (args_list or [])
    print(f">>> {' '.join(cmd)}\n")
    rc = run_cmd(cmd)
    if rc != 0:
        print(f"\n!!! {name} завершился с кодом {rc}")
        sys.exit(rc)


def cmd_doctor(_args):
    print("Проверка окружения:\n")
    all_ok = True
    for ok, msg in config.check_env():
        print(f"  [{'OK' if ok else 'FAIL'}] {msg}")
        all_ok = all_ok and ok
    # CosyVoice
    try:
        import requests
        r = requests.get(config.COSYVOICE_URL + "/", timeout=5)
        print(f"  [OK] CosyVoice отвечает: {config.COSYVOICE_URL} (HTTP {r.status_code})")
    except Exception as e:
        print(f"  [FAIL] CosyVoice недоступен ({config.COSYVOICE_URL}): {e}")
        all_ok = False
    print("\n" + ("Всё готово." if all_ok else "Есть проблемы — см. выше."))
    sys.exit(0 if all_ok else 1)


def cmd_map(_args):
    run_script("01_mapper.py")


def cmd_scan(args):
    a = []
    if getattr(args, 'all_categories', False):
        a.append("--all-categories")
    elif getattr(args, 'category', None):
        a += ["--category", args.category]
    elif args.all:
        a.append("--all")
    elif args.chapter is not None:
        a += ["--chapter", str(args.chapter)]
    run_script("02_scan.py", a)


AUDIT_IMAGE = "hsr-cosyvoice-cosyvoice"   # образ CosyVoice: в нём уже есть torch + whisper


def _audit_pending():
    """Сколько записей из mapping.csv ещё не распознано."""
    done = set()
    for p in glob.glob(os.path.join(config.RUN, "asr", "asr_*.csv")):
        with open(p, encoding="utf-8-sig", newline="") as f:
            done |= {r["file"] for r in csv.DictReader(f, delimiter=";")}
    with open(os.path.join(config.RUN, "mapping.csv"), encoding="utf-8-sig", newline="") as f:
        return sum(1 for r in csv.DictReader(f, delimiter=";") if r["file"] not in done)


def _run_transcribe():
    """Распознаёт речь в ещё не проверенных оригиналах (Whisper в контейнерах на образе CosyVoice)."""
    pending = _audit_pending()
    if not pending:
        print("Сверка: новых записей для распознавания нет.\n")
        return
    # распознавание упирается в один поток CPU — большой объём делим на части
    shards = 3 if pending > 1500 else 1
    print(f">>> Сверка: распознаю {pending} записей, потоков: {shards}\n")
    procs = []
    for k in range(shards):
        cmd = ["docker", "run", "--rm", "--gpus", "all",
               "-v", f"{config.DATASET}:/data:ro",
               "-v", f"{config.RUN}:/work",
               "-v", f"{config.SCRIPTS}:/scripts:ro",
               "-v", f"{os.path.join(config.RUN, 'whisper_cache')}:/root/.cache/whisper",
               AUDIT_IMAGE, "python", "/scripts/03_audit_transcribe.py", "--shard", f"{k}/{shards}"]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      encoding="utf-8", errors="replace"))

    def pump(k, p):
        for line in p.stdout:
            # прогресс-бар загрузки модели и баннер образа в лог не нужны
            if line.startswith(("[", "Уже распознано")) or "Error" in line or "error" in line:
                print(f"[поток {k}] {line}", end="")

    threads = [threading.Thread(target=pump, args=(k, p)) for k, p in enumerate(procs)]
    for t in threads: t.start()
    for t in threads: t.join()
    if any(p.wait() != 0 for p in procs):
        print("\n!!! Распознавание завершилось с ошибкой (запущен ли Docker и собран ли образ CosyVoice?)")
        sys.exit(1)
    print()


def cmd_audit(args):
    """Шаги 3-4: сверка звука оригинала с текстом. Останавливает пайплайн при неразобранных расхождениях."""
    if getattr(args, "no_audit", False):
        print("Сверка пропущена (--no-audit).\n")
        return
    _run_transcribe()
    run_script("04_audit_report.py")


def cmd_generate(args):
    a = []
    if getattr(args, 'all_categories', False):
        a.append("--all-categories")
    elif getattr(args, 'category', None):
        a += ["--category", args.category]
    elif args.all:
        a.append("--all")
    elif args.chapter is not None:
        a += ["--chapter", str(args.chapter)]
    if args.limit:
        a += ["--limit", str(args.limit)]
    run_script("05_generate.py", a)


def cmd_build(_args):
    run_script("06_build_repack_list.py")


def cmd_findpck(_args):
    run_script("07_find_pck.py")


def cmd_wwise(args):
    run_script("08_prepare_wwise.py", ["--gender", args.gender])


def cmd_collect(args):
    run_script("09_collect_wem.py", ["--gender", args.gender])


def cmd_repack(args):
    run_script("10_repack_pck.py", ["--gender", args.gender])


def cmd_install(args):
    ps = os.path.join(config.SCRIPTS, "11_install.ps1")
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps]
    if args.uninstall:
        cmd.append("-Uninstall")
    else:
        cmd += ["-Gender", args.gender]
    print(f">>> {' '.join(cmd)}\n")
    # PowerShell пишет в pipe в OEM-кодировке консоли
    sys.exit(run_cmd(cmd, encoding="oem"))


def cmd_utils(args):
    """Запуск утилит из scripts/utils/"""
    util_map = {
        "find-missing-text": "utils/find_missing_text_sources.py",
    }
    script = util_map.get(args.util_cmd)
    if not script:
        print(f"Неизвестная утилита: {args.util_cmd}")
        sys.exit(1)
    script_path = os.path.join(config.SCRIPTS, script)
    cmd = [sys.executable, script_path]
    print(f">>> {' '.join(cmd)}\n")
    sys.exit(run_cmd(cmd))


def cmd_full(args):
    """Шаги 1-7: map + scan + audit + generate + build + findpck"""
    cmd_map(args)
    cmd_scan(args)
    cmd_audit(args)
    cmd_generate(args)
    cmd_build(args)
    cmd_findpck(args)
    print("\nДалее: python pipeline.py wwise --gender m|f  (затем WwiseConsole, см. вывод)")
    print("       python pipeline.py collect --gender m|f")
    print("       python pipeline.py repack --gender m|f")
    print("       python pipeline.py install --gender m|f")


def _run_wwise_console(gender):
    """Автозапуск WwiseConsole для конвертации."""
    if not config.WWISE_CONSOLE:
        print("!! WwiseConsole не найден. Пропускаю автозапуск.")
        return False
    xml_path = os.path.join(config.RUN, f"externals_{gender}.wsources")
    wem_out = os.path.join(config.RUN, f"wem_out_{gender}")
    if not os.path.exists(xml_path):
        print(f"!! Нет {xml_path}. Сначала запусти wwise-шаг.")
        return False
    cmd = [
        config.WWISE_CONSOLE,
        "convert-external-source",
        config.WPROJ,
        "--source-file", xml_path,
        "--platform", "Windows",
        "--output", wem_out,
        "--verbose"
    ]
    print(f">>> Автозапуск WwiseConsole...\n")
    rc = run_cmd(cmd)
    if rc != 0:
        print(f"!! WwiseConsole завершился с кодом {rc}")
        return False
    print("WwiseConsole: конвертация завершена успешно")
    return True


def _update_submodules():
    """git submodule update --remote"""
    print(">>> Обновление сабмодулей (git submodule update --remote)\n")
    rc = run_cmd(["git", "submodule", "update", "--remote"])
    if rc != 0:
        print("!! Ошибка обновления сабмодулей")
        sys.exit(rc)
    print()


def cmd_chapter(args):
    """Полный цикл для глав: одна или все"""
    if args.chapter is not None:
        print(f"=== Глава {args.chapter}, пол {args.gender} ===\n")
        if args.update:
            _update_submodules()
        cmd_map(args)
        args.all = False  # для scan/generate
        cmd_scan(args)
        cmd_audit(args)
        cmd_generate(args)
        cmd_build(args)
        cmd_findpck(args)
        cmd_wwise(args)
        if not args.no_wwise and _run_wwise_console(args.gender):
            cmd_collect(args)
            cmd_repack(args)
            print(f"\n=== Готово. Для установки: python pipeline.py install --gender {args.gender}")
        else:
            print(f"\n=== Запусти WwiseConsole (команда выше), затем: ===")
            print(f"  python pipeline.py collect --gender {args.gender}")
            print(f"  python pipeline.py repack --gender {args.gender}")
            print(f"  python pipeline.py install --gender {args.gender}")
    else:
        # все главы
        print(f"=== Все главы, пол {args.gender} ===\n")
        if args.update:
            _update_submodules()
        cmd_map(args)
        args.all = True  # для scan/generate
        args.all_categories = False
        cmd_scan(args)
        cmd_audit(args)
        cmd_generate(args)
        cmd_build(args)
        cmd_findpck(args)
        cmd_wwise(args)
        if not args.no_wwise and _run_wwise_console(args.gender):
            cmd_collect(args)
            cmd_repack(args)
            print(f"\n=== Готово. Для установки: python pipeline.py install --gender {args.gender}")
        else:
            print(f"\n=== Запусти WwiseConsole (команда выше), затем: ===")
            print(f"  python pipeline.py collect --gender {args.gender}")
            print(f"  python pipeline.py repack --gender {args.gender}")
            print(f"  python pipeline.py install --gender {args.gender}")


def cmd_all(args):
    """Полный цикл для всего контента: map + scan + generate + build + findpck + wwise + collect + repack"""
    print(f"=== Весь контент (главы + побочка), пол {args.gender} ===\n")
    if args.update:
        _update_submodules()
    cmd_map(args)
    args.all = False
    args.all_categories = True
    cmd_scan(args)
    cmd_audit(args)
    cmd_generate(args)
    cmd_build(args)
    cmd_findpck(args)
    cmd_wwise(args)
    if not args.no_wwise and _run_wwise_console(args.gender):
        cmd_collect(args)
        cmd_repack(args)
        print(f"\n=== Готово. Для установки: python pipeline.py install --gender {args.gender}")
    else:
        print(f"\n=== Запусти WwiseConsole (команда выше), затем: ===")
        print(f"  python pipeline.py collect --gender {args.gender}")
        print(f"  python pipeline.py repack --gender {args.gender}")
        print(f"  python pipeline.py install --gender {args.gender}")


def cmd_extra(args):
    """Полный цикл для побочного контента: map + scan + generate + build + findpck + wwise + collect + repack"""
    cat = args.category or "все категории"
    print(f"=== Побочный контент ({cat}), пол {args.gender} ===\n")
    if args.update:
        _update_submodules()
    cmd_map(args)
    if args.category:
        args.all = False
        args.all_categories = False
    else:
        args.all = False
        args.all_categories = True
    cmd_scan(args)
    cmd_audit(args)
    cmd_generate(args)
    cmd_build(args)
    cmd_findpck(args)
    cmd_wwise(args)
    if not args.no_wwise and _run_wwise_console(args.gender):
        cmd_collect(args)
        cmd_repack(args)
        print(f"\n=== Готово. Для установки: python pipeline.py install --gender {args.gender}")
    else:
        print(f"\n=== Запусти WwiseConsole (команда выше), затем: ===")
        print(f"  python pipeline.py collect --gender {args.gender}")
        print(f"  python pipeline.py repack --gender {args.gender}")
        print(f"  python pipeline.py install --gender {args.gender}")


def add_chapter_args(p):
    g = p.add_mutually_exclusive_group()
    g.add_argument("--chapter", type=int, help="номер главы (0, 1, 2, ...)")
    g.add_argument("--all", action="store_true", help="все найденные главы")
    g.add_argument("--category", type=str, help="конкретная категория (side0, companion1, vo, ...)")
    g.add_argument("--all-categories", action="store_true", help="все категории (chapters + sides + companions + vo + ...)")


def main():
    ap = argparse.ArgumentParser(description="HSR RU Voiceover pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="проверка окружения").set_defaults(fn=cmd_doctor)

    # === Полные циклы (map + scan + generate + build + findpck + wwise + collect + repack) ===
    # Одна глава или все главы
    p = sub.add_parser("chapter", help="полный цикл для глав: одна или все (без install)")
    p.add_argument("chapter", type=int, nargs="?", default=None, help="номер главы (0, 1, 2, ...)")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-wwise", action="store_true", help="не запускать WwiseConsole автоматически")
    p.add_argument("--update", action="store_true", help="обновить сабмодули перед генерацией")
    p.add_argument("--no-audit", action="store_true", help="пропустить сверку звука с текстом")
    p.set_defaults(fn=cmd_chapter)

    # Побочный контент: одна категория или все
    p = sub.add_parser("extra", help="полный цикл для побочного контента: одна категория или все (без install)")
    p.add_argument("category", type=str, nargs="?", default=None,
                   help="категория (side0, companion1, vo, ambient, archive, ...)")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-wwise", action="store_true", help="не запускать WwiseConsole автоматически")
    p.add_argument("--update", action="store_true", help="обновить сабмодули перед генерацией")
    p.add_argument("--no-audit", action="store_true", help="пропустить сверку звука с текстом")
    p.set_defaults(fn=cmd_extra)

    # Весь контент (главы + побочка)
    p = sub.add_parser("all", help="полный цикл для всего контента: главы + побочка (без install)")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-wwise", action="store_true", help="не запускать WwiseConsole автоматически")
    p.add_argument("--update", action="store_true", help="обновить сабмодули перед генерацией")
    p.add_argument("--no-audit", action="store_true", help="пропустить сверку звука с текстом")
    p.set_defaults(fn=cmd_all)

    # === Отдельные шаги (для отладки) ===
    sub.add_parser("map", help="шаг 1: маппинг").set_defaults(fn=cmd_map)

    p = sub.add_parser("scan", help="шаг 2: фильтр по главам и категориям")
    add_chapter_args(p); p.set_defaults(fn=cmd_scan)

    sub.add_parser("audit", help="шаги 3-4: сверка звука оригинала с текстом").set_defaults(fn=cmd_audit)

    p = sub.add_parser("generate", help="шаг 5: генерация TTS")
    add_chapter_args(p)
    p.add_argument("--limit", type=int, default=None, help="лимит задач (для теста)")
    p.set_defaults(fn=cmd_generate)

    sub.add_parser("build", help="шаг 6: repack_list").set_defaults(fn=cmd_build)
    sub.add_parser("findpck", help="шаг 7: id_to_pck").set_defaults(fn=cmd_findpck)

    p = sub.add_parser("wwise", help="шаг 8: staging + wsources")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_wwise)

    p = sub.add_parser("collect", help="шаг 9: сбор wem")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("repack", help="шаг 10: сборка pck")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_repack)

    # === Установка ===
    p = sub.add_parser("install", help="шаг 11: установка в игру")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--uninstall", action="store_true")
    p.set_defaults(fn=cmd_install)

    # === Утилиты ===
    p = sub.add_parser("utils", help="диагностика и утилиты")
    utils_sub = p.add_subparsers(dest="util_cmd", required=True)
    utils_sub.add_parser("find-missing-text", help="найти таблицы с текстом для voiceid без текста")
    p.set_defaults(fn=cmd_utils)

    args = ap.parse_args()
    config.ensure_dirs()
    setup_logging(args.cmd)
    args.fn(args)


if __name__ == "__main__":
    main()
