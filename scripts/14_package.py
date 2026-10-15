# -*- coding: utf-8 -*-
"""
14_package.py — пакет озвучки для игрока -> dist\\HSR-RU-Voiceover-<версия>\\ (и .zip с --zip).

В пакете только наши wem и установщик (installer\\), pck игры в нём нет: установщик патчит
pck самого игрока так же, как 12_repack_pck.py (дописывает wem в конец, правит записи).
Выборка — как в 12: строки repack_list.csv, у которых есть wem в repack\\<пол> и pck в id_to_pck.csv.
wem, побайтно одинаковые в m и f, идут в common.bin; различающиеся — в m.bin / f.bin.
Порядок строк index.csv = порядок repack_list.csv: в нём 12 дописывает wem, от него зависит
побайтное совпадение pck.

Запуск: python 14_package.py [--genders m,f] [--version X] [--zip] [--out DIR]
        [--repack DIR] [--pck NAME ...] [--no-build]
"""
import os, csv, sys, shutil, hashlib, argparse, subprocess, zipfile, filecmp, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

INSTALLER = os.path.join(config.ROOT, "installer")
CSPROJ = os.path.join(INSTALLER, "HSR-RU-Voiceover.csproj")
EXE = os.path.join(INSTALLER, "bin", "Release", "net48", "HSR-RU-Voiceover.exe")
FORMAT = 1

ap = argparse.ArgumentParser()
ap.add_argument("--genders", default="m,f", help="какие полы класть в пакет (по умолчанию m,f)")
ap.add_argument("--version", help="версия пакета (по умолчанию — <Version> из installer\\HSR-RU-Voiceover.csproj)")
ap.add_argument("--zip", action="store_true", help="упаковать в zip (без сжатия: Vorbis не сжимается)")
ap.add_argument("--out", default=os.path.join(config.ROOT, "dist"))
ap.add_argument("--repack", default=config.REPACK, help="папка с repack_list.csv, id_to_pck.csv и <пол>\\*.wem")
ap.add_argument("--pck", action="append", help="только эти pck (для тестов)")
ap.add_argument("--no-build", action="store_true", help="не собирать установщик, взять готовый exe")
args = ap.parse_args()

genders = [g.strip() for g in args.genders.split(",") if g.strip()]
if not genders or any(g not in ("m", "f") for g in genders):
    sys.exit("--genders: m, f или m,f")
version = args.version or re.search(r"<Version>([^<]+)</Version>", open(CSPROJ, encoding="utf-8").read()).group(1)

# ---- установщик ----
if not args.no_build:
    print(">>> dotnet build installer (Release)")
    rc = subprocess.call(["dotnet", "build", CSPROJ, "-c", "Release", "-nologo", "-v", "q"])
    if rc != 0:
        sys.exit(f"!! сборка установщика завершилась с кодом {rc}")
if not os.path.isfile(EXE):
    sys.exit(f"!! нет {EXE} — собери установщик (dotnet build installer -c Release)")

# ---- выборка, как в 12_repack_pck.py ----
id2pck = {r["wem_id"].lower(): r["pck"] for r in csv.DictReader(
    open(os.path.join(args.repack, "id_to_pck.csv"), encoding="utf-8-sig"), delimiter=";")}
only = {p.lower() for p in args.pck} if args.pck else None
wemdir = {g: os.path.join(args.repack, g) for g in genders}
for g, d in wemdir.items():
    if not os.path.isdir(d):
        sys.exit(f"!! нет {d}: сначала собери пол {g} (pipeline.py wwise/collect --gender {g})")

rows = []   # (pck, wem_id, {пол: путь к wem})
for r in csv.DictReader(open(os.path.join(args.repack, "repack_list.csv"), encoding="utf-8-sig"), delimiter=";"):
    wid = r["wem_id"].lower()
    pck = id2pck.get(wid)
    if not pck or (only and pck.lower() not in only):
        continue
    have = {g: os.path.join(wemdir[g], wid + ".wem") for g in genders}
    have = {g: p for g, p in have.items() if os.path.exists(p)}
    if have:
        rows.append((pck, wid, have))
