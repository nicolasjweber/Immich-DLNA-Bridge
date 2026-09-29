param (
    [string]$Server = "http://localhost:8200"
)

function Browse-DLNA ($id = "0") {
    $body = @"
<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <ObjectID>$id</ObjectID>
      <BrowseFlag>BrowseDirectChildren</BrowseFlag>
      <Filter>*</Filter>
      <StartingIndex>0</StartingIndex>
      <RequestedCount>25</RequestedCount>
      <SortCriteria></SortCriteria>
    </u:Browse>
  </s:Body>
</s:Envelope>
"@
    try {
        $res = Invoke-RestMethod -Uri "$Server/ContentDirectory/control" `
            -Method Post -Body $body `
            -Headers @{"SOAPAction"='"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"'; "Content-Type"="text/xml"}
        
        [xml]$didl = $res.Envelope.Body.BrowseResponse.Result
        return $didl.'DIDL-Lite'
    }
    catch {
        Write-Error "Failed to connect to DLNA server at $($Server): $_"
        return $null
    }
}

Write-Host "========================================" -ForegroundColor Yellow
Write-Host " Testing Immich DLNA Bridge at $Server " -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

# 1. Health check
try {
    $health = Invoke-RestMethod -Uri "$Server/health" -TimeoutSec 5
    Write-Host "`n[+] Health Check OK:" -ForegroundColor Green
    $health | Format-List
}
catch {
    Write-Error "Cannot reach $Server/health. Is the container running?"
    exit
}

# 2. Browse Root folders
Write-Host "`n--- TOP-LEVEL FOLDERS ---" -ForegroundColor Cyan
$root = Browse-DLNA "0"
if ($root.container) {
    $root.container | Select-Object id, title | Format-Table -AutoSize
}

# 3. Browse People
Write-Host "`n--- PEOPLE IN IMMICH ---" -ForegroundColor Green
$people = Browse-DLNA "people"
if ($people.container) {
    $hasSubcategories = ($people.container | Where-Object { $_.id -like "people:*" })
    if ($hasSubcategories) {
        Write-Host "People sorting categories:" -ForegroundColor Green
        $people.container | Select-Object id, title | Format-Table -AutoSize
        
        Write-Host "Fetching people from 'Most Photos' (people:photos)..." -ForegroundColor Cyan
        $people = Browse-DLNA "people:photos"
    }
    
    if ($people.container) {
        $people.container | Select-Object id, title, @{Name="AvatarURL"; Expression={
            if ($_.albumArtURI -is [array]) { $_.albumArtURI[0].'#text' } else { $_.albumArtURI }
        }} | Select-Object -First 10 | Format-Table -AutoSize
        
        $firstPerson = $people.container[0]
        if ($firstPerson) {
            Write-Host "`n--- SAMPLE ASSETS FOR PERSON: $($firstPerson.title) ($($firstPerson.id)) ---" -ForegroundColor Magenta
            $personAssets = Browse-DLNA $firstPerson.id
            if ($personAssets.item) {
                $personAssets.item | Select-Object id, title, @{Name="ResourceURL"; Expression={
                    if ($_.res -is [array]) { $_.res[0].'#text' } else { $_.res }
                }} | Select-Object -First 5 | Format-Table -AutoSize
            } else {
                Write-Host "No assets returned for this person yet." -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "No people found inside category." -ForegroundColor Yellow
    }
} else {
    Write-Host "No people containers found (or none named)." -ForegroundColor Yellow
}

# 4. Browse Favorites
Write-Host "`n--- SAMPLE FAVORITES ---" -ForegroundColor Cyan
$favs = Browse-DLNA "favorites"
if ($favs.item) {
    $favs.item | Select-Object id, title | Select-Object -First 5 | Format-Table -AutoSize
} else {
    Write-Host "No favorites found." -ForegroundColor Gray
}

Write-Host "`n[+] Test complete! If folders and people appeared above, your DLNA server is 100% operational!" -ForegroundColor Green
