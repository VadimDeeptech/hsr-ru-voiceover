# -*- coding: utf-8 -*-
"""2_scan.py — фильтр mapping.csv по главе(ам) -> chapterN.csv

Запуск:
    python 2_scan.py --chapter 0      # только chapter0
    python 2_scan.py --all            # все найденные главы
"""
import os, csv, re, argparse
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

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

def main():
    ap = argparse.ArgumentParser(description="Фильтр mapping.csv по главам")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chapter", type=int, help="номер главы")
    g.add_argument("--all", action="store_true", help="все найденные главы")
    args = ap.parse_args()

    csv_path = os.path.join(config.RUN, "mapping.csv")
    if not os.path.exists(csv_path):
        print(f"Нет {csv_path}. Сначала запусти: python pipeline.py map")
        sys.exit(1)

    out_dir = config.RUN
    os.makedirs(out_dir, exist_ok=True)

    chapters = []
    if args.all:
        # авто-скан: какие главы есть в mapping.csv
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

if __name__ == "__main__":
    main()
