using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace HsrRuVoiceover
{
    static class Program
    {
        const string Usage =
@"HSR RU Voiceover — установка русской озвучки Honkai: Star Rail

Без параметров открывается окно. Командная строка:
  HSR-RU-Voiceover.exe install   [--game <папка>] --gender m|f [--data <папка пакета>] [--state <папка>]
  HSR-RU-Voiceover.exe uninstall [--game <папка>] [--state <папка>]
  HSR-RU-Voiceover.exe status    [--game <папка>] [--state <папка>]

  --game   папка игры (где StarRail.exe); по умолчанию — найти автоматически
  --gender пол Первопроходца: m — Келус, f — Стелла
  --data   папка data пакета; по умолчанию — data рядом с exe
  --state  где хранить данные для отката; по умолчанию — %LOCALAPPDATA%\HSR-RU-Voiceover";

        public static string ExeDir => Path.GetDirectoryName(Application.ExecutablePath);

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Length > 0 && (args[0] == "install" || args[0] == "uninstall" || args[0] == "status" ||
                                    args[0] == "--help" || args[0] == "/?"))
                return RunCli(args);

            string game = null;
            for (int i = 0; i + 1 < args.Length; i++)
                if (args[i] == "--game") game = args[i + 1];
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm(game));
            return 0;
        }

        // ===================== командная строка =====================

        [DllImport("kernel32.dll")] static extern bool AttachConsole(int pid);
        [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int n);

        static int RunCli(string[] args)
        {
            // exe оконный: вывод либо уже перенаправлен (тесты), либо подключаемся к консоли запустившего
            var h = GetStdHandle(-11);
            if (h == IntPtr.Zero || h == new IntPtr(-1)) AttachConsole(-1);
            else Console.SetOut(new StreamWriter(Console.OpenStandardOutput(), new UTF8Encoding(false)) { AutoFlush = true });

            string cmd = args[0], game = null, gender = null, data = null, stateRoot = null;
            for (int i = 1; i < args.Length; i++)
            {
                bool known = args[i] == "--game" || args[i] == "--gender" || args[i] == "--data" || args[i] == "--state";
                if (!known || i + 1 >= args.Length)
                {
                    Console.WriteLine((known ? "Не указано значение для " : "Неизвестный параметр: ") + args[i] + "\n\n" + Usage);
                    return 1;
                }
                string v = args[++i];
                switch (args[i - 1])
                {
                    case "--game": game = v; break;
                    case "--gender": gender = v; break;
                    case "--data": data = v; break;
                    case "--state": stateRoot = v; break;
                }
            }
            if (cmd == "--help" || cmd == "/?") { Console.WriteLine(Usage); return 0; }

            stateRoot = stateRoot ?? Engine.DefaultStateRoot;
            Directory.CreateDirectory(stateRoot);
            var logPath = Path.Combine(stateRoot, "install.log");
            void Log(string s)
            {
                Console.WriteLine(s);
                File.AppendAllText(logPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {s}\r\n", Encoding.UTF8);
            }

            try
            {
                var gameDir = game != null ? GameLocator.Resolve(game) : GameLocator.Find(null);
                if (gameDir == null)
                    throw new UserError(game != null ? "В папке нет StarRail.exe: " + game
                                                     : "Игра не найдена, укажите папку: --game <папка>");
                var audio = Engine.AudioDir(gameDir);
                var engine = new Engine(audio, Engine.StateDirFor(stateRoot, audio), Log, null);
                Log($"== {cmd}: {gameDir}");
                switch (cmd)
                {
                    case "status":
                        Log(engine.Status());
                        return 0;
                    case "uninstall":
                        engine.Uninstall();
                        return engine.Report.Errors > 0 ? 3 : 0;
                    default:
                        if (gender != "m" && gender != "f") throw new UserError("Укажите пол: --gender m или --gender f");
                        var pkg = Package.Load(data ?? Path.Combine(ExeDir, "data"));
                        engine.Install(pkg, gender);
                        return engine.Report.Errors > 0 ? 3 : 0;
                }
            }
            catch (Exception e) when (e is UserError || e is FileNotFoundException || e is InvalidDataException)
            {
                Log("ОШИБКА: " + e.Message);
                return 1;
            }
            catch (Exception e)
            {
                Log("ОШИБКА: " + e);
                return 2;
            }
        }
    }
}
