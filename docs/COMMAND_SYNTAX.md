# WMS CLI Command Syntax Proposal

**Version:** 1.0
**Date:** 2025-12-05

---

## Implementation Status

| Command | Status | Notes |
|---------|--------|-------|
| `wms init` | ✅ **Complete** | Supports file and server sources, `--force` flag |
| `wms map` | ✅ **Complete** | Fuzzy search, dimensions, debug mode, `--bbox`, `--crs`, `--format`, `--style` |
| `wms tile` | ✅ **Working** | Random tile generation |
| `wms legend` | ✅ **Working** | Basic implementation |
| `wms layers` | ✅ **Complete** | Search/list with `--verbose`, `--json`, `--count`, `--all` options |
| `wms hammer` | ✅ **Complete** | Performance testing with profiles, metrics |
| `wms profiles` | ✅ **Complete** | Hammer profile management |
| `wms status` | ✅ **Working** | Shows config |
| `wms batch` | ✅ **Complete** | Fetch all layers matching pattern, `--dry-run`, `--list` |
| `wms groups` | ✅ **Complete** | List layer groups/hierarchy, `--tree`, `--counts` |
| `wms describe` | ✅ **Complete** | Show layer details, dimensions, styles |
| `wms url` | ✅ **Complete** | Build URLs for map/tile/legend/capabilities |
| `wms cache` | ✅ **Complete** | Cache status/clear/refresh subcommands |
| `wms info` | ❌ **Not Implemented** | GetFeatureInfo (low priority) |

### Remaining Enhancements

| Command | Optional Features |
|---------|-------------------|
| `wms tile` | `--row`, `--col` for specific tile coords |
| `wms hammer` | `--all-forecasts` option |
| `wms layers` | `--model` filter option |

---

## Implementation Plan

All core commands have been implemented. Remaining work is optional enhancements.

### Completed ✅

1. ~~Add `--force` flag to `wms init`~~ - Done
2. ~~Add `--bbox`, `--crs`, `--format`, `--style` to `wms map`~~ - Done
3. ~~Add `--verbose`, `--json`, `--count`, `--all` to `wms layers`~~ - Done
4. ~~Implement `wms groups`~~ - Done
5. ~~Implement `wms describe`~~ - Done
6. ~~Implement `wms cache` (status/clear/refresh)~~ - Done
7. ~~Implement `wms batch`~~ - Done
8. ~~Implement `wms url`~~ - Done

### Future Enhancements (Optional)

1. **`wms info`** - GetFeatureInfo request
   - Requires `--point` for coordinates
   - `WMSClient` already has `get_feature_info` method

2. **`wms tile` enhancements**
   - Add `--row`, `--col` for specific tile coordinates

3. **`wms hammer` enhancements**
   - Add `--all-forecasts` to iterate forecast times

4. **`wms layers --model` filter**
   - Filter layers by model name prefix

---

## Overview

This document proposes a comprehensive command-line interface for the WMS CLI tool. The design prioritizes:

1. **Natural language queries** - Use fuzzy matching and intuitive syntax
2. **Dimension shortcuts** - `6h`, `12z`, `850mb` instead of ISO8601 strings
3. **Flexible input** - Commands work with layer names, groups, or search terms
4. **Batch operations** - Process multiple layers efficiently
5. **Developer-friendly** - Debug modes, URL building, dry runs

---

## Command Reference

### `wms init` - Initialize WMS Context

Initialize the tool with a WMS capabilities source. Required before using other commands.

```bash
# From server (fetches GetCapabilities)
wms init <server-url>
wms init http://localhost:8006/ogc/AFW_WMS
wms init https://ogc.shyftwx.com/ogc/WMS

# From local file (for offline use or testing)
wms init <path-to-capabilities.xml>
wms init ./capabilities.xml

# From local file with different server for requests
wms init ./capabilities.xml --server http://prod-server/wms
```

**Options:**
| Option | Description |
|--------|-------------|
| `--server, -s <url>` | Server URL for requests when source is a local file |
| `--force, -f` | Force re-initialization (clears cache) |

