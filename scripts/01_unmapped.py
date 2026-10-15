# -*- coding: utf-8 -*-
"""
01_unmapped.py — возвращает в пайплайн файлы из папок unmapped (AnimeWwise не знает их имён).
Имя такого файла — 64-битный хэш пути (он же wem_id английского варианта в pck), а сам путь
из хэша не восстановить. Поэтому сверяем звук с текстом: Whisper распознаёт речь
(05_audit_transcribe.py), а распознанное сравнивается с английскими субтитрами записей VoiceConfig.

    python 01_unmapped.py list    -> hsr-generate\\audit\\unmapped\\list.csv (что распознавать)
    python 01_unmapped.py match   -> hsr-generate\\audit\\unmapped\\match.csv (итог по каждому файлу)
                                     + hsr-generate\\audit\\asr\\asr_unmapped.csv (распознанное для сверки)

Обычно запускается из pipeline.py unmapped (и в начале полных циклов).

В pck External_del_* файлы лежат по алфавиту имени, поэтому там сопоставление по тексту
дополняется порядком (order_pass): файлы между известными соседями — это записи, лежащие между
ними по алфавиту. Колонка method: text — по тексту, order — по порядку в pck.

Статусы в match.csv:
    new       — запись VoiceConfig, у которой нет файла: 03_mapper.py добавит её в mapping.csv
                под «виртуальным» путём pck\\voice\\...\\<voicepath>.wav (колонка file),
                настоящий файл — в колонке src
    alias     — копия строки, файл которой уже есть: 08_build_repack_list.py кладёт ту же
                озвучку и под этот wem_id
    ambiguous — похожий текст у нескольких уже озвученных записей (у копии мог бы оказаться чужой голос)
    gender    — запись с вариантами _m/_f, а вариант не различить ни по тексту, ни по высоте голоса
                (pitch.csv, 02_unmapped_pitch.py)
    dup       — все подходящие записи уже заняты файлами с лучшим совпадением
    low       — совпадение слабое (нет текста в данных игры, выкрики, новости...)
    nospeech  — Whisper ничего не распознал

VoBanks*.pck не берём: там звук лежит внутри саундбанков (имена — 32-битные media ID),
а 12_repack_pck.py меняет только externals pck.
"""
import os, re, csv, json, glob, difflib, argparse, sys, struct, bisect
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import texts

LIST  = os.path.join(config.UNMAPPED, "list.csv")
MATCH = os.path.join(config.UNMAPPED, "match.csv")
ASR_OUT = os.path.join(config.ASR, "asr_unmapped.csv")

MIN_NEW   = 0.90   # порог для новой записи (в пилоте верные совпадения — от 0.92)
MIN_ALIAS = 0.95   # для копии уже озвученной строки — строже: ошибка заменит чужую реплику
NEAR      = 0.05   # кандидаты в пределах NEAR от лучшего считаются равными
ALIAS_WORDS = 4    # ...и не короче стольких слов
MIN_LOOSE = 0.80   # ...или ниже, если остальные записи заметно хуже (Whisper ошибся в паре слов)
MARGIN    = 0.20
GENDER_GAP = 0.02  # насколько вариант _m/_f должен совпадать лучше другого
PITCH_RATIO = 1.25 # во сколько раз голос варианта _f в паре выше, чтобы различить по нему
ORDER_MIN = 0.30   # по порядку в pck, когда файлов и записей поровну: ниже — звучит явно не та строка
ORDER_LOOSE = 0.50 # ...когда не поровну (часть файлов — копии строк из других pck)

def is_unmapped(rel):
    parts = rel.split(os.sep)
    return len(parts) > 2 and parts[1].lower() == "unmapped" and not parts[0].lower().startswith("vobanks")

def cmd_list():
    files = []
    for dp, dn, fn in os.walk(config.DATASET):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), config.DATASET)
            if f.lower().endswith(".wav") and is_unmapped(rel):
                files.append(rel)
    os.makedirs(config.UNMAPPED, exist_ok=True)
    with open(LIST, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["file"])
        wr.writerows([r] for r in sorted(files))
    print(f"Файлов unmapped (без VoBanks): {len(files)} -> {LIST}")

