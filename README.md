# WMS CLI

A command-line tool for making WMS (Web Map Service) requests with fuzzy search. Designed for meteorological data services.

## Features

- **Fuzzy search** - Type `wms map gfs tempf` and it resolves to `GFS_Surface_Temperature_in_F`
- **Smart defaults** - Automatically uses latest RUN, default FORECAST, and appropriate dimensions
- **Multi-server support** - Register and manage multiple WMS servers
- **CAC/Auth support** - Works with CAC-protected and authentication-required servers
- **Capabilities diff** - Compare capabilities between servers and track changes
- **Debug mode** - Preview resolved URLs without fetching
- **Multiple request types** - GetMap, GetGTile, GetLegendGraphic
- **Batch automation** - Hammer layers with all dimension combinations

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
./wms init ./capabilities.xml
# or
./wms init http://your-wms-server/wms

# Search for layers
./wms layers gfs temp

# Fetch a map (with debug to see URL without fetching)
./wms map gfs tempf --debug

# Fetch a random tile
./wms tile hrrr precip --debug

# Fetch legend
./wms legend gfs wind --debug
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
./wms layers                      # List all
./wms layers gfs                  # Search for GFS layers
./wms layers cloud 850            # Search with multiple terms
./wms layers --server prod        # List from a specific server
./wms layers gfs --server staging # Search a specific server
```

### `wms map <query>`
Fetch a GetMap image.

```bash
./wms map gfs temp                    # Basic query
./wms map galwem cloud 850            # With elevation
./wms map hrrr precip +6h             # With forecast time
./wms map gfs wind contour            # With style hint
./wms map gfs temp --debug            # Show URL only
./wms map gfs temp -o output.png      # Custom filename
```

### `wms tile <query>`
Fetch a random GetGTile.

```bash
./wms tile galwem cloud
./wms tile gfs temp --zoom 5
./wms tile hrrr --debug
```

### `wms legend <query>`
Fetch a GetLegendGraphic.

```bash
./wms legend gfs temp
./wms legend galwem wind --debug
```

### `wms hammer <query>`
Hammer all layers matching query with all dimension combinations.

```bash
./wms hammer gfs                      # Hammer all GFS layers
./wms hammer galwem cloud -w 10       # 10 workers
./wms hammer hrrr --dry-run           # Preview only
```

### `wms inspect <query>`
Show detailed information about a layer.

```bash
./wms inspect gfs temp                # Inspect a layer
./wms inspect GFS_Temperature_in_C    # Exact layer name
./wms inspect gfs temp --server prod  # From specific server
./wms inspect gfs temp --json         # JSON output
```

---

## Multi-Server Management

Manage multiple WMS servers for comparison and querying.

### `wms server add <name> <url>`
Register a named WMS server.

```bash
# Standard server - fetch capabilities automatically
./wms server add prod "https://prod.example.com/wms"

# CAC/auth-protected server - provide local capabilities file
./wms server add afweather "https://afweather.mil/wms" --caps-file ./caps.xml

# Register without fetching (for manual import later)
./wms server add internal "https://internal.server/wms" --no-fetch --notes "Requires VPN"

# With SSH tunnel documentation
./wms server add tunneled "http://localhost:8080/wms" --ssh-tunnel "user@bastion:8080:server:80"
```

### `wms server list`
List all registered servers.

```bash
./wms server list           # Basic listing
./wms server list -v        # Verbose with details
```

### `wms server remove <name>`
Remove a registered server.

```bash
./wms server remove staging
./wms server remove staging -y    # Skip confirmation
```

### `wms server fetch <name>`
Refresh capabilities for a server.

```bash
./wms server fetch prod                              # Fetch from URL
./wms server fetch afweather --caps-file ./new.xml   # Update from file
```

### `wms server fetch-interactive <name>`
Browser-based fetch for CAC/auth-protected servers.

```bash
./wms server fetch-interactive afweather
./wms server fetch-interactive afweather --watch-dir ~/Desktop
./wms server fetch-interactive afweather --timeout 600
```

This command:
1. Opens the GetCapabilities URL in your browser
2. Prompts you to authenticate (CAC, login, etc.)
3. Watches your Downloads folder for the XML file
4. Auto-imports when the file appears

### `wms server update-caps <name> <file>`
Manually import capabilities from a file.

```bash
./wms server update-caps afweather ~/Downloads/capabilities.xml
```

---

## Capabilities Diff & Compare

Compare WMS capabilities between servers to track changes.

### `wms diff <source_a> <source_b>`
Compare two capability sources (servers, files, or URLs).

```bash
# Compare registered servers
./wms diff prod staging

