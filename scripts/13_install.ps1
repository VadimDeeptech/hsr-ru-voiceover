# 13_install.ps1 — install mod. Game must be closed!
# Usage:  .\13_install.ps1 -Gender m     (or f)
#         .\13_install.ps1 -Uninstall    (rollback to original)
param(
    [ValidateSet("m","f")][string]$Gender = "m",
    [switch]$Uninstall
)

# Авто-определение путей относительно расположения скрипта
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir

# Читаем config.toml (простой парсинг key = "value")
$configPath = Join-Path $root "config.toml"
$gameDir = $null
if (Test-Path $configPath) {
    $line = Get-Content $configPath | Where-Object { $_ -match '^\s*game_dir\s*=' } | Select-Object -First 1
    if ($line -match '^\s*game_dir\s*=\s*"([^"]+)"') { $gameDir = $Matches[1] }
}

if (-not $gameDir) {
    # Автопоиск
    # HoYoPlay ставит игру в <Star Rail>\Games\StarRail.exe
    # Сам лаунчер обычно в C:\Program Files\HoYoPlay
    $candidates = @(
        # Стандартные пути HoYoPlay
        "C:\Program Files\Star Rail\Games",
        "D:\Program Files\Star Rail\Games",
        "C:\Program Files\Honkai Star Rail\Games",
        "D:\Program Files\Honkai Star Rail\Games",
        # Старый лаунчер / кастомные пути
        "C:\Games\Star Rail Games",
        "D:\Games\Star Rail Games",
        "E:\Games\Star Rail Games",
        "C:\Star Rail\Games",
        "D:\Star Rail\Games"
    )
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "StarRail.exe")) { $gameDir = $c; break }
        # Проверяем и родительскую папку (Games -> Star Rail)
        $parent = Split-Path -Parent $c
        if (Test-Path (Join-Path $parent "Games\StarRail.exe")) { $gameDir = $parent; break }
    }
}

if (-not $gameDir) {
    Write-Host "Игра не найдена. Укажи game_dir в config.toml"
    exit 1
}

$eng = Join-Path $gameDir "StarRail_Data\Persistent\Audio\AudioPackage\Windows\English"
$bak = Join-Path $root "hsr-run-voice\pck_backup_en"

# Игра держит pck открытыми: копирование поверх них упадёт на середине
if (Get-Process -Name StarRail -ErrorAction SilentlyContinue) {
    Write-Host "The game is running. Close it and run the command again."
    exit 1
}

# Манифест: что мы сами положили в игру (state: mod — наш мод, orig — оригинал после отката).
# Если файл в игре с ним не совпадает — его заменила игра (обновление/восстановление),
# значит в игре свежий оригинал, а бэкап этого pck устарел.
$manPath = Join-Path $bak "installed.csv"

function Get-Stamp($path) {
    $f = Get-Item -LiteralPath $path
    [pscustomobject]@{ size = $f.Length; mtime = [DateTimeOffset]::new($f.LastWriteTimeUtc).ToUnixTimeSeconds() }
}

function Test-Stamp($path, $e) {
    if (-not $e -or -not (Test-Path -LiteralPath $path)) { return $false }
    $s = Get-Stamp $path
    return ($s.size -eq [int64]$e.size) -and ([math]::Abs($s.mtime - [int64]$e.mtime) -le 1)
}

function Read-Manifest {
    $m = @{}
    if (Test-Path $manPath) { Import-Csv $manPath -Delimiter ';' | ForEach-Object { $m[$_.name] = $_ } }
    return $m
}

function Write-Manifest($m) {
    if ($m.Count -eq 0) { return }
    $m.Values | Sort-Object name | Select-Object name, state, size, mtime |
        Export-Csv $manPath -Delimiter ';' -NoTypeInformation -Encoding UTF8
}

function New-Entry($name, $state, $path) {
    $s = Get-Stamp $path
    [pscustomobject]@{ name = $name; state = $state; size = $s.size; mtime = $s.mtime }
}

