using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;

namespace HsrRuVoiceover
{
    /// <summary>Ошибка, которую нужно показать игроку как есть (без стека).</summary>
    class UserError : Exception { public UserError(string m) : base(m) { } }
    sealed class AccessError : UserError { public AccessError(string m) : base(m) { } }

    sealed class Report
    {
        public int Installed, UpToDate, Reinstalled, Replaced, RolledBack, MissingPck, MissingIds, NoBackup, Errors;
    }

    /// <summary>
    /// Патч pck игры на месте — тот же, что делает 12_repack_pck.py: wem дописывается в конец pck
    /// (выравнивание 16), в его записи меняются size/offset. Бэкап — только исходная длина файла
    /// и исходные записи. Откат — вернуть записи и обрезать файл до исходной длины.
    /// </summary>
    sealed class Engine
    {
        enum Kind { Installed, Ours, Foreign }

        public const string GameProcess = "StarRail";

        readonly string audioDir, stateDir;
        readonly Action<string> log;
        readonly Action<long, long> progress;
        public Report Report { get; } = new Report();

        // только для тестов: оборвать установку посреди записи (append | entries)
        static readonly string testCrash = Environment.GetEnvironmentVariable("HSRVO_TEST_CRASH");

        public Engine(string audioDir, string stateDir, Action<string> log, Action<long, long> progress)
        {
            this.audioDir = audioDir;
            this.stateDir = stateDir;
            this.log = log ?? (_ => { });
            this.progress = progress ?? ((_, __) => { });
        }

        public static string AudioDir(string gameDir) =>
            Path.Combine(gameDir, "StarRail_Data", "Persistent", "Audio", "AudioPackage", "Windows", "English");

        public static string DefaultStateRoot =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "HSR-RU-Voiceover");

