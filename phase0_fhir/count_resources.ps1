$base = "http://localhost:8080/fhir"

$types = @("Patient", "Observation", "Condition", "Encounter", "Organization", "Practitioner")

foreach ($type in $types) {
    try {
        $result = Invoke-RestMethod -Uri "$base/$type`?_summary=count"
        Write-Host "$type : $($result.total)"
    }
    catch {
        Write-Host "$type : Could not retrieve count"
    }
}
