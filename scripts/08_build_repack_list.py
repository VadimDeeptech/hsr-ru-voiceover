# -*- coding: utf-8 -*-
"""
08_build_repack_list.py — repack_list.csv: file name -> wem_id (English-вариант из hkrpg.map)
Авто-сканирует все *.csv в hsr-run-voice (chapterN, sideN, companionN, vo, ambient, archive, ...),
добавляет колонку src (папка в output_ru).
Записи из unmapped (01_unmapped.py): wem_id — имя настоящего файла (колонка src в csv);
копии уже озвученных строк (alias в match.csv) получают ту же озвучку под своим wem_id.
"""
import os, csv, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import decisions

AW = config.AWWISE
sys.path.insert(0, AW)
from mapper import Mapper

DECISIONS = decisions.load()
HEX_ID = re.compile(r"^[0-9a-f]{16}\.wav$", re.I)   # имя файла из unmapped = wem_id

# авто-скан *.csv -> папка с wav в output_ru: chapterN.csv -> chapterN, side0.csv -> side0, ...
SOURCES = [(f, f[:-4]) for f in config.category_csvs()]

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

rows, miss, kept = [], 0, 0
for csv_name, src in SOURCES:
    csv_path = os.path.join(config.RUN, csv_name)
    if not os.path.exists(csv_path):
        print(f"(нет {csv_name} — пропуск)")
        continue
    n0 = len(rows)
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"):
        fp = r["file"].replace("/", "\\")
        key = fp.split("\\", 1)[1].lower().replace(".wav", ".wem")
        if HEX_ID.match(os.path.basename(r.get("src") or "")):
            # путь file виртуальный: слот — сам файл из unmapped, а не запись карты с тем же путём
            wid = os.path.splitext(os.path.basename(r["src"]))[0].lower()
        else:
            wid = path2id.get(key)
        name = os.path.splitext(os.path.basename(fp))[0]
        if (decisions.find(DECISIONS, name) or ("",))[0] == "keep":
            # в игре остаётся оригинал — даже если wav уже был сгенерирован раньше
            kept += 1
            continue
        if wid:
            rows.append({"pck": fp.split("\\")[0], "wem_id": wid, "name": name, "src": src})
        else:
            miss += 1
            print(f"  !! нет ID: {key}")
    print(f"{csv_name}: +{len(rows) - n0}")

# копии строк из unmapped: та же озвучка под другим wem_id
aliases = 0
match_csv = os.path.join(config.UNMAPPED, "match.csv")
if os.path.exists(match_csv):
    by_name = {r["name"].lower(): r for r in rows}
    ids = {r["wem_id"] for r in rows}
    for a in csv.DictReader(open(match_csv, encoding="utf-8-sig"), delimiter=";"):
        base = by_name.get(a["stem"].lower())
        wid = os.path.splitext(os.path.basename(a["src"]))[0].lower()
        if a["status"] != "alias" or not base or wid in ids or not HEX_ID.match(os.path.basename(a["src"])):
            continue
        rows.append({"pck": a["src"].split("\\")[0], "wem_id": wid, "name": base["name"], "src": base["src"]})
        ids.add(wid); aliases += 1
    print(f"Копии строк из unmapped: +{aliases}")

with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
    wtr = csv.DictWriter(f, ["pck", "wem_id", "name", "src"], delimiter=";")
    wtr.writeheader(); wtr.writerows(rows)
print(f"Всего сопоставлено: {len(rows)}, без ID: {miss}, оставлен оригинал по решению: {kept}")
print("->", OUT)