# -*- coding: utf-8 -*-
"""
05_generate.py — генерация RU-озвучки через CosyVoice (cross_lingual, :8020).
- разметка: {RUBY_B#аннотация}текст{RUBY_E#} -> только текст; {F#}/{M#} -> по полу;
  {NICKNAME}/{TEXTJOIN#54} -> имя; <color>/<unbreak>/<size>/<i> -> выкидываем
- гендерные строки (теги в тексте) -> пара файлов <name>__m.wav и <name>__f.wav
- гендерные ФАЙЛЫ (<name>_m/_f.wav, колонка gender в CSV) -> ОДИН вариант,
  текст чистится под свой пол, референс — свой же (m-файл из m-референса)
- строки без текста (дубли Ag1) -> текст из двойника (персонаж+номер)
- резюмируемый

Запуск:
    python 05_generate.py --chapter 0        # только chapter0
    python 05_generate.py --all              # все найденные главы
    python 05_generate.py --category side0   # только side0
    python 05_generate.py --all-categories   # все категории
    python 05_generate.py --all --limit 20   # тестовый прогон
"""
import os, io, csv, re, time, wave, struct, subprocess, argparse
import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from utils import decisions

DECISIONS = decisions.load()

NICK  = {"m": "Первопроходец", "f": "Первопроходчица"}
GENDER_RE = re.compile(r"\{[FM]#|\{NICKNAME|\{TEXTJOIN#54", re.I)
NAME_RE   = re.compile(r"(?:chapter|side|companion)\w*?_(.+?)_([a-z][a-z0-9]*)_(\d+)(?:_[a-z])?$", re.I)
WORD_RE   = re.compile(r"[^\W_]")   # хоть одна буква или цифра; "...", "?!", "♪", "███" — не слова
REMARK_RE = re.compile(r"\*[^*]+\*")  # весь текст — ремарка: *бормотание титана*, *Зевок*

MAX_REF_SEC   = 29.0   # CosyVoice не принимает образец голоса длиннее 30 с
SCENE_MIN_CPS = 3.0    # символов текста на секунду оригинала; ниже — сцена с однострочным субтитром

