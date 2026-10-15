# -*- coding: utf-8 -*-
"""09_find_pck.py — сканирует таблицы externals всех pck игры -> id_to_pck.csv"""
import os, csv, struct, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

GAME   = config.GAME_AUDIO
REPACK = config.REPACK
OUT    = os.path.join(REPACK, "id_to_pck.csv")

if not GAME or not os.path.isdir(GAME):
    print(f"Папка с игрой не найдена: {GAME}")
    print("Укажи game_dir в config.toml или положи игру в стандартное место.")
    sys.exit(1)

ids = {r["wem_id"].lower() for r in csv.DictReader(
    open(os.path.join(REPACK, "repack_list.csv"), encoding="utf-8-sig"), delimiter=";")}
print(f"Целевых ID: {len(ids)}")

result = {}
pcks = [f for f in os.listdir(GAME) if f.lower().endswith(".pck")]
for i, pck in enumerate(sorted(pcks), 1):
    data = open(os.path.join(GAME, pck), "rb").read()
    lang, banks, sounds = struct.unpack_from("<III", data, 12)
    ext = struct.unpack_from("<I", data, 24)[0]
    if ext == 0: continue
    pos = 28 + lang + banks + sounds
    n   = struct.unpack_from("<I", data, pos)[0]
    for j in range(n):
        id2, id1 = struct.unpack_from("<II", data, pos + 4 + j * 24)
        hexid = f"{id1:08x}{id2:08x}"
        if hexid in ids:
            result[hexid] = pck
    if i % 20 == 0: print(f"  [{i}/{len(pcks)}] найдено {len(result)}")

with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["wem_id", "pck"])
    for k, v in sorted(result.items()): w.writerow([k, v])

missing = ids - set(result)
print(f"\nИтого: {len(result)}/{len(ids)} найдено")
if missing: print(f"Не найдено: {len(missing)}: {sorted(missing)[:5]}")
print("->", OUT)