        /// <summary>Своя папка состояния на каждую папку игры (их может быть несколько).</summary>
        public static string StateDirFor(string stateRoot, string audioDir)
        {
            var full = Path.GetFullPath(audioDir).TrimEnd('\\').ToLowerInvariant();
            var dir = Path.Combine(stateRoot, "games", AkpkTable.Sha256Hex(Encoding.UTF8.GetBytes(full)).Substring(0, 12));
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "game.txt"), audioDir + "\n", Encoding.UTF8);
            return dir;
        }

        public static void EnsureGameClosed()
        {
            if (Process.GetProcessesByName(GameProcess).Length > 0)
                throw new UserError("Игра запущена. Закройте Honkai: Star Rail и повторите.");
        }

        /// <summary>Можно ли писать в папку игры без прав администратора.</summary>
        public static bool CanWrite(string audioDir)
        {
            var probe = Path.Combine(audioDir, ".hsrvo_write_test");
            try
            {
                File.WriteAllBytes(probe, new byte[0]);
                File.Delete(probe);
                return true;
            }
            catch (UnauthorizedAccessException) { return false; }
            catch (IOException) { return false; }
        }

        /// <summary>Сводка для окна: сколько pck сейчас с модом, какой версии и пола.</summary>
        public string Status()
        {
            var states = PckState.Names(stateDir).Select(n => PckState.Load(stateDir, n)).ToList();
            if (states.Count == 0) return "Мод не установлен";
            var g = states.GroupBy(s => s.Version + " / " + (s.Gender == "f" ? "женский" : "мужской"))
                          .Select(x => $"{x.Key}: {x.Count()} pck");
            return "Установлено: " + string.Join("; ", g);
        }

        public string InstalledGender() =>
            PckState.Names(stateDir).Select(n => PckState.Load(stateDir, n).Gender).FirstOrDefault();

        // ===================== установка =====================

        public void Install(Package pkg, string gender)
        {
            if (!pkg.Genders.Contains(gender))
                throw new UserError($"В этом пакете нет озвучки для выбранного пола ({gender})");
            if (!Directory.Exists(audioDir))
                throw new UserError("Не найдена папка английской озвучки игры: " + audioDir +
                                    "\nВ лаунчере должен быть скачан пакет озвучки English.");
            EnsureGameClosed();

            log("Проверка файлов пакета…");
            pkg.Verify(gender, progress);

            var groups = pkg.ForGender(gender);
            var fps = groups.ToDictionary(g => g.Key, g => pkg.Fingerprint(g.Value), StringComparer.OrdinalIgnoreCase);
            CheckFreeSpace(groups, fps);

            var blobs = pkg.VariantsFor(gender).ToDictionary(v => v,
                v => new FileStream(pkg.BlobPath(v), FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16));
            try
            {
                long total = groups.Sum(g => g.Value.Sum(i => (long)i.Size)), done = 0;
                log($"Установка: {groups.Count} pck, пол — {(gender == "f" ? "женский" : "мужской")}, версия {pkg.Version}");
                foreach (var g in groups)
                {
                    try { InstallPck(g.Key, g.Value, blobs, pkg, gender, fps[g.Key]); }
                    catch (UserError) { throw; }
                    catch (Exception e) when (e is IOException || e is InvalidDataException)
                    {
                        Report.Errors++;
                        log($"  !! {g.Key}: {e.Message}");
                    }
                    done += g.Value.Sum(i => (long)i.Size);
                    progress(done, total);
                }
            }
            finally
            {
                foreach (var b in blobs.Values) b.Dispose();
            }

            // pck, которые ставила прошлая версия, а в этой их нет, — вернуть оригинал
            foreach (var name in PckState.Names(stateDir).ToList())
                if (!fps.ContainsKey(name))
                    UninstallPck(name);

            var r = Report;
            log("");
            log($"Готово. Установлено pck: {r.Installed + r.Reinstalled}, уже были актуальны: {r.UpToDate}.");
            if (r.Replaced > 0) log($"Игра обновила {r.Replaced} pck после прошлой установки — мод поставлен в них заново.");
            if (r.RolledBack > 0) log($"Возвращён оригинал для {r.RolledBack} pck, которых нет в этой версии мода.");
            if (r.MissingIds > 0) log($"ВНИМАНИЕ: {r.MissingIds} реплик не найдено в pck игры (игра обновилась?) — для них остаётся оригинал.");
            if (r.MissingPck > 0) log($"ВНИМАНИЕ: {r.MissingPck} pck из мода нет в игре — пропущены.");
            if (r.NoBackup > 0) log($"ВНИМАНИЕ: в {r.NoBackup} pck мод уже стоит, но данных для отката нет (их удалили?). " +
                                    "Чтобы вернуть оригинал, выполните в лаунчере проверку целостности файлов.");
            if (r.Errors > 0) log($"ОШИБКИ: {r.Errors} pck не установлены, подробности выше.");
        }

        void CheckFreeSpace(List<KeyValuePair<string, List<PackageItem>>> groups, Dictionary<string, string> fps)
        {
            long need = 0;
            foreach (var g in groups)
            {
                var st = PckState.Load(stateDir, g.Key);
                if (st != null && st.Status == PckState.Installed && st.Fingerprint == fps[g.Key]) continue;
                need += g.Value.Sum(i => (long)i.Size + 16);
            }
            try
            {
                var free = new DriveInfo(Path.GetPathRoot(Path.GetFullPath(audioDir))).AvailableFreeSpace;
                if (free < need + (64L << 20))
                    throw new UserError($"Недостаточно места на диске с игрой: нужно {need >> 20} МБ, свободно {free >> 20} МБ.");
            }
            catch (ArgumentException) { /* сетевой путь: проверить нечем */ }
        }

        void InstallPck(string name, List<PackageItem> items, Dictionary<string, FileStream> blobs,
                        Package pkg, string gender, string fingerprint)
        {
            var path = Path.Combine(audioDir, name);
            if (!File.Exists(path))
            {
                Report.MissingPck++;
                PckState.Delete(stateDir, name);
                log($"  !! {name}: нет в игре — пропуск");
                return;
            }

            using (var fs = OpenGameFile(path))
            {
                var st = PckState.Load(stateDir, name);
                bool had = st != null;
                if (had)
                {
                    var kind = Classify(fs, st);
                    if (kind == Kind.Installed && st.Fingerprint == fingerprint)
                    {
                        Report.UpToDate++;
                        return;
                    }
                    if (kind == Kind.Foreign)
                    {
                        // игра заменила файл (обновление или проверка файлов): в нём свежий оригинал
                        Report.Replaced++;
                        log($"  {name}: файл обновлён игрой — ставлю заново");
                    }
                    else
                    {
                        // другая версия мода / другой пол / прерванная установка
                        Rollback(fs, st);
                        Report.Reinstalled++;
                    }
                    PckState.Delete(stateDir, name);
                }

                var table = AkpkTable.Read(fs);
                var targets = new List<KeyValuePair<int, PackageItem>>();
                foreach (var it in items)
                {
                    if (!table.TryFind(it.WemId, out int i))
                    {
                        Report.MissingIds++;
                        log($"  !! {name}: нет в таблице {it.WemId} — пропуск");
                        continue;
                    }
                    if (table.BlockSize(i) != 1)
                        throw new InvalidDataException($"blockSize {table.BlockSize(i)} у {it.WemId} — такой pck не поддерживается");
                    targets.Add(new KeyValuePair<int, PackageItem>(i, it));
                }
                if (targets.Count == 0) return;

                if (!had && AlreadyOurs(fs, table, targets, blobs))
                {
                    // мод уже в файле, а состояния нет: дописывать второй раз не нужно,
                    // но и откатить нечем — исходных записей нет
                    Report.NoBackup++;
                    log($"  !! {name}: мод уже установлен, данных для отката нет");
                    return;
                }

                var ns = new PckState
                {
                    Name = name, Status = PckState.Installing, Version = pkg.Version, Gender = gender,
                    Fingerprint = fingerprint, OrigLength = fs.Length, OrigTable = table.Hash(),
                    Entries = targets.Select(t => new KeyValuePair<int, byte[]>(t.Key, table.Entry(t.Key))).ToList(),
                };
                // сначала бэкап на диск, потом правка: прерванная установка откатится по нему
                ns.Save(stateDir);
                try
                {
                    Patch(fs, table, targets, blobs);
                }
                catch
                {
                    Rollback(fs, ns);
                    PckState.Delete(stateDir, name);
                    throw;
                }
                ns.Status = PckState.Installed;
                ns.InstalledLength = fs.Length;
                ns.InstalledTable = AkpkTable.Read(fs).Hash();
                ns.Save(stateDir);
                if (!had) Report.Installed++;
            }
        }

        static void Patch(FileStream fs, AkpkTable table, List<KeyValuePair<int, PackageItem>> targets,
                          Dictionary<string, FileStream> blobs)
        {
            long len = fs.Length;
            fs.Position = len;
            var placed = new List<KeyValuePair<int, long>>();
            var zeros = new byte[16];
            foreach (var t in targets)
            {
                int pad = (int)((16 - len % 16) % 16);
                fs.Write(zeros, 0, pad);
                len += pad;
                if (len + t.Value.Size > uint.MaxValue)
                    throw new IOException("pck вырос бы больше 4 ГБ — такой патч невозможен");
                var data = AkpkTable.ReadAt(blobs[t.Value.Variant], t.Value.Offset, t.Value.Size);
                fs.Write(data, 0, data.Length);
                placed.Add(new KeyValuePair<int, long>(t.Key, len));
                len += data.Length;
                if (testCrash == "append") { fs.Flush(true); Environment.Exit(99); }
            }
            // данные на диск раньше записей: записи не должны указывать на недописанное
            fs.Flush(true);

            for (int k = 0; k < placed.Count; k++)
            {
                var e = new byte[8];
                BitConverter.GetBytes((uint)targets[k].Value.Size).CopyTo(e, 0);
                BitConverter.GetBytes((uint)placed[k].Value).CopyTo(e, 4);
                fs.Position = table.EntryPos(placed[k].Key) + AkpkTable.SizeField;
                fs.Write(e, 0, e.Length);
                if (testCrash == "entries") { fs.Flush(true); Environment.Exit(99); }
            }
            fs.Flush(true);
        }

        /// <summary>Во всех записях уже наши wem (мод стоит, а состояние потеряно).</summary>
        static bool AlreadyOurs(FileStream fs, AkpkTable table, List<KeyValuePair<int, PackageItem>> targets,
                                Dictionary<string, FileStream> blobs)
        {
            foreach (var t in targets)
            {
                if (table.Size(t.Key) != t.Value.Size) return false;
                var have = AkpkTable.ReadAt(fs, table.Offset(t.Key), t.Value.Size);
                var ours = AkpkTable.ReadAt(blobs[t.Value.Variant], t.Value.Offset, t.Value.Size);
                if (!have.SequenceEqual(ours)) return false;
            }
            return true;
        }

        // ===================== откат =====================

        public void Uninstall()
        {
            EnsureGameClosed();
            var names = PckState.Names(stateDir).ToList();
            if (names.Count == 0)
            {
                log("Мод не установлен — откатывать нечего.");
                return;
            }
            int k = 0;
            foreach (var name in names)
            {
                try { UninstallPck(name); }
                catch (UserError) { throw; }
                catch (Exception e) when (e is IOException || e is InvalidDataException)
                {
                    Report.Errors++;
                    log($"  !! {name}: {e.Message}");
                }
                progress(++k, names.Count);
            }
            log("");
            log($"Готово. Возвращён оригинал: {Report.RolledBack} pck.");
            if (Report.Replaced > 0) log($"В {Report.Replaced} pck игра уже сама вернула оригинал (обновление или проверка файлов).");
            if (Report.Errors > 0) log($"ОШИБКИ: {Report.Errors} pck не откачены, подробности выше. " +
                                       "Вернуть оригинал можно проверкой целостности файлов в лаунчере.");
        }

        void UninstallPck(string name)
        {
            var path = Path.Combine(audioDir, name);
            if (!File.Exists(path))
            {
                PckState.Delete(stateDir, name);
                return;
            }
            using (var fs = OpenGameFile(path))
            {
                var st = PckState.Load(stateDir, name);
                if (Classify(fs, st) == Kind.Foreign)
                {
                    Report.Replaced++;
                    log($"  {name}: игра уже заменила файл — в нём оригинал");
                }
                else
                {
                    Rollback(fs, st);
                    Report.RolledBack++;
                }
                PckState.Delete(stateDir, name);
            }
        }

        // ===================== общее =====================

        /// <summary>
        /// Installed — файл ровно такой, каким мы его оставили.
        /// Ours — наш патч (в т.ч. прерванный): если вернуть исходные записи, таблица совпадёт с исходной.
        /// Foreign — файл заменила игра: откатывать нельзя, в нём и так оригинал.
        /// </summary>
        static Kind Classify(FileStream fs, PckState st)
        {
            AkpkTable t;
            try { t = AkpkTable.Read(fs); }
            catch (InvalidDataException) { return Kind.Foreign; }
            catch (EndOfStreamException) { return Kind.Foreign; }
            if (st.Status == PckState.Installed && fs.Length == st.InstalledLength && t.Hash() == st.InstalledTable)
                return Kind.Installed;
            if (fs.Length >= st.OrigLength && t.HashWith(st.Entries) == st.OrigTable)
                return Kind.Ours;
            return Kind.Foreign;
        }

        /// <summary>Сначала записи, потом длина: прерванный откат повторяется с тем же результатом.</summary>
        static void Rollback(FileStream fs, PckState st)
        {
            var t = AkpkTable.Read(fs);
            foreach (var e in st.Entries)
            {
                fs.Position = t.EntryPos(e.Key);
                fs.Write(e.Value, 0, e.Value.Length);
            }
            fs.Flush(true);
            fs.SetLength(st.OrigLength);
            fs.Flush(true);
        }

        static FileStream OpenGameFile(string path)
        {
            try
            {
                return new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None, 1 << 20);
            }
            catch (UnauthorizedAccessException)
            {
                throw new AccessError("Нет прав на запись в папку игры. Запустите установщик от имени администратора.");
            }
            catch (IOException e) when ((e.HResult & 0xFFFF) == 32 || (e.HResult & 0xFFFF) == 33)
            {
                throw new UserError("Файл игры занят другой программой: " + Path.GetFileName(path) +
                                    "\nЗакройте игру и лаунчер (или дождитесь окончания загрузки обновления) и повторите.");
            }
        }
    }
}
