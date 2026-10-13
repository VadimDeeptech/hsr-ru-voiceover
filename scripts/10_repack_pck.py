# -*- coding: utf-8 -*-
"""
10_repack_pck.py — сборка мода под GENDER -> pck_out_<GENDER>\.
База = pck_backup_en, если есть (гарантия чистого исходника), иначе папка игры.
Патч: wem дописывается в конец pck (выравнивание 16), в записи обновляются size/offset.

Запуск: python 10_repack_pck.py --gender m|f
"""
import os, csv, struct, shutil, argparse, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ap = argparse.ArgumentParser()
ap.add_argument("--gender", choices=["m", "f"], required=True)
args = ap.parse_args()
GENDER = args.gender

GAME   = config.GAME_AUDIO
BACKUP = config.PCK_BACKUP
REPACK = config.REPACK
WEMDIR = os.path.join(REPACK, GENDER)
OUTDIR = os.path.join(config.RUN, f"pck_out_{GENDER}")
SRCDIR = BACKUP if os.path.isdir(BACKUP) else GAME

if not SRCDIR or not os.path.isdir(SRCDIR):
    print(f"Источник оригиналов не найден: {SRCDIR}")
    print("Укажи game_dir в config.toml или сделай бэкап pck_backup_en.")
    sys.exit(1)

os.makedirs(OUTDIR, exist_ok=True)
print(f"Источник оригиналов: {SRCDIR}")

id2pck = {r["wem_id"].lower(): r["pck"] for r in csv.DictReader(
    open(os.path.join(REPACK, "id_to_pck.csv"), encoding="utf-8-sig"), delimiter=";")}

groups = {}
for r in csv.DictReader(open(os.path.join(REPACK, "repack_list.csv"), encoding="utf-8-sig"), delimiter=";"):
    wid = r["wem_id"].lower()
    if os.path.exists(os.path.join(WEMDIR, wid + ".wem")) and wid in id2pck:
        groups.setdefault(id2pck[wid], []).append(wid)

total = 0
for pck_name, wids in groups.items():
    dst = os.path.join(OUTDIR, pck_name)
    shutil.copy2(os.path.join(SRCDIR, pck_name), dst)
    data = bytearray(open(dst, "rb").read())
    lang, banks, sounds = struct.unpack_from("<III", data, 12)
    ext = struct.unpack_from("<I", data, 24)[0]
    pos = 28 + lang + banks + sounds
    n   = struct.unpack_from("<I", data, pos)[0]
    table = {}
    for i in range(n):
        e = pos + 4 + i * 24
        id2, id1 = struct.unpack_from("<II", data, e)
        table[f"{id1:08x}{id2:08x}"] = e
    rep = 0
    for wid in wids:
        e = table.get(wid)
        if e is None:
            print(f"  !! нет в таблице {pck_name}: {wid}"); continue
        wem = open(os.path.join(WEMDIR, wid + ".wem"), "rb").read()
        data += b"\x00" * ((-len(data)) % 16)
        struct.pack_into("<I", data, e + 12, len(wem))
        struct.pack_into("<I", data, e + 16, len(data))
        data += wem
        rep += 1
    open(dst, "wb").write(data)
    total += rep
    print(f"{pck_name}: {rep}/{len(wids)}")
print(f"\nПол {GENDER}: заменено {total} -> {OUTDIR}")