def load(p):
    with open(p, encoding="utf-8") as f: return json.load(f)

def render(text, gender):
    """Английский субтитр в варианте для пола (как clean_text в 07_generate.py)."""
    text = re.sub(r"\{F#([^}]*)\}\{M#([^}]*)\}", lambda m: m.group(1) if gender == "f" else m.group(2), text)
    text = re.sub(r"\{F#([^}]*)\}", lambda m: m.group(1) if gender == "f" else "", text)
    text = re.sub(r"\{M#([^}]*)\}", lambda m: "" if gender == "f" else m.group(1), text)
    return text

def norm(text):
    text = re.sub(r"\{[^}]*\}|<[^>]*>", " ", (text or "").lower())
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())

def voice_texts():
    """VoiceID -> (английские, русские) субтитры из всех таблиц, откуда текст берёт 03_mapper.py
    (utils\\texts.py): речь сверяется со всеми вариантами, 03 выберет один по приоритету."""
    en, ru, src = texts.textmap_en(), texts.textmap_ru(), texts.Sources()
    vids = (set(src.voice_sents) | set(src.atlas) | set(src.atlas_audio) | set(src.extra)
            | set(src.multivoice) | set(src.sent_hash))
    out = {}
    for vid in vids:
        hs = src.all_hashes(vid)
        out[vid] = (list(dict.fromkeys(en[h] for h in hs if en.get(h))), [ru[h] for h in hs if ru.get(h)])
    return out

def same_for_genders(texts):
    """Русский текст одинаков для _m и _f — тогда неважно, какой из двух файлов какой."""
    return all(render(t, "m") == render(t, "f") and not re.search(r"\{(NICKNAME|PLAYER_NAME|MC_NAME)", t, re.I)
               for t in texts)

def virtual_path(src, stem, dirs):
    """pck\\voice\\...\\<stem>.wav: папка — как у соседних записей с тем же префиксом имени,
    иначе по частям имени (chapter5_61_nihilux_115 -> voice\\chapter5\\61\\nihilux)."""
    prefix = re.sub(r"_\d+(?:_[mf])?$", "", stem)
    d = dirs.get(prefix.lower()) or os.path.join("voice", *prefix.split("_"))
    return os.path.join(src.split(os.sep)[0], d, stem + ".wav")

def pck_order(path):
    """wem_id файлов pck в порядке их данных (externals); None — pck нет или это заглушка."""
    if not os.path.isfile(path) or os.path.getsize(path) < 32: return None
    with open(path, "rb") as f: data = f.read()
    lang, banks, sounds = struct.unpack_from("<III", data, 12)
    pos = 28 + lang + banks + sounds
    n = struct.unpack_from("<I", data, pos)[0]
    ents = []
    for j in range(n):
        id2, id1, bs, size, off = struct.unpack_from("<IIIII", data, pos + 4 + j * 24)
        ents.append((off, f"{id1:08x}{id2:08x}"))
    return [h for off, h in sorted(ents)]

def increasing(items):
    """Самая длинная строго возрастающая по имени подпоследовательность items [(позиция, имя)]."""
    tails, keys, prev = [], [], [None] * len(items)
    for i, (_, k) in enumerate(items):
        j = bisect.bisect_left(keys, k)
        if j: prev[i] = tails[j - 1]
        if j == len(tails): tails.append(i); keys.append(k)
        else: tails[j] = i; keys[j] = k
    out, i = [], tails[-1] if tails else None
    while i is not None: out.append(items[i]); i = prev[i]
    return out[::-1]

