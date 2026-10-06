# -*- coding: utf-8 -*-
"""2_scan.py — фильтр mapping.csv по главе(ам) и категориям -> *.csv

Запуск:
    python 2_scan.py --chapter 0        # только chapter0
    python 2_scan.py --all              # все найденные главы
    python 2_scan.py --category side0   # только side0
    python 2_scan.py --all-categories   # все категории (chapters + sides + companions + vo + ambient + archive)
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
    """Фильтрует mapping.csv по категории (side0, companion1, vo, ambient, ...) -> <cat>.csv"""
    out_path = os.path.join(out_dir, f"{cat_name}.csv")
    rows_out = []
    chars = defaultdict(lambda: [0, 0])

    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            parts = row["file"].replace("/", "\\").split("\\")
            if len(parts) < 3 or parts[1] != "voice" or parts[2] != cat_name:
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


def find_categories(csv_path):
    """Находит все категории в mapping.csv (voice/<cat>/...)."""
    cats = set()
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f, delimiter=";"):
            parts = row["file"].replace("/", "\\").split("\\")
            if len(parts) >= 3 and parts[1] == "voice":
                cats.add(parts[2])
    return sorted(cats)


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
        total, with_ru = scan_category(args.category, csv_path, out_dir)
        if total:
            print(f"{args.category}: {total} реплик, с RU: {with_ru}")
        else:
            print(f"{args.category}: нет реплик")
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