if not rows:
    sys.exit("!! Нечего упаковывать: нет ни одного wem из repack_list.csv")

# ---- общие и различающиеся по полу ----
plan = []   # (pck, wem_id, вариант, путь)
diff = only_one = 0
if len(genders) == 2:
    print(f"Сравнение wem m и f: {len(rows)} реплик")
for k, (pck, wid, have) in enumerate(rows, 1):
    if len(genders) == 2 and k % 10000 == 0:
        print(f"  сравнено {k}/{len(rows)}")
    if len(genders) == 1:
        plan.append((pck, wid, "common", have[genders[0]]))
    elif len(have) == 2 and (os.path.samefile(have["m"], have["f"]) or filecmp.cmp(have["m"], have["f"], shallow=False)):
        plan.append((pck, wid, "common", have["m"]))
    else:
        if len(have) == 2:
            diff += 1
        else:
            only_one += 1
        for g in genders:
            if g in have:
                plan.append((pck, wid, g, have[g]))

# ---- запись пакета ----
name = f"HSR-RU-Voiceover-{version}"
out = os.path.abspath(os.path.join(args.out, name))
if os.path.exists(out):
    shutil.rmtree(out)
data = os.path.join(out, "data")
os.makedirs(data)

blobs = {}
for v in ("common", "m", "f"):
    items = [p for p in plan if p[2] == v]
    if not items:
        continue
    sha, off = hashlib.sha256(), 0
    with open(os.path.join(data, v + ".bin"), "wb") as f:
        for i, (_, wid, _, path) in enumerate(items):
            b = open(path, "rb").read()
            f.write(b)
            sha.update(b)
            off += len(b)
            if (i + 1) % 5000 == 0:
                print(f"  {v}.bin: {i + 1}/{len(items)}")
    blobs[v] = (off, sha.hexdigest())

offsets = {v: 0 for v in blobs}
with open(os.path.join(data, "index.csv"), "w", encoding="utf-8", newline="") as f:
    f.write("pck;wem_id;variant;offset;size\n")
    for pck, wid, v, path in plan:
        size = os.path.getsize(path)
        f.write(f"{pck};{wid};{v};{offsets[v]};{size}\n")
        offsets[v] += size

with open(os.path.join(data, "package.txt"), "w", encoding="utf-8", newline="\n") as f:
    f.write(f"format={FORMAT}\nversion={version}\ngenders={','.join(genders)}\n")
    for v, (size, h) in blobs.items():
        f.write(f"blob={v}.bin;{size};{h}\n")

shutil.copy2(EXE, out)
cfg = EXE + ".config"
if os.path.isfile(cfg):
    shutil.copy2(cfg, out)
shutil.copy2(os.path.join(INSTALLER, "README.txt"), out)
shutil.copy2(os.path.join(config.ROOT, "LICENSE"), os.path.join(out, "LICENSE.txt"))

pcks = len({p[0] for p in plan})
print(f"\nПакет {name}: {pcks} pck, реплик {len(rows)}, полы: {','.join(genders)}")
for v, (size, _) in blobs.items():
    print(f"  {v}.bin: {sum(1 for p in plan if p[2] == v)} wem, {size / 2**20:.1f} МБ")
if len(genders) == 2:
    print(f"  различаются в m и f: {diff}, есть только в одном поле: {only_one}")
print(f"-> {out}")

if args.zip:
    zpath = out + ".zip"
    print(f">>> zip -> {zpath}")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for base, _, files in os.walk(out):
            for fn in files:
                p = os.path.join(base, fn)
                z.write(p, os.path.join(name, os.path.relpath(p, out)))
    print(f"   {os.path.getsize(zpath) / 2**30:.2f} ГБ")
