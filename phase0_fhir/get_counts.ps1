$base = "http://localhost:8080/fhir"
$types = @('Organization','Practitioner','Patient','Observation','Condition','Encounter')
foreach ($t in $types) {
    try {
        $c = Invoke-RestMethod -Uri "$base/$t`?_summary=count" -UseBasicParsing -Method GET
        Write-Host "$t : $($c.total)"
    } catch {
        Write-Host "$t : ERROR"
    }
}
