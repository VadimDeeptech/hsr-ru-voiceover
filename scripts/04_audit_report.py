# -*- coding: utf-8 -*-
"""
04_audit_report.py — сверка «что звучит в оригинале» (asr\\asr_*.csv) с английским субтитром
(mapping.csv). Ничего не исправляет: пишет audit_report.csv и останавливает пайплайн,
если есть неразобранные расхождения.

Виды расхождений:
    нет речи       — в записи не распознано слов, а текст есть (пение, шум, вздохи)
    звука больше   — в записи заметно больше слов, чем в тексте (текст разбит на несколько строк?)
    текст не тот   — слова в записи не похожи на субтитр

Расхождение считается разобранным, если:
    - для записи есть решение в audit_decisions.csv (см. utilsdecisions.py), или
    - оно попадает под правило автоприёма (AUTO_ACCEPT ниже), или
    - текст записи взят из ненадёжного источника (decisions.UNSURE_SOURCES): такие записи
      без подтверждения распознаванием не озвучиваются — список пишется в audit_auto.csv.
Остальные — «НЕ РАЗОБРАНО»: код возврата 2, генерация не начинается.

Запуск: python 04_audit_report.py            (после 03_audit_transcribe.py; можно во время прогона)
"""
import os, csv, re, sys, glob, difflib, argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import decisions

MIN_SIM = 0.5    # похожесть слов записи и субтитра; ниже — «текст не тот»

# Автоприём: фоновые разговоры, где английская озвучка перефразирует субтитр.
# (префикс voicepath, вид расхождения, минимальная похожесть)
# ПРЕДВАРИТЕЛЬНО — пороги уточняются по полному прогону.
AUTO_ACCEPT = [
    ("vo_ambient", "текст не тот", 0.30),
]

ap = argparse.ArgumentParser(description="Отчёт о расхождениях звука и текста")
ap.add_argument("--no-gate", action="store_true", help="только отчёт, код возврата всегда 0")
args = ap.parse_args()

TAGS = re.compile(r"\{[^}]*\}|</?[^>]+>")

def words(s):
    return re.sub(r"[^a-z0-9' ]", " ", TAGS.sub(" ", s).lower()).split()

asr = {}
for p in glob.glob(os.path.join(config.RUN, "asr", "asr_*.csv")):
    with open(p, encoding="utf-8-sig", newline="") as f:
        asr.update((r["file"], r) for r in csv.DictReader(f, delimiter=";"))
if not asr:
    print("Нет результатов распознавания. Сначала запусти: python pipeline.py audit")
    sys.exit(1)

DEC = decisions.load(auto=False)
rows, stats, by_cat = [], Counter(), Counter()
auto_keep = []   # (voicepath, причина) -> audit_auto.csv
with open(os.path.join(config.RUN, "mapping.csv"), encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f, delimiter=";"):
        # ненадёжный источник текста: без подтверждения распознаванием не озвучиваем
        unsure = (r.get("text_source") in decisions.UNSURE_SOURCES and r["text_ru"].strip()
                  and not decisions.find(DEC, r["voicepath"]))
        a = asr.get(r["file"])
        if not a or a["note"]:
            stats["ещё не распознано" if not a else "ошибка распознавания"] += 1
            if unsure:
                auto_keep.append((r["voicepath"], f"{r['text_source']}: не распознано"))
            continue
        text, heard = words(r["text_en"]), words(a["heard"])
        if not text or not r["text_ru"].strip():
            stats["нечего сверять (нет текста или слов в нём)"] += 1
            continue
        sim = difflib.SequenceMatcher(None, heard, text).ratio()
        # насколько начало записи совпадает с текстом: высоко, если текст — лишь первая часть звука
        head = difflib.SequenceMatcher(None, heard[:len(text)], text).ratio()
        if not heard:
            kind = "нет речи"
        elif len(heard) > 1.6 * len(text) + 3 and head >= MIN_SIM:
            kind = "звука больше"
        elif sim < MIN_SIM:
            kind = "текст не тот"
        else:
            stats["совпадает"] += 1
            continue

        dec = decisions.find(DEC, r["voicepath"])
        if dec:
            status = f"решение: {dec[0]}"
        elif unsure:
            status = "оригинал: источник текста"
            auto_keep.append((r["voicepath"], f"{r['text_source']}: {kind}, похожесть {sim:.2f}"))
        elif any(r["voicepath"].startswith(p) and kind == k and sim >= s for p, k, s in AUTO_ACCEPT):
            status = "принято правилом"
        else:
            status = "НЕ РАЗОБРАНО"
        stats[f"{kind} — {status}"] += 1
        parts = r["file"].split("\\")
        cat = parts[2] if len(parts) > 2 else ""
        if status == "НЕ РАЗОБРАНО":
            by_cat[(kind, cat)] += 1
        rows.append([status, kind, f"{sim:.2f}", len(heard), len(text), cat, r["voicepath"],
                     a["heard"], r["text_en"], r["text_ru"], r["file"]])

# неразобранные — первыми
rows.sort(key=lambda x: (x[0] != "НЕ РАЗОБРАНО", x[1], float(x[2])))
out = os.path.join(config.RUN, "audit_report.csv")
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f, delimiter=";")
    wr.writerow(["status", "kind", "similarity", "words_heard", "words_text", "category", "voicepath",
                 "heard", "text_en", "text_ru", "file"])
    wr.writerows(rows)

with open(decisions.AUTO_PATH, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f, delimiter=";")
    wr.writerow(["voicepath", "action", "lines", "comment"])
    wr.writerows([vp, "keep", "", why] for vp, why in auto_keep)

for k, n in sorted(stats.items(), key=lambda x: -x[1]):
    print(f"{k}: {n}")
if auto_keep:
    print(f"Текст из ненадёжного источника не подтверждён — остаётся оригинал: {len(auto_keep)} "
          f"({decisions.AUTO_PATH}; чтобы озвучить, впиши accept в {decisions.PATH})")
unresolved = sum(1 for r in rows if r[0] == "НЕ РАЗОБРАНО")
print("->", out)
if unresolved:
    print(f"\nНе разобрано расхождений: {unresolved}. По категориям:")
    for (kind, cat), n in sorted(by_cat.items(), key=lambda x: (x[0][0], -x[1]))[:30]:
        print(f"  {kind:13} {cat:18} {n}")
    print(f"\nОткрой {out} (неразобранные идут первыми) и впиши решения в {decisions.PATH}:")
    print("  accept — озвучивать текст как есть; join/next N — приклеить следующие N строк;")
    print("  keep — оставить в игре оригинал. Затем запусти ту же команду пайплайна снова.")
    if not args.no_gate:
        sys.exit(2)
else:
    print("\nНеразобранных расхождений нет.")
