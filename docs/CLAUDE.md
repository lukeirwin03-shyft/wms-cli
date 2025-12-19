# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**WMS CLI** is a command-line tool for interacting with OGC Web Map Service (WMS) endpoints. It features fuzzy search for layer names and natural language dimension syntax.

### Key Features
- Fuzzy search to find layers by name/description
- Natural dimension syntax: `6h`, `12z`, `850mb` instead of ISO8601
- Batch operations for downloading multiple layers
- Performance testing (hammer) for stress testing WMS servers
- Interactive TUI mode

## Project Structure

```
wms-cli/
├── src/                    # Core modules
│   ├── cli.py              # Click-based CLI commands
│   ├── completions.py      # Shell tab completion
│   ├── config.py           # Configuration and cache management
│   ├── dimension_parser.py # Parse natural time expressions
│   ├── fuzzy.py            # Fuzzy search engine (rapidfuzz)
│   ├── hammer.py           # Batch automation tool
│   ├── smart_resolver.py   # Query resolution with dimensions
│   ├── tui.py              # Interactive TUI (Textual)
│   ├── wms_client.py       # HTTP client for WMS operations
│   └── wms_parser.py       # XML parser for GetCapabilities
├── tests/                  # Test files
├── docs/                   # Documentation
│   ├── USAGE.md            # Comprehensive usage guide
│   ├── COMMAND_SYNTAX.md   # CLI command reference
│   └── CLAUDE.md           # This file - development guide
├── init.sh                 # Setup script (installs CLI + shell completion)
├── pyproject.toml          # Package configuration
├── requirements.txt        # Dependencies
└── wms                     # CLI entry point (dev use)
```

## Development Setup

```bash
# Quick setup (recommended)
./init.sh

# Or manual setup
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Run CLI
wms --help
```

## Key Commands

```bash
# Initialize with a WMS server
wms init https://ogc.shyftwx.com/ogc/WMS

# Search and explore layers
wms layers temp              # Search layers
wms layers temp -v           # With dimensions/styles
wms groups --counts          # List groups
wms describe gfs temp        # Layer details

# Fetch maps
wms map gfs temp f 6h        # Fetch map
wms map gfs temp --debug     # Preview URL
wms legend gfs temp          # Get legend
wms tile gfs temp -z 5       # Get tile

# Batch operations
wms batch gfs temp --list    # List matches
wms batch gfs temp -o ./out/ # Download all
wms hammer gfs -p balanced   # Performance test with profile
wms profiles list            # List hammer profiles

# Cache management
wms cache status             # Check cache
wms cache refresh            # Force refresh

# URL building
wms url map gfs temp 6h      # Build GetMap URL

# Interactive TUI
wms
```

See `docs/USAGE.md` for comprehensive usage guide and `docs/COMMAND_SYNTAX.md` for full command reference.

## Architecture

### Query Resolution Flow

```
User Query: "gfs temp f 12z 6h"
     ↓
SmartQueryResolver
     ↓
1. Extract dimensions: {RUN: '12z', FORECAST: '6h'}
2. Extract unit preference: 'f' (Fahrenheit)
3. Clean query: "gfs temp"
     ↓
FuzzySearchEngine
     ↓
4. Fuzzy match layer name
5. Apply unit filter
6. Return: GFS_Temperature_F
     ↓
DimensionParser
     ↓
7. Validate '12z' → find closest 12Z run
8. Validate '6h' → PT6H
     ↓
Result: Resolved layer with valid dimensions
```

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `SmartQueryResolver` | `smart_resolver.py` | Main query resolution orchestrator |
| `FuzzySearchEngine` | `fuzzy.py` | Layer name matching with rapidfuzz |
| `DimensionParser` | `dimension_parser.py` | Parse and validate dimension values |
| `WMSClient` | `wms_client.py` | HTTP client for all WMS requests |
| `WMSCapabilities` | `wms_parser.py` | Parsed GetCapabilities data |

### Configuration

Config stored in `~/.wms/`:
- `config.json` - Source URL, output directory, settings
- `capabilities_cache.xml` - Cached GetCapabilities (10-min sliding TTL)
- `profiles.json` - Custom hammer profiles

## WMS Concepts

### Dimensions

WMS layers can have multiple dimensions:

| Dimension | Purpose | Example Values |
|-----------|---------|----------------|
| RUN | Model run time | 2025-11-05T12:00:00Z |
| FORECAST | Forecast period | PT6H, PT12H, P2D |
| ELEVATION | Pressure level | 850, 500, 300 (hPa) |
| TIME | Valid time | ISO datetime |
| STATION | Point location | For meteograms |
| PLACE | Line location | For cross-sections |

### Natural Dimension Syntax

The CLI accepts shortcuts:
- `6h`, `12h`, `24h` → FORECAST (PT6H, PT12H, PT24H)
- `00z`, `12z`, `latest` → RUN (model run time)
- `850`, `500mb` → ELEVATION (pressure level)
- `f`, `c`, `k` → Unit preference (Fahrenheit/Celsius/Kelvin)

## Testing

```bash
# Run smart resolver tests
python tests/test_smart_resolver.py

# Verify syntax
python -m py_compile src/*.py
```

## Common Tasks

### Adding a New CLI Command

1. Add command function in `src/cli.py`
2. Use `@cli.command()` decorator
3. Use `get_resolver()` to get SmartQueryResolver
4. Handle `AmbiguousQueryError` for low-confidence matches

### Modifying Dimension Parsing

1. Edit `src/dimension_parser.py`
2. Add patterns to `FORECAST_SHORTCUTS` or `RUN_PATTERNS`
3. Update `_extract_tokens()` in `smart_resolver.py` if needed

### Updating Cache Behavior

1. Edit `src/config.py`
2. Cache TTL is in `WMSConfig.cache_ttl` (default 600s)
3. `is_cache_valid()` and `touch_cache()` handle sliding window

## Implementation Status

All core commands are implemented and working:

| Command | Status |
|---------|--------|
| `wms init` | ✅ Complete |
| `wms map` | ✅ Complete |
| `wms tile` | ✅ Complete |
| `wms legend` | ✅ Complete |
| `wms layers` | ✅ Complete |
| `wms describe` | ✅ Complete |
| `wms groups` | ✅ Complete |
| `wms batch` | ✅ Complete |
| `wms hammer` | ✅ Complete |
| `wms profiles` | ✅ Complete |
| `wms url` | ✅ Complete |
| `wms cache` | ✅ Complete |
| `wms status` | ✅ Complete |

See `docs/COMMAND_SYNTAX.md` for detailed command syntax and options.
