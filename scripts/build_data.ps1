$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Data = Join-Path $Root 'data'
$Out = Join-Path $Root 'public\data'
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$START_YEAR = 1876
$END_YEAR = (Get-Date).Year

function Parse-Year($v) {
  if (-not $v) { return $null }
  if ($v -match '(\d{4})') { return [int]$Matches[1] }
  return $null
}

function In-ChinaBBox($lat, $lon) {
  return ($lon -ge 73 -and $lon -le 135 -and $lat -ge 17.5 -and $lat -le 54.5)
}

$csvPath = Join-Path $Data 'stations_wikidata.csv'
$rows = Import-Csv -Path $csvPath -Encoding UTF8
$map = @{}
foreach ($row in $rows) {
  $lat = [double]$row.lat
  $lon = [double]$row.lon
  if (-not (In-ChinaBBox $lat $lon)) { continue }
  $id = $row.id
  $openY = Parse-Year $row.open_date
  $closeY = Parse-Year $row.close_date
  if (-not $map.ContainsKey($id)) {
    $map[$id] = [ordered]@{
      id = $id; name_zh = $row.name_zh; name_en = $row.name_en
      lat = $lat; lon = $lon; open_year = $openY; close_year = $closeY
    }
  } else {
    $e = $map[$id]
    if ($openY -and (-not $e.open_year -or $openY -lt $e.open_year)) { $e.open_year = $openY }
    if ($closeY) { $e.close_year = $closeY }
    if (-not $e.name_en -and $row.name_en) { $e.name_en = $row.name_en }
    if (-not $e.name_zh -and $row.name_zh) { $e.name_zh = $row.name_zh }
  }
}

$stations = @($map.Values)
$histStations = Get-Content (Join-Path $Data 'historical_stations.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$stations += $histStations
$stations = $stations | Where-Object { $_.open_year }

$historical = Get-Content (Join-Path $Data 'historical_railways.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$railways = @()
foreach ($r in $historical) {
  $railways += [ordered]@{
    id = $r.id; name_zh = $r.name_zh; name_en = $r.name_en
    open_year = $r.open_year; close_year = $r.close_year; coords = $r.coords
  }
}

$tiles = @(
  @{ name='nw'; south=32; west=73; north=54; east=100 },
  @{ name='ne'; south=32; west=100; north=54; east=135 },
  @{ name='sw'; south=18; west=73; north=32; east=100 },
  @{ name='se'; south=18; west=100; north=32; east=135 }
)

function Simplify-Coords($coords, $max=10) {
  if ($coords.Count -le $max) { return $coords }
  $step = [math]::Ceiling($coords.Count / $max)
  $out = @()
  for ($i = 0; $i -lt $coords.Count; $i += $step) { $out += ,$coords[$i] }
  $last = $coords[-1]
  if ($out[-1][0] -ne $last[0] -or $out[-1][1] -ne $last[1]) { $out += ,$last }
  return $out
}

foreach ($tile in $tiles) {
  $q = "[out:json][timeout:90];way[""railway""~""^(rail|light_rail|subway|tram)$""]($($tile.south),$($tile.west),$($tile.north),$($tile.east));out tags geom;"
  Write-Host "Fetching tile $($tile.name)..."
  try {
    $resp = Invoke-RestMethod -Uri 'https://overpass.kumi.systems/api/interpreter' -Method Post -Body @{ data = $q } -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 180
    foreach ($el in $resp.elements) {
      if ($el.type -ne 'way' -or -not $el.geometry) { continue }
      $coords = @($el.geometry | ForEach-Object { ,@([math]::Round($_.lon, 3), [math]::Round($_.lat, 3)) })
      if ($coords.Count -lt 2) { continue }
      $tags = $el.tags
      $openY = Parse-Year $tags.start_date
      if (-not $openY) { $openY = Parse-Year $tags.opening_date }
      $closeY = Parse-Year $tags.end_date
      if ($tags.railway -in @('abandoned','razed') -and -not $closeY) { $closeY = 1990; if (-not $openY) { $openY = 1950 } }
      if (-not $openY) {
        if ($tags.highspeed -eq 'yes') { $openY = 2008 }
        elseif ($tags.railway -in @('subway','light_rail')) { $openY = 1990 }
        else { $openY = 1950 }
      }
      $railways += [ordered]@{
        id = "osm-$($el.id)"
        name_zh = if ($tags.'name:zh') { $tags.'name:zh' } else { $tags.name }
        name_en = if ($tags.'name:en') { $tags.'name:en' } else { $tags.name }
        open_year = $openY; close_year = $closeY
        coords = Simplify-Coords $coords
      }
    }
    Write-Host "  total railways: $($railways.Count)"
  } catch {
    Write-Warning "Tile $($tile.name) failed: $_"
  }
}

$compactStations = $stations | ForEach-Object {
  ,@($_.id, $_.name_zh, $_.name_en,
    [math]::Round($_.lon, 4), [math]::Round($_.lat, 4),
    $_.open_year, $(if ($_.close_year) { $_.close_year } else { 0 }))
}

$compactRailways = $railways | ForEach-Object {
  ,@($_.id, $_.name_zh, $_.name_en, $_.open_year, $(if ($_.close_year) { $_.close_year } else { 0 }), $_.coords)
}

$bins = @()
for ($y = $START_YEAR; $y -le $END_YEAR; $y++) {
  $so = ($stations | Where-Object { $_.open_year -eq $y }).Count
  $sc = ($stations | Where-Object { $_.close_year -eq $y }).Count
  $ro = ($railways | Where-Object { $_.open_year -eq $y }).Count
  $rc = ($railways | Where-Object { $_.close_year -eq $y }).Count
  $bins += @{ year = $y; stations_open = $so; stations_close = $sc; railways_open = $ro; railways_close = $rc }
}

$meta = @{
  start_year = $START_YEAR
  end_year = $END_YEAR
  station_count = $compactStations.Count
  railway_count = $compactRailways.Count
  first_line_zh = [char]0x5434 + [char]0x6c85 + [char]0x94c1 + [char]0x8def
  first_line_en = 'Wusong Railway (Shanghai-Wusong)'
  first_line_year = 1876
  sources = @(
    'Wikidata CC0 railway stations China P1619 P3999',
    'OpenStreetMap railway ways start_date end_date',
    'Curated historical Wusong 1876 Tangxu 1881',
    'Shanghai Baoshan Gov Cambridge IJAS 2014'
  )
  generated_at = (Get-Date).ToString('yyyy-MM-dd')
}

$meta | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $Out 'meta.json') -Encoding UTF8
$compactStations | ConvertTo-Json -Depth 6 -Compress | Set-Content (Join-Path $Out 'stations.json') -Encoding UTF8
$compactRailways | ConvertTo-Json -Depth 8 -Compress | Set-Content (Join-Path $Out 'railways.json') -Encoding UTF8
$bins | ConvertTo-Json -Compress | Set-Content (Join-Path $Out 'histogram.json') -Encoding UTF8

Write-Host "Built $($compactStations.Count) stations, $($compactRailways.Count) railways"
