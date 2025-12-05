# WMS CLI

A command-line tool for making WMS (Web Map Service) requests with fuzzy search. Designed for meteorological data services.

## Features

- **Fuzzy search** - Type `wms map gfs tempf` and it resolves to `GFS_Surface_Temperature_in_F`
- **Smart defaults** - Automatically uses latest RUN, default FORECAST, and appropriate dimensions
- **Debug mode** - Preview resolved URLs without fetching
- **Multiple request types** - GetMap, GetGTile, GetLegendGraphic
- **Batch automation** - Hammer layers with all dimension combinations
- **Terminal image display** - View images directly in the terminal (supports Kitty, iTerm2, Sixel, and ASCII fallback)

## Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
# Initialize with a capabilities file or server
./wms init ./useful-files/capabilities.xml
# or
./wms init http://your-wms-server/wms

# Search for layers
./wms layers gfs temp
./wms layers galwem cloud

# Fetch a map (with debug to see URL without fetching)
./wms map gfs tempf --debug
./wms map galwem cloud 850 +6h --debug

# Fetch a random tile
./wms tile hrrr precip --debug

# Fetch legend
./wms legend gfs wind --debug

# Hammer all matching layers
./wms hammer gfs --dry-run
```

## Commands

### `wms init <source>`
Initialize from a local capabilities XML file or remote WMS server.

```bash
./wms init ./capabilities.xml
./wms init http://localhost:8008/ogc/AFW_WMS
./wms init ./caps.xml --server http://prod-server/wms
```

### `wms status`
Show current configuration.

### `wms layers [query]`
List available layers, optionally filtered by fuzzy search.

```bash
./wms layers              # List all
./wms layers gfs          # Search for GFS layers
./wms layers cloud 850    # Search with multiple terms
```

### `wms map <query>`
Fetch and display a GetMap image in the terminal.

```bash
./wms map gfs temp                    # Basic query
./wms map galwem cloud 850            # With elevation
./wms map hrrr precip +6h             # With forecast time
./wms map gfs wind contour            # With style hint
./wms map gfs temp --debug            # Show URL only
./wms map gfs temp -o output.png      # Show png and save
```

### `wms tile <query>`
Fetch and display a random GetGTile in the terminal.

```bash
./wms tile galwem cloud
./wms tile gfs temp --zoom 5
./wms tile hrrr --debug
./wms tile gfs temp -o tile.png       # Save to file AND display
```

### `wms legend <query>`
Fetch and display a GetLegendGraphic in the terminal.

```bash
./wms legend gfs temp
./wms legend galwem wind --debug
./wms legend gfs temp -o legend.png   # Save to file AND display
```

### `wms hammer <query>`
Hammer all layers matching query with all dimension combinations.

```bash
./wms hammer gfs                      # Hammer all GFS layers
./wms hammer galwem cloud -w 10       # 10 workers
./wms hammer hrrr --dry-run           # Preview only
```

## Fuzzy Search Syntax

The fuzzy search understands several patterns:

- **Model + product**: `gfs temp`, `galwem cloud`, `hrrr precip`
- **Temperature units**: `tempf` (Fahrenheit), `tempc` (Celsius)
- **Elevation**: `850`, `500`, `300` (common pressure levels in hPa)
- **Forecast time**: `+6h`, `+24h`, `+2d`
- **Style hints**: `contour`, `filled`, `wind`

Examples:
```bash
./wms map gfs tempf 500 +12h    # GFS Temperature in F at 500hPa, 12hr forecast
./wms map galwem wind 850       # GALWEM Wind at 850hPa
./wms map hrrr cloud +3h        # HRRR Clouds at 3hr forecast
```

## Project Structure

```
wms-cli/
├── wms                    # Entry point script
├── src/
│   ├── cli.py             # Click CLI commands
│   ├── fuzzy.py           # Fuzzy search engine
│   ├── resolver.py        # Query resolution
│   ├── config.py          # Configuration management
│   ├── wms_client.py      # HTTP client for WMS
│   ├── wms_parser.py      # Capabilities XML parser
│   └── hammer.py          # Batch automation
├── useful-files/
│   ├── capabilities.xml   # Sample capabilities (687 layers)
│   └── wms-queries.txt    # Example queries
└── docs/
    ├── CLAUDE.md          # Development notes
    └── HAMMER_USAGE.md    # Hammer documentation
```

## Terminal Image Display

The CLI displays PNG images directly in your terminal by default using Unicode half-block characters with dual colors for 2x vertical resolution:

```bash
./wms map gfs temp                    # Displays image without saving
./wms tile galwem cloud               # Displays image without saving
./wms legend hrrr precip              # Displays image without saving
./wms map gfs temp -o file.png        # Saves AND displays
```

Images are rendered using the `▀` character with:
- **Foreground color** = top pixel
- **Background color** = bottom pixel
- **Full RGB color** support using ANSI 24-bit color codes
- Works in any terminal that supports 24-bit color

## Configuration

Config is stored in `~/.wms/config.json` after running `wms init`.

## Dependencies

- Python 3.10+
- click - CLI framework
- rapidfuzz - Fuzzy string matching
- requests - HTTP client
- lxml - XML parsing
- textual - TUI framework (for future interactive mode)
- Pillow - Image handling
