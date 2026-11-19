param([switch] $Diagnostics)

$ErrorActionPreference = 'Stop'
$Project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$Prefix = $Project.TrimEnd('\') + '\'
$PythonCheck = 'import sys, sysconfig; raise SystemExit(sys.version_info[:2] not in ((3, 12), (3, 11)) or sysconfig.get_platform() != ''win-amd64'')'

function Get-ProjectPath([string] $RelativePath) {
    $Path = [IO.Path]::GetFullPath((Join-Path $Project $RelativePath))
    if (-not $Path.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the Harbor City project: $Path"
    }
    $Current = $Path
    while ($Current.StartsWith($Prefix, [StringComparison]::OrdinalIgnoreCase)) {
        $Item = Get-Item -LiteralPath $Current -Force -ErrorAction SilentlyContinue
        if ($Item -and ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "Setup cannot write through a redirected path: $Current"
        }
        $Current = [IO.Path]::GetDirectoryName($Current)
    }
    return $Path
}

function New-ProjectDirectory([string] $RelativePath) {
    $Path = Get-ProjectPath $RelativePath
    [void] [IO.Directory]::CreateDirectory($Path)
    return $Path
}

function Write-SetupLog([string] $Message) {
    $Record = '[{0}] {1}' -f [DateTimeOffset]::Now.ToString('o'), $Message
    Add-Content -LiteralPath $SetupLog -Value $Record -Encoding UTF8
    Write-Host $Message
}

function Test-Python([string] $Path, [string] $Check = $PythonCheck) {
    if (-not [IO.File]::Exists($Path)) {
        return $false
    }
    try {
        & $Path '-I' '-c' $Check > $null 2>&1
        return ($LASTEXITCODE -eq 0)
    }
    catch {
        return $false
    }
}

function Get-PinnedDownload([string] $Name, [string] $Url, [string] $Hash) {
    $Path = Get-ProjectPath (Join-Path 'logs\bootstrap-cache' $Name)
    if ((Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -eq $Hash) {
        Write-SetupLog "Verified cached $Name."
        return $Path
    }
    Write-SetupLog "Downloading $Name from $Url"
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path -TimeoutSec 60 -MaximumRedirection 0
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) {
        throw "SHA-256 verification failed for $Name. Run setup.bat to retry."
    }
    Write-SetupLog "Verified SHA-256 for $Name."
    return $Path
}

function Install-PortablePython([string] $Destination) {
    [void] (New-ProjectDirectory 'logs\bootstrap-cache')
    [void] (New-ProjectDirectory '.venv')
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Add-Type -AssemblyName System.IO.Compression.FileSystem

    $PythonZip = Get-PinnedDownload 'python-3.12.10-embed-amd64.zip' `
        'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' `
        '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
    $PipWheel = Get-PinnedDownload 'pip-26.3-py3-none-any.whl' `
        'https://files.pythonhosted.org/packages/07/25/ee8c38ae72d66b844ce8eb9711ba905dba21ca1a8a0c960057c41cd23337/pip-26.3-py3-none-any.whl' `
        'f3b60b20ffaadd4415ed7957212a38ac63fa4c5fa375bd0f4a797777940fad13'

    $Suffix = [Guid]::NewGuid().ToString('N')
    $StageName = '.venv\portable-stage-' + $Suffix
    $Stage = Get-ProjectPath $StageName
    [IO.Compression.ZipFile]::ExtractToDirectory($PythonZip, $Stage)
    [IO.Compression.ZipFile]::ExtractToDirectory($PipWheel, (Get-ProjectPath (Join-Path $StageName 'bootstrap-pip')))
    $ImportPaths = [string[]] @('python312.zip', '.', 'packages', 'bootstrap-pip', '..\..')
    [IO.File]::WriteAllLines((Get-ProjectPath (Join-Path $StageName 'python312._pth')), $ImportPaths, [Text.Encoding]::ASCII)
    if (-not (Test-Python (Join-Path $Stage 'python.exe') ('import pip; ' + $PythonCheck))) {
        throw 'The downloaded Python and pip could not start on this Windows machine.'
    }

    $Previous = Get-ProjectPath ('.venv\portable-previous-' + $Suffix)
    if (Test-Path -LiteralPath $Destination) {
        [IO.Directory]::Move($Destination, $Previous)
    }
    try {
        [IO.Directory]::Move($Stage, $Destination)
    }
    catch {
        if (Test-Path -LiteralPath $Previous -PathType Container) {
            [IO.Directory]::Move($Previous, $Destination)
        }
        throw
    }
    if (Test-Path -LiteralPath $Previous -PathType Container) {
        Write-SetupLog "Previous project runtime retained at $Previous."
    }
}

$SetupLog = $null
$Lock = $null
try {
    $ProjectDirectory = Get-Item -LiteralPath $Project -Force
    if ($ProjectDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'The Harbor City project root is a redirected path.'
    }
    Set-Location -LiteralPath $Project
    [void] (New-ProjectDirectory 'logs')
    $PortablePython = Get-ProjectPath '.venv\portable\python.exe'
    $ExistingPython = $null
    try {
        $ExistingPython = Get-ProjectPath '.venv\Scripts\python.exe'
    }
    catch {
        Write-Host 'Skipping a redirected previous Python environment.'
    }

    if ($Diagnostics) {
        $Python = if (Test-Python $PortablePython) { $PortablePython } elseif (Test-Python $ExistingPython) { $ExistingPython }
        if ($Python) {
            & $Python '-I' (Join-Path $PSScriptRoot 'launch.py') 'diag'
            exit $LASTEXITCODE
        }
        $Report = Get-ProjectPath 'logs\diag.log'
        $Details = @(
            'Harbor City diagnostics',
            ('Windows version: ' + [Environment]::OSVersion.VersionString),
            ('64-bit OS: ' + [Environment]::Is64BitOperatingSystem),
            ('Logical processors: ' + [Environment]::ProcessorCount),
            'FAIL - No usable project Python. Run setup.bat and check logs\setup.log.'
        )
        $Details | Set-Content -LiteralPath $Report -Encoding UTF8
        $Details | Write-Host
        exit 1
    }

    $SetupLog = Get-ProjectPath 'logs\setup.log'
    $LockPath = Get-ProjectPath 'logs\setup.lock'
    try {
        $Lock = [IO.File]::Open($LockPath, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    }
    catch [IO.IOException] {
        throw 'Setup is already running or logs\setup.lock is unavailable.'
    }
    if (-not [Environment]::Is64BitOperatingSystem) {
        throw 'Harbor City requires 64-bit Windows 10 or 11.'
    }
    Write-SetupLog 'Checking the project Python runtime ...'
    if (Test-Python $PortablePython ('import pip; ' + $PythonCheck)) {
        $Python = $PortablePython
    }
    elseif (-not (Test-Path -LiteralPath (Get-ProjectPath '.venv\portable')) -and
            (Test-Python $ExistingPython ('import pip; ' + $PythonCheck))) {
        $Python = $ExistingPython
    }
    else {
        Install-PortablePython (Get-ProjectPath '.venv\portable')
        $Python = $PortablePython
    }
    & $Python '-I' (Join-Path $PSScriptRoot 'launch.py') 'setup'
    if ($LASTEXITCODE -ne 0) {
        throw 'Dependency or asset setup failed. See logs\setup.log for the failing step.'
    }
    exit 0
}
catch {
    $Message = 'FAIL - ' + $_.Exception.Message
    if ($SetupLog -and $Lock) {
        try { Write-SetupLog $Message }
        catch { Write-Host $Message }
    }
    else {
        Write-Host $Message
    }
    exit 1
}
finally {
    if ($Lock) {
        $Lock.Dispose()
    }
}
