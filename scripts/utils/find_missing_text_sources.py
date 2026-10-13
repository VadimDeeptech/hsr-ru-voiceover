# -*- coding: utf-8 -*-
"""
find_missing_text_sources.py — диагностика: какие таблицы содержат текст для voiceid без текста.

Запуск:
    python scripts/utils/find_missing_text_sources.py

Показывает:
    - сколько voiceid без текста в mapping.csv
    - в каких таблицах ExcelOutput они встречаются
    - какие колонки содержат хэш текста
    - есть ли хэш в TextMap RU
"""
import os, json, csv, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

EO = os.path.join(config.GAMEDATA, "ExcelOutput")
TM = os.path.join(config.GAMEDATA, "TextMap")

# TextMap RU
textmap = {}
for name in ("TextMapRU_0.json", "TextMapRU_1.json", "TextMapMainRU.json"):
    p = os.path.join(TM, name)
    if os.path.exists(p):
        for k, v in json.load(open(p, encoding="utf-8")).items():
            textmap.setdefault(k, v)

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
    hash_col = None
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
                            hash_col = hk
                            sample_hash = str(h)
                            sample_text = textmap.get(sample_hash, "")
                            break
                    break

    if overlaps > 0:
        in_textmap = "ДА" if sample_text else "нет"
        results.append((fname, overlaps, hash_col, sample_text[:50] if sample_text else ""))

print(f"\nНайдено таблиц с совпадениями: {len(results)}")
print(f"{'Таблица':<40} {'Совпадений':>10} {'Хэш-колонка':<20} {'Текст в RU':>10}")
print("-" * 90)
for fname, overlaps, hash_col, sample in sorted(results, key=lambda x: -x[1]):
    print(f"{fname:<40} {overlaps:>10} {hash_col or '':<20} {sample:>10}")

print("\nРекомендация:")
print("Добавь в 01_mapper.py строки вида:")
for fname, overlaps, hash_col, _ in results:
    if overlaps > 10 and hash_col:
        if fname == "TalkSentenceMultiVoice.json":
            # Особый случай: TalkSentenceID -> VoiceIDList -> hash из TalkSentenceConfig
            print(f'    # {fname}: обрабатывается отдельно через sent_hash (уже в коде)')
        else:
            # Угадываем vid_key по имени файла
            vid_key = "VoiceID"  # чаще всего
            print(f'    load_extra("{fname}", "{vid_key}", "{hash_col}")')
