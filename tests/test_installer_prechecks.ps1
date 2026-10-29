# Forces every installer pre-check to fail (via the /CKSIMULATE test hook) and checks that
# the installer stops with the right exit code, logs the plain message, and writes NOTHING
# into the target folder. Safe: no simulated case gets as far as copying a file.
#
#   powershell -ExecutionPolicy Bypass -File tests\test_installer_prechecks.ps1 -Setup Q:\tools\ck-pack-payload\out\CorridorKey-Setup.exe
param(
    [Parameter(Mandatory = $true)][string]$Setup,
    [string]$Work = "$env:TEMP\ckpack-precheck-test"
)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $Work | Out-Null
$target = "C:\ck-precheck-target\CorridorKey"

# case, expected exit code, log text. Exit 1 = Setup stopped before copying anything: the hardware
# checks stop it at start-up, the folder/disk checks on the folder page (in silent installs too).
# PrepareToInstall repeats the folder/disk check as a backstop (exit 7) but these cases never reach it.
$cases = @(
    @("oldwindows", 1, "needs Windows 10 (version 22H2) or Windows 11"),
    @("nogpu", 1, "No NVIDIA graphics card"),
    @("oldgpu", 1, "older than an RTX 30-series"),
    @("olddriver", 1, "CorridorKey needs 570.65 or newer"),
    @("lowvram", 1, "needs at least 6 GB"),
    @("lowdisk", 1, "CorridorKey needs 12 GB"),
    @("unicodedir", 1, "only plain English letters"),
    @("smallvram,lowdisk", 1, "only for small clips")   # 6-8 GB: warning logged, then stopped by the disk check
)
$failed = 0
foreach ($c in $cases) {
    $sim, $want, $text = $c
    $log = Join-Path $Work ("setup-" + ($sim -replace ",", "+") + ".log")
    Remove-Item $log -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $Setup -Wait -PassThru -ArgumentList @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=`"$target`"", "/LOG=`"$log`"", "/CKSIMULATE=$sim")
    $logText = if (Test-Path $log) { Get-Content $log -Raw } else { "" }
    $wrote = Test-Path $target
    $ok = ($p.ExitCode -eq $want) -and $logText.Contains($text) -and (-not $wrote)
    if (-not $ok) { $failed++ }
    "{0,-18} exit {1} (want {2})  message logged: {3}  target folder created: {4}  -> {5}" -f `
        $sim, $p.ExitCode, $want, $logText.Contains($text), $wrote, $(if ($ok) { "PASS" } else { "FAIL" })
}
if (Test-Path "C:\ck-precheck-target") { Remove-Item -Recurse -Force "C:\ck-precheck-target" }
if ($failed) { "PRECHECKS: $failed case(s) FAILED"; exit 1 } else { "PRECHECKS: all $($cases.Count) cases PASS"; exit 0 }
