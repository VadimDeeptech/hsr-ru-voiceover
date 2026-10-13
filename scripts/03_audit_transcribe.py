# -*- coding: utf-8 -*-
"""
03_audit_transcribe.py — распознаёт английскую речь в оригинальных wav (Whisper) -> asr.csv.
Нужен для сверки «что звучит» с «что написано в субтитре» (см. 04_audit_report.py).
- работает ВНУТРИ образа CosyVoice: там уже есть torch + whisper и доступ к GPU
- резюмируемый: уже распознанные файлы пропускаются, после обновления игры
  распознаются только новые
- ~0.7 с на файл (small.en); упирается в один поток CPU, поэтому полный прогон
  делится на части (--shard) и идёт несколькими контейнерами параллельно

Запуск в 3 потока (PowerShell, из корня проекта):
    0..2 | % { docker run -d --name "hsr-audit-$_" --gpus all `
      -v "${PWD}\\hsr-dataset:/data:ro" -v "${PWD}\\hsr-run-voice:/work" `
      -v "${PWD}\\scripts:/scripts:ro" -v "${PWD}\\hsr-run-voice\\whisper_cache:/root/.cache/whisper" `
      hsr-cosyvoice-cosyvoice python /scripts/03_audit_transcribe.py --shard "$_/3" }
    docker logs -f hsr-audit-0
Результат: hsr-run-voice\\asr\\asr_*.csv
"""
import os, csv, glob, time, argparse
import whisper

ap = argparse.ArgumentParser(description="Распознавание оригинальной озвучки для сверки с текстом")
ap.add_argument("--mapping", default="/work/mapping.csv")
ap.add_argument("--dataset", default="/data")
ap.add_argument("--out-dir", default="/work/asr")
ap.add_argument("--shard", default="0/1", help="K/N — эта часть из N (каждая пишет свой asr_K.csv)")
ap.add_argument("--model", default="small.en")
ap.add_argument("--limit", type=int, default=None, help="лимит файлов (для теста)")
args = ap.parse_args()

shard, nshards = map(int, args.shard.split("/"))
os.makedirs(args.out_dir, exist_ok=True)
out_path = os.path.join(args.out_dir, f"asr_{shard}.csv")

done = set()
for p in glob.glob(os.path.join(args.out_dir, "asr_*.csv")):
    with open(p, encoding="utf-8-sig", newline="") as f:
        done |= {r["file"] for r in csv.DictReader(f, delimiter=";")}

with open(args.mapping, encoding="utf-8-sig", newline="") as f:
    todo = [r["file"] for i, r in enumerate(csv.DictReader(f, delimiter=";"))
            if i % nshards == shard and r["file"] not in done]
if args.limit:
    todo = todo[:args.limit]
print(f"Уже распознано: {len(done)}, осталось: {len(todo)}", flush=True)
if not todo:
    raise SystemExit

model = whisper.load_model(args.model)
new = not os.path.exists(out_path)
t0 = time.time()
with open(out_path, "a", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f, delimiter=";")
    if new:
        wr.writerow(["file", "heard", "no_speech", "note"])
    for i, rel in enumerate(todo, 1):
        src = os.path.join(args.dataset, rel.replace("\\", "/"))
        try:
            res = model.transcribe(src, language="en", fp16=True)
            segs = res["segments"]
            # вероятность «это не речь»: высокая у пения, шума, вздохов
            ns = max((s["no_speech_prob"] for s in segs), default=1.0)
            wr.writerow([rel, " ".join(res["text"].split()), f"{ns:.2f}", ""])
        except Exception as e:
            wr.writerow([rel, "", "", f"EXC {str(e)[:150]}"])
        if i % 50 == 0 or i == len(todo):
            f.flush()
        if i % 500 == 0 or i == len(todo):
            el = time.time() - t0
            print(f"[{i}/{len(todo)}] {el / i:.2f} с/файл, осталось ~{(len(todo) - i) * el / i / 3600:.1f} ч", flush=True)
