# -*- coding: utf-8 -*-
"""
6_prepare_wwise.py — staging + externals.wsources под GENDER. Запускать для m и f.
wav ищется в output_ru\<src> (src — колонка из repack_list.csv).
Файлы с зашитым гендером (<name>_m/_f.wav) идут в ОБА репака как есть —
игра сама выбирает _m.wem/_f.wem по полу Первопроходца.
Требуется: проект hsr-wwise.wproj с ShareSet "Vorbis_RU" (Vorbis, SampleRate Auto), Wwise GUI закрыт.

Запуск: python 6_prepare_wwise.py --gender m|f
"""
import os, csv, shutil, argparse, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ap = argparse.ArgumentParser()
ap.add_argument("--gender", choices=["m", "f"], required=True)
args = ap.parse_args()
GENDER = args.gender

WPROJ     = config.WPROJ
REPACK    = config.REPACK
STAGE     = os.path.join(config.RUN, f"wwise_stage_{GENDER}")
WEM_OUT   = os.path.join(config.RUN, f"wem_out_{GENDER}")
WCONSOLE  = config.WWISE_CONSOLE
CONV_NAME = "Vorbis_RU"

os.makedirs(STAGE, exist_ok=True)
rows = list(csv.DictReader(open(os.path.join(REPACK, "repack_list.csv"), encoding="utf-8-sig"), delimiter=";"))

sources, missing, gender_files = [], 0, 0
for r in rows:
    name = r["name"]
    low = name.lower()
    wav_dir = os.path.join(config.RUN, "output_ru", r["src"])

    if low.endswith("_m") or low.endswith("_f"):
        # гендер зашит в имя: копируем как есть в оба репака
        wav = os.path.join(wav_dir, name + ".wav")
        gender_files += 1
    else:
        wav = os.path.join(wav_dir, f"{name}__{GENDER}.wav")
        if not os.path.exists(wav):
            wav = os.path.join(wav_dir, name + ".wav")

    if not os.path.exists(wav):
        missing += 1
        print(f"  !! нет wav: {name} (src={r['src']})")
        continue
    dst = os.path.join(STAGE, r["wem_id"] + ".wav")
    if not os.path.exists(dst):
        shutil.copy2(wav, dst)
    sources.append(r["wem_id"] + ".wav")

xml_path = os.path.join(config.RUN, f"externals_{GENDER}.wsources")
with open(xml_path, "w", encoding="utf-8") as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n')
    f.write(f'<ExternalSourcesList SchemaVersion="1" Root="{STAGE}">\n')
    for s in sources:
        f.write(f'  <Source Path="{s}" Conversion="{CONV_NAME}"/>\n')
    f.write('</ExternalSourcesList>\n')

print(f"Пол {GENDER}: staging {len(sources)} wav (из них гендерных _m/_f: {gender_files}), пропущено {missing}")
print("Команда конвертации (PowerShell):")
if WCONSOLE:
    print(f'& "{WCONSOLE}" convert-external-source "{WPROJ}" --source-file "{xml_path}" --platform Windows --output "{WEM_OUT}" --verbose')
else:
    print("WwiseConsole не найден. Укажи wwise_console в config.toml")