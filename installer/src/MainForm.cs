using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace HsrRuVoiceover
{
    sealed class MainForm : Form
    {
        readonly TextBox gamePath = new TextBox { Dock = DockStyle.Fill };
        readonly Button browse = new Button { Text = "Обзор…", AutoSize = true };
        readonly RadioButton male = new RadioButton { Text = "Мужской (Келус)", AutoSize = true, Checked = true };
        readonly RadioButton female = new RadioButton { Text = "Женский (Стелла)", AutoSize = true };
        readonly Button install = new Button { Text = "Установить", AutoSize = true, Padding = new Padding(8, 2, 8, 2) };
        readonly Button uninstall = new Button { Text = "Удалить мод", AutoSize = true, Padding = new Padding(8, 2, 8, 2) };
        readonly Label status = new Label { AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(0, 6, 0, 6) };
        readonly ProgressBar bar = new ProgressBar { Dock = DockStyle.Fill, Maximum = 1000, Height = 18 };
        readonly TextBox logBox = new TextBox
        {
            Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Vertical,
            Font = new Font(FontFamily.GenericMonospace, 9f), BackColor = SystemColors.Window,
        };

        readonly string stateRoot = Engine.DefaultStateRoot;
        string LastGameFile => Path.Combine(stateRoot, "last_game.txt");
        Package pkg;
        bool busy;

        public MainForm(string presetGame)
        {
            Text = "HSR RU Voiceover — русская озвучка Honkai: Star Rail";
            AutoScaleMode = AutoScaleMode.Dpi;
            Font = SystemFonts.MessageBoxFont;
            ClientSize = new Size(720, 520);
            MinimumSize = new Size(560, 420);
            StartPosition = FormStartPosition.CenterScreen;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch (ArgumentException) { }

            var root = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, Padding = new Padding(12) };
            Controls.Add(root);

            root.Controls.Add(new Label
            {
                AutoSize = true, Padding = new Padding(0, 0, 0, 8),
                Text = "Неофициальный фанатский мод: озвучка сгенерирована нейросетью.\n" +
                       "Изменение файлов игры может нарушать её пользовательское соглашение — на свой риск.\n" +
                       "В настройках игры язык озвучки должен быть English.",
            });

            root.Controls.Add(new Label { Text = "Папка игры (где StarRail.exe):", AutoSize = true });
            var pathRow = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, AutoSize = true };
            pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            pathRow.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            pathRow.Controls.Add(gamePath, 0, 0);
            pathRow.Controls.Add(browse, 1, 0);
            root.Controls.Add(pathRow);

            var genderBox = new GroupBox { Text = "Пол Первопроходца", AutoSize = true, Dock = DockStyle.Fill, Padding = new Padding(8) };
            var genderRow = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true };
            genderRow.Controls.Add(male);
            genderRow.Controls.Add(female);
            genderBox.Controls.Add(genderRow);
            root.Controls.Add(genderBox);

            var buttons = new FlowLayoutPanel { AutoSize = true, Dock = DockStyle.Fill };
            buttons.Controls.Add(install);
            buttons.Controls.Add(uninstall);
            root.Controls.Add(buttons);
            root.Controls.Add(status);
            root.Controls.Add(bar);
            root.Controls.Add(logBox);
            for (int i = 0; i < root.Controls.Count - 1; i++) root.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));

            browse.Click += (s, e) => Browse();
            gamePath.Leave += (s, e) => RefreshStatus();
            install.Click += (s, e) => Run(true);
            uninstall.Click += (s, e) => Run(false);
            FormClosing += (s, e) =>
            {
                if (busy && MessageBox.Show(this, "Идёт работа с файлами игры. Прервать её небезопасно — дождитесь окончания.\nВсё равно закрыть?",
                        Text, MessageBoxButtons.YesNo, MessageBoxIcon.Warning) != DialogResult.Yes)
                    e.Cancel = true;
            };

            LoadPackage();
            string remembered = null;
            try { if (File.Exists(LastGameFile)) remembered = File.ReadAllText(LastGameFile).Trim(); } catch (IOException) { }
            gamePath.Text = GameLocator.Resolve(presetGame) ?? GameLocator.Find(remembered) ?? "";
            RefreshStatus();
        }

        void LoadPackage()
        {
            try
            {
                pkg = Package.Load(Path.Combine(Program.ExeDir, "data"));
                Text += "  —  версия " + pkg.Version;
                male.Enabled = pkg.Genders.Contains("m");
                female.Enabled = pkg.Genders.Contains("f");
                if (!male.Enabled) female.Checked = true;
            }
            catch (Exception e) when (e is IOException || e is InvalidDataException || e is FormatException)
            {
                pkg = null;
                Log("Не найдены файлы озвучки: " + e.Message);
                Log("Распакуйте архив целиком и запускайте установщик из распакованной папки (рядом с ним должна быть папка data).");
            }
        }

        void Browse()
        {
            using (var dlg = new FolderBrowserDialog { Description = "Выберите папку игры Honkai: Star Rail (где лежит StarRail.exe или папка Games)", ShowNewFolderButton = false })
            {
                if (Directory.Exists(gamePath.Text)) dlg.SelectedPath = gamePath.Text;
                if (dlg.ShowDialog(this) != DialogResult.OK) return;
                var g = GameLocator.Resolve(dlg.SelectedPath);
                if (g == null)
                {
                    MessageBox.Show(this, "В этой папке нет StarRail.exe. Выберите папку, куда установлена игра.", Text,
                                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                    return;
                }
                gamePath.Text = g;
                RefreshStatus();
            }
        }

        Engine MakeEngine(string game, Action<string> log, Action<long, long> progress)
        {
            var audio = Engine.AudioDir(game);
            return new Engine(audio, Engine.StateDirFor(stateRoot, audio), log, progress);
        }

        void RefreshStatus()
        {
            var g = GameLocator.Resolve(gamePath.Text);
            if (g == null)
            {
                status.Text = "Укажите папку игры.";
                return;
            }
            try
            {
                var engine = MakeEngine(g, null, null);
                status.Text = engine.Status();
                var installed = engine.InstalledGender();
                if (installed == "f" && female.Enabled) female.Checked = true;
                if (installed == "m" && male.Enabled) male.Checked = true;
            }
            catch (Exception e) when (e is IOException || e is InvalidDataException || e is UnauthorizedAccessException)
            {
                status.Text = "Не удалось прочитать состояние: " + e.Message;
            }
        }

        void Run(bool doInstall)
        {
            if (busy) return;
            var game = GameLocator.Resolve(gamePath.Text);
            if (game == null)
            {
                MessageBox.Show(this, "Укажите папку игры (где лежит StarRail.exe).", Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (doInstall && pkg == null)
            {
                MessageBox.Show(this, "Не найдены файлы озвучки (папка data рядом с установщиком).", Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            var audio = Engine.AudioDir(game);
            if (Directory.Exists(audio) && !Engine.CanWrite(audio))
            {
                if (MessageBox.Show(this, "Папка игры защищена от записи. Перезапустить установщик с правами администратора?", Text,
                        MessageBoxButtons.YesNo, MessageBoxIcon.Question) == DialogResult.Yes)
                    RestartAsAdmin(game);
                return;
            }
            try { Directory.CreateDirectory(stateRoot); File.WriteAllText(LastGameFile, game, Encoding.UTF8); } catch (IOException) { }

            string gender = female.Checked ? "f" : "m";
            busy = true;
            SetEnabled(false);
            logBox.Clear();
            bar.Value = 0;
            Task.Run(() =>
            {
                var logPath = Path.Combine(stateRoot, "install.log");
                void Log2(string s)
                {
                    try { File.AppendAllText(logPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {s}\r\n", Encoding.UTF8); } catch (IOException) { }
                    BeginInvoke(new Action(() => Log(s)));
                }
                void Progress(long done, long total) =>
                    BeginInvoke(new Action(() => bar.Value = total > 0 ? (int)Math.Min(1000, done * 1000 / total) : 0));
                try
                {
                    var engine = MakeEngine(game, Log2, Progress);
                    Log2($"== {(doInstall ? "Установка" : "Удаление")}: {game}");
                    if (doInstall) engine.Install(pkg, gender);
                    else engine.Uninstall();
                    return engine.Report.Errors > 0 ? "Готово, но с ошибками — см. журнал." : "Готово.";
                }
                catch (Exception e) when (e is UserError || e is IOException || e is InvalidDataException || e is UnauthorizedAccessException)
                {
                    Log2("ОШИБКА: " + e.Message);
                    return "Ошибка: " + e.Message;
                }
                catch (Exception e)
                {
                    Log2("ОШИБКА: " + e);
                    return "Непредвиденная ошибка — см. журнал.";
                }
            }).ContinueWith(t =>
            {
                busy = false;
                SetEnabled(true);
                bar.Value = bar.Maximum;
                RefreshStatus();
                MessageBox.Show(this, t.Result, Text, MessageBoxButtons.OK,
                                t.Result == "Готово." ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
            }, TaskScheduler.FromCurrentSynchronizationContext());
        }

        void RestartAsAdmin(string game)
        {
            try
            {
                Process.Start(new ProcessStartInfo(Application.ExecutablePath, $"--game \"{game}\"")
                {
                    UseShellExecute = true, Verb = "runas", WorkingDirectory = Program.ExeDir,
                });
                Close();
            }
            catch (Win32Exception)
            {
                // игрок отказался в окне UAC
            }
        }

        void SetEnabled(bool on)
        {
            foreach (Control c in new Control[] { gamePath, browse, male, female, install, uninstall })
                c.Enabled = on;
            if (on && pkg != null)
            {
                male.Enabled = pkg.Genders.Contains("m");
                female.Enabled = pkg.Genders.Contains("f");
            }
        }

        void Log(string s) => logBox.AppendText(s + Environment.NewLine);
    }
}
