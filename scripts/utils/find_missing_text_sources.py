# -*- coding: utf-8 -*-
"""
find_missing_text_sources.py — диагностика: какие таблицы содержат текст для voiceid без текста.

Запуск:
    python scripts/utils/find_missing_text_sources.py           # только показать
    python scripts/utils/find_missing_text_sources.py --apply   # и дописать новые таблицы в extra_tables.csv

Показывает:
    - сколько voiceid без текста в mapping.csv
    - в каких таблицах ExcelOutput они встречаются
    - какие колонки содержат хэш текста
    - есть ли хэш в TextMap RU
"""
import os, json, csv, sys, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import texts

ap = argparse.ArgumentParser(description="Какие таблицы содержат текст для VoiceID без текста")
ap.add_argument("--apply", action="store_true", help="дописать надёжные новые таблицы в extra_tables.csv")
args = ap.parse_args()

EO = texts.EO
textmap = texts.textmap_ru()
# таблицы, которые utils\texts.py уже читает
KNOWN = {"TalkSentenceConfig.json", "VoiceAtlas.json", "TalkSentenceMultiVoice.json"} | {t[0] for t in texts.EXTRA_TABLES}

# mapping.csv -> voiceid без текста
mapping_path = os.path.join(config.RUN, "mapping.csv")
no_text_vids = set()
with open(mapping_path, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if not r["text_ru"].strip():
            no_text_vids.add(int(r["voiceid"]))

print(f"VoiceID без текста в mapping.csv: {len(no_text_vids)}")

# Сканируем все таблицы ExcelOutput
results = []
files = sorted(f for f in os.listdir(EO) if f.endswith(".json"))
for fname in files:
    p = os.path.join(EO, fname)
    try:
        data = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    if not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        continue

    keys = list(data[0].keys())
    # Ключи, которые могут содержать VoiceID — строго VoiceID или заканчивающиеся на VoiceID
    vid_keys = [k for k in keys if k == "VoiceID" or k.endswith("VoiceID") or k == "VoiceIDList"]
    # Ключи, которые могут содержать хэш текста
    hash_keys = [k for k in keys if any(x in k for x in ("Hash", "Text", "Content", "Sentence", "Talk", "Desc", "Name", "Title"))]

    if not vid_keys or not hash_keys:
        continue

    overlaps = 0
    hash_col = vid_col = None
    sample_hash = None
    sample_text = None

    for e in data:
        for vk in vid_keys:
            vid = e.get(vk)
            # vid может быть int, str или list (VoiceIDList)
            if isinstance(vid, list):
                vid_list = vid
            else:
                vid_list = [vid]
            for v in vid_list:
                if v in no_text_vids:
                    overlaps += 1
                    # Ищем первый непустой хэш
                    for hk in hash_keys:
                        h = e.get(hk)
                        if isinstance(h, dict):
                            h = h.get("Hash")
                        if h:
                            hash_col, vid_col = hk, vk
                            sample_hash = str(h)
                            sample_text = textmap.get(sample_hash, "")
                            break
                    break

    if overlaps > 0:
        results.append((fname, overlaps, hash_col, sample_text[:50] if sample_text else "", vid_col))

print(f"\nНайдено таблиц с совпадениями: {len(results)}")
print(f"{'Таблица':<40} {'Совпадений':>10} {'Хэш-колонка':<20} {'Текст в RU':>10}")
print("-" * 90)
for fname, overlaps, hash_col, sample, _ in sorted(results, key=lambda x: -x[1]):
    print(f"{fname:<40} {overlaps:>10} {hash_col or '':<20} {sample:>10}")

# Кандидаты в extra_tables.csv. Добавляются только надёжные: одна колонка VoiceID (не список),
# у примера есть русский текст, колонка текста — не название/заголовок (Name, Title):
# чужая таблица дала бы в озвучку не тот текст
new, manual = [], []
for f, n, hk, sample, vk in results:
    if n <= 10 or not hk or f in KNOWN:
        continue
    safe = vk != "VoiceIDList" and sample and not any(x in hk for x in ("Name", "Title"))
    (new if safe else manual).append((f, vk, hk, sample))

print("\nРекомендация:")
if not new and not manual:
    print(f"Новых таблиц нет: все найденные уже читаются ({texts.EXTRA_CSV}).")
for f, vk, hk, sample in new:
    print(f"  + {f}: {vk} -> {hk}, пример: «{sample}»")
for f, vk, hk, sample in manual:
    print(f"  ? {f}: {vk} -> {hk}, пример: «{sample}» — проверь вручную, автоматически не добавляется")
if new:
    if args.apply:
        with open(texts.EXTRA_CSV, "rb") as f:
            ends_nl = f.read().endswith(b"\n")
        with open(texts.EXTRA_CSV, "a", encoding="utf-8", newline="") as f:
            if not ends_nl:
                f.write("\r\n")   # файл правили руками и не закончили строку
            wr = csv.writer(f, delimiter=";")
            for t, vk, hk, sample in new:
                wr.writerow([t, vk, hk, f"find-missing-text {datetime.date.today()}: «{sample}»"])
        print(f"Добавлено в {texts.EXTRA_CSV}: {len(new)}. Дальше: python pipeline.py map")
    else:
        print(f"Отмеченные + добавит в {texts.EXTRA_CSV} запуск с --apply "
              f"(python pipeline.py utils find-missing-text --apply)")
