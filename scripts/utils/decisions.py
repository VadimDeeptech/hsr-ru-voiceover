# -*- coding: utf-8 -*-
"""
decisions.py — чтение audit_decisions.csv: ручные решения по записям, у которых звук
оригинала расходится с текстом (их находит 04_audit_report.py).

Формат (разделитель ;): voicepath;action;lines;comment
    voicepath — как в mapping.csv (имя файла без .wav, нижний регистр);
                для гендерных файлов можно без суффикса _m/_f — тогда на оба
    action:
        accept — расхождение известно, озвучиваем текст как есть
        join   — текст продолжается: своя строка + следующие `lines` строк субтитров
        next   — своя строка — ремарка: берём только следующие `lines` строк
        keep   — не озвучиваем, в игре остаётся оригинал
"""
import os, csv, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import config

PATH    = os.path.join(config.ROOT, "audit_decisions.csv")
ACTIONS = ("accept", "join", "next", "keep")

def load():
    """-> {voicepath: (action, lines)}"""
    dec = {}
    if not os.path.exists(PATH):
        return dec
    with open(PATH, encoding="utf-8-sig", newline="") as f:
        for n, r in enumerate(csv.DictReader(f, delimiter=";"), 2):
            vp = (r.get("voicepath") or "").strip().lower()
            if not vp or vp.startswith("#"):
                continue
            action = (r.get("action") or "").strip().lower()
            lines = (r.get("lines") or "").strip()
            if action not in ACTIONS or (action in ("join", "next") and not lines.isdigit()):
                print(f"!! {PATH}, строка {n}: action должен быть одним из {ACTIONS}, "
                      f"для join/next нужно число в lines")
                sys.exit(1)
            dec[vp] = (action, int(lines) if lines.isdigit() else 0)
    return dec

def find(dec, stem):
    """Решение для файла: по точному имени или по имени без гендерного суффикса."""
    stem = stem.lower()
    if stem in dec:
        return dec[stem]
    if len(stem) > 2 and stem[-2] == "_" and stem[-1] in "mf":
        return dec.get(stem[:-2])
    return None
