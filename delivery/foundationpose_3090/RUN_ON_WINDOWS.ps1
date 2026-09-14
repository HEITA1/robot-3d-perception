# RUN_ON_WINDOWS.ps1 — Windows 路线引导器（WSL2 + conda r3p-fp，Stage A bundle）。
#
# 用法（在 Windows PowerShell 中，cd 到仓库根后）：
#   powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 doctor      # 体检
#   ... -File ... RUN_ON_WINDOWS.ps1 install        # WSL 内装 miniconda + r3p-fp 环境（safe-fail）
#   ... check_env | prepare_data | smoke | exp013 -Unlock | collect
#
# 原则：WSL2 内原生执行（去 Docker 化，空间省一半）；任何一步失败即停，禁止换版本乱试。
# 完整说明见 WINDOWS.md；协议红线与 README_3090.md 相同。
param(
  [Parameter(Position = 0)][string]$Step = "doctor",
  [string]$RepoRoot = "",
  [string]$FpRepo = "",
  [string]$CheckpointDir = "",
  [switch]$Unlock
)
$ErrorActionPreference = "Stop"

# RepoRoot 默认 = 本脚本所在位置上溯两级（Bundle 在 <repo>/delivery/foundationpose_3090/ 内），
# 因此仓库放任何盘（如 E:\robot-3d-perception）都零参数可用；找不到时退回 $HOME\robot-3d-perception。
if (-not $RepoRoot) {
  $here = $PSScriptRoot
  if ($here -and (Test-Path (Join-Path $here "..\..\delivery"))) {
    $RepoRoot = (Resolve-Path (Join-Path $here "..\..")).Path
  } else {
    $RepoRoot = Join-Path $HOME "robot-3d-perception"
  }
}
# FpRepo / weights 默认 = 仓库所在盘根下的 FoundationPose\（匹配"整个目录放 E 盘"的部署）；
# 需要放别处时用 -FpRepo / -CheckpointDir 覆盖。
if (-not $FpRepo) {
  $driveRoot = ([System.IO.DriveInfo]::new($RepoRoot)).Name
  $FpRepo = Join-Path $driveRoot "FoundationPose"
}
if (-not $CheckpointDir) { $CheckpointDir = Join-Path $FpRepo "weights" }
$Bundle = Join-Path $RepoRoot "delivery\foundationpose_3090"

function Test-Prerequisites {
  if (-not (Test-Path (Join-Path $Bundle "CHECK_ENV.sh"))) {
    throw "Bundle 不在 $Bundle —— 请先把 U 盘的 robot-3d-perception 整体拷到 $RepoRoot"
  }
  & nvidia-smi > $null 2>&1
  if ($LASTEXITCODE -ne 0) { throw "Windows 侧 nvidia-smi 不可用——先装/更新 NVIDIA 驱动（WSL CUDA 依赖 Windows 驱动直通）" }
}

function Convert-ToWslPath([string]$p) {
  $n = $p -replace '\\', '/'
  $out = & wsl bash -c ("wslpath -a '" + $n + "'")
  if ($LASTEXITCODE -ne 0 -or -not $out) { throw "wslpath 失败（$p）——WSL2 未安装？先以管理员运行: wsl --install -d Ubuntu" }
  return ([string]($out | Select-Object -First 1)).Trim()
}

function Invoke-WslStep([string]$bashCmd, [string]$label) {
  Write-Host "== [$label] WSL 执行 =="
  & wsl bash -lc $bashCmd
  if ($LASTEXITCODE -ne 0) {
    throw "步骤 $label 失败（exit $LASTEXITCODE）——按上方输出逐项处理；禁止自动换版本重试"
  }
}

function Get-LinuxRepo { return (Convert-ToWslPath $RepoRoot) }
function Get-LinuxFp { return (Convert-ToWslPath $FpRepo) }
function Get-LinuxCkpt { return (Convert-ToWslPath $CheckpointDir) }
function Get-CondaSource { return 'test -f ~/miniconda3/etc/profile.d/conda.sh && source ~/miniconda3/etc/profile.d/conda.sh' }