def clean_text(text, gender="m"):
    text = re.sub(r"\{RUBY_B#[^}]*\}([^{]*)\{RUBY_E#\}", r"\1", text)
    text = re.sub(r"\{F#([^}]*)\}\{M#([^}]*)\}",
                  lambda m: m.group(1) if gender == "f" else m.group(2), text)
    text = re.sub(r"\{F#([^}]*)\}", lambda m: m.group(1) if gender == "f" else "", text)
    text = re.sub(r"\{M#([^}]*)\}", lambda m: "" if gender == "f" else m.group(1), text)
    text = re.sub(r"\{(NICKNAME|PLAYER_NAME|MC_NAME)\}", NICK[gender], text, flags=re.I)
    text = re.sub(r"\{TEXTJOIN#54\}", NICK[gender], text, flags=re.I)
    text = re.sub(r"\{TEXTJOIN#(\d+)\}",
                  lambda m: print(f"  !! неизвестный TEXTJOIN#{m.group(1)}") or "", text)
    text = re.sub(r"</?[^>]+>", "", text)           # <color>, <unbreak>, <size>, <i>...
    text = re.sub(r"\\n|\t", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def is_wordless(text):
    """Текст, который нечем озвучить: нет букв/цифр или это целиком ремарка в *звёздочках*."""
    return not WORD_RE.search(text) or bool(REMARK_RE.fullmatch(text))

def ref_audio(src, orig):
    """Образец голоса для CosyVoice: файл целиком или его первые MAX_REF_SEC секунд."""
    if not orig or orig <= MAX_REF_SEC:
        with open(src, "rb") as f:
            return f.read()
    try:
        with wave.open(src, "rb") as w:
            params = w.getparams()
            frames = w.readframes(int(params.framerate * MAX_REF_SEC))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as o:
            o.setparams(params)
            o.writeframes(frames)
        return buf.getvalue()
    except (wave.Error, EOFError):
        # не-PCM wav: режем через ffmpeg
        r = subprocess.run(["ffmpeg", "-v", "quiet", "-i", src, "-t", str(MAX_REF_SEC), "-f", "wav", "-"],
                           capture_output=True, timeout=60)
        r.check_returncode()
        return r.stdout

def wav_duration(path):
    try:
        with open(path, "rb") as f:
            if f.read(12)[:4] != b"RIFF": return ffprobe_duration(path)
            byte_rate = None
            while True:
                hdr = f.read(8)
                if len(hdr) < 8: break
                cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
                if cid == b"fmt ":
                    byte_rate = struct.unpack("<I", f.read(size)[8:12])[0]
                    if size % 2: f.read(1)
                elif cid == b"data" and byte_rate:
                    return size / byte_rate
                else:
                    f.seek(size + (size % 2), 1)
    except Exception:
        pass
    return ffprobe_duration(path)

def ffprobe_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", path],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return None

def name_key(basename):
    m = NAME_RE.match(basename.lower())
    return (m.group(2), m.group(3)) if m else None

def row_gender(r, base):
    """Пол из колонки gender; fallback — суффикс имени файла (для старого chapter0.csv)."""
    g = (r.get("gender") or "").strip().lower()
    if g in ("m", "f"):
        return g, False
    b = base.lower()
    if len(b) > 2 and b[-2] == "_" and b[-1] in "mf":
        return b[-1], True
    return "", False

def generate_chapter(csv_name, out_name, limit=None):
    """Генерация одной категории. Возвращает (done, skip, fail)."""
    csv_path = os.path.join(config.RUN, csv_name)
    out_dir  = os.path.join(config.RUN, "output_ru", out_name)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(csv_path):
        print(f"  нет {csv_path} — пропуск")
        return 0, 0, 0

    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig"), delimiter=";"))

    # двойники: (персонаж, номер) -> текст (для строк без своего текста)
    by_key = {}
    for r in rows:
        if not r["text_ru"].strip(): continue
        k = name_key(os.path.splitext(os.path.basename(r["file"]))[0])
        if k: by_key.setdefault(k, r["text_ru"])

    tasks, gendered, wordless, kept, fallback_warned = [], 0, 0, 0, False
    for r in rows:
        base = os.path.splitext(os.path.basename(r["file"]))[0]
        if (decisions.find(DECISIONS, base) or ("",))[0] == "keep":
            # ручное решение из audit_decisions.csv: в игре остаётся оригинал
            kept += 1
            continue
        text = r["text_ru"].strip()
        if not text:
            k = name_key(base)
            text = by_key.get(k, "") if k else ""
            if text:
                print(f"  дубль {base}: текст из двойника {k}")
            else:
                print(f"  !! нет текста и двойника: {base} — пропуск")
                continue

        if is_wordless(clean_text(text)):
            # вздох, пауза, ремарка, зацензуренная речь — озвучивать нечего, в игре остаётся оригинал
            wordless += 1
            continue

        g, from_suffix = row_gender(r, base)
        if from_suffix and "gender" not in r and not fallback_warned:
            print("  !! в csv нет колонки gender — вывожу из суффикса имени.")
            print("     Лучше пересобрать: pipeline.py map -> pipeline.py scan")
            fallback_warned = True

        if g in ("m", "f"):
            # гендер зашит в сам файл: один вариант из своего референса
            tasks.append((r, base, clean_text(text, g)))
        elif GENDER_RE.search(text):
            gendered += 1
            tasks.append((r, base + "__m", clean_text(text, "m")))
            tasks.append((r, base + "__f", clean_text(text, "f")))
        else:
            tasks.append((r, base, clean_text(text, "m")))

    if limit:
        tasks = tasks[:limit]
    print(f"{out_name}: задач {len(tasks)} (текстово-гендерных строк: {gendered}), "
          f"без слов — оставлен оригинал: {wordless}"
          + (f", оригинал по решению: {kept}" if kept else ""))

    rep_path = os.path.join(out_dir, "gen_report.csv")
    new_rep = not os.path.exists(rep_path)
    done = fail = skip = scenes = 0
    with open(rep_path, "a", encoding="utf-8-sig", newline="") as rep:
        wr = csv.writer(rep, delimiter=";")
        if new_rep:
            wr.writerow(["file", "status", "orig_sec", "gen_sec", "ratio", "sec_taken", "note"])
        for i, (r, out_name_wav, text) in enumerate(tasks, 1):
            dst = os.path.join(out_dir, out_name_wav + ".wav")
            if os.path.exists(dst):
                skip += 1; continue
            src = os.path.join(config.DATASET, r["file"])
            orig = wav_duration(src)
            if orig and orig > MAX_REF_SEC and len(text) / orig < SCENE_MIN_CPS:
                # длинная сцена, к которой в данных игры привязана одна строка субтитра:
                # озвучка заменила бы минуту звука парой секунд — оставляем оригинал
                scenes += 1; continue
            t0 = time.time()
            try:
                resp = requests.post(config.COSYVOICE_URL + "/tts",
                                     data={"text": text, "mode": "cross_lingual",
                                           "response_format": "wav"},
                                     files={"voice": (os.path.basename(src), ref_audio(src, orig), "audio/wav")},
                                     timeout=300)
                took = time.time() - t0
                if resp.status_code == 200:
                    with open(dst, "wb") as f: f.write(resp.content)
                    done += 1
                    g = wav_duration(dst)
                    wr.writerow([r["file"], "OK", f"{orig:.2f}" if orig else "?",
                                 f"{g:.2f}" if g else "?",
                                 f"{g/orig:.2f}" if g and orig else "", f"{took:.1f}", out_name_wav])
                else:
                    fail += 1
                    wr.writerow([r["file"], f"HTTP {resp.status_code}", "", "", "", f"{took:.1f}", resp.text[:150]])
            except Exception as e:
                fail += 1
                wr.writerow([r["file"], "EXC", "", "", "", "", str(e)[:150]])
            rep.flush()
            if i % 10 == 0 or i == len(tasks):
                print(f"[{i}/{len(tasks)}] ok={done} skip={skip} fail={fail}")
            time.sleep(0.3)
    print(f"{out_name}: {done} сгенерировано, {skip} пропущено, {fail} ошибок"
          + (f", длинных сцен — оставлен оригинал: {scenes}" if scenes else ""))
    return done, skip, fail

def main():
    ap = argparse.ArgumentParser(description="Генерация RU-озвучки")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--chapter", type=int, help="номер главы")
    g.add_argument("--all", action="store_true", help="все найденные главы")
    g.add_argument("--category", type=str, help="конкретная категория (side0, companion1, vo, ...)")
    g.add_argument("--all-categories", action="store_true",
                   help="все категории (chapters + sides + companions + vo + ambient + archive + ...)")
    ap.add_argument("--limit", type=int, default=None, help="лимит задач (для теста)")
    args = ap.parse_args()

    # --- Режим --chapter / --all (только главы) ---
    if args.chapter is not None or args.all:
        chapters = []
        if args.all:
            # авто-скан: какие chapterN.csv есть в hsr-run-voice
            for f in os.listdir(config.RUN):
                m = re.match(r"chapter(\d+)\.csv$", f)
                if m:
                    chapters.append(int(m.group(1)))
            chapters.sort()
            if not chapters:
                print("Не найдено ни одного chapterN.csv. Сначала запусти: pipeline.py scan --all")
                sys.exit(1)
        else:
            chapters = [args.chapter]

        total_done = total_skip = total_fail = 0
        for ch in chapters:
            d, s, f = generate_chapter(f"chapter{ch}.csv", f"chapter{ch}", args.limit)
            total_done += d; total_skip += s; total_fail += f

        print(f"\n=== ИТОГО: {total_done} сгенерировано, {total_skip} пропущено, {total_fail} ошибок ===")
        return

    # --- Режим --category ---
    if args.category:
        d, s, f = generate_chapter(f"{args.category}.csv", args.category, args.limit)
        print(f"\n=== ИТОГО: {d} сгенерировано, {s} пропущено, {f} ошибок ===")
        return

    # --- Режим --all-categories ---
    if args.all_categories:
        # Находим все *.csv в RUN, которые не mapping.csv
        all_csvs = [f for f in os.listdir(config.RUN)
                    if f.endswith(".csv") and f != "mapping.csv"]
        # Сначала главы
        chapters = sorted([c for c in all_csvs if re.match(r"chapter\d+\.csv$", c)],
                          key=lambda x: int(re.search(r"\d+", x).group()))
        # Потом остальные
        others = sorted([c for c in all_csvs if not re.match(r"chapter\d+\.csv$", c)])

        total_done = total_skip = total_fail = 0
        for csv_name in chapters + others:
            cat_name = csv_name[:-4]  # без .csv
            d, s, f = generate_chapter(csv_name, cat_name, args.limit)
            total_done += d; total_skip += s; total_fail += f

        print(f"\n=== ИТОГО: {total_done} сгенерировано, {total_skip} пропущено, {total_fail} ошибок ===")

if __name__ == "__main__":
    main()
