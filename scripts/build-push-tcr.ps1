param(
    [string]$SaasPath = $env:DEV2_SAAS_SRC_DIR,
    [string]$Registry = $env:TCR_REGISTRY,
    [string]$Namespace = $env:TCR_NAMESPACE,
    [string]$Tag = "",
    [switch]$NoLatest,
    [switch]$SkipLogin
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SaasPath)) {
    $Parent = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    if ((Split-Path -Leaf $Parent) -eq "OpenHarness") {
        $MaybeSaasRoot = Split-Path -Parent $Parent
        if (Test-Path (Join-Path $MaybeSaasRoot "deploy/Dockerfile")) {
            $SaasPath = $MaybeSaasRoot
        }
    }
}

if ([string]::IsNullOrWhiteSpace($SaasPath)) {
    $Sibling = Join-Path (Split-Path -Parent $PSScriptRoot) "dev2_OpenHarness_SaaS"
    if (Test-Path $Sibling) {
        $SaasPath = $Sibling
    }
}

if ([string]::IsNullOrWhiteSpace($SaasPath) -or -not (Test-Path $SaasPath)) {
    throw "SaaS repository path is required. Pass -SaasPath or set DEV2_SAAS_SRC_DIR."
}

$Script = Join-Path (Resolve-Path $SaasPath).Path "scripts/build-push-tcr.ps1"
if (-not (Test-Path $Script)) {
    throw "SaaS build script not found: $Script"
}

$ArgsList = @(
    "-OpenHarnessPath", (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

if (-not [string]::IsNullOrWhiteSpace($Registry)) {
    $ArgsList += @("-Registry", $Registry)
}
if (-not [string]::IsNullOrWhiteSpace($Namespace)) {
    $ArgsList += @("-Namespace", $Namespace)
}
if (-not [string]::IsNullOrWhiteSpace($Tag)) {
    $ArgsList += @("-Tag", $Tag)
}
if ($NoLatest) {
    $ArgsList += "-NoLatest"
}
if ($SkipLogin) {
    $ArgsList += "-SkipLogin"
}

& $Script @ArgsList
