
$base = "http://localhost:8080/fhir"

# Get paths relative to this script
$patientDir = Join-Path $PSScriptRoot "synthea\output_phase0\fhir"
$logPath = Join-Path $PSScriptRoot "reports\PATIENT_IMPORT_LOG.md"

# Check patient directory
if (-not (Test-Path $patientDir)) {
    Write-Error "Patient directory not found: $patientDir"
    exit 1
}

# Get patient bundle files
$patientFiles = Get-ChildItem -Path $patientDir -Filter "*.json" |
    Where-Object {
        $_.Name -notmatch "hospitalInformation|practitionerInformation"
    }

if (-not $patientFiles) {
    Write-Error "No patient JSON files found."
    exit 1
}

$importLog = @()

foreach ($file in $patientFiles) {
    Write-Host "Importing $($file.Name)..."

    try {
        $response = Invoke-RestMethod `
            -Method POST `
            -Uri $base `
            -Headers @{'Content-Type'='application/fhir+json'} `
            -InFile $file.FullName `
            -ErrorAction Stop

        $successCount = 0
        $failCount = 0

        foreach ($entry in $response.entry) {
            $status = $entry.response.status.Split(' ')[0]

            if ($status -eq '201' -or $status -eq '200') {
                $successCount++
            } else {
                $failCount++
            }
        }

        $importLog += [pscustomobject]@{
            File       = $file.Name
            Success    = $successCount
            Failed     = $failCount
            HttpStatus = 'OK'
        }

        if ($failCount -gt 0) {
            Write-Error "Import had $failCount failed entries. Stopping."
            break
        }
    }
    catch {
        $importLog += [pscustomobject]@{
            File       = $file.Name
            Success    = 0
            Failed     = 0
            HttpStatus = $_.Exception.Message
        }

        Write-Error "Failed to import $($file.Name): $($_.Exception.Message)"
        break
    }
}

# Ensure reports directory exists
$reportDir = Split-Path $logPath -Parent
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

# Write import log
$logLines = @(
    "# Patient Import Log"
    ""
)

foreach ($entry in $importLog) {
    $logLines += "- **$($entry.File)** – HTTP status: $($entry.HttpStatus) – Successful entries: $($entry.Success) – Failed entries: $($entry.Failed)"
}

Set-Content -Path $logPath -Value ($logLines -join "`n") -Encoding UTF8

Write-Host "Import log saved to: $logPath"
