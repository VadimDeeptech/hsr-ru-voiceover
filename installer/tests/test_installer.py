# -*- coding: utf-8 -*-
"""
Тест установщика на подставной папке игры. Настоящая игра только читается (копируются pck).

  python installer\\tests\\test_installer.py --work <пустая папка> [--pck NAME --pck NAME]

Нужно: собранный установщик (dotnet build installer -c Release), repack\\m, pck_out_m (шаг 12)
и игра (config.GAME_AUDIO). pck_out_m — эталон: установщик должен дать побайтно тот же pck.
Пол f — синтетический (часть wem изменена, одного нет), эталон для него считает ref_patch —
та же логика, что в 12_repack_pck.py.
"""
import os, sys, csv, shutil, struct, argparse, subprocess, hashlib

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import config

EXE = os.path.join(ROOT, "installer", "bin", "Release", "net48", "HSR-RU-Voiceover.exe")
PACKAGE = os.path.join(ROOT, "scripts", "14_package.py")
DEFAULT_PCKS = ["External_del_4.2_side5_zhounian.pck", "External_del_1.1_sidex_ag1.pck"]

ap = argparse.ArgumentParser()
ap.add_argument("--work", required=True)
ap.add_argument("--pck", action="append")
args = ap.parse_args()
PCKS = args.pck or DEFAULT_PCKS
WORK = os.path.abspath(args.work)
if os.path.commonpath([WORK, ROOT]) == ROOT:
    sys.exit("--work должна быть вне проекта")

GAME = os.path.join(WORK, "game")
AUDIO = os.path.join(GAME, "StarRail_Data", "Persistent", "Audio", "AudioPackage", "Windows", "English")
ORIG = os.path.join(WORK, "orig")
STATE = os.path.join(WORK, "state")
REPACK = os.path.join(WORK, "repack")
DIST = os.path.join(WORK, "dist")

failures = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def read(p):
    with open(p, "rb") as f:
        return f.read()


def sha(p):
    return hashlib.sha256(read(p)).hexdigest()


# ---------- эталон: логика 12_repack_pck.py ----------
def ref_patch(orig, wems):
    data = bytearray(orig)
    lang, banks, sounds = struct.unpack_from("<III", data, 12)
    pos = 28 + lang + banks + sounds
    n = struct.unpack_from("<I", data, pos)[0]
    table = {}
    for i in range(n):
        e = pos + 4 + i * 24
        id2, id1 = struct.unpack_from("<II", data, e)
        table[f"{id1:08x}{id2:08x}"] = e
    for wid, wem in wems:
        e = table.get(wid)
        if e is None:
            continue
        data += b"\x00" * ((-len(data)) % 16)
        struct.pack_into("<I", data, e + 12, len(wem))
        struct.pack_into("<I", data, e + 16, len(data))
        data += wem
    return bytes(data)


def run(cmd, gender=None, data=None, crash=None):
    a = [EXE, cmd, "--game", GAME, "--state", STATE]
    if gender:
        a += ["--gender", gender]
    if data:
        a += ["--data", data]
    env = dict(os.environ)
    env.pop("HSRVO_TEST_CRASH", None)
    if crash:
        env["HSRVO_TEST_CRASH"] = crash
    p = subprocess.run(a, capture_output=True, env=env)
    out = p.stdout.decode("utf-8", "replace")
    return p.returncode, out


def reset():
    """Как после «проверки целостности» в лаунчере и без данных установщика."""
    for p in PCKS:
        shutil.copy2(os.path.join(ORIG, p), os.path.join(AUDIO, p))
    shutil.rmtree(STATE, ignore_errors=True)


def files_equal(expected, label):
    ok = all(read(os.path.join(AUDIO, p)) == expected[p] for p in PCKS)
    check(ok, label)


def state_files():
    return [f for _, _, fs in os.walk(STATE) for f in fs if f.endswith(".state")]