**What it does:**
1. Fetches or reads GetCapabilities XML
2. Validates the XML structure
3. Caches capabilities in `~/.wms/capabilities_cache.xml`
4. Saves config to `~/.wms/config.json`

---

### `wms map` - Fetch Single Map Image (GetMap)

Fetch a single map image using fuzzy search to find the layer.

```bash
wms map <query> [dimension-args...]
```

**Query Syntax:**
```bash
# Basic query (fuzzy matches layer name/title)
wms map gfs temp                    # GFS Temperature (any matching layer)
wms map galwem cloud                # GALWEM cloud-related layer
wms map hrrr precipitation          # HRRR precipitation

# With model prefix
wms map galwem cloud base           # GALWEM_CloudBase
wms map gfs temperature 2m          # GFS_Temperature_2m

# With unit preference (for temperature layers)
wms map gfs temp f                  # Fahrenheit version
wms map gfs temp c                  # Celsius version
wms map gfs temp k                  # Kelvin version
```

**Dimension Arguments:**

Dimensions can be specified using natural syntax in any order:

| Syntax | Dimension | Example Values |
|--------|-----------|----------------|
| `6h`, `12h`, `24h`, `2d` | FORECAST | PT6H, PT12H, PT24H, P2D |
| `00z`, `06z`, `12z`, `18z` | RUN | Latest run at that cycle |
| `latest` | RUN | Most recent run available |
| `850`, `500`, `700mb` | ELEVATION | 850, 500, 700 hPa |
| `f`, `c`, `k` | Unit preference | Filters to F/C/K version |

```bash
# With forecast time
wms map gfs temp 6h                 # 6-hour forecast
wms map galwem cloud 12h            # 12-hour forecast
wms map gfs temp 2d                 # 2-day forecast

# With model run time
wms map gfs temp 12z                # Latest 12Z run
wms map galwem wind 00z             # Latest 00Z run
wms map hrrr precip latest          # Most recent run

# With elevation/pressure level
wms map gfs temp 850                # 850 hPa level
wms map galwem wind 500mb           # 500 hPa level

# Combined (any order)
wms map gfs temp f 12z 6h 850       # Fahrenheit, 12Z run, 6h forecast, 850mb
wms map galwem cloud 6h 12z         # Same dimensions, different order
```

**Options:**
| Option | Description |
|--------|-------------|
| `--output, -o <file>` | Output filename (default: auto-generated) |
| `--width, -w <int>` | Image width in pixels (default: 800) |
| `--height, -h <int>` | Image height in pixels (default: 600) |
| `--bbox <minx,miny,maxx,maxy>` | Custom bounding box |
| `--crs <crs>` | Coordinate reference system (default: CRS:84) |
| `--format <fmt>` | Image format (default: image/png) |
| `--style <name>` | Specific style name |
| `--debug, -d` | Show resolved URL without fetching |

**Examples:**
```bash
# Basic usage
wms map gfs temp

# With output file
wms map galwem cloud -o cloud_cover.png

# Custom size
wms map hrrr precip -w 1200 -h 900

# Custom bbox (CONUS)
wms map gfs temp --bbox -125,24,-66,50

# Debug mode (show URL only)
wms map gfs temp 6h 12z --debug
```

---

### `wms batch` - Fetch All Layers in a Group

Fetch all layers matching a group/model pattern. Useful for getting all products from a model run.

```bash
wms batch <group-pattern> [dimension-args...] [options]
```

**Group Patterns:**

The group pattern matches against the layer hierarchy:
- Model name: `galwem`, `gfs`, `hrrr`
- Category: `cloud`, `precipitation`, `wind`
- Partial group path: `galwem/clouds`, `gfs/temperature`

```bash
# All layers from a model
wms batch galwem                    # All GALWEM layers
wms batch gfs                       # All GFS layers
wms batch hrrr                      # All HRRR layers

# All layers in a category
wms batch galwem cloud              # All GALWEM cloud products
wms batch gfs temp                  # All GFS temperature products
wms batch hrrr precipitation        # All HRRR precipitation products

# With glob pattern
wms batch "GALWEM_Cloud*"           # Layers starting with GALWEM_Cloud
wms batch "*Temperature*"           # All temperature layers
wms batch "GFS_*_F"                 # All GFS Fahrenheit layers
```

