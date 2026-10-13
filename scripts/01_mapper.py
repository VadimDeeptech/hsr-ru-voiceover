# -*- coding: utf-8 -*-
"""01_mapper.py — маппинг wav -> VoiceID -> текст. Результат: mapping.csv
v3: гендерные суффиксы _m/_f (IsPlayerInvolved: true в VoiceConfig).
    VoiceConfig хранит БАЗОВЫЙ VoicePath (chapter0_2_mar7th_141),
    а файлы на диске сплитятся на *_m.wav / *_f.wav.
    Ищем с отрезанным суффиксом, пол пишем в колонку gender.
"""
import os, json, csv, re
from collections import Counter

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import decisions

DECISIONS = decisions.load()

EO   =os.path.join(config.GAMEDATA, "ExcelOutput")
TM   = os.path.join(config.GAMEDATA, "TextMap")
DS   = config.DATASET
OUT  = config.RUN
os.makedirs(OUT, exist_ok=True)

def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

print("Загружаю VoiceConfig...")
voice_by_path = {}
for e in load(os.path.join(EO, "VoiceConfig.json")):
    vp = e.get("VoicePath")
    if vp: voice_by_path[vp.lower()] = (e["VoiceID"], e.get("VoiceType", ""))

print("Загружаю TalkSentenceConfig...")
sent_hash = {}
voice_sents = {}   # VoiceID -> [TalkSentenceID, ...] по полю VoiceID самой строки
for e in load(os.path.join(EO, "TalkSentenceConfig.json")):
    h = e.get("TalkSentenceText", {}).get("Hash")
    if not h: continue
    sent_hash[e["TalkSentenceID"]] = str(h)
    if e.get("VoiceID"):
        voice_sents.setdefault(e["VoiceID"], []).append(e["TalkSentenceID"])

def sentence_id(voiceid):
    """Строка субтитра для звука. Какой звук играет под строкой, задаёт её поле VoiceID —
    с номером строки оно обычно совпадает, но не всегда. Если на звук не ссылается
    ни одна строка, берём строку с тем же номером (старые данные без поля)."""
    sids = voice_sents.get(voiceid)
    if not sids:
        return voiceid if voiceid in sent_hash else None
    if voiceid in sids:
        return voiceid
    stats["text_by_voice_field"] += 1
    return next((s for s in sids if textmap.get(sent_hash[s])), sids[0])

def following(sid, n):
    """Хэши следующих n строк субтитров с текстом — продолжение той же записи."""
    res, i = [], sid + 1
    while len(res) < n and i in sent_hash:
        if textmap.get(sent_hash[i]): res.append(sent_hash[i])
        i += 1
    return res

print("Загружаю VoiceAtlas...")
atlas = {}
atlas_by_audioid = {}
for e in load(os.path.join(EO, "VoiceAtlas.json")):
    h = e.get("Voice_M", {}).get("Hash")
    if h:
        atlas[e["VoiceID"]] = (e.get("AvatarID"), str(h))
        if e.get("AudioID"):
            atlas_by_audioid[e["AudioID"]] = (e.get("AvatarID"), str(h))

print("Загружаю TextMap RU + EN...")
textmap = {}
for name in ("TextMapRU_0.json", "TextMapRU_1.json", "TextMapMainRU.json"):
    p = os.path.join(TM, name)
    if os.path.exists(p):
        for k, v in load(p).items(): textmap.setdefault(k, v)
textmap_en = load(os.path.join(TM, "TextMapEN.json"))

# Дополнительные таблицы с текстом по VoiceID
extra_hash = {}

def load_extra(fname, vid_key, hash_key):
    """Загружает таблицу вида [{VoiceID: ..., Hash: ...}, ...] -> {vid: hash}"""
    p = os.path.join(EO, fname)
    if not os.path.exists(p):
        return
    data = load(p)
    if not isinstance(data, list) or len(data) == 0 or not isinstance(data[0], dict):
        return
    for e in data:
        vid = e.get(vid_key)
        h = e.get(hash_key)
        if isinstance(h, dict):
            h = h.get("Hash")
        if vid and h:
            extra_hash[vid] = str(h)

print("Загружаю дополнительные таблицы...")
load_extra("TarotBookSentence.json", "VoiceID", "Sentence")
load_extra("TarotFiles.json", "VoiceID", "Sentence")
load_extra("B51RacingTR.json", "VoiceID", "TRName")
load_extra("HeartDialTalk.json", "VoiceID", "SDFText")
print(f"  Доп.таблиц: {len(extra_hash)} записей")

