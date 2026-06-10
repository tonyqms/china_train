$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Data = Join-Path $Root 'data'
$Out = Join-Path $Root 'public\data'
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$START_YEAR = 1876
$END_YEAR = (Get-Date).Year

function Parse-Year($v) {
  if (-not $v) { return $null }
  if ("$v" -match '(\d{4})') { return [int]$Matches[1] }
  return $null
}

function In-ChinaBBox($lat, $lon) {
  return ($lon -ge 73 -and $lon -le 135 -and $lat -ge 17.5 -and $lat -le 54.5)
}

$rows = Import-Csv -Path (Join-Path $Data 'stations_wikidata.csv') -Encoding UTF8
$map = @{}
foreach ($row in $rows) {
  $lat = [double]$row.lat
  $lon = [double]$row.lon
  if (-not (In-ChinaBBox $lat $lon)) { continue }
  $id = $row.id
  $openY = Parse-Year $row.open_date
  $closeY = Parse-Year $row.close_date
  if (-not $map.ContainsKey($id)) {
    $map[$id] = @{ id=$id; name_zh=$row.name_zh; name_en=$row.name_en; lat=$lat; lon=$lon; open_year=$openY; close_year=$closeY }
  } else {
    $e = $map[$id]
    if ($openY -and (-not $e.open_year -or $openY -lt $e.open_year)) { $e.open_year = $openY }
    if ($closeY) { $e.close_year = $closeY }
  }
}

$histStations = Get-Content (Join-Path $Data 'historical_stations.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$stationList = New-Object System.Collections.Generic.List[object]
foreach ($s in $map.Values) { if ($s.open_year) { $stationList.Add($s) } }
foreach ($s in $histStations) { $stationList.Add(@{ id=$s.id; name_zh=$s.name_zh; name_en=$s.name_en; lat=[double]$s.lat; lon=[double]$s.lon; open_year=[int]$s.open_year; close_year=$s.close_year }) }

$historical = Get-Content (Join-Path $Data 'historical_railways.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$railwayList = New-Object System.Collections.Generic.List[object]
foreach ($r in $historical) {
  $railwayList.Add(@{ id=$r.id; name_zh=$r.name_zh; name_en=$r.name_en; open_year=[int]$r.open_year; close_year=$r.close_year; coords=$r.coords })
}

$compactStations = New-Object System.Collections.Generic.List[object]
foreach ($s in $stationList) {
  $close = 0
  if ($s.close_year) { $close = [int]$s.close_year }
  $compactStations.Add(@(
    $s.id, $s.name_zh, $s.name_en,
    [math]::Round([double]$s.lon, 4), [math]::Round([double]$s.lat, 4),
    [int]$s.open_year, $close
  ))
}

$compactRailways = New-Object System.Collections.Generic.List[object]
foreach ($r in $railwayList) {
  $close = 0
  if ($r.close_year) { $close = [int]$r.close_year }
  $compactRailways.Add(@($r.id, $r.name_zh, $r.name_en, [int]$r.open_year, $close, $r.coords))
}

$bins = New-Object System.Collections.Generic.List[object]
for ($y = $START_YEAR; $y -le $END_YEAR; $y++) {
  $so = 0; $sc = 0; $ro = 0; $rc = 0
  foreach ($s in $stationList) {
    if ($s.open_year -eq $y) { $so++ }
    if ($s.close_year -eq $y) { $sc++ }
  }
  foreach ($r in $railwayList) {
    if ($r.open_year -eq $y) { $ro++ }
    if ($r.close_year -eq $y) { $rc++ }
  }
  $bins.Add(@{ year=$y; stations_open=$so; stations_close=$sc; railways_open=$ro; railways_close=$rc })
}

$meta = @{
  start_year = $START_YEAR
  end_year = $END_YEAR
  station_count = $compactStations.Count
  railway_count = $compactRailways.Count
  first_line_zh = 'Wusong Railway'
  first_line_en = 'Wusong Railway (Shanghai-Wusong)'
  first_line_year = 1876
  sources = @('Wikidata CC0', 'Curated historical railways', 'Natural Earth coastline')
  generated_at = (Get-Date).ToString('yyyy-MM-dd')
}

[System.IO.File]::WriteAllText((Join-Path $Out 'meta.json'), ($meta | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $Out 'stations.json'), ($compactStations | ConvertTo-Json -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $Out 'railways.json'), ($compactRailways | ConvertTo-Json -Depth 8 -Compress), [Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $Out 'histogram.json'), ($bins | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))

Write-Host "Fast build: $($compactStations.Count) stations, $($compactRailways.Count) railways"
