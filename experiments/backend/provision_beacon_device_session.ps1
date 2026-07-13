param(
    [string]$AccountSecretPath = "secrets/dreem-beacon-registered-test-account.json",
    [string]$OutputSecretPath = "secrets/dreem-beacon-device-session.json"
)

$ErrorActionPreference = "Stop"

function Invoke-JsonRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Headers,
        [object]$Body
    )

    $params = @{
        Method = $Method
        Uri = $Uri
        Headers = $Headers
        SkipHttpErrorCheck = $true
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = $Body | ConvertTo-Json -Compress -Depth 8
    }

    $response = Invoke-WebRequest @params
    $parsed = $null
    if (-not [string]::IsNullOrWhiteSpace($response.Content)) {
        try { $parsed = $response.Content | ConvertFrom-Json } catch { $parsed = $response.Content }
    }
    [pscustomobject]@{
        status = [int]$response.StatusCode
        headers = $response.Headers
        body = $parsed
    }
}

function Decode-JwtPayload {
    param([string]$Token)
    $segment = $Token.Split('.')[1].Replace('-', '+').Replace('_', '/')
    switch ($segment.Length % 4) {
        2 { $segment += '==' }
        3 { $segment += '=' }
    }
    [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($segment)) | ConvertFrom-Json
}

$account = Get-Content $AccountSecretPath -Raw | ConvertFrom-Json
$accountToken = $account.token.body.token
$userId = $account.token.body.user_id
$mac = "AA_BB_CC_DD_EE_4F"
$headbandId = "00000000-0000-4000-8000-000000000000"
$apiHeaders = @{
    Authorization = "Bearer $accountToken"
    "x-app-version" = "1.0.4"
    "x-app-build-code" = "104"
    "x-app-os" = "10"
    "Accept-Language" = "en"
}

$allotmentsBefore = Invoke-JsonRequest -Method GET -Uri "https://api.band.beacon.bio/v1/dreem/dreemer/allotment/?dreemer=$userId" -Headers $apiHeaders
$alreadyAllotted = $false
if ($allotmentsBefore.status -eq 200 -and $null -ne $allotmentsBefore.body.results) {
    $alreadyAllotted = @($allotmentsBefore.body.results | Where-Object {
        $_.device -eq $headbandId -or $_.headband -eq $headbandId
    }).Count -gt 0
}

$allotmentCreate = $null
if (-not $alreadyAllotted) {
    $allotmentCreate = Invoke-JsonRequest -Method POST -Uri "https://api.band.beacon.bio/v1/dreem/dreemer/allotment/" -Headers $apiHeaders -Body @{
        dreemer = $userId
        device = $headbandId
    }
    if ($allotmentCreate.status -notin @(200, 201, 204)) {
        throw "Allotment creation failed with HTTP $($allotmentCreate.status)"
    }
}

$passwordResponse = Invoke-JsonRequest -Method POST -Uri "https://api.band.beacon.bio/v1/dreem/headband/headband/update_password/" -Headers $apiHeaders -Body @{
    headband_mac = $mac
}
if ($passwordResponse.status -ne 200 -or [string]::IsNullOrWhiteSpace($passwordResponse.body.password)) {
    throw "Password rotation failed with HTTP $($passwordResponse.status)"
}
$devicePassword = $passwordResponse.body.password

$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("${mac}:$devicePassword"))
$loginHeaders = @{
    Authorization = "Basic $basic"
    "x-app-version" = "1.0.4"
    "x-app-build-code" = "104"
    "x-app-os" = "10"
    "Accept-Language" = "en"
}

$deviceLogins = [ordered]@{}
foreach ($loginDomain in @("login.band.beacon.bio", "login.rythm.co")) {
    $deviceLogins[$loginDomain] = Invoke-JsonRequest -Method POST -Uri "https://$loginDomain/token/" -Headers $loginHeaders
}

$firmwareProbes = @()
foreach ($loginDomain in $deviceLogins.Keys) {
    $login = $deviceLogins[$loginDomain]
    if ($login.status -notin @(200, 201) -or [string]::IsNullOrWhiteSpace($login.body.token)) { continue }
    $token = $login.body.token
    foreach ($apiDomain in @("api.band.beacon.bio", "api.rythm.co")) {
        foreach ($profile in @(
            @{ name = "beacon_app"; version = "1.0.4"; build = "104"; os = "10" },
            @{ name = "legacy_app"; version = "2.15.1"; build = "478"; os = "10" },
            @{ name = "auth_only"; version = $null; build = $null; os = $null }
        )) {
            $headers = @{ Authorization = "Bearer $token"; "Accept-Language" = "en" }
            if ($null -ne $profile.version) {
                $headers["x-app-version"] = $profile.version
                $headers["x-app-build-code"] = $profile.build
                $headers["x-app-os"] = $profile.os
            }
            $probe = Invoke-JsonRequest -Method GET -Uri "https://$apiDomain/v1/dreem/headband/firmware/" -Headers $headers
            $firmwareProbes += [pscustomobject]@{
                login_domain = $loginDomain
                api_domain = $apiDomain
                header_profile = $profile.name
                response = $probe
            }
        }
    }
}

$claims = [ordered]@{}
foreach ($loginDomain in $deviceLogins.Keys) {
    $login = $deviceLogins[$loginDomain]
    if ($login.status -in @(200, 201) -and -not [string]::IsNullOrWhiteSpace($login.body.token)) {
        $claims[$loginDomain] = Decode-JwtPayload $login.body.token
    }
}

$result = [ordered]@{
    createdAt = (Get-Date).ToUniversalTime().ToString("o")
    account = @{ email = $account.email; user_id = $userId }
    headset = @{ id = $headbandId; mac = $mac }
    allotment = @{
        already_allotted = $alreadyAllotted
        before = $allotmentsBefore
        create = $allotmentCreate
    }
    device_password = $devicePassword
    device_logins = $deviceLogins
    device_claims = $claims
    firmware_probes = $firmwareProbes
}

$result | ConvertTo-Json -Depth 20 | Set-Content $OutputSecretPath -Encoding utf8

$probeSummary = foreach ($item in $firmwareProbes) {
    $body = $item.response.body
    $bodyShape = if ($null -eq $body) {
        "empty"
    } elseif ($body -is [string]) {
        "text"
    } else {
        ($body.PSObject.Properties.Name | Sort-Object) -join ","
    }
    [pscustomobject]@{
        login = $item.login_domain
        api = $item.api_domain
        headers = $item.header_profile
        status = $item.response.status
        body_shape = $bodyShape
    }
}

[pscustomobject]@{
    user_id = $userId
    allotment_created = (-not $alreadyAllotted)
    allotment_status = if ($null -eq $allotmentCreate) { $allotmentsBefore.status } else { $allotmentCreate.status }
    password_rotated = $true
    password_length = $devicePassword.Length
    device_login_statuses = [ordered]@{
        beacon = $deviceLogins["login.band.beacon.bio"].status
        rythm = $deviceLogins["login.rythm.co"].status
    }
    device_permissions = [ordered]@{
        beacon = $claims["login.band.beacon.bio"].permissions
        rythm = $claims["login.rythm.co"].permissions
    }
    firmware_probes = $probeSummary
    saved_to = $OutputSecretPath
} | ConvertTo-Json -Depth 8
