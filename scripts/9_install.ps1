# 9_install.ps1 — install mod. Game must be closed!
# Usage:  .\9_install.ps1 -Gender m     (or f)
#         .\9_install.ps1 -Uninstall    (rollback to original)
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

if ($Uninstall) {
    if (Test-Path $bak) {
        Copy-Item "$bak\*.pck" $eng -Force
        Write-Host "Rollback done: originals restored from $bak"
    } else { Write-Host "Backup not found: $bak" }
    exit
}

$src = Join-Path $root "hsr-run-voice\pck_out_$Gender"
if (-not (Test-Path $src)) { Write-Host "Mod not found: $src"; exit 1 }

New-Item -ItemType Directory -Force $bak | Out-Null
$count = 0
Get-ChildItem "$src\*.pck" | ForEach-Object {
    $orig = Join-Path $eng $_.Name
    $bakf = Join-Path $bak $_.Name
    if ((Test-Path $orig) -and -not (Test-Path $bakf)) { Copy-Item $orig $bakf }  # backup once
    Copy-Item $_.FullName $eng -Force
    $count++
}
Write-Host "Mod installed (gender: $Gender), files: $count. Backup: $bak"