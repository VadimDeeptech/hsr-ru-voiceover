# -*- coding: utf-8 -*-
"""09_collect_wem.py — сбор wem после конвертации -> repack\<GENDER>\

Запуск: python 09_collect_wem.py --gender m|f
"""
import os, glob, shutil, argparse, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ap = argparse.ArgumentParser()
ap.add_argument("--gender", choices=["m", "f"], required=True)
args = ap.parse_args()
GENDER = args.gender

WPDIR  = os.path.join(config.RUN, f"wem_out_{GENDER}")
DST    = os.path.join(config.REPACK, GENDER)

os.makedirs(DST, exist_ok=True)
found = 0
for wem in glob.glob(os.path.join(WPDIR, "**", "*.wem"), recursive=True):
    shutil.copy2(wem, os.path.join(DST, os.path.basename(wem)))
    found += 1
print(f"Пол {GENDER}: собрано {found} wem -> {DST}")
