param(
    [string]$AccountSecretPath = "secrets/dreem-registered-test-account.json",
    [string]$OutputSecretPath = "secrets/dreem-rythm-device-session.json"
)

$ErrorActionPreference = "Stop"

function Invoke-Api {
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [object]$Body)
    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        SkipHttpErrorCheck = $true
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = $Body | ConvertTo-Json -Compress -Depth 6
    }
    $response = Invoke-WebRequest @params
    $parsed = $null
    if (-not [string]::IsNullOrWhiteSpace($response.Content)) {
        try { $parsed = $response.Content | ConvertFrom-Json } catch { $parsed = $response.Content }
    }
    [pscustomobject]@{ status = [int]$response.StatusCode; headers = $response.Headers; body = $parsed }
}

function Decode-JwtPayload([string]$Token) {
    $part = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    if ($part.Length % 4 -eq 2) { $part += '==' }
    if ($part.Length % 4 -eq 3) { $part += '=' }
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($part)) | ConvertFrom-Json
}

$account = Get-Content $AccountSecretPath -Raw | ConvertFrom-Json
$accountToken = $account.token.body.token
$userId = $account.token.body.user_id
$mac = "AA_BB_CC_DD_EE_4F"
$headbandId = "00000000-0000-4000-8000-000000000000"
$appHeaders = @{
    Authorization = "Bearer $accountToken"
    "x-app-version" = "2.15.1"
    "x-app-build-code" = "478"
    "x-app-os" = "10"
    "Accept-Language" = "en"
}

$before = Invoke-Api GET "https://api.rythm.co/v1/dreem/dreemer/allotment/?dreemer=$userId" $appHeaders
$already = $false
if ($before.status -eq 200 -and $null -ne $before.body.results) {
    $already = @($before.body.results | Where-Object { $_.device -eq $headbandId -or $_.headband -eq $headbandId }).Count -gt 0
}
$create = $null
if (-not $already) {
    $create = Invoke-Api POST "https://api.rythm.co/v1/dreem/dreemer/allotment/" $appHeaders @{ dreemer = $userId; device = $headbandId }
    if ($create.status -notin @(200, 201, 204)) { throw "Rythm allotment failed with HTTP $($create.status)" }
}

$rotation = Invoke-Api POST "https://api.rythm.co/v1/dreem/headband/headband/update_password/" $appHeaders @{ headband_mac = $mac }
if ($rotation.status -ne 200 -or [string]::IsNullOrWhiteSpace($rotation.body.password)) {
    throw "Rythm D905 rotation failed with HTTP $($rotation.status)"
}
$devicePassword = $rotation.body.password
$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${mac}:$devicePassword"))
$loginHeaders = @{
    Authorization = "Basic $basic"
    "x-app-version" = "2.15.1"
    "x-app-build-code" = "478"
    "x-app-os" = "10"
    "Accept-Language" = "en"
}
$login = Invoke-Api POST "https://login.rythm.co/token/" $loginHeaders
if ($login.status -notin @(200, 201) -or [string]::IsNullOrWhiteSpace($login.body.token)) {
    throw "Rythm device login failed with HTTP $($login.status)"
}
$claims = Decode-JwtPayload $login.body.token

$probes = @()
foreach ($profile in @(
    @{ name = "legacy_app"; version = "2.15.1"; build = "478"; os = "10" },
    @{ name = "beacon_app"; version = "1.0.4"; build = "104"; os = "10" },
    @{ name = "auth_only"; version = $null; build = $null; os = $null }
)) {
    $headers = @{ Authorization = "Bearer $($login.body.token)"; "Accept-Language" = "en" }
    if ($null -ne $profile.version) {
        $headers["x-app-version"] = $profile.version
        $headers["x-app-build-code"] = $profile.build
        $headers["x-app-os"] = $profile.os
    }
    $response = Invoke-Api GET "https://api.rythm.co/v1/dreem/headband/firmware/" $headers
    $probes += [pscustomobject]@{ profile = $profile.name; response = $response }
}

[ordered]@{
    createdAt = (Get-Date).ToUniversalTime().ToString("o")
    account = @{ email = $account.email; user_id = $userId }
    headset = @{ id = $headbandId; mac = $mac }
    allotment = @{ already_allotted = $already; before = $before; create = $create }
    device_password = $devicePassword
    device_login = $login
    device_claims = $claims
    firmware_probes = $probes
} | ConvertTo-Json -Depth 20 | Set-Content $OutputSecretPath -Encoding utf8

[pscustomobject]@{
    user_id = $userId
    allotment_created = (-not $already)
    allotment_status = if ($null -eq $create) { $before.status } else { $create.status }
    password_rotated = $true
    password_length = $devicePassword.Length
    device_login_status = $login.status
    device_permissions = $claims.permissions
    firmware_probes = @($probes | ForEach-Object {
        [pscustomobject]@{ profile = $_.profile; status = $_.response.status; detail = $_.response.body.detail }
    })
    saved_to = $OutputSecretPath
} | ConvertTo-Json -Depth 8
