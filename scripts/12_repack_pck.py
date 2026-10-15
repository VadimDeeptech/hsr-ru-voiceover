# -*- coding: utf-8 -*-
"""
12_repack_pck.py — сборка мода под GENDER -> pck_out_<GENDER>\.
База для каждого pck = pck_backup_en, пока в игре стоит наш мод (по манифесту installed.csv),
иначе папка игры: там оригинал — мод не ставился либо игра заменила файл при обновлении.
Патч: wem дописывается в конец pck (выравнивание 16), в записи обновляются size/offset.

Запуск: python 12_repack_pck.py --gender m|f
"""
import os, csv, struct, argparse, sys

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

# манифест установки (пишет 13_install.ps1): какие файлы в игре положили мы сами
installed = {}
if os.path.isfile(os.path.join(BACKUP, "installed.csv")):
    with open(os.path.join(BACKUP, "installed.csv"), encoding="utf-8-sig", newline="") as f:
        installed = {r["name"].lower(): r for r in csv.DictReader(f, delimiter=";")}

stats = {"backup": 0, "game": 0, "updated": 0, "untracked": 0}


def mod_in_game(pck_name):
    """В игре сейчас лежит pck нашего мода (а не оригинал и не файл после обновления игры)."""
    e = installed.get(pck_name.lower())
    p = os.path.join(GAME, pck_name) if GAME else ""
    if not e or e["state"] != "mod" or not os.path.isfile(p):
        return False
    st = os.stat(p)
    return st.st_size == int(e["size"]) and abs(int(st.st_mtime) - int(e["mtime"])) <= 1


def source_pck(pck_name):
    """Чистый оригинал pck. Бэкап нужен, только пока в игре стоит наш мод:
    если игра заменила файл (обновление), оригинал — в игре, а бэкап устарел."""
    game = os.path.join(GAME, pck_name) if GAME else ""
    bak = os.path.join(BACKUP, pck_name)
    has_bak = os.path.isfile(bak)
    if mod_in_game(pck_name):
        if not has_bak:
            print(f"  !! {pck_name}: в игре стоит мод, а оригинала в бэкапе нет — "
                  f"восстанови файлы игры в лаунчере")
            return None
        stats["backup"] += 1
        return bak
    if has_bak and pck_name.lower() not in installed:
        # бэкап сделан до появления манифеста: проверить нечем, верим ему как раньше
        stats["untracked"] += 1
        return bak
    if os.path.isfile(game):
        # запись mod, а файл в игре другой — его заменила игра
        replaced = has_bak and installed[pck_name.lower()]["state"] == "mod"
        stats["updated" if replaced else "game"] += 1
        return game
    return bak if has_bak else None

if not (GAME and os.path.isdir(GAME)) and not os.path.isdir(BACKUP):
    print(f"Источник оригиналов не найден: ни {BACKUP}, ни папка игры ({GAME})")
    print("Укажи game_dir в config.toml или сделай бэкап pck_backup_en.")
    sys.exit(1)

os.makedirs(OUTDIR, exist_ok=True)
print(f"Источники оригиналов: {BACKUP} -> {GAME}")

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
    src = source_pck(pck_name)
    if not src:
        print(f"  !! нет оригинала {pck_name} — пропуск")
        if os.path.exists(dst):
            # pck от прошлой сборки install поставил бы как свежий
            os.remove(dst)
        continue
    with open(src, "rb") as f:
        data = bytearray(f.read())
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
    with open(dst, "wb") as f:
        f.write(data)
    total += rep
    print(f"{pck_name}: {rep}/{len(wids)}")
print(f"\nПол {GENDER}: заменено {total} -> {OUTDIR}")
print(f"Оригиналы pck: из игры {stats['game'] + stats['updated']}, из бэкапа {stats['backup'] + stats['untracked']}")
if stats["updated"]:
    print(f"  игра заменила {stats['updated']} pck после установки мода (обновление) — взяты из игры, "
          f"бэкап обновится при install")
if stats["untracked"]:
    print(f"  !! {stats['untracked']} pck взяты из бэкапа, сделанного до появления манифеста установки.")
    print(f"     Если игра с тех пор обновлялась — восстанови файлы в лаунчере и удали {BACKUP}")