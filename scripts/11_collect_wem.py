# -*- coding: utf-8 -*-
"""11_collect_wem.py — сбор wem после конвертации -> repack\\<GENDER>\\

repack\\<GENDER> синхронизируется со списком externals_<GENDER>.wsources (шаг 10): в нём ровно
те реплики, у которых сейчас есть wav. wem остальных удаляются — иначе 12_repack_pck.py и
14_package.py взяли бы старую озвучку реплик, wav которых 07_generate.py удалил
(например, у реплики пропал текст, и в игре должен остаться оригинал).

Запуск: python 11_collect_wem.py --gender m|f
"""
import os, re, glob, shutil, argparse, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ap = argparse.ArgumentParser()
ap.add_argument("--gender", choices=["m", "f"], required=True)
args = ap.parse_args()
GENDER = args.gender

WPDIR  = os.path.join(config.RUN, f"wem_out_{GENDER}")
DST    = os.path.join(config.REPACK, GENDER)
XML    = os.path.join(config.RUN, f"externals_{GENDER}.wsources")

if not os.path.isfile(XML):
    sys.exit(f"!! нет {XML} — сначала шаг 10: python pipeline.py wwise --gender {GENDER}")
with open(XML, encoding="utf-8") as f:
    wanted = {m.lower() for m in re.findall(r'<Source Path="([^"]+)\.wav"', f.read())}

os.makedirs(DST, exist_ok=True)
found = 0
for wem in glob.glob(os.path.join(WPDIR, "**", "*.wem"), recursive=True):
    wid = os.path.basename(wem)[:-4].lower()
    if wid not in wanted:
        continue
    dst = os.path.join(DST, os.path.basename(wem))
    found += 1
    if os.path.exists(dst):
        if os.path.samefile(wem, dst):
            continue
        os.remove(dst)
    # жёсткая ссылка вместо копии: wem не лежит на диске дважды
    try:
        os.link(wem, dst)
    except OSError:
        shutil.copy2(wem, dst)

removed = 0
for f in os.listdir(DST):
    if f.lower().endswith(".wem") and f[:-4].lower() not in wanted:
        os.remove(os.path.join(DST, f))
        removed += 1

print(f"Пол {GENDER}: собрано {found} wem -> {DST}")
if removed:
    print(f"  удалено {removed} wem реплик, которых нет в {os.path.basename(XML)} (нет wav — в игре остаётся оригинал)")
if found < len(wanted):
    print(f"  !! нет wem для {len(wanted) - found} из {len(wanted)} wav: конвертация WwiseConsole не прошла?")