**With Dimensions:**
```bash
# All GALWEM cloud products at 6h forecast
wms batch galwem cloud 6h

# All GFS products at 12Z run, 24h forecast
wms batch gfs 12z 24h

# All HRRR products at latest run
wms batch hrrr latest
```

**Options:**
| Option | Description |
|--------|-------------|
| `--output, -o <dir>` | Output directory (default: ./wms_output) |
| `--workers, -w <int>` | Parallel download workers (default: 10) |
| `--format <fmt>` | Image format (default: image/png) |
| `--width <int>` | Image width (default: 800) |
| `--height <int>` | Image height (default: 600) |
| `--dry-run` | Show what would be fetched without fetching |
| `--list` | Just list matching layers, don't fetch |
| `--limit <int>` | Max layers to process (default: unlimited) |

**Examples:**
```bash
# Download all GALWEM cloud products
wms batch galwem cloud -o ./galwem_clouds/

# Preview what would be downloaded
wms batch gfs temp --dry-run

# List matching layers without downloading
wms batch hrrr --list

# Limit concurrent downloads
wms batch galwem --workers 5

# Limit number of layers
wms batch gfs --limit 10
```

---

### `wms legend` - Fetch Legend Graphic

Fetch the legend image for a layer's style.

```bash
wms legend <query> [options]
```

```bash
# Basic usage
wms legend gfs temp
wms legend galwem cloud base
wms legend hrrr precipitation

# Specific style
wms legend galwem contrails --style No_Bypass

# Output to file
wms legend gfs temp -o temp_legend.png

# Debug mode
wms legend galwem cloud --debug
```