# ---------- подготовка ----------
if not os.path.isfile(EXE):
    sys.exit(f"нет {EXE}")
if os.path.exists(WORK):
    shutil.rmtree(WORK)
os.makedirs(AUDIO)
os.makedirs(ORIG)
open(os.path.join(GAME, "StarRail.exe"), "wb").close()

pck_out = os.path.join(config.RUN, "pck_out_m")
for p in PCKS:
    src = os.path.join(config.GAME_AUDIO, p)
    built = os.path.join(pck_out, p)
    if not (os.path.isfile(src) and os.path.isfile(built)):
        sys.exit(f"нет {src} или {built}")
    if read(src) == read(built):
        sys.exit(f"в игре стоит мод ({p} = pck_out_m): тесту нужен оригинал — удалите мод установщиком")
    if os.path.getmtime(built) < os.path.getmtime(src):
        sys.exit(f"{built} собран раньше, чем игра обновила {p}: эталон устарел")
    shutil.copy2(src, os.path.join(ORIG, p))

# синтетический repack: m — настоящие wem, f — часть изменена, одного нет
id2pck = {r["wem_id"].lower(): r["pck"] for r in csv.DictReader(
    open(os.path.join(config.REPACK, "id_to_pck.csv"), encoding="utf-8-sig"), delimiter=";")}
rows = [r for r in csv.DictReader(open(os.path.join(config.REPACK, "repack_list.csv"), encoding="utf-8-sig"), delimiter=";")
        if id2pck.get(r["wem_id"].lower()) in PCKS]