def align(files, stems, sim):
    """Монотонное сопоставление: files и stems — по порядку; максимум пар, затем похожести."""
    n, m = len(files), len(stems)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            dp[i][j] = max(dp[i + 1][j], dp[i][j + 1], 1 + sim(files[i], stems[j]) + dp[i + 1][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        s = sim(files[i], stems[j])
        if dp[i][j] == 1 + s + dp[i + 1][j + 1]:
            pairs.append((files[i], stems[j], s)); i += 1; j += 1
        elif dp[i][j] == dp[i + 1][j]: i += 1
        else: j += 1
    return pairs

def order_pass(results, pool, have, dirs):
    """В pck External_del_* файлы лежат по алфавиту имени (проверено на известных pck:
    1049 из 1050 соседних пар). Файлы между двумя известными соседями — это записи без файла,
    лежащие между ними по алфавиту. Так различаются и повторяющиеся реплики, и _m/_f
    с одинаковым текстом (_f всегда раньше _m)."""
    if not config.GAME_AUDIO or not os.path.isdir(config.GAME_AUDIO):
        print("Порядок в pck: папка игры не найдена — пропуск"); return
    by_pck = defaultdict(dict)
    for r in results:
        pck = r["src"].split(os.sep)[0]
        if pck.lower().startswith("external_del"):
            by_pck[pck][os.path.splitext(os.path.basename(r["src"]))[0].lower()] = r
    if not by_pck: return

    sys.path.insert(0, config.AWWISE)
    from mapper import Mapper
    m = Mapper(os.path.join(config.AWWISE, "maps", "hkrpg.map"))
    en = next(i for i, n in enumerate(m.languages) if "engl" in n.lower())
    known = {}
    for h, (off, lang) in m.keys.items():
        if lang == en:
            p = m.get_key(h)
            if p: known[h] = os.path.basename(p[0]).lower()

    # все имена файлов по VoiceConfig; у IsPlayerInvolved — _f и _m
    stem_vp, stem_text, has_file = {}, defaultdict(list), set()
    for vp, has, variants, _ in pool:
        for s, n in variants: stem_text[s.lower()].append(n)
    for e in load(os.path.join(config.GAMEDATA, "ExcelOutput", "VoiceConfig.json")):
        vp = e.get("VoicePath")
        if not vp: continue
        stems = have.get(vp.lower()) or ([f"{vp}_f", f"{vp}_m"] if e.get("IsPlayerInvolved") else [vp])
        for s in stems:
            stem_vp.setdefault(s.lower(), (s, vp))
            if have.get(vp.lower()): has_file.add(s.lower())
    universe = sorted(stem_vp)
    text_owners = defaultdict(set)
    for s, ns in stem_text.items():
        for n in ns: text_owners[n].add(s)
    unique = lambda s: stem_text.get(s) and all(text_owners[n] == {s} for n in stem_text[s])

    cache = {}
    def sim(r, s):
        key = (r["src"], s)
        if key not in cache: cache[key] = similarity(r, s)
        return cache[key]
    def similarity(r, s):
        heard, ts = norm(r["heard"]), stem_text.get(s)
        if not ts:   # в субтитре нет слов («...»): подходит короткий возглас
            return 0.5 if len(heard.split()) <= 2 else 0.1
        if not heard: return 0.3
        return max(difflib.SequenceMatcher(None, heard, t).ratio() for t in ts)

    stats = Counter()
    for pck, files in sorted(by_pck.items()):
        seq = pck_order(os.path.join(config.GAME_AUDIO, pck))
        if seq is None:
            print(f"Порядок в pck: {pck} нет в игре — пропуск"); continue
        # якоря: известные файлы pck и уверенные совпадения по уникальному тексту
        items = []
        for i, h in enumerate(seq):
            r = files.get(h)
            if r is None:
                if h in known: items.append((i, known[h]))
            elif r["status"] == "new" and float(r["score"]) >= 0.95 and unique(r["stem"].lower()):
                items.append((i, r["stem"].lower()))
        anchors = increasing(items)
        fixed, done = {i for i, _ in anchors}, set()
        used = {s for _, s in anchors}
        bounds = [(-1, None)] + anchors + [(len(seq), None)]
        for (ia, na), (ib, nb) in zip(bounds, bounds[1:]):
            gap = [files[seq[i]] for i in range(ia + 1, ib) if seq[i] in files]
            if not gap: continue
            lo = bisect.bisect_right(universe, na) if na else None
            hi = bisect.bisect_left(universe, nb) if nb else None
            if lo is None and hi is None: continue
            # до первого якоря и после последнего — только ближайшие записи
            if lo is None: lo = max(0, hi - len(gap) - 10)
            if hi is None: hi = lo + len(gap) + 10
            cand = [s for s in universe[lo:hi] if s not in has_file and s not in used]
            # файлов столько же, сколько записей, — сопоставление однозначно, иначе нужен похожий текст
            exact = len(gap) == len(cand)
            for r, s, sc in align(gap, cand, sim):
                if sc < (ORDER_MIN if exact and stem_text.get(s) else 0 if exact else ORDER_LOOSE): continue
                stem, vp = stem_vp[s]
                r.update(stem=stem, voicepath=vp, status="new", method="order", score=f"{sc:.3f}",
                         text_en=(stem_text.get(s) or [""])[0], file=virtual_path(r["src"], stem, dirs))
                used.add(s); done.add(id(r)); stats["по порядку"] += 1
        for i, h in enumerate(seq):
            r = files.get(h)
            if r and r["status"] == "new" and i not in fixed and id(r) not in done:
                # совпадение по тексту противоречит порядку в pck
                r.update(status="ambiguous", method="", file="", stem=""); stats["против порядка"] += 1

    # на запись — один файл: из del-pck по порядку; копии той же строки в других pck — alias
    by_stem = defaultdict(list)
    for r in results:
        if r["status"] == "new": by_stem[r["stem"].lower()].append(r)
    # Но если запись уверенно узнана по тексту, а по порядку ей достался файл с непохожей речью —
    # порядок ошибся (в промежутке был файл реплики без субтитра): такой файл не берём вовсе,
    # иначе он стал бы главным, а верные файлы — его копиями
    weak = lambda r: r["method"] == "order" and float(r["score"]) < MIN_LOOSE
    for rs in by_stem.values():
        sure = any(r["method"] == "text" and float(r["score"]) >= MIN_NEW for r in rs)
        rs.sort(key=lambda r: (sure and weak(r), r["method"] != "order",
                               not r["src"].lower().startswith("external_del"), -float(r["score"])))
        for r in rs[1:]:
            if sure and weak(r):
                r.update(status="ambiguous", method="", file="", stem=""); stats["против текста"] += 1
                continue
            r.update(status="alias" if r["src"].split(os.sep)[0] != rs[0]["src"].split(os.sep)[0] else "dup", file="")
            stats["в копии"] += 1
    print("Порядок в pck: " + ", ".join(f"{k}: {v}" for k, v in stats.items()))

def cmd_match():
    print("Загружаю данные игры...")
    texts = voice_texts()

    # что уже есть в датасете: voicepath -> [имена файлов], папка по префиксу имени
    have, dirs = defaultdict(list), {}
    for dp, dn, fn in os.walk(config.DATASET):
        for f in fn:
            if not f.lower().endswith(".wav"): continue
            rel = os.path.relpath(os.path.join(dp, f), config.DATASET)
            parts = rel.split(os.sep)
            if len(parts) < 3 or parts[1].lower() == "unmapped": continue
            stem = os.path.splitext(f)[0]
            have[re.sub(r"_[mf]$", "", stem.lower())].append(stem)
            dirs.setdefault(re.sub(r"_\d+(?:_[mf])?$", "", stem.lower()), os.path.join(*parts[1:-1]))

    # кандидаты: (voicepath, есть ли файл, [(имя файла, нормализованный текст)], русский текст одинаков для _m/_f)
    pool, seen = [], set()
    for e in load(os.path.join(config.GAMEDATA, "ExcelOutput", "VoiceConfig.json")):
        vp = e.get("VoicePath")
        en, ru = texts.get(e["VoiceID"], ([], []))
        if not vp or not en or vp.lower() in seen: continue
        seen.add(vp.lower())
        stems = have.get(vp.lower()) or ([f"{vp}_m", f"{vp}_f"] if e.get("IsPlayerInvolved") else [vp])
        variants = []
        for s in stems:
            g = s[-1].lower() if re.search(r"_[mf]$", s, re.I) else ""
            for t in en:
                for n in dict.fromkeys(norm(render(t, gg)) for gg in ([g] if g else ["m", "f"])):
                    if n: variants.append((s, n))
        if variants:
            pool.append((vp, bool(have.get(vp.lower())), variants, same_for_genders(ru)))
    print(f"Записей VoiceConfig с английским текстом: {len(pool)}, из них без файла: {sum(not p[1] for p in pool)}")

    index = defaultdict(set)
    for i, (_, _, variants, _) in enumerate(pool):
        for _, n in variants:
            for w in n.split():
                if len(w) > 3: index[w].add(i)

    # только файлы текущей выгрузки (list.csv): в кэше остаются и файлы, которых в датасете
    # уже нет (pck убран обновлением игры, AnimeWwise узнал имя)
    with open(LIST, encoding="utf-8-sig", newline="") as f:
        current = {r["file"] for r in csv.DictReader(f, delimiter=";")}
    asr = {}
    for p in glob.glob(os.path.join(config.UNMAPPED, "asr_*.csv")):
        with open(p, encoding="utf-8-sig", newline="") as f:
            asr.update((r["file"], r) for r in csv.DictReader(f, delimiter=";") if r["file"] in current)
    print(f"Распознано файлов: {len(asr)} из {len(current)}")

    pitch = {}
    pitch_csv = os.path.join(config.UNMAPPED, "pitch.csv")
    if os.path.exists(pitch_csv):
        with open(pitch_csv, encoding="utf-8-sig", newline="") as f:
            pitch = {r["file"]: float(r["f0"]) for r in csv.DictReader(f, delimiter=";") if r["f0"]}

    # 1. кандидаты для каждого файла
    results, pending = [], []
    for src, a in sorted(asr.items()):
        heard = norm(a["heard"])
        row = {"src": src, "file": "", "stem": "", "voicepath": "", "status": "", "score": "",
               "heard": a["heard"], "text_en": ""}
        results.append(row)
        if not heard:
            row["status"] = "nospeech"; continue
        cand = Counter()
        for w in set(heard.split()):
            if len(w) > 3 and len(index[w]) < 3000:
                for i in index[w]: cand[i] += 1
        # лучший вариант текста по каждой записи и по каждому её файлу (_m/_f)
        scored = []
        # больше общих слов — раньше; при равенстве порядок по номеру, чтобы итог не менялся от запуска к запуску
        for i, _ in sorted(cand.items(), key=lambda x: (-x[1], x[0]))[:500]:
            sc = {}
            for s, n in pool[i][2]:
                sc[s] = max(sc.get(s, 0), difflib.SequenceMatcher(None, heard, n).ratio())
            scored.append((max(sc.values()), i, sc))
        if not scored:
            row["status"] = "low"; continue
        scored.sort(key=lambda x: -x[0])
        best = scored[0][0]
        near = [x for x in scored if x[0] >= best - NEAR]
        far = max((x[0] for x in scored if x[0] < best - NEAR), default=0)
        # запись без файла важнее копии; среди равных записей без файла — раздаём по очереди:
        # текст у них один, так что озвучка выйдет та же при любом распределении
        missing = [x for x in near if not pool[x[1]][1]]
        options = missing or (near if len(near) == 1 else [])
        sc, i, _ = (options or scored)[0]
        row.update(voicepath=pool[i][0], score=f"{sc:.3f}", text_en=pool[i][2][0][1])
        if not options:
            # несколько уже озвученных записей: у копии мог бы оказаться чужой голос
            row["status"] = "ambiguous"; continue
        # короткий выкрик («Enough!») мог сказать кто угодно — копией с чужим голосом не берём
        ok = ((sc >= MIN_NEW or sc >= MIN_LOOSE and sc - far >= MARGIN) if missing
              else sc >= MIN_ALIAS and len(heard.split()) >= ALIAS_WORDS)
        if not ok:
            row["status"] = "low"; continue
        pending.append((row, options))

    # 2. файл -> запись: сначала однозначные и лучшие совпадения; у записи без файла
    #    мест столько, сколько у неё вариантов (_m/_f)
    assigned = defaultdict(list)
    pending.sort(key=lambda x: (len(x[1]) > 1, -float(x[0]["score"])))
    for row, options in pending:
        for sc, i, by_stem in options:
            if pool[i][1] or len(assigned[i]) < len(by_stem):
                assigned[i].append((row, sc, by_stem)); break
        else:
            row["status"] = "dup"

    # 3. запись -> конкретный файл _m/_f
    for i, items in assigned.items():
        vp, has_file, variants, ru_same = pool[i]
        stems = list(items[0][2])
        chosen, undecided = {}, []
        for row, sc, by_stem in items:
            ranked = sorted(by_stem.items(), key=lambda x: -x[1])
            if len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= GENDER_GAP:
                chosen[id(row)] = ranked[0][0]
            else:
                undecided.append(row)
        if not has_file:
            # два файла претендуют на один вариант: лучший остаётся, второй — в нерешённые
            taken = {}
            for row, sc, _ in sorted(items, key=lambda x: -x[1]):
                st = chosen.get(id(row))
                if st and st in taken:
                    del chosen[id(row)]; undecided.append(row)
                elif st:
                    taken[st] = row
            free = [s for s in stems if s not in taken]
            if len(undecided) == 1 and len(free) == 1:
                chosen[id(undecided.pop())] = free[0]
        else:
            free = stems
        if len(undecided) == 2 and len(free) == 2 and all(r["src"] in pitch for r in undecided):
            # одинаковый английский текст у _m и _f: в паре у мужского варианта голос ниже
            lo, hi = sorted(undecided, key=lambda r: pitch[r["src"]])
            if pitch[hi["src"]] >= pitch[lo["src"]] * PITCH_RATIO:
                fm = {s[-1].lower(): s for s in free}
                if set(fm) == {"m", "f"}:
                    chosen[id(lo)], chosen[id(hi)] = fm["m"], fm["f"]
                    undecided = []
        if undecided and not has_file and ru_same and len(undecided) <= len(free):
            # голос берётся из самого файла, а текст для обоих вариантов один —
            # озвучка выйдет верной при любом распределении
            for row, s in zip(undecided, free):
                chosen[id(row)] = s
            undecided = []
        for row in undecided:
            row["status"] = "gender"
        for row, sc, by_stem in items:
            stem = chosen.get(id(row))
            if not stem: continue
            # voicepath — у записи, которой достался файл (в шаге 1 там лучший кандидат,
            # а место могло найтись только у следующей записи с тем же текстом)
            row.update(stem=stem, voicepath=vp, score=f"{by_stem[stem]:.3f}", status="alias" if has_file else "new",
                       text_en=next(n for s, n in variants if s == stem))
            if not has_file:
                row["file"] = virtual_path(row["src"], stem, dirs)

    for r in results:
        r.setdefault("method", "text" if r["status"] in ("new", "alias") else "")
    order_pass(results, pool, have, dirs)

    with open(MATCH, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, list(results[0].keys()) if results else ["src"], delimiter=";")
        wr.writeheader(); wr.writerows(results)
    # распознанное для сверки (06_audit_report.py) — под виртуальным путём, как в mapping.csv
    with open(ASR_OUT, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["file", "heard", "no_speech", "note"])
        for r in results:
            if r["status"] == "new":
                a = asr[r["src"]]
                wr.writerow([r["file"], a["heard"], a["no_speech"], a["note"]])

    stats = Counter(r["status"] for r in results)
    print("Итог: " + ", ".join(f"{k}: {v}" for k, v in stats.most_common()))
    by_pck = Counter(r["src"].split(os.sep)[0] for r in results if r["status"] == "new")
    for pck, n in by_pck.most_common(5):
        print(f"  {pck}: новых {n}")
    print(f"-> {MATCH}")

ap = argparse.ArgumentParser(description="Сопоставление файлов unmapped с записями VoiceConfig по распознанной речи")
ap.add_argument("cmd", choices=["list", "match"])
args = ap.parse_args()
cmd_list() if args.cmd == "list" else cmd_match()
