# -*- coding: utf-8 -*-
"""02_scan.py — фильтр mapping.csv по главе(ам) и категориям -> *.csv

Запуск:
    python 02_scan.py --chapter 0        # только chapter0
    python 02_scan.py --all              # все найденные главы
    python 02_scan.py --category side0   # только side0
    python 02_scan.py --all-categories   # все категории (chapters + sides + companions + vo + ambient + archive)
"""
import os, csv, re, argparse
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# Категории, которые обрабатываются помимо chapterN
EXTRA_CATEGORIES = [
    "side", "Side", "companion", "vo", "ambient", "archive",
    "chapterfate", "chapterfate02", "chapterfinality1", "chaptersummer01",
    "CG", "bgm"
]

def scan_chapter(chapter, csv_path, out_dir):
    """Фильтрует mapping.csv по главе chapter -> chapterN.csv"""
    out_path = os.path.join(out_dir, f"chapter{chapter}.csv")
    rows_out = []
    chars = defaultdict(lambda: [0, 0])

    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            parts = row["file"].replace("/", "\\").split("\\")
            if len(parts) < 3 or parts[1] != "voice" or parts[2] != f"chapter{chapter}":
                continue
            rows_out.append(row)
            ch = row["character"] or "(не определён)"
            chars[ch][0] += 1
            if row["text_ru"].strip():
                chars[ch][1] += 1

    if not rows_out:
        return 0, 0

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, delimiter=";", fieldnames=rows_out[0].keys())
        wr.writeheader()
        wr.writerows(rows_out)

    return len(rows_out), sum(v[1] for v in chars.values())


def scan_category(cat_name, csv_path, out_dir):
    """Фильтрует mapping.csv по категории (side0, companion1, vo, ambient, ...) -> <cat>.csv

    Категория сравнивается без учёта регистра: Side0 и side0 идут в один csv,
    иначе на Windows второй файл затирает первый.
    """
    out_name = f"{cat_name}.csv"
    out_path = os.path.join(out_dir, out_name)
    rows_out = []
    chars = defaultdict(lambda: [0, 0])
    seen = {}       # имя файла -> папка категории, откуда оно пришло
    clashes = []

    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            parts = row["file"].replace("/", "\\").split("\\")
            if len(parts) < 3 or parts[1] != "voice" or parts[2].lower() != cat_name.lower():
                continue
            stem = os.path.splitext(parts[-1])[0].lower()
            if seen.setdefault(stem, parts[2]) != parts[2]:
                clashes.append(f"{stem}: {seen[stem]} и {parts[2]}")
            rows_out.append(row)
            ch = row["character"] or "(не определён)"
            chars[ch][0] += 1
            if row["text_ru"].strip():
                chars[ch][1] += 1

    if clashes:
        # в output_ru оба файла легли бы под одним именем — один затёр бы другой
        print(f"!! {cat_name}: одинаковые имена файлов в папках с разным регистром ({len(clashes)}):")
        for c in clashes[:20]:
            print(f"   {c}")
        sys.exit(1)

    if not rows_out:
        return 0, 0

    # старый csv с тем же именем в другом регистре (Side0.csv при записи side0.csv)
    for f in os.listdir(out_dir):
        if f.lower() == out_name.lower() and f != out_name:
            os.remove(os.path.join(out_dir, f))

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, delimiter=";", fieldnames=rows_out[0].keys())
        wr.writeheader()
        wr.writerows(rows_out)

    return len(rows_out), sum(v[1] for v in chars.values())


def find_categories(csv_path):
    """Находит все категории в mapping.csv (voice/<cat>/...).

    Варианты, различающиеся только регистром (Side0/side0), считаются одной
    категорией; из них берётся вариант со строчной буквы.
    """
    cats = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            parts = row["file"].replace("/", "\\").split("\\")
            if len(parts) >= 3 and parts[1] == "voice":
                key = parts[2].lower()
                cats[key] = max(cats.get(key, parts[2]), parts[2])
    return sorted(cats.values())


def main():
    ap = argparse.ArgumentParser(description="Фильтр mapping.csv по главам и категориям")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chapter", type=int, help="номер главы")
    g.add_argument("--all", action="store_true", help="все найденные главы")
    g.add_argument("--category", type=str, help="конкретная категория (side0, companion1, vo, ...)")
    g.add_argument("--all-categories", action="store_true",
                   help="все категории (chapters + sides + companions + vo + ambient + archive + ...)")
    args = ap.parse_args()

    csv_path = os.path.join(config.RUN, "mapping.csv")
    if not os.path.exists(csv_path):
        print(f"Нет {csv_path}. Сначала запусти: python pipeline.py map")
        sys.exit(1)

    out_dir = config.RUN
    os.makedirs(out_dir, exist_ok=True)

    # --- Режим --chapter / --all (только главы) ---
    if args.chapter is not None or args.all:
        chapters = []
        if args.all:
            with open(csv_path, encoding="utf-8-sig") as f:
                for row in csv.DictReader(f, delimiter=";"):
                    parts = row["file"].replace("/", "\\").split("\\")
                    if len(parts) >= 3 and parts[1] == "voice":
                        m = re.match(r"chapter(\d+)", parts[2])
                        if m:
                            chapters.append(int(m.group(1)))
            chapters = sorted(set(chapters))
            if not chapters:
                print("В mapping.csv не найдено ни одной главы (voice/chapterN/...)")
                sys.exit(1)
        else:
            chapters = [args.chapter]

        for ch in chapters:
            total, with_ru = scan_chapter(ch, csv_path, out_dir)
            if total:
                print(f"chapter{ch}: {total} реплик, с RU: {with_ru}")
            else:
                print(f"chapter{ch}: нет реплик")
        return

    # --- Режим --category ---
    if args.category:
        known = {c.lower(): c for c in find_categories(csv_path)}
        cat = known.get(args.category.lower(), args.category)
        total, with_ru = scan_category(cat, csv_path, out_dir)
        if total:
            print(f"{cat}: {total} реплик, с RU: {with_ru}")
        else:
            print(f"{cat}: нет реплик")
        return

    # --- Режим --all-categories ---
    if args.all_categories:
        all_cats = find_categories(csv_path)
        # Сначала главы
        chapters = sorted([c for c in all_cats if re.match(r"chapter\d+", c)],
                          key=lambda x: int(re.search(r"\d+", x).group()))
        for ch in chapters:
            total, with_ru = scan_category(ch, csv_path, out_dir)
            if total:
                print(f"{ch}: {total} реплик, с RU: {with_ru}")
        # Потом остальные категории
        for cat in all_cats:
            if re.match(r"chapter\d+", cat):
                continue
            total, with_ru = scan_category(cat, csv_path, out_dir)
            if total:
                print(f"{cat}: {total} реплик, с RU: {with_ru}")


if __name__ == "__main__":
    main()