os.makedirs(os.path.join(REPACK, "m"))
os.makedirs(os.path.join(REPACK, "f"))
with open(os.path.join(REPACK, "repack_list.csv"), "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
    w.writeheader()
    w.writerows(rows)
with open(os.path.join(REPACK, "id_to_pck.csv"), "w", encoding="utf-8", newline="") as f:
    f.write("wem_id;pck\n")
    for r in rows:
        f.write(f"{r['wem_id'].lower()};{id2pck[r['wem_id'].lower()]}\n")

built_ids = [r["wem_id"].lower() for r in rows if os.path.exists(os.path.join(config.REPACK, "m", r["wem_id"].lower() + ".wem"))]
changed, dropped = set(built_ids[0:3]), built_ids[3]
for wid in built_ids:
    b = read(os.path.join(config.REPACK, "m", wid + ".wem"))
    open(os.path.join(REPACK, "m", wid + ".wem"), "wb").write(b)
    if wid == dropped:
        continue
    open(os.path.join(REPACK, "f", wid + ".wem"), "wb").write(b[::-1] + b"F" if wid in changed else b)

expected = {}
for g in ("m", "f"):
    expected[g] = {}
    for p in PCKS:
        wems = [(r["wem_id"].lower(), read(os.path.join(REPACK, g, r["wem_id"].lower() + ".wem")))
                for r in rows if id2pck[r["wem_id"].lower()] == p
                and os.path.exists(os.path.join(REPACK, g, r["wem_id"].lower() + ".wem"))]
        expected[g][p] = ref_patch(read(os.path.join(ORIG, p)), wems)
orig = {p: read(os.path.join(ORIG, p)) for p in PCKS}


def package(version):
    rc = subprocess.call([sys.executable, PACKAGE, "--repack", REPACK, "--out", DIST, "--version", version, "--no-build"],
                         stdout=subprocess.DEVNULL)
    if rc != 0:
        sys.exit(f"14_package.py: код {rc}")
    return os.path.join(DIST, f"HSR-RU-Voiceover-{version}", "data")


print(f"pck: {', '.join(PCKS)}; реплик {len(rows)}, wem {len(built_ids)}")
PKG1, PKG2 = package("t1"), package("t2")

print("\n[эталон]")
check(all(expected["m"][p] == read(os.path.join(pck_out, p)) for p in PCKS),
      "ref_patch(m) совпадает с pck_out_m от 12_repack_pck.py")
info = open(os.path.join(PKG1, "package.txt"), encoding="utf-8").read()
check("blob=m.bin" in info and "blob=f.bin" in info and "blob=common.bin" in info, "в пакете есть common/m/f")

print("\n[установка, повтор, смена пола, откат]")
reset()
rc, out = run("install", "m", PKG1)
check(rc == 0, f"install m: код {rc}")
files_equal(expected["m"], "pck = pck_out_m (побайтно)")
sizes = [os.path.getsize(os.path.join(AUDIO, p)) for p in PCKS]
rc, out = run("install", "m", PKG1)
check(rc == 0 and "уже были актуальны: 2" in out, "повтор: ничего не делает")
check([os.path.getsize(os.path.join(AUDIO, p)) for p in PCKS] == sizes, "повтор: файлы не выросли")
files_equal(expected["m"], "повтор: pck не изменились")
rc, out = run("status")
check("t1 / мужской: 2 pck" in out, "status")
rc, out = run("install", "f", PKG1)
check(rc == 0, f"install f: код {rc}")
files_equal(expected["f"], "смена пола на f = эталон f")
rc, out = run("install", "m", PKG1)
files_equal(expected["m"], "обратно на m = pck_out_m")
rc, out = run("install", "m", PKG2)
check(rc == 0, "новая версия пакета: код 0")
files_equal(expected["m"], "новая версия: переустановлено, pck = pck_out_m")
rc, out = run("uninstall")
check(rc == 0, f"uninstall: код {rc}")
files_equal(orig, "откат = оригинал (побайтно)")
check(not state_files(), "после отката состояния нет")
rc, out = run("uninstall")
check(rc == 0 and "откатывать нечего" in out, "повторный откат: нечего откатывать")

print("\n[игра обновила файл]")
reset()
run("install", "m", PKG1)
shutil.copy2(os.path.join(ORIG, PCKS[0]), os.path.join(AUDIO, PCKS[0]))   # лаунчер вернул оригинал
rc, out = run("install", "m", PKG1)
check(rc == 0, "после восстановления оригинала: код 0")
files_equal(expected["m"], "после восстановления оригинала: мод на месте")
# новая версия pck: другая таблица (изменено поле записи, которой нет в моде) и длина
a = PCKS[0]
v2 = bytearray(orig[a])
lang, banks, sounds = struct.unpack_from("<III", v2, 12)
pos = 28 + lang + banks + sounds
n = struct.unpack_from("<I", v2, pos)[0]
mod_ids = {r["wem_id"].lower() for r in rows}
for i in range(n):
    e = pos + 4 + i * 24
    id2, id1 = struct.unpack_from("<II", v2, e)
    if f"{id1:08x}{id2:08x}" not in mod_ids:
        struct.pack_into("<I", v2, e + 20, struct.unpack_from("<I", v2, e + 20)[0] ^ 1)
        break
else:
    # все записи pck — наши: меняем заголовок (version)
    struct.pack_into("<I", v2, 8, struct.unpack_from("<I", v2, 8)[0] ^ 1)
v2 = bytes(v2) + b"\x00" * 32
open(os.path.join(AUDIO, a), "wb").write(v2)
rc, out = run("install", "m", PKG1)
check(rc == 0 and "файл обновлён игрой" in out, "новая версия pck: распознана")
exp_v2 = dict(expected["m"])
exp_v2[a] = ref_patch(v2, [(r["wem_id"].lower(), read(os.path.join(REPACK, "m", r["wem_id"].lower() + ".wem")))
                          for r in rows if id2pck[r["wem_id"].lower()] == a
                          and os.path.exists(os.path.join(REPACK, "m", r["wem_id"].lower() + ".wem"))])
files_equal(exp_v2, "новая версия pck: мод поставлен заново, = эталон")
run("uninstall")
check(read(os.path.join(AUDIO, a)) == v2, "откат новой версии = новая версия, а не старый оригинал")
# игра заменила файл, пока стоял мод, затем откат: старый бэкап не применяется
reset()
run("install", "m", PKG1)
open(os.path.join(AUDIO, a), "wb").write(v2)
rc, out = run("uninstall")
check(rc == 0 and "игра уже заменила файл" in out, "откат после обновления: распознано")
check(read(os.path.join(AUDIO, a)) == v2, "откат после обновления: файл игры не тронут")

print("\n[обрыв установки]")
for stage in ("append", "entries"):
    reset()
    rc, out = run("install", "m", PKG1, crash=stage)
    check(rc == 99, f"{stage}: установка оборвана (код {rc})")
    check(read(os.path.join(AUDIO, PCKS[0])) != orig[PCKS[0]], f"{stage}: pck изменён наполовину")
    rc, out = run("uninstall")
    files_equal(orig, f"{stage}: откат после обрыва = оригинал")
    run("install", "m", PKG1, crash=stage)
    rc, out = run("install", "m", PKG1)
    check(rc == 0, f"{stage}: установка после обрыва: код {rc}")
    files_equal(expected["m"], f"{stage}: установка после обрыва = pck_out_m")

print("\n[потеряны данные для отката]")
reset()
run("install", "m", PKG1)
shutil.rmtree(STATE)
rc, out = run("install", "m", PKG1)
check(rc == 0 and "данных для отката нет" in out, "предупреждение")
files_equal(expected["m"], "второй раз не дописано")

print("\n[реплики нет в pck игры]")
reset()
pkg_missing = os.path.join(WORK, "pkg_missing")
shutil.copytree(PKG1, pkg_missing)
with open(os.path.join(pkg_missing, "index.csv"), "a", encoding="utf-8", newline="") as f:
    f.write(f"{PCKS[0]};deadbeefdeadbeef;common;0;16\n")
rc, out = run("install", "m", pkg_missing)
check(rc == 0 and "нет в таблице deadbeefdeadbeef" in out, "пропуск с предупреждением")
files_equal(expected["m"], "остальное установлено = pck_out_m")

print("\n[pck нет в игре]")
reset()
os.rename(os.path.join(AUDIO, PCKS[1]), os.path.join(WORK, "moved.pck"))
rc, out = run("install", "m", PKG1)
check(rc == 0 and f"{PCKS[1]}: нет в игре" in out, "пропуск с предупреждением")
check(read(os.path.join(AUDIO, PCKS[0])) == expected["m"][PCKS[0]], "другой pck установлен")
os.rename(os.path.join(WORK, "moved.pck"), os.path.join(AUDIO, PCKS[1]))

print("\n[битый пакет]")
reset()
pkg_bad = os.path.join(WORK, "pkg_bad")
shutil.copytree(PKG1, pkg_bad)
with open(os.path.join(pkg_bad, "common.bin"), "r+b") as f:
    f.seek(100)
    c = f.read(1)
    f.seek(100)
    f.write(bytes([c[0] ^ 0xFF]))
rc, out = run("install", "m", pkg_bad)
check(rc == 1 and "повреждён" in out, "отказ с сообщением")
files_equal(orig, "игра не тронута")

print("\n[игра запущена]")
reset()
fake = os.path.join(WORK, "StarRail.exe")
shutil.copy2(os.path.join(os.environ["SystemRoot"], "System32", "PING.EXE"), fake)
proc = subprocess.Popen([fake, "-n", "30", "127.0.0.1"], stdout=subprocess.DEVNULL)
try:
    rc, out = run("install", "m", PKG1)
    check(rc == 1 and "Игра запущена" in out, "отказ")
    files_equal(orig, "игра не тронута")
finally:
    proc.kill()
    proc.wait()

print()
if failures:
    print(f"ПРОВАЛЕНО: {len(failures)}")
    for f in failures:
        print("  - " + f)
    sys.exit(1)
print("Все проверки пройдены")
