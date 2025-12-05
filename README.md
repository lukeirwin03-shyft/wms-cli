# WMS CLI

A command-line tool for making WMS (Web Map Service) requests with fuzzy search and natural dimension syntax.

## Features

- **Fuzzy search** - Find layers with natural queries like `gfs temp f`
- **Natural dimensions** - Use `6h`, `12z`, `850mb` instead of ISO8601
- **Smart defaults** - Automatically uses latest RUN, default FORECAST
- **Shell completion** - Tab completion for commands, options, and layer names
- **Terminal image display** - View images directly in terminal with `--display` flag
- **Cache management** - 10-minute sliding TTL cache for capabilities
- **Batch downloads** - Download multiple layers matching a pattern
- **Performance testing** - Hammer WMS servers with concurrent requests
- **Interactive TUI** - Terminal UI with autocomplete

## Installation

```bash
# Quick setup (installs CLI + shell completion)
./init.sh

# Or manual setup
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## Shell Completion

Enable tab completion for commands, options, and layer names:

**Bash** (add to `~/.bashrc`):
```bash
eval "$(_WMS_COMPLETE=bash_source wms)"
```

**Zsh** (add to `~/.zshrc`):
```bash
eval "$(_WMS_COMPLETE=zsh_source wms)"
```

**Fish** (run once):
```bash
_WMS_COMPLETE=fish_source wms > ~/.config/fish/completions/wms.fish
```

After adding, restart your shell or run `source ~/.bashrc` (or `~/.zshrc`).

### What Completes

- `wms <tab>` - Shows all commands
- `wms map --<tab>` - Shows all options
- `wms map gfs<tab>` - Shows matching layer names

## Quick Start

```bash
# Initialize with a WMS server
wms init https://ogc.shyftwx.com/ogc/WMS

# Search for layers
wms layers temp

# Fetch a map with natural syntax
wms map gfs temp f 6h

# Get layer details
wms describe gfs surface temp

# Launch interactive TUI
wms
```

## Commands

| Command | Description |
|---------|-------------|
| `wms init <source>` | Initialize from server URL or XML file |
| `wms map <query>` | Fetch a map image (GetMap) |
| `wms tile <query>` | Fetch a tile (GetGTile) |
| `wms legend <query>` | Fetch legend graphic |
| `wms layers [query]` | List/search layers |
| `wms describe <query>` | Show layer details |
| `wms groups` | List layer groups |
| `wms batch <query>` | Download all matching layers |
| `wms hammer <query>` | Performance testing |
| `wms url <type> <query>` | Build URL without fetching |
| `wms cache status` | Show cache status |
| `wms cache clear` | Clear capabilities cache |
| `wms cache refresh` | Force refresh from server |
| `wms status` | Show configuration |
| `wms` | Launch interactive TUI |

## Natural Dimension Syntax

Instead of ISO8601 strings, use shortcuts:

| Input | Dimension | Meaning |
|-------|-----------|---------|
| `6h`, `12h`, `24h` | FORECAST | Forecast time |
| `00z`, `12z`, `latest` | RUN | Model run time |
| `850`, `500mb` | ELEVATION | Pressure level |
| `f`, `c`, `k` | Unit | Temperature unit preference |

## Display Images in Terminal

Use the `--display` or `-D` flag to render images directly in your terminal:

```bash
wms map gfs temp -D                   # Display in terminal
wms map gfs temp -D -o output.png     # Display AND save
wms tile galwem cloud --display       # Display tile
wms legend hrrr precip -D             # Display legend
```

Images are rendered using Unicode half-block characters (`▀`) with 24-bit color:
- **Foreground color** = top pixel
- **Background color** = bottom pixel
- Works in any terminal that supports 24-bit color (most modern terminals)

## Configuration

Stored in `~/.wms/`:
- `config.json` - Server URL, settings
- `capabilities_cache.xml` - Cached capabilities (10-min sliding TTL)

## Dependencies

- Python 3.10+
- click, rapidfuzz, requests, lxml, textual, Pillow