switch ($Step) {
  "doctor" {
    Test-Prerequisites
    Write-Host "== Windows 侧 =="
    & nvidia-smi | Select-Object -First 10
    $drive = ([System.IO.DriveInfo]::new($RepoRoot)).AvailableFreeSpace / 1GB
    $wslDrive = ([System.IO.DriveInfo]::new($env:SystemDrive + "\")).AvailableFreeSpace / 1GB
    Write-Host ("磁盘可用空间（仓库所在盘 {0}:）: {1:N1} GB" -f $RepoRoot.Substring(0, 1), $drive)
    Write-Host ("磁盘可用空间（系统盘 {0}:，WSL VHDX 默认落这里）: {1:N1} GB" -f $env:SystemDrive.Substring(0, 1), $wslDrive)
    if ($drive -lt 25) { Write-Warning "仓库所在盘可用空间 < 25GB——本路线预估需 10–15GB，建议清理后再继续" }
    if ($wslDrive -lt 15) { Write-Warning "系统盘可用空间 < 15GB——WSL 发行版默认在系统盘；可迁移: wsl --manage Ubuntu --move <盘>:\WSL（较新 WSL 版本）" }
    Write-Host "== WSL 侧 =="
    & wsl -l -v
    & wsl bash -lc "nvidia-smi | head -12; echo; echo 'WSL CUDA 直通 OK'"
    if ($LASTEXITCODE -ne 0) { throw "WSL 内 nvidia-smi 不可用——更新 Windows NVIDIA 驱动（支持 WSL CUDA 的版本）" }
    Write-Host "doctor PASS —— 下一步: install"
  }
  "install" {
    Test-Prerequisites
    & wsl bash -lc "grep -qi ubuntu /etc/os-release || { echo 'Default WSL distro is not Ubuntu; run first: wsl --install -d Ubuntu'; exit 1; }"
    Invoke-WslStep ('test -d ~/miniconda3 || (wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh && bash /tmp/miniconda.sh -b -p ~/miniconda3) && echo "miniconda OK"') "miniconda-in-wsl"
    $cmd = (Get-CondaSource) + ' && cd "' + (Get-LinuxRepo) + '" && USE_DOCKER=0 bash delivery/foundationpose_3090/INSTALL.sh'
    Invoke-WslStep $cmd "INSTALL（创建 r3p-fp env + torch cu124 + WSL nvcc + 官方依赖编译）"
    Write-Host "install 完成 —— 下一步: check_env（下载 checkpoints 前部分项 FAIL 属预期）"
  }
  "check_env" {
    Test-Prerequisites
    $cmd = (Get-CondaSource) + ' && conda activate r3p-fp && cd "' + (Get-LinuxRepo) + '" && USE_DOCKER=0 FP_REPO_ROOT="' + (Get-LinuxFp) + '" FP_CHECKPOINT_DIR="' + (Get-LinuxCkpt) + '" bash delivery/foundationpose_3090/CHECK_ENV.sh'
    Invoke-WslStep $cmd "CHECK_ENV"
  }
  "prepare_data" {
    Test-Prerequisites
    $cmd = (Get-CondaSource) + ' && conda activate r3p-fp && cd "' + (Get-LinuxRepo) + '" && USE_DOCKER=0 bash delivery/foundationpose_3090/PREPARE_DATA.sh'
    Invoke-WslStep $cmd "PREPARE_DATA"
  }
  "smoke" {
    Test-Prerequisites
    $cmd = (Get-CondaSource) + ' && conda activate r3p-fp && cd "' + (Get-LinuxRepo) + '" && USE_DOCKER=0 FP_REPO_ROOT="' + (Get-LinuxFp) + '" FP_CHECKPOINT_DIR="' + (Get-LinuxCkpt) + '" bash delivery/foundationpose_3090/RUN_SMOKE_TEST.sh'
    Invoke-WslStep $cmd "RUN_SMOKE_TEST（单帧 gate）"
    Write-Host "smoke 完成 —— 人工目检 overlay（GT 绿 / 预测红）后再决定 Stage B"
  }
  "exp013" {
    if (-not $Unlock) { throw "EXP-013 默认锁定（Stage B 需用户明确授权）：加 -Unlock 并设置环境变量 CONFIRM_EXP013=YES" }
    if ($env:CONFIRM_EXP013 -ne "YES") { throw "需要 CONFIRM_EXP013=YES（PowerShell: `$env:CONFIRM_EXP013='YES'）" }
    Test-Prerequisites
    $cmd = (Get-CondaSource) + ' && conda activate r3p-fp && cd "' + (Get-LinuxRepo) + '" && USE_DOCKER=0 FP_REPO_ROOT="' + (Get-LinuxFp) + '" FP_CHECKPOINT_DIR="' + (Get-LinuxCkpt) + '" CONFIRM_EXP013=YES bash delivery/foundationpose_3090/RUN_EXP013.sh --unlock'
    Invoke-WslStep $cmd "RUN_EXP013（正式 5 帧，冻结协议）"
  }
  "collect" {
    Test-Prerequisites
    $cmd = 'cd "' + (Get-LinuxRepo) + '" && bash delivery/foundationpose_3090/COLLECT_RESULTS.sh'
    Invoke-WslStep $cmd "COLLECT_RESULTS"
    Write-Host ("拷回轻薄本: " + (Join-Path $RepoRoot "outputs\phase4_foundationpose\delivery_back"))
  }
  default { throw "未知步骤 '$Step' —— 可用: doctor / install / check_env / prepare_data / smoke / exp013 -Unlock / collect" }
}