# Compare server with local file
./wms diff prod ./new_caps.xml

# Compare two local files
./wms diff ./old.xml ./new.xml

# Compare with live URL
./wms diff prod "https://new-server.com/wms"
```

### Diff Options

```bash
# Verbose output with full details
./wms diff prod staging -v

# Show statistics with percentages
./wms diff prod staging --stats

# Filter by change type
./wms diff prod staging --filter added
./wms diff prod staging --filter removed
./wms diff prod staging --filter modified

# Single layer deep diff
./wms diff prod staging --layer GFS_Temperature_in_C

# JSON output
./wms diff prod staging --json

# Save to file
./wms diff prod staging -o diff_report.txt

# Summary only
./wms diff prod staging --summary

# Show unchanged layers too
./wms diff prod staging --show-unchanged

# Skip service metadata
./wms diff prod staging --layers-only
```

### Example Output

**Basic diff:**
```
Comparing: prod → staging

Layers:
  + NewLayer1
  - OldLayer2
  ~ ModifiedLayer
    Dimension 'TIME' modified:
      +3 values

Summary: 1 added, 1 removed, 1 modified, 95 unchanged
```

**Statistics (`--stats`):**
```
═══ DIFF STATISTICS ═══

── Layer Counts ──
  Layers in A: 100
  Layers in B: 102
  Difference:  +2

── Change Breakdown ──
  Added:       3  ( 2.9%) ██░░░░░░░░░░░░░░░░░░
  Removed:     1  ( 1.0%) █░░░░░░░░░░░░░░░░░░░
  Modified:    5  ( 4.9%) █░░░░░░░░░░░░░░░░░░░
  Unchanged:  93  (91.2%) ██████████████████░░

── Assessment ──
  ✓ Net increase in layers
  ✓ Low change ratio: 8.8% of layers affected
```

---

## CAC/Auth-Protected Server Workflow

For servers requiring CAC cards or special authentication:

```bash
# 1. Register server without fetching
./wms server add afweather "https://afweather.mil/wms" --no-fetch --notes "Requires CAC"

# 2. Use interactive fetch (opens browser, watches Downloads)
./wms server fetch-interactive afweather

# OR manually download and import:
# - Open browser to GetCapabilities URL
# - Authenticate with CAC
# - Save the XML file
# - Import it:
./wms server update-caps afweather ~/Downloads/capabilities.xml

# 3. Now use normally
./wms layers --server afweather
./wms diff prod afweather
./wms inspect gfs temp --server afweather
```

---

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

---

## Project Structure

```
wms-cli/
├── wms                    # Entry point script
├── src/
│   ├── cli.py             # Click CLI commands
│   ├── config.py          # Configuration & server management
│   ├── fuzzy.py           # Fuzzy search engine
│   ├── resolver.py        # Query resolution
│   ├── wms_client.py      # HTTP client for WMS
│   ├── wms_parser.py      # Capabilities XML parser
│   ├── diff.py            # Capabilities comparison engine
│   ├── diff_formatter.py  # Diff output formatting
│   ├── browser_fetch.py   # Browser-based fetch for CAC/auth
│   └── hammer.py          # Batch automation
└── tests/
    └── test_diff.py       # Unit tests for diff engine
```

## Configuration

Config is stored in `~/.wms/config.json` after running `wms init`.

Server capabilities are cached in `~/.wms/servers/`.

## Dependencies

- Python 3.10+
- click - CLI framework
- rapidfuzz - Fuzzy string matching
- requests - HTTP client
- lxml - XML parsing
- watchdog - File system monitoring (for interactive fetch)
- textual - TUI framework (for future interactive mode)
- Pillow - Image handling
