using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;

namespace HsrRuVoiceover
{
    /// <summary>
    /// Таблица externals pck (AKPK). Читаются только заголовок и записи, сам звук — нет.
    /// Заголовок: magic, headerSize, version, затем по смещениям 12/16/20/24 размеры
    /// lang/banks/sounds/externals. Таблица externals — с 28+lang+banks+sounds:
    /// count (u32), затем записи по 24 байта: id2, id1, blockSize, size, offset (u32), ...
    /// wem_id = id1:x8 + id2:x8 — так же, как в 12_repack_pck.py.
    /// </summary>
    sealed class AkpkTable
    {
        public const int EntrySize = 24;
        public const int SizeField = 12;
        public const int OffsetField = 16;

        public long TablePos { get; private set; }
        public int Count { get; private set; }
        /// <summary>Всё до таблицы externals: заголовок, lang, banks, sounds.</summary>
        public byte[] Head { get; private set; }
        /// <summary>count + все записи — как лежат в файле.</summary>
        public byte[] Raw { get; private set; }
        readonly Dictionary<string, int> index = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        public static AkpkTable Read(Stream fs)
        {
            var head = ReadAt(fs, 0, 28);
            if (head[0] != 'A' || head[1] != 'K' || head[2] != 'P' || head[3] != 'K')
                throw new InvalidDataException("не pck (нет сигнатуры AKPK)");
            long lang = BitConverter.ToUInt32(head, 12);
            long banks = BitConverter.ToUInt32(head, 16);
            long sounds = BitConverter.ToUInt32(head, 20);
            long pos = 28 + lang + banks + sounds;
            long n = BitConverter.ToUInt32(ReadAt(fs, pos, 4), 0);
            if (pos + 4 + n * EntrySize > fs.Length)
                throw new InvalidDataException("таблица externals выходит за конец файла");

            var t = new AkpkTable
            {
                TablePos = pos, Count = (int)n,
                Head = ReadAt(fs, 0, (int)pos), Raw = ReadAt(fs, pos, 4 + (int)n * EntrySize),
            };
            for (int i = 0; i < t.Count; i++)
                t.index[t.WemId(i)] = i;
            return t;
        }

        public bool TryFind(string wemId, out int i) => index.TryGetValue(wemId, out i);

        public long EntryPos(int i) => TablePos + 4 + (long)i * EntrySize;

        uint Field(int i, int off) => BitConverter.ToUInt32(Raw, 4 + i * EntrySize + off);

        public string WemId(int i) => Field(i, 4).ToString("x8") + Field(i, 0).ToString("x8");
        public uint BlockSize(int i) => Field(i, 8);
        public uint Size(int i) => Field(i, SizeField);
        public uint Offset(int i) => Field(i, OffsetField);

        public byte[] Entry(int i)
        {
            var e = new byte[EntrySize];
            Buffer.BlockCopy(Raw, 4 + i * EntrySize, e, 0, EntrySize);
            return e;
        }

        /// <summary>Хэш всего индекса pck (от начала файла до конца таблицы externals).</summary>
        public string Hash() => Sha256Hex(Head, Raw);

        /// <summary>Хэш индекса, если вернуть в таблицу записи из бэкапа (проверка, что это тот же pck).</summary>
        public string HashWith(IEnumerable<KeyValuePair<int, byte[]>> entries)
        {
            var raw = (byte[])Raw.Clone();
            foreach (var e in entries)
            {
                if (e.Key < 0 || e.Key >= Count) return null;
                Buffer.BlockCopy(e.Value, 0, raw, 4 + e.Key * EntrySize, EntrySize);
            }
            return Sha256Hex(Head, raw);
        }

        public static string Sha256Hex(params byte[][] parts)
        {
            using (var sha = SHA256.Create())
            {
                foreach (var p in parts) sha.TransformBlock(p, 0, p.Length, null, 0);
                sha.TransformFinalBlock(new byte[0], 0, 0);
                return Hex(sha.Hash);
            }
        }

        public static string Hex(byte[] b) => BitConverter.ToString(b).Replace("-", "").ToLowerInvariant();

        public static byte[] ReadAt(Stream fs, long pos, int count)
        {
            if (pos < 0 || pos + count > fs.Length)
                throw new InvalidDataException("чтение за концом файла");
            var buf = new byte[count];
            fs.Position = pos;
            int done = 0;
            while (done < count)
            {
                int r = fs.Read(buf, done, count - done);
                if (r <= 0) throw new EndOfStreamException();
                done += r;
            }
            return buf;
        }
    }
}
