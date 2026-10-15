# -*- coding: utf-8 -*-
"""
texts.py — откуда берётся текст реплики по VoiceID: общие таблицы для 03_mapper.py
(выбирает один текст по приоритету) и 01_unmapped.py (сверяет речь со всеми вариантами).

Дополнительные таблицы с текстом по VoiceID — в extra_tables.csv рядом: новые находит и дописывает
pipeline.py utils find-missing-text --apply, оба скрипта подхватят их сами.
"""
import os, csv, json, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

EO = os.path.join(config.GAMEDATA, "ExcelOutput")
TM = os.path.join(config.GAMEDATA, "TextMap")
EXTRA_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_tables.csv")

def extra_tables():
    """[(таблица ExcelOutput, колонка с VoiceID, колонка с хэшем текста)] из extra_tables.csv."""
    with open(EXTRA_CSV, encoding="utf-8-sig", newline="") as f:
        return [(r["table"].strip(), r["voiceid_column"].strip(), r["text_column"].strip())
                for r in csv.DictReader(f, delimiter=";") if (r.get("table") or "").strip()]

EXTRA_TABLES = extra_tables()

def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

def textmap_ru():
    """Хэш -> русский текст (TextMapRU_0 важнее _1 и Main)."""
    tm = {}
    for name in ("TextMapRU_0.json", "TextMapRU_1.json", "TextMapMainRU.json"):
        p = os.path.join(TM, name)
        if os.path.exists(p):
            for k, v in load(p).items(): tm.setdefault(k, v)
    return tm

def textmap_en():
    return load(os.path.join(TM, "TextMapEN.json"))

class Sources:
    """Ссылки VoiceID -> хэш текста из всех таблиц. Списки — в порядке строк таблицы:
    03_mapper.py берёт последнюю ссылку, 01_unmapped.py — все."""

    def __init__(self):
        self.sent_hash = {}                 # TalkSentenceID -> хэш
        self.voice_sents = defaultdict(list)  # VoiceID -> [TalkSentenceID] по полю VoiceID строки
        for e in load(os.path.join(EO, "TalkSentenceConfig.json")):
            h = e.get("TalkSentenceText", {}).get("Hash")
            if not h: continue
            self.sent_hash[e["TalkSentenceID"]] = str(h)
            if e.get("VoiceID"):
                self.voice_sents[e["VoiceID"]].append(e["TalkSentenceID"])

        self.atlas = defaultdict(list)      # VoiceID -> [(AvatarID, хэш)]
        self.atlas_audio = defaultdict(list)  # AudioID -> [(AvatarID, хэш)]
        for e in load(os.path.join(EO, "VoiceAtlas.json")):
            h = e.get("Voice_M", {}).get("Hash")
            if not h: continue
            self.atlas[e["VoiceID"]].append((e.get("AvatarID"), str(h)))
            if e.get("AudioID"):
                self.atlas_audio[e["AudioID"]].append((e.get("AvatarID"), str(h)))

        self.extra = defaultdict(list)      # VoiceID -> [хэш] из EXTRA_TABLES
        for fname, vk, hk in EXTRA_TABLES:
            p = os.path.join(EO, fname)
            if not os.path.exists(p): continue
            data = load(p)
            if not isinstance(data, list): continue
            for e in data:
                if not isinstance(e, dict): continue
                h = e.get(hk)
                h = h.get("Hash") if isinstance(h, dict) else h
                if e.get(vk) and h: self.extra[e[vk]].append(str(h))

        self.multivoice = defaultdict(list)  # VoiceID -> [хэш строки] по TalkSentenceMultiVoice
        for e in load(os.path.join(EO, "TalkSentenceMultiVoice.json")):
            sid = e.get("TalkSentenceID")
            if sid in self.sent_hash:
                for vid in e.get("VoiceIDList", []):
                    self.multivoice[vid].append(self.sent_hash[sid])

    def all_hashes(self, voiceid):
        """Все хэши текста, которые могут относиться к VoiceID (для сверки речи с текстом)."""
        hs = [self.sent_hash[s] for s in self.voice_sents.get(voiceid, ())]
        hs += [h for _, h in self.atlas.get(voiceid, ())]
        hs += [h for _, h in self.atlas_audio.get(voiceid, ())]
        hs += self.extra.get(voiceid, [])
        hs += self.multivoice.get(voiceid, [])
        if voiceid in self.sent_hash:
            hs.append(self.sent_hash[voiceid])
        return hs
