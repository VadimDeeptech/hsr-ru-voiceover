using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace HsrRuVoiceover
{
    /// <summary>Одна наша реплика: в какой pck, какой wem_id и где её байты в .bin.</summary>
    sealed class PackageItem
    {
        public string Pck;
        public string WemId;
        public string Variant;   // common | m | f
        public long Offset;
        public int Size;
    }

    /// <summary>
    /// Пакет (собирает pipeline.py package):
    ///   package.txt — format, version, genders, blob=имя;размер;sha256
    ///   index.csv   — pck;wem_id;variant;offset;size в порядке repack_list.csv
    ///   common.bin  — wem, одинаковые для обоих полов; m.bin / f.bin — различающиеся.
    /// Порядок строк = порядок, в котором 12_repack_pck.py дописывает wem: от него зависит
    /// побайтное совпадение pck.
    /// </summary>
    sealed class Package
    {
        public const int SupportedFormat = 1;

        public string Dir { get; private set; }
        public string Version { get; private set; }
        public IList<string> Genders { get; private set; }
        public IList<PackageItem> Items { get; private set; }
        readonly Dictionary<string, KeyValuePair<long, string>> blobs = new Dictionary<string, KeyValuePair<long, string>>();

        public static Package Load(string dir)
        {
            var info = Path.Combine(dir, "package.txt");
            var idx = Path.Combine(dir, "index.csv");
            if (!File.Exists(info) || !File.Exists(idx))
                throw new FileNotFoundException("Не найдены файлы пакета (package.txt, index.csv) в " + dir);

            var p = new Package { Dir = dir };
            int format = 0;
            foreach (var line in File.ReadAllLines(info, Encoding.UTF8))
            {
                int eq = line.IndexOf('=');
                if (line.StartsWith("#") || eq < 0) continue;
                string k = line.Substring(0, eq).Trim(), v = line.Substring(eq + 1).Trim();
                switch (k)
                {
                    case "format": format = int.Parse(v); break;
                    case "version": p.Version = v; break;
                    case "genders": p.Genders = v.Split(',').Select(s => s.Trim()).Where(s => s != "").ToList(); break;
                    case "blob":
                        var b = v.Split(';');
                        p.blobs[b[0]] = new KeyValuePair<long, string>(long.Parse(b[1]), b[2].ToLowerInvariant());
                        break;
                }
            }
            if (format != SupportedFormat)
                throw new InvalidDataException($"Формат пакета {format} не поддерживается этой версией установщика");
            if (string.IsNullOrEmpty(p.Version) || p.Genders == null || p.Genders.Count == 0)
                throw new InvalidDataException("package.txt повреждён");

            var items = new List<PackageItem>();
            bool header = true;
            foreach (var line in File.ReadLines(idx, Encoding.UTF8))
            {
                if (header) { header = false; continue; }
                if (line.Length == 0) continue;
                var c = line.Split(';');
                items.Add(new PackageItem
                {
                    Pck = c[0], WemId = c[1].ToLowerInvariant(), Variant = c[2],
                    Offset = long.Parse(c[3]), Size = int.Parse(c[4]),
                });
            }
            p.Items = items;
            return p;
        }

        static string BlobName(string variant) => variant + ".bin";

        public string BlobPath(string variant) => Path.Combine(Dir, BlobName(variant));

        /// <summary>Реплики для пола: общие + этого пола, сгруппированные по pck в порядке пакета.</summary>
        public List<KeyValuePair<string, List<PackageItem>>> ForGender(string gender)
        {
            var groups = new List<KeyValuePair<string, List<PackageItem>>>();
            var byPck = new Dictionary<string, List<PackageItem>>(StringComparer.OrdinalIgnoreCase);
            foreach (var it in Items)
            {
                if (it.Variant != "common" && it.Variant != gender) continue;
                if (!byPck.TryGetValue(it.Pck, out var list))
                {
                    list = new List<PackageItem>();
                    byPck[it.Pck] = list;
                    groups.Add(new KeyValuePair<string, List<PackageItem>>(it.Pck, list));
                }
                list.Add(it);
            }
            return groups;
        }

        public IEnumerable<string> VariantsFor(string gender) =>
            new[] { "common", gender }.Where(v => blobs.ContainsKey(BlobName(v)));

        /// <summary>Целостность .bin нужного пола (битая загрузка) — до того, как трогать игру.</summary>
        public void Verify(string gender, Action<long, long> progress)
        {
            var need = VariantsFor(gender).ToList();
            long total = need.Sum(v => blobs[BlobName(v)].Key), done = 0;
            var buf = new byte[4 << 20];
            foreach (var v in need)
            {
                var path = BlobPath(v);
                var expected = blobs[BlobName(v)];
                if (!File.Exists(path))
                    throw new FileNotFoundException("Нет файла пакета: " + path);
                if (new FileInfo(path).Length != expected.Key)
                    throw new InvalidDataException($"Файл {BlobName(v)} повреждён (не тот размер) — скачайте пакет заново");
                using (var sha = SHA256.Create())
                using (var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16, FileOptions.SequentialScan))
                {
                    int r;
                    while ((r = fs.Read(buf, 0, buf.Length)) > 0)
                    {
                        sha.TransformBlock(buf, 0, r, null, 0);
                        done += r;
                        progress?.Invoke(done, total);
                    }
                    sha.TransformFinalBlock(buf, 0, 0);
                    if (AkpkTable.Hex(sha.Hash) != expected.Value)
                        throw new InvalidDataException($"Файл {BlobName(v)} повреждён (не совпала контрольная сумма) — скачайте пакет заново");
                }
            }
        }

        /// <summary>Что именно ставится в pck: если не изменилось — переустанавливать не нужно.</summary>
        public string Fingerprint(IEnumerable<PackageItem> items)
        {
            var sb = new StringBuilder(Version).Append('\n');
            foreach (var it in items)
                sb.Append(it.WemId).Append(';').Append(it.Variant).Append(';').Append(it.Size).Append('\n');
            return AkpkTable.Sha256Hex(Encoding.UTF8.GetBytes(sb.ToString()));
        }
    }
}
