@echo off
echo  Rebuilding intercity-only data...
cd /d "%~dp0"
python scripts\fetch_stations_wikidata.py
python scripts\merge_railway_cache.py
python scripts\build_data.py
python scripts\audit_dates.py
cd public
echo.
echo  China Rail Viz - local server
echo  Open: http://127.0.0.1:8080
echo  Press Ctrl+C to stop
echo.
python -m http.server 8080
pause
