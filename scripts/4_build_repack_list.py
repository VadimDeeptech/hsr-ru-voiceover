# -*- coding: utf-8 -*-
"""
4_build_repack_list.py — repack_list.csv: file name -> wem_id (English-вариант из hkrpg.map)
Авто-сканирует все chapterN.csv в hsr-run-voice, добавляет колонку src (папка в output_ru).
"""
import os, csv, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

AW = config.AWWISE
sys.path.insert(0, AW)
from mapper import Mapper

# авто-скан chapterN.csv -> папка с wav в output_ru
SOURCES = []
for f in sorted(os.listdir(config.RUN)):
    m = re.match(r"chapter(\d+)\.csv$", f)
    if m:
        SOURCES.append((f, f"chapter{m.group(1)}"))

OUT = os.path.join(config.REPACK, "repack_list.csv")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

m = Mapper(os.path.join(AW, r"maps\hkrpg.map"))
print("Языки в карте:", m.languages)
en_idx = next(i for i, n in enumerate(m.languages) if "engl" in n.lower())
print(f"English = индекс {en_idx}")

cands = {}
if m.map_version == b"\x33\x32":
    for hid, (offset, lang) in m.keys.items():
        path = m.get_key(hid)
        if not path: continue
        p = (path[0].replace("/", "\\") + ".wem").lower()
        cands.setdefault(p, []).append((hid, lang))
else:
    for hid in m.keys:
        path = m.get_key(hid)
        if not path: continue
        p = (path[0].replace("/", "\\") + ".wem").lower()
        cands.setdefault(p, []).append((hid, (m.keys[hid] >> 22) & 0x03))

path2id = {}
for p, lst in cands.items():
    en = [h for h, l in lst if l == en_idx]
    path2id[p] = en[0] if en else lst[0][0]

rows, miss = [], 0
for csv_name, src in SOURCES:
    csv_path = os.path.join(config.RUN, csv_name)
    if not os.path.exists(csv_path):
        print(f"(нет {csv_name} — пропуск)")
        continue
    n0 = len(rows)
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"):
        fp = r["file"].replace("/", "\\")
        key = fp.split("\\", 1)[1].lower().replace(".wav", ".wem")
        wid = path2id.get(key)
        name = os.path.splitext(os.path.basename(fp))[0]
        if wid:
            rows.append({"pck": fp.split("\\")[0], "wem_id": wid, "name": name, "src": src})
        else:
            miss += 1
            print(f"  !! нет ID: {key}")
    print(f"{csv_name}: +{len(rows) - n0}")

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    wtr = csv.DictWriter(f, ["pck", "wem_id", "name", "src"], delimiter=";")
    wtr.writeheader(); wtr.writerows(rows)
print(f"Всего сопоставлено: {len(rows)}, без ID: {miss}")
print("->", OUT)