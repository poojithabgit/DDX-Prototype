param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath
)

$base = "http://localhost:8080/fhir"
$bundlePath = (Resolve-Path -LiteralPath $BundlePath).Path
$reachable = $false
$postSuccess = $false
$postError = "Import was not attempted because HAPI FHIR was unreachable."
# 1. Verify HAPI FHIR reachable (GET base)
try {
    $health = Invoke-RestMethod -Method GET -Uri $base -UseBasicParsing -ErrorAction Stop
    $reachable = $true
} catch {
    $reachable = $false
    $healthError = $_.Exception.Message
}

# 2. POST the first patient transaction bundle
if ($reachable) {
    try {
        $postResponse = Invoke-RestMethod -Method POST -Uri $base -Headers @{'Content-Type'='application/fhir+json'} -InFile $bundlePath -UseBasicParsing -ErrorAction Stop
        $postSuccess = $true
    } catch {
        $postSuccess = $false
        $postError = $_.Exception.Message
    }
}

# 3. Retrieve counts after import (if post succeeded)
$types = @("Patient","Observation","Condition","Encounter")
$counts = @{}
if ($postSuccess) {
    foreach ($t in $types) {
        try {
            $cnt = Invoke-RestMethod -Method GET -Uri "$base/$t`?_summary=count" -UseBasicParsing -ErrorAction Stop
            $counts[$t] = $cnt.total
        } catch {
            $counts[$t] = "error"
        }
    }
}

# Build report markdown
$reportPath = Join-Path $PSScriptRoot "reports\FIRST_PATIENT_IMPORT_REPORT.md"
$md = @()
$md += "# First Patient Bundle Import Report"
$md += ""
$md += "## 1. HAPI FHIR Reachability"
if ($reachable) { $md += "- HAPI FHIR endpoint `$base` is reachable (GET succeeded)." } else { $md += "- Could NOT reach HAPI FHIR endpoint. Error: $healthError" }
$md += ""
$md += "## 2. POST of first patient transaction bundle"
if ($postSuccess) {
    $md += "- POST request succeeded."
    $md += "- Response type: $($postResponse.resourceType)"
    if ($postResponse.resourceType -eq "Bundle" -and $postResponse.entry) {
        $totalEntries = $postResponse.entry.Count
        $md += "- Bundle contains $totalEntries entry responses."
        # Count how many entries have a successful HTTP status (201 or 200)
        $success = 0
        $failed = 0
        foreach ($e in $postResponse.entry) {
            if ($e.response -and $e.response.status) {
                $status = $e.response.status.Split(' ')[0]
                if ($status -eq "201" -or $status -eq "200") { $success++ } else { $failed++ }
            } else { $failed++ }
        }
        $md += "- Successful resource creations: $success"
        $md += "- Failed entries: $failed"
    }
} else {
    $md += "- POST request failed. Error: $postError"
}
$md += ""
$md += "## 3. Resource counts after import"
foreach ($t in $types) {
    $md += "- $t : $($counts[$t])"
}

$mdString = $md -join "`n"
Set-Content -Path $reportPath -Value $mdString -Encoding UTF8
