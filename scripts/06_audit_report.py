# -*- coding: utf-8 -*-
"""
06_audit_report.py — сверка «что звучит в оригинале» (hsr-generate\\audit\\asr\\asr_*.csv)
с английским субтитром (mapping.csv). Ничего не исправляет: пишет hsr-generate\\audit\\audit_report.csv
и останавливает пайплайн,
если есть неразобранные расхождения.

Виды расхождений:
    нет речи       — в записи не распознано слов, а текст есть (пение, шум, вздохи)
    звука больше   — в записи заметно больше слов, чем в тексте (текст разбит на несколько строк?)
    текст не тот   — слова в записи не похожи на субтитр

Расхождение считается разобранным, если:
    - для записи есть решение в audit_decisions.csv (см. utils\\decisions.py), или
    - текст записи взят из ненадёжного источника (decisions.UNSURE_SOURCES): такие записи
      без подтверждения распознаванием не озвучиваются, или
    - оно попадает под правило:
        нет речи, текст не тот с похожестью < KEEP_BELOW — оставить оригинал (существа, говорящие
            звуками; пересказ в английской записи; приветствия NPC; короткие возгласы)
        текст не тот с похожестью от KEEP_BELOW — озвучить (обычно ошибка распознавания имён)
        сюжет (главы, побочка, компаньоны) с надёжным источником текста: текст не тот при любой
            похожести — озвучить, если это речь человека (см. story_keep_reason): текст привязан
            к записи явно, а расхождение почти всегда — распознавание имён («Casterous» = Castorice).
            Кроме записей из unmapped (колонка src): их связь со звуком угадана по речи
Автоматические keep пишутся в audit_auto.csv. «Звука больше» разбирается вручную:
остальные — «НЕ РАЗОБРАНО», код возврата 2, генерация не начинается.

Запуск: python 06_audit_report.py            (после 05_audit_transcribe.py; можно во время прогона)
"""
import os, csv, re, sys, glob, difflib, argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import decisions

MIN_SIM    = 0.5   # похожесть слов записи и субтитра; ниже — «текст не тот»
KEEP_BELOW = 0.3   # «текст не тот» ниже этого — звук не тот, что в субтитре: оставляем оригинал;
                   # от 0.3 до MIN_SIM — по полному прогону почти всегда тот же текст с ошибками распознавания

ap = argparse.ArgumentParser(description="Отчёт о расхождениях звука и текста")
ap.add_argument("--no-gate", action="store_true", help="только отчёт, код возврата всегда 0")
args = ap.parse_args()

TAGS = re.compile(r"\{[^}]*\}|</?[^>]+>")

_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
         "fifteen sixteen seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()

def num_words(n):
    if n < 20: return _ONES[n]
    if n < 100: return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    for div, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= div:
            hi, lo = divmod(n, div)
            return num_words(hi) + " " + name + ("" if lo == 0 else (" and " if div == 100 else " ") + num_words(lo))

def words(s):
    # цифры -> слова: распознавание пишет «24 million», субтитр — «Twenty-four million»
    s = re.sub(r"(\d),(\d{3})\b", r"\1\2", TAGS.sub(" ", s))
    s = re.sub(r"\d{1,12}", lambda m: " " + num_words(int(m.group())) + " ", s)
    return re.sub(r"[^a-z' ]", " ", s.lower().replace("-", " ")).split()

