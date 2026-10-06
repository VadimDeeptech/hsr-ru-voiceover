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
    python pipeline.py generate [--chapter N|--all] [--limit N]
    python pipeline.py build
    python pipeline.py findpck
    python pipeline.py wwise --gender m|f
    python pipeline.py collect --gender m|f
    python pipeline.py repack --gender m|f
"""
import argparse
import os
import subprocess
import sys

# UTF-8 для консоли Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import config


def run_script(name, args_list=None):
    """Запускает scripts/<name> с переданными аргументами."""
    script = os.path.join(config.SCRIPTS, name)
    cmd = [sys.executable, script] + (args_list or [])
    print(f">>> {' '.join(cmd)}\n")
    r = subprocess.run(cmd, cwd=config.ROOT)
    if r.returncode != 0:
        print(f"\n!!! {name} завершился с кодом {r.returncode}")
        sys.exit(r.returncode)


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
    run_script("1_mapper.py")


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
    run_script("2_scan.py", a)


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
    run_script("3_generate.py", a)


def cmd_build(_args):
    run_script("4_build_repack_list.py")


def cmd_findpck(_args):
    run_script("5_find_pck.py")


def cmd_wwise(args):
    run_script("6_prepare_wwise.py", ["--gender", args.gender])


def cmd_collect(args):
    run_script("7_collect_wem.py", ["--gender", args.gender])


def cmd_repack(args):
    run_script("8_repack_pck.py", ["--gender", args.gender])


def cmd_install(args):
    ps = os.path.join(config.SCRIPTS, "9_install.ps1")
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps]
    if args.uninstall:
        cmd.append("-Uninstall")
    else:
        cmd += ["-Gender", args.gender]
    print(f">>> {' '.join(cmd)}\n")
    r = subprocess.run(cmd, cwd=config.ROOT)
    sys.exit(r.returncode)


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
    r = subprocess.run(cmd, cwd=config.ROOT)
    sys.exit(r.returncode)


def cmd_full(args):
    """Шаги 1-5: map + scan + generate + build + findpck"""
    cmd_map(args)
    cmd_scan(args)
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
    r = subprocess.run(cmd, cwd=config.ROOT)
    if r.returncode != 0:
        print(f"!! WwiseConsole завершился с кодом {r.returncode}")
        return False
    print("WwiseConsole: конвертация завершена успешно")
    return True


def _update_submodules():
    """git submodule update --remote"""
    print(">>> Обновление сабмодулей (git submodule update --remote)\n")
    r = subprocess.run(["git", "submodule", "update", "--remote"], cwd=config.ROOT)
    if r.returncode != 0:
        print("!! Ошибка обновления сабмодулей")
        sys.exit(r.returncode)
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
    p.set_defaults(fn=cmd_chapter)

    # Побочный контент: одна категория или все
    p = sub.add_parser("extra", help="полный цикл для побочного контента: одна категория или все (без install)")
    p.add_argument("category", type=str, nargs="?", default=None,
                   help="категория (side0, companion1, vo, ambient, archive, ...)")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-wwise", action="store_true", help="не запускать WwiseConsole автоматически")
    p.add_argument("--update", action="store_true", help="обновить сабмодули перед генерацией")
    p.set_defaults(fn=cmd_extra)

    # Весь контент (главы + побочка)
    p = sub.add_parser("all", help="полный цикл для всего контента: главы + побочка (без install)")
    p.add_argument("--gender", choices=["m", "f"], default="m")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--no-wwise", action="store_true", help="не запускать WwiseConsole автоматически")
    p.add_argument("--update", action="store_true", help="обновить сабмодули перед генерацией")
    p.set_defaults(fn=cmd_all)

    # === Отдельные шаги (для отладки) ===
    sub.add_parser("map", help="шаг 1: маппинг").set_defaults(fn=cmd_map)

    p = sub.add_parser("scan", help="шаг 2: фильтр по главам и категориям")
    add_chapter_args(p); p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("generate", help="шаг 3: генерация TTS")
    add_chapter_args(p)
    p.add_argument("--limit", type=int, default=None, help="лимит задач (для теста)")
    p.set_defaults(fn=cmd_generate)

    sub.add_parser("build", help="шаг 4: repack_list").set_defaults(fn=cmd_build)
    sub.add_parser("findpck", help="шаг 5: id_to_pck").set_defaults(fn=cmd_findpck)

    p = sub.add_parser("wwise", help="шаг 6: staging + wsources")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_wwise)

    p = sub.add_parser("collect", help="шаг 7: сбор wem")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_collect)

    p = sub.add_parser("repack", help="шаг 8: сборка pck")
    p.add_argument("--gender", choices=["m", "f"], required=True)
    p.set_defaults(fn=cmd_repack)

    # === Установка ===
    p = sub.add_parser("install", help="шаг 9: установка в игру")
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
    args.fn(args)


if __name__ == "__main__":
    main()