function Test-OurBuild($path) {
    # Файл в игре — сборка из pck_out_m/f (Copy-Item сохраняет размер и время), даже если
    # манифест о ней не знает: установка оборвалась раньше, чем он был записан.
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    foreach ($g in 'm', 'f') {
        $built = Join-Path $root ("hsr-run-voice\pck_out_$g\" + (Split-Path -Leaf $path))
        if ((Test-Path -LiteralPath $built) -and (Test-Stamp $path (Get-Stamp $built))) { return $true }
    }
    return $false
}

if ($Uninstall) {
    if (-not (Test-Path $bak)) { Write-Host "Backup not found: $bak"; exit }
    $man = Read-Manifest
    $restored = 0; $skipped = 0
    Get-ChildItem "$bak\*.pck" | ForEach-Object {
        $orig = Join-Path $eng $_.Name
        $e = $man[$_.Name]
        # в игре уже не наш мод (игра заменила файл) — старый бэкап поверх него не кладём
        if ($e -and (Test-Path $orig) -and -not ((Test-Stamp $orig $e) -and $e.state -eq 'mod')) { $skipped++; return }
        Copy-Item $_.FullName $eng -Force -ErrorAction Stop
        $man[$_.Name] = New-Entry $_.Name 'orig' $orig
        Write-Manifest $man
        $restored++
    }
    Write-Host "Rollback done: restored $restored from $bak, skipped $skipped (game already has its own files)"
    exit
}

$src = Join-Path $root "hsr-run-voice\pck_out_$Gender"
if (-not (Test-Path $src)) { Write-Host "Mod not found: $src"; exit 1 }

New-Item -ItemType Directory -Force $bak | Out-Null
$man = Read-Manifest
$count = 0; $refreshed = 0; $untracked = 0; $noOrig = 0; $stale = 0
Get-ChildItem "$src\*.pck" | ForEach-Object {
    $orig = Join-Path $eng $_.Name
    $bakf = Join-Path $bak $_.Name
    $e = $man[$_.Name]
    $match = Test-Stamp $orig $e
    if (($match -and $e.state -eq 'mod') -or (Test-OurBuild $orig)) {
        # в игре наш прошлый мод: оригинал уже лежит в бэкапе
        if (-not (Test-Path $bakf)) { $noOrig++ }
    } elseif (Test-Path $orig) {
        # в игре оригинал: первая установка либо игра заменила файл
        if ($e -and $e.state -eq 'mod' -and $_.LastWriteTimeUtc -lt (Get-Item -LiteralPath $orig).LastWriteTimeUtc) {
            # игра заменила файл уже после сборки pck_out: мод собран на старом оригинале
            $stale++; return
        }
        if ((Test-Path $bakf) -and -not $e) {
            $untracked++   # бэкап от версии без манифеста: проверить нечем, оставляем как есть
        } elseif (-not ($match -and (Test-Path $bakf))) {
            if (Test-Path $bakf) { $refreshed++ }
            Copy-Item $orig $bakf -Force -ErrorAction Stop
        }
    }
    # через временный файл: в игре либо прежний pck, либо новый целиком
    Copy-Item $_.FullName "$orig.tmp" -Force -ErrorAction Stop
    Move-Item "$orig.tmp" $orig -Force -ErrorAction Stop
    $man[$_.Name] = New-Entry $_.Name 'mod' $orig
    # манифест пишем сразу: прерванная установка не оставит в игре неучтённый мод
    Write-Manifest $man
    $count++
}
Write-Host "Mod installed (gender: $Gender), files: $count. Backup: $bak"
if ($stale) { Write-Host "WARNING: $stale pck were replaced by the game after the mod was built (game update) - NOT installed. Run 'python pipeline.py repack --gender $Gender' and install again" }
if ($refreshed) { Write-Host "Game files changed since last install (game update): backup refreshed for $refreshed pck" }
if ($untracked) { Write-Host "WARNING: $untracked pck have a backup made before install tracking existed - kept as is. If the game was updated since, restore the game files in the launcher and delete $bak" }
if ($noOrig)    { Write-Host "WARNING: $noOrig pck have the mod in the game but no original in the backup - rollback for them is impossible until the launcher restores the files" }