# TalkSentenceMultiVoice: TalkSentenceID -> VoiceIDList -> TalkSentenceConfig hash
tsmv = load(os.path.join(EO, "TalkSentenceMultiVoice.json"))
tsmv_map = {}  # voiceid -> sentence_hash
for e in tsmv:
    tsid = e.get("TalkSentenceID")
    if tsid and tsid in sent_hash:
        for vid in e.get("VoiceIDList", []):
            tsmv_map[vid] = sent_hash[tsid]
print(f"  TalkSentenceMultiVoice: {len(tsmv_map)} записей")

print("Сканирую wav-файлы...")
rows, stats = [], Counter()
char_re = re.compile(r"^(?:chapter\w*|side\w*|vo)_\w*?_([a-z][a-z0-9]+?)_\d+", re.I)

for dp, dn, fn in os.walk(DS):
    for f in fn:
        if not f.lower().endswith(".wav"): continue
        stats["wav_total"] += 1
        full  = os.path.join(dp, f)
        rel   = os.path.relpath(full, DS)
        stem  = os.path.splitext(f)[0].lower()
        parts = rel.split(os.sep)
        if len(parts) > 1 and parts[1].lower() == "unmapped":
            stats["unmapped_skip"] += 1
            continue

        hit = voice_by_path.get(stem)
        gender = ""
        if not hit and len(stem) > 2 and stem[-2] == "_" and stem[-1] in "mf":
            # VoiceConfig хранит базовый путь, файл сплитится на _m/_f
            hit = voice_by_path.get(stem[:-2])
            if hit:
                gender = stem[-1]
                stats["matched_gender_suffix"] += 1
        if not hit:
            stats["no_voiceconfig"] += 1
            continue
        voiceid, vtype = hit
        stats["matched"] += 1

        char = ""
        if len(parts) >= 4 and parts[1].lower() == "voice" and parts[2].lower() == "archive":
            char = parts[3]
        else:
            m = char_re.match(stem)
            if m: char = m.group(1)

        sid, avatar = sentence_id(voiceid), ""
        h = sent_hash[sid] if sid is not None else None
        if not h and voiceid in atlas:
            avatar, h = atlas[voiceid]
        if not h and voiceid in atlas_by_audioid:
            avatar, h = atlas_by_audioid[voiceid]
        if not h and voiceid in extra_hash:
            h = extra_hash[voiceid]
        if not h and voiceid in tsmv_map:
            h = tsmv_map[voiceid]
        text_ru = textmap.get(h) if h else None
        text_en = textmap_en.get(h) if h else None

        dec = decisions.find(DECISIONS, stem)
        if dec and dec[0] in ("join", "next") and sid is not None:
            # ручное решение: текст записи продолжается в следующих строках субтитров
            more = following(sid, dec[1])
            if len(more) < dec[1]:
                print(f"  !! {stem}: в решении {dec[1]} строк продолжения, найдено {len(more)}")
            own = [] if dec[0] == "next" else [h]
            text_ru = " ".join(textmap.get(x) or "" for x in own + more)
            text_en = " ".join(textmap_en.get(x) or "" for x in own + more)
            stats["joined"] += 1

        if text_ru: stats["with_ru_text"] += 1
        else: stats["no_text"] += 1

        rows.append([rel, stem, voiceid, vtype, char, avatar, gender,
                     (text_ru or "").replace("\r", " "), (text_en or "").replace("\r", " ")])

csv_path = os.path.join(OUT, "mapping.csv")
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    wr = csv.writer(f, delimiter=";")
    wr.writerow(["file", "voicepath", "voiceid", "voicetype", "character", "avatarid", "gender", "text_ru", "text_en"])
    wr.writerows(rows)

print(f"\nГотово: {csv_path}")
print(f"Всего wav: {stats['wav_total']} | unmapped: {stats['unmapped_skip']} | нет в VoiceConfig: {stats['no_voiceconfig']}")
print(f"Текст взят по полю VoiceID другой строки: {stats['text_by_voice_field']} | "
      f"склеено по audit_decisions.csv: {stats['joined']}")
print(f"Совпало: {stats['matched']} (из них по _m/_f-суффиксу: {stats['matched_gender_suffix']}) | с RU-текстом: {stats['with_ru_text']} | без текста: {stats['no_text']}")