# -*- coding: utf-8 -*-
"""
02_unmapped_pitch.py — медианная высота голоса файлов из unmapped -> pitch.csv.
Нужна 01_unmapped.py, чтобы различить варианты _m/_f реплик с одинаковым английским текстом
(обычно это реплики самого Первопроходца): в паре файлов у мужского варианта голос ниже.
- работает ВНУТРИ образа CosyVoice (там есть librosa)
- резюмируемый: уже посчитанные файлы пропускаются

Обычно запускается из pipeline.py unmapped.
"""
import os, csv, argparse
import numpy as np
import librosa

ap = argparse.ArgumentParser()
ap.add_argument("--list", default="/work/list.csv")
ap.add_argument("--dataset", default="/data")
ap.add_argument("--out", default="/work/pitch.csv")
args = ap.parse_args()

done = set()
if os.path.exists(args.out):
    with open(args.out, encoding="utf-8-sig", newline="") as f:
        done = {r["file"] for r in csv.DictReader(f, delimiter=";")}
with open(args.list, encoding="utf-8-sig", newline="") as f:
    todo = [r["file"] for r in csv.DictReader(f, delimiter=";") if r["file"] not in done]
print(f"Высота голоса: уже посчитано {len(done)}, осталось {len(todo)}", flush=True)

new = not os.path.exists(args.out)
with open(args.out, "a", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f, delimiter=";")
    if new:
        wr.writerow(["file", "f0"])
    for i, rel in enumerate(todo, 1):
        try:
            y, sr = librosa.load(os.path.join(args.dataset, rel.replace("\\", "/")), sr=16000)
            f0 = librosa.yin(y, fmin=60, fmax=500, sr=sr)
            rms = librosa.feature.rms(y=y)[0][:len(f0)]
            voiced = f0[:len(rms)][rms > rms.max() * 0.1] if len(rms) else f0
            wr.writerow([rel, f"{float(np.median(voiced)):.1f}" if len(voiced) else ""])
        except Exception as e:
            wr.writerow([rel, ""])
        if i % 500 == 0 or i == len(todo):
            print(f"[{i}/{len(todo)}]", flush=True)