**Options:**
| Option | Description |
|--------|-------------|
| `--output, -o <file>` | Output filename |
| `--style <name>` | Specific style (default: layer's default style) |
| `--format <fmt>` | Image format (default: image/png) |
| `--debug, -d` | Show URL without fetching |

---

### `wms tile` - Fetch Map Tile (GetGTile)

Fetch a single tile using the vendor-specific GetGTile request. Useful for testing tile servers.

```bash
wms tile <query> [dimension-args...] [options]
```

```bash
# Random tile at default zoom
wms tile gfs temp

# Specific zoom level
wms tile galwem cloud -z 5

# Specific tile coordinates
wms tile hrrr precip --zoom 4 --row 5 --col 10

# With dimensions
wms tile gfs temp 6h 12z -z 3
```

**Options:**
| Option | Description |
|--------|-------------|
| `--zoom, -z <int>` | Tile zoom level (default: 3) |
| `--row <int>` | Tile row (default: random) |
| `--col <int>` | Tile column (default: random) |
| `--output, -o <file>` | Output filename |
| `--style <name>` | Style name |
| `--debug, -d` | Show URL without fetching |

---

### `wms layers` - List and Search Layers

List available layers, optionally filtered by search query.

```bash
wms layers [query] [options]
```

```bash
# List all layers
wms layers

# Search for layers
wms layers gfs                      # All GFS layers
wms layers cloud                    # All cloud-related layers
wms layers temperature              # All temperature layers
wms layers "galwem cloud"           # GALWEM cloud layers

# Show detailed info
wms layers gfs temp --verbose

# List by model
wms layers --model galwem
wms layers --model hrrr

# Output formats
wms layers gfs --json               # JSON output
wms layers --count                  # Just show count
```

**Options:**
| Option | Description |
|--------|-------------|
| `--limit, -n <int>` | Maximum results (default: 20) |
| `--model <name>` | Filter by model name |
| `--verbose, -v` | Show dimensions and styles |
| `--json` | Output as JSON |
| `--count` | Just show count of matching layers |
| `--all` | Show all layers (no limit) |

**Output Columns:**
```
Score  Layer Name                              Dimensions
─────  ──────────────────────────────────────  ──────────────────
100.0  GALWEM_CloudBase                        [RUN, FORECAST]
 95.2  GALWEM_CloudTops                        [RUN, FORECAST]
 90.1  GALWEM_Cloud_Amount                     [RUN, FORECAST]
```

---

### `wms groups` - List Layer Groups

List the hierarchical group structure of available layers.

```bash
wms groups [pattern] [options]
```

```bash
# Show all groups
wms groups

# Filter by pattern
wms groups galwem
wms groups cloud

# Show as tree
wms groups --tree

# Show layer counts
wms groups --counts
```

**Options:**
| Option | Description |
|--------|-------------|
| `--tree` | Show as hierarchical tree |
| `--counts` | Show number of layers in each group |
| `--depth <int>` | Maximum tree depth to show |

**Example Output:**
```
MODEL DATA
├── GALWEM (156 layers)
│   ├── Clouds (24 layers)
│   ├── Precipitation (18 layers)
│   ├── Temperature (12 layers)
│   └── Wind (8 layers)
├── GFS (89 layers)
│   ├── Temperature (15 layers)
│   └── ...
└── HRRR (45 layers)
```

---

### `wms describe` - Show Layer Details

Show detailed information about a specific layer.

```bash
wms describe <query>
```

```bash
wms describe galwem cloud base
wms describe gfs temp f
wms describe "GALWEM_CloudBase"     # Exact name
```

**Output:**
```
Layer: GALWEM_CloudBase
Title: GALWEM Cloud Bases
Model: GALWEM
Path: MODEL DATA > GALWEM > Clouds

Dimensions:
  RUN (12 values)
    Default: 2025-11-05T18:00:00Z
    Range: 2025-11-03T00:00:00Z to 2025-11-05T18:00:00Z
    Cycles: 00Z, 06Z, 12Z, 18Z

  FORECAST (98 values)
    Default: PT0S
    Range: PT0S to P10D
    Shortcuts: 0h, 6h, 12h, 24h, 2d, 3d, 5d, 7d, 10d

Styles:
  - default (GALWEM Cloud Bases)

Bounding Box: -90, -90, 90, 90 (CRS:84)
Queryable: Yes
```

---

### `wms hammer` - Performance Testing

Stress test WMS servers with parallel GetMap requests and track performance metrics.

```bash
wms hammer <query> [options]
```

**Using Profiles (Recommended):**
```bash
# Built-in profiles for different scenarios
wms hammer gfs -p gentle        # 5 workers, small images
wms hammer gfs -p balanced      # 10 workers, medium images
wms hammer gfs -p aggressive    # 50 workers, large images
wms hammer gfs -p stress        # 100 workers - stress testing only

# Create custom profile
wms hammer gfs -w 8 --size small --save-profile myserver

# Use custom profile
wms hammer gfs -p myserver
```

**Custom Settings:**
```bash
# Adjust workers and image size
wms hammer gfs -w 5 --size small

# With timeout and retries
wms hammer galwem cloud -w 10 -t 15 --retries 2

# Save images to directory
wms hammer gfs temp -o ./output/

# Dry run (preview without executing)
wms hammer gfs temp --dry-run

# Save JSON performance report
wms hammer gfs -p balanced -r performance.json
```

**Options:**
| Option | Description |
|--------|-------------|
| `-p, --profile <name>` | Use a saved profile (gentle, balanced, aggressive, stress) |
| `--save-profile <name>` | Save current settings as a new profile |
| `-w, --workers <int>` | Concurrent workers (default: 20) |
| `--size <size>` | Image size: small (256x256), medium (512x512), large (800x600) |
| `-t, --timeout <int>` | Request timeout in seconds (default: 30) |
| `--retries <int>` | Number of times to retry failed requests (default: 0) |
| `-o, --output <dir>` | Save images to directory (by default images are not saved) |
| `-r, --report <file>` | Save JSON performance report |
| `--dry-run` | Show requests without executing |

**Metrics Tracked:**
- Response time: avg, min, max, p50, p95, p99
- Throughput: requests/sec, bytes/sec
- Success/failure rates
- Data transferred per request

**Output:**
```
WMS Hammer - Performance Testing
════════════════════════════════════════════
URL: https://ogc.shyftwx.com/ogc/WMS
Layers: 5 matching 'gfs'
Workers: 10 | Timeout: 20s | Image: 512x512

Progress: 50/50 [████████████████████] 100%

Results:
  Total: 50 | Success: 48 (96%) | Failed: 2 (4%)
  Time: 12.5s | Throughput: 4.0 req/s
  Data: 15.2 MB | Avg size: 316 KB

Response Times:
  Avg: 245ms | Min: 89ms | Max: 1.2s
  p50: 210ms | p95: 450ms | p99: 890ms
════════════════════════════════════════════
```

---

### `wms profiles` - Manage Hammer Profiles

Manage saved profiles for the hammer command.

```bash
# List all profiles
wms profiles list

# Show profile details
wms profiles show balanced
wms profiles show myserver

# Delete a custom profile
wms profiles delete myserver
```

**Built-in Profiles:**
| Profile | Workers | Size | Timeout | Description |
|---------|---------|------|---------|-------------|
| gentle | 5 | small | 30s | Low concurrency - for slow servers |
| balanced | 10 | medium | 20s | Moderate load - most servers |
| aggressive | 50 | large | 30s | High concurrency - robust servers |
| stress | 100 | large | 60s | Maximum load - stress testing only |

**Subcommands:**
| Command | Description |
|---------|-------------|
| `list` | List all available profiles |
| `show <name>` | Show details of a specific profile |
| `delete <name>` | Delete a custom profile (built-ins cannot be deleted) |

---

### `wms info` - Get Feature Info

Query feature information at a specific point (GetFeatureInfo).

```bash
wms info <query> --point <lon,lat> [options]
```

```bash
# Get info at a point
wms info gfs temp --point -105.5,40.0

# With dimensions
wms info galwem cloud 6h 12z --point -98.5,35.2

# Specify pixel coordinates instead of geographic
wms info gfs temp --pixel 400,300 --bbox -125,24,-66,50
```

**Options:**
| Option | Description |
|--------|-------------|
| `--point <lon,lat>` | Geographic coordinates |
| `--pixel <x,y>` | Pixel coordinates (requires --bbox) |
| `--bbox <bounds>` | Bounding box for pixel mode |
| `--format <fmt>` | Info format (text/html, text/xml) |

---

### `wms url` - Build WMS URL

Build a WMS URL without fetching. Useful for integration with other tools.

```bash
wms url <request-type> <query> [options]
```

```bash
# GetMap URL
wms url map gfs temp 6h

# GetGTile URL
wms url tile galwem cloud -z 5

# GetLegendGraphic URL
wms url legend gfs temp

# GetCapabilities URL
wms url capabilities
```

**Output:**
```
http://localhost:8006/ogc/AFW_WMS?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=GFS_Temperature_F&BBOX=-180,-90,180,90&WIDTH=800&HEIGHT=600&CRS=CRS:84&FORMAT=image/png&STYLES=default&DIM_RUN=2025-11-05T12:00:00Z&DIM_FORECAST=PT6H
```

---

### `wms status` - Show Configuration

Show current WMS configuration and cache status.

```bash
wms status
```

**Output:**
```
WMS CLI Status
══════════════════════════════════════════
Source:      http://localhost:8006/ogc/AFW_WMS
Type:        server
Cache:       ~/.wms/capabilities_cache.xml
Cache Age:   2 minutes (valid for 8 more minutes)

Service:     LCMC Wx Web Mapping Services
Version:     1.3.0
Layers:      687 queryable

Models:      GALWEM, GFS, HRRR, GEPS, DWD, ...
Dimensions:  RUN, FORECAST, ELEVATION, TIME, ...
```

---

### `wms cache` - Cache Management

Manage the capabilities cache.

```bash
# Show cache status
wms cache status

# Clear cache (forces refresh on next command)
wms cache clear

# Refresh cache now
wms cache refresh
```

---

## Dimension Reference

### Forecast Time (FORECAST)

| Input | Resolves To | Description |
|-------|-------------|-------------|
| `0h`, `0` | PT0S | Analysis time |
| `6h` | PT6H | 6-hour forecast |
| `12h` | PT12H | 12-hour forecast |
| `24h`, `1d` | PT24H, P1D | 24-hour forecast |
| `48h`, `2d` | PT48H, P2D | 48-hour forecast |
| `3d` | P3D | 3-day forecast |
| `7d`, `1w` | P7D | 7-day forecast |
| `PT6H` | PT6H | ISO 8601 (pass-through) |

### Model Run Time (RUN)

| Input | Resolves To | Description |
|-------|-------------|-------------|
| `00z` | Latest 00Z run | Most recent 00:00 UTC run |
| `06z` | Latest 06Z run | Most recent 06:00 UTC run |
| `12z` | Latest 12Z run | Most recent 12:00 UTC run |
| `18z` | Latest 18Z run | Most recent 18:00 UTC run |
| `latest` | Most recent run | Latest available run (any cycle) |
| ISO datetime | Pass-through | e.g., `2025-11-05T12:00:00Z` |

### Elevation/Pressure Level (ELEVATION)

| Input | Resolves To | Description |
|-------|-------------|-------------|
| `850`, `850mb` | 850 | 850 hPa level |
| `700`, `700hpa` | 700 | 700 hPa level |
| `500` | 500 | 500 hPa level |
| `300` | 300 | 300 hPa level |
| `surface`, `sfc` | surface | Surface level |

### Unit Preference (Temperature)

| Input | Effect |
|-------|--------|
| `f`, `fahrenheit` | Prefer `*_F` layers |
| `c`, `celsius` | Prefer `*_C` layers |
| `k`, `kelvin` | Prefer `*_K` layers |

---

## Examples Cheatsheet

```bash
# Setup
wms init http://server/wms

# Single map
wms map gfs temp f 12z 6h
wms map galwem cloud --debug
wms map hrrr precip -o rain.png

# Batch operations
wms batch galwem cloud 6h -o ./output/
wms batch gfs --dry-run
wms batch "*Temperature*" --list

# Legends
wms legend gfs temp
wms legend galwem contrails --style No_Bypass

# Search and explore
wms layers cloud
wms groups --tree
wms describe galwem cloud base

# Performance testing
wms hammer galwem -p balanced
wms hammer gfs -w 20 --size small
wms hammer gfs --save-profile myprofile

# Hammer profiles
wms profiles list
wms profiles show balanced

# Utilities
wms url map gfs temp 6h
wms status
wms cache clear
```

---

## Configuration

Configuration is stored in `~/.wms/config.json`:

```json
{
  "source_type": "server",
  "source_path": "http://localhost:8006/ogc/AFW_WMS",
  "server_url": "http://localhost:8006/ogc/AFW_WMS",
  "output_dir": ".",
  "default_format": "image/png",
  "cache_ttl": 600
}
```

| Setting | Description | Default |
|---------|-------------|---------|
| `source_type` | "server" or "file" | - |
| `source_path` | Original source location | - |
| `server_url` | URL for WMS requests | - |
| `output_dir` | Default output directory | "." |
| `default_format` | Default image format | "image/png" |
| `cache_ttl` | Cache lifetime in seconds | 600 (10 min) |

---

## Error Handling

### Ambiguous Query
```
$ wms map temp
Error: Query too ambiguous (45% confidence)

Did you mean one of these?
  - GFS_Temperature_F (45%)
  - GFS_Temperature_C (44%)
  - GALWEM_Temperature (42%)
  - HRRR_Temperature_2m (40%)

Tip: Add model name for better matches: 'wms map gfs temp'
```

### Layer Not Found
```
$ wms map xyz123
Error: No layers found matching 'xyz123'

Try:
  - wms layers          # List all available layers
  - wms layers temp     # Search for temperature layers
  - wms groups          # Show layer hierarchy
```

### Dimension Not Available
```
$ wms map gfs temp 96h
Warning: FORECAST 'PT96H' not available for this layer
  Auto-corrected to: PT72H (closest available)
```

---

## Future Enhancements

1. **Animation support** - `wms animate galwem cloud --frames 24`
2. **Diff mode** - `wms diff gfs temp 6h 12h` (compare two forecasts)
3. **Watch mode** - `wms watch galwem --interval 5m` (auto-refresh)
4. **Profile presets** - `wms --profile conus map gfs temp`
5. **Output formats** - GeoTIFF, KMZ export
6. **Layer favorites** - `wms favorite add "gfs temp f"`
