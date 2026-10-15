using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace HsrRuVoiceover
{
    /// <summary>
    /// Состояние одного pck в игре: всё, что нужно для отката (исходная длина и исходные
    /// 24-байтные записи), и отпечаток после установки, чтобы узнать файл, который заменила игра.
    /// Хранится в %LOCALAPPDATA%\HSR-RU-Voiceover\..., не в папке игры.
    /// </summary>
    sealed class PckState
    {
        public const string Installing = "installing";
        public const string Installed = "installed";

        public string Name;
        public string Status;
        public string Version;
        public string Gender;
        public string Fingerprint;
        public long OrigLength;
        public string OrigTable;        // sha256 таблицы externals до установки
        public long InstalledLength;
        public string InstalledTable;   // sha256 таблицы после установки
        public List<KeyValuePair<int, byte[]>> Entries = new List<KeyValuePair<int, byte[]>>();

        static string PathFor(string dir, string name) => Path.Combine(dir, name + ".state");

        public static IEnumerable<string> Names(string dir) =>
            Directory.Exists(dir)
                ? Directory.GetFiles(dir, "*.state").Select(f => Path.GetFileNameWithoutExtension(f))
                : Enumerable.Empty<string>();

        public static PckState Load(string dir, string name)
        {
            var path = PathFor(dir, name);
            if (!File.Exists(path)) return null;
            var s = new PckState { Name = name };
            foreach (var line in File.ReadAllLines(path, Encoding.UTF8))
            {
                int eq = line.IndexOf('=');
                if (eq < 0) continue;
                string k = line.Substring(0, eq), v = line.Substring(eq + 1);
                switch (k)
                {
                    case "status": s.Status = v; break;
                    case "version": s.Version = v; break;
                    case "gender": s.Gender = v; break;
                    case "fingerprint": s.Fingerprint = v; break;
                    case "orig_length": s.OrigLength = long.Parse(v, CultureInfo.InvariantCulture); break;
                    case "orig_table": s.OrigTable = v; break;
                    case "installed_length": s.InstalledLength = long.Parse(v, CultureInfo.InvariantCulture); break;
                    case "installed_table": s.InstalledTable = v; break;
                    case "entry":
                        var c = v.Split(':');
                        s.Entries.Add(new KeyValuePair<int, byte[]>(int.Parse(c[0], CultureInfo.InvariantCulture), FromHex(c[1])));
                        break;
                }
            }
            if (s.Status == null || s.OrigTable == null)
                throw new InvalidDataException("Повреждён файл состояния " + path);
            return s;
        }

        /// <summary>Запись через временный файл: на диске либо старое состояние, либо новое целиком.</summary>
        public void Save(string dir)
        {
            Directory.CreateDirectory(dir);
            var sb = new StringBuilder();
            sb.Append("status=").Append(Status).Append('\n');
            sb.Append("version=").Append(Version).Append('\n');
            sb.Append("gender=").Append(Gender).Append('\n');
            sb.Append("fingerprint=").Append(Fingerprint).Append('\n');
            sb.Append("orig_length=").Append(OrigLength.ToString(CultureInfo.InvariantCulture)).Append('\n');
            sb.Append("orig_table=").Append(OrigTable).Append('\n');
            sb.Append("installed_length=").Append(InstalledLength.ToString(CultureInfo.InvariantCulture)).Append('\n');
            sb.Append("installed_table=").Append(InstalledTable).Append('\n');
            foreach (var e in Entries)
                sb.Append("entry=").Append(e.Key.ToString(CultureInfo.InvariantCulture)).Append(':').Append(AkpkTable.Hex(e.Value)).Append('\n');

            var path = PathFor(dir, Name);
            var tmp = path + ".tmp";
            var data = new UTF8Encoding(false).GetBytes(sb.ToString());
            using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                fs.Write(data, 0, data.Length);
                fs.Flush(true);
            }
            if (File.Exists(path)) File.Replace(tmp, path, null);
            else File.Move(tmp, path);
        }

        public static void Delete(string dir, string name)
        {
            var path = PathFor(dir, name);
            if (File.Exists(path)) File.Delete(path);
        }

        static byte[] FromHex(string s)
        {
            var b = new byte[s.Length / 2];
            for (int i = 0; i < b.Length; i++)
                b[i] = byte.Parse(s.Substring(i * 2, 2), NumberStyles.HexNumber, CultureInfo.InvariantCulture);
            return b;
        }
    }
}