# --- сюжет: какие расхождения — не речь человека (оставляем оригинал) ---
STORY_RE    = re.compile(r"^(chapter|side|companion)", re.I)
STORY_SOURCES = ("sentence", "extra")   # текст привязан к записи явно
SPEAKER_RE  = re.compile(r"(?:chapter|side|companion)\w*?_(.+?)_([a-z][a-z0-9]*)_(\d+)(?:_[a-z])?(?:_together)?$", re.I)
CREATURE_SHARE = 0.3   # у говорящего столько сверенных записей не похожи на текст — существо (mem, титаны, баки)
REMARK_RE   = re.compile(r"^\W*[*(♪（]")          # *ремарка*, (Мурлычет), ♪ песня
SYSTEM_RE   = re.compile(r"^\s*(>|\[)")           # >>> системный голос, [Сообщение...]
GLITCH_RE   = re.compile(r"[█▀▄■□◆◇●○ωっ∋]")      # «сломанный» текст, эмотиконы тюленей
# слова сравниваются «сжатыми»: повторы букв схлопнуты (Raaaawr -> rawr, Zzz -> z, Mhmm -> mhm)
INTJ  = re.compile(r"^(a|ah|aha|ahem|e|eh|em|er|erm|ek|o|oh|of|ow|ouch|u|uh|um|ug|ugh|urk|ngh|hngh|hng|"
                   r"h?m|hm|hmph|mph|mhm|m?hm|pf?t|pfh|tsk|tch|ts|sh|pst|z|"
                   r"(h?a)+h?|(h?e)+h?|(h?i)+|(h?o)+|hu+h|bwa(ha)*h?|mua(ha)*h?|ahaha|"
                   r"wh?o?a|wo|woh|wow|whew|phew|wh?ah?|wuh|uwa?h?|uwha|yay|yeah|hey|hu?f|"
                   r"ag?h|arg?h|rg?h|ack|gah|gr|ar|ra|rawr|yeowch|ow?ch|achoo|"
                   r"gasp|sigh|sob|snif|yawn|glug|gulp|hic|cough|bo|bo-ho|ho)$")
ONOMA = re.compile(r"^(wo?f|ruf|arf|bark|howof|me?ow|mew|nya|pur|prr?|oink|grunt|squeal|awo|hawo|"
                   r"bana\w*|ba|na|dot|do|re|mi|fa|sol|la|ti|mo|quack|ribit|roar|growl|squeak|chirp|tweet|hiss|"
                   r"wuba\w*|beep|bop|blop|bz|grumph|kweh|caw|co|honk|neigh|pipi|pika|"
                   r"mem|memi|mam|mum|me|m|nem|mee?m)$")

def squeeze(w):
    return re.sub(r"(.)\1+", r"\1", w)

def speaker(voicepath):
    m = SPEAKER_RE.match(voicepath)
    return m.group(2).lower() if m else None

def repetitive(ws):
    return len(ws) >= 4 and len(set(ws)) <= len(ws) / 3

def story_keep_reason(r, heard_words, creatures):
    """None — сюжетную реплику можно озвучить вопреки расхождению; иначе причина оставить оригинал."""
    text = r["text_en"]
    plain, tw = TAGS.sub("", text), words(text)
    st, sh = [squeeze(w) for w in tw], [squeeze(w) for w in heard_words]
    if speaker(r["voicepath"]) in creatures or "trashcan" in r["voicepath"].lower(): return "говорящий-существо"
    if REMARK_RE.match(plain) or "♪" in text or "*" in text: return "ремарка/песня"
    if SYSTEM_RE.match(plain): return "системный голос"
    if GLITCH_RE.search(text): return "спецсимволы"
    if not tw or all(INTJ.match(w) for w in st): return "междометие"
    if sum(bool(ONOMA.match(w)) for w in st) * 2 >= len(st): return "звукоподражание"
    if sh and sum(bool(ONOMA.match(w)) for w in sh) * 2 >= len(sh): return "в записи звукоподражание"
    if sh and all(INTJ.match(w) for w in sh) and len(tw) <= 2: return "в записи только вздох"
    if len(tw) >= 6 and len(heard_words) * 3 <= len(tw): return "звука меньше (описание сцены?)"
    if repetitive(heard_words) or repetitive(tw): return "повтор слогов"
    return None

asr = {}
for p in glob.glob(os.path.join(config.ASR, "asr_*.csv")):
    with open(p, encoding="utf-8-sig", newline="") as f:
        asr.update((r["file"], r) for r in csv.DictReader(f, delimiter=";"))
if not asr:
    print("Нет результатов распознавания. Сначала запусти: python pipeline.py audit")
    sys.exit(1)

def compare(r, a):
    """(вид расхождения или None, если совпадает; похожесть; слова записи). Без сверки — None."""
    text, heard = words(r["text_en"]), words(a["heard"])
    if not text or not r["text_ru"].strip():
        return None
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
        kind = None
    return kind, sim, heard

