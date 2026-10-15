using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Win32;

namespace HsrRuVoiceover
{
    /// <summary>Поиск папки игры (той, где лежит StarRail.exe).</summary>
    static class GameLocator
    {
        const string Exe = "StarRail.exe";

        /// <summary>Игрок мог выбрать корень игры, папку Games или любую папку внутри игры.</summary>
        public static string Resolve(string dir)
        {
            if (string.IsNullOrWhiteSpace(dir)) return null;
            try
            {
                var d = new DirectoryInfo(dir.Trim().Trim('"'));
                if (d.Exists && File.Exists(Path.Combine(d.FullName, "Games", Exe)))
                    return Path.Combine(d.FullName, "Games");
                for (int i = 0; d != null && i < 10; i++, d = d.Parent)
                    if (File.Exists(Path.Combine(d.FullName, Exe)))
                        return d.FullName;
            }
            catch (Exception e) when (e is ArgumentException || e is IOException || e is UnauthorizedAccessException || e is NotSupportedException) { }
            return null;
        }

        public static string Find(string remembered)
        {
            foreach (var c in Candidates(remembered))
            {
                var g = Resolve(c);
                if (g != null) return g;
            }
            return null;
        }

        static IEnumerable<string> Candidates(string remembered)
        {
            if (!string.IsNullOrEmpty(remembered)) yield return remembered;
            // HoYoPlay хранит путь установки в реестре (если ключа нет — просто пропускаем)
            foreach (var key in new[] { @"Software\Cognosphere\HYP\1_0\hkrpg_global", @"Software\Cognosphere\HYP\1_0\hkrpg_cn" })
            {
                string v = null;
                try
                {
                    using (var k = Registry.CurrentUser.OpenSubKey(key))
                        v = k?.GetValue("GameInstallPath") as string;
                }
                catch (Exception e) when (e is System.Security.SecurityException || e is IOException || e is UnauthorizedAccessException) { }
                if (!string.IsNullOrEmpty(v)) yield return v;
            }
            foreach (var drive in new[] { "C", "D", "E", "F" })
            {
                yield return drive + @":\Program Files\Star Rail";
                yield return drive + @":\Program Files\Honkai Star Rail";
                yield return drive + @":\Games\Star Rail";
                yield return drive + @":\Games\Star Rail Games";
                yield return drive + @":\Star Rail";
                yield return drive + @":\HoYoPlay\games\Star Rail";
            }
        }
    }
}