with open(os.path.join(config.RUN, "mapping.csv"), encoding="utf-8-sig", newline="") as f:
    mapping = list(csv.DictReader(f, delimiter=";"))

# существа: у говорящего заметная доля сверенных записей совсем не похожа на текст
# (mem, титаны, химеры, толпы) — их расхождения в сюжете не считаем ошибкой распознавания
checked, unlike = Counter(), Counter()
for r in mapping:
    a = asr.get(r["file"])
    if not STORY_RE.match(r["voicepath"]) or not a or a["note"]:
        continue
    c = compare(r, a)
    if c is None:
        continue
    s = speaker(r["voicepath"])
    checked[s] += 1
    unlike[s] += c[0] in ("текст не тот", "нет речи") and c[1] < KEEP_BELOW
creatures = {s for s in checked if s and unlike[s] >= 2 and unlike[s] / checked[s] >= CREATURE_SHARE}

DEC = decisions.load(auto=False)
rows, stats, by_cat = [], Counter(), Counter()
auto_keep = []   # (voicepath, причина) -> audit_auto.csv
for r in mapping:
    # ненадёжный источник текста: без подтверждения распознаванием не озвучиваем
    unsure = (r.get("text_source") in decisions.UNSURE_SOURCES and r["text_ru"].strip()
              and not decisions.find(DEC, r["voicepath"]))
    a = asr.get(r["file"])
    if not a or a["note"]:
        stats["ещё не распознано" if not a else "ошибка распознавания"] += 1
        if unsure:
            auto_keep.append((r["voicepath"], f"{r['text_source']}: не распознано"))
        continue
    c = compare(r, a)
    if c is None:
        stats["нечего сверять (нет текста или слов в нём)"] += 1
        continue
    kind, sim, heard = c
    if kind is None:
        stats["совпадает"] += 1
        continue

    dec = decisions.find(DEC, r["voicepath"])
    # у записей из unmapped (src) текст привязан к звуку не явно, а сопоставлением 01_unmapped.py:
    # непохожая речь там скорее значит чужой файл, чем ошибку распознавания имён
    story = (kind == "текст не тот" and sim < KEEP_BELOW and STORY_RE.match(r["voicepath"])
             and r.get("text_source") in STORY_SOURCES and not r.get("src"))
    if dec:
        status = f"решение: {dec[0]}"
    elif unsure:
        status = "оригинал: источник текста"
        auto_keep.append((r["voicepath"], f"{r['text_source']}: {kind}, похожесть {sim:.2f}"))
    elif story and (why := story_keep_reason(r, heard, creatures)):
        status = "оригинал по правилу"
        auto_keep.append((r["voicepath"], f"сюжет, {why}, похожесть {sim:.2f}"))
    elif story:
        status = "принято правилом (сюжет)"
    elif kind == "нет речи" or (kind == "текст не тот" and sim < KEEP_BELOW):
        status = "оригинал по правилу"
        auto_keep.append((r["voicepath"], f"{kind}, похожесть {sim:.2f}"))
    elif kind == "текст не тот":
        status = "принято правилом"
    else:
        status = "НЕ РАЗОБРАНО"
    stats[f"{kind} — {status}"] += 1
    parts = r["file"].split("\\")
    cat = parts[2] if len(parts) > 2 else ""
    if status == "НЕ РАЗОБРАНО":
        by_cat[(kind, cat)] += 1
    rows.append([status, kind, f"{sim:.2f}", len(heard), len(words(r["text_en"])), cat, r["voicepath"],
                 a["heard"], r["text_en"], r["text_ru"], r["file"]])

# неразобранные — первыми
rows.sort(key=lambda x: (x[0] != "НЕ РАЗОБРАНО", x[1], float(x[2])))
os.makedirs(config.AUDIT, exist_ok=True)
out = os.path.join(config.AUDIT, "audit_report.csv")
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
    print(f"\nОстаётся оригинал автоматически: {len(auto_keep)} ({decisions.AUTO_PATH}). "
          f"Чтобы всё же озвучить запись, впиши для неё accept в {decisions.PATH}")
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
