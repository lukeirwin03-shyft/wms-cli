#!/usr/bin/env python3
"""
WMS CLI - Command-line interface for WMS queries with fuzzy search.
"""

import sys
import random
import click
from pathlib import Path

from .config import (
    load_config, save_config, get_capabilities_xml,
    init_from_file, init_from_server, WMSConfig,
    # Multi-server support
    add_server, remove_server, list_servers, get_server,
    get_server_capabilities, fetch_server_capabilities,
    update_server_caps_from_file, ServerConfig
)
from .wms_parser import parse_capabilities
from .wms_client import WMSClient
from .resolver import QueryResolver
from .fuzzy import FuzzySearchEngine


def get_resolver():
    """Get resolver from current config"""
    config = load_config()
    if not config.is_initialized():
        click.echo("Error: WMS not initialized. Run 'wms init <source>' first.", err=True)
        click.echo("\nExamples:", err=True)
        click.echo("  wms init ./capabilities.xml", err=True)
        click.echo("  wms init http://my-server/wms", err=True)
        sys.exit(1)

    xml_content = get_capabilities_xml(config)
    capabilities = parse_capabilities(xml_content)
    return QueryResolver(capabilities), config


def sanitize_filename(name: str) -> str:
    """Sanitize string for use in filename"""
    # Remove/replace problematic characters
    name = name.replace(':', '-').replace('/', '-').replace('\\', '-')
    name = name.replace(' ', '_').replace('?', '').replace('&', '_')
    return name


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """WMS query tool with fuzzy search.

    Run without arguments to open interactive TUI.
    """
    if ctx.invoked_subcommand is None:
        # Launch TUI
        try:
            from .tui.app import WMSApp
            app = WMSApp()
            app.run()
        except ImportError:
            click.echo("TUI not yet implemented. Use subcommands:")
            click.echo("  wms init <source>")
            click.echo("  wms map <query>")
            click.echo("  wms tile <query>")
            click.echo("  wms legend <query>")
            click.echo("  wms layers [query]")
            click.echo("  wms hammer <query>")


@cli.command()
@click.argument('source')
@click.option('--server', '-s', help='Server URL for requests (when source is local file)')
def init(source, server):
    """Initialize WMS context from file or server.

    SOURCE can be a local file path or HTTP URL.

    Examples:
        wms init ./capabilities.xml
        wms init http://localhost:8008/ogc/AFW_WMS
        wms init ./caps.xml --server http://prod-server/wms
    """
    try:
        if source.startswith('http://') or source.startswith('https://'):
            # Initialize from server
            click.echo(f"Fetching capabilities from {source}...")
            config = init_from_server(source)
            click.echo("✓ Fetched capabilities from server")
        else:
            # Initialize from local file
            click.echo(f"Loading capabilities from {source}...")
            config = init_from_file(source, server)
            click.echo("✓ Initialized from local file")

        # Show summary
        xml_content = get_capabilities_xml(config)
        caps = parse_capabilities(xml_content)

        click.echo(f"  Service: {caps.service_title}")
        click.echo(f"  Layers: {len(caps.get_queryable_layers())} queryable")

        if config.server_url:
            click.echo(f"  Server: {config.server_url}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def status():
    """Show current WMS configuration."""
    config = load_config()

    if not config.is_initialized():
        click.echo("Not initialized. Run 'wms init <source>' first.")
        return

    click.echo(f"Source: {config.source_path}")
    click.echo(f"Type: {config.source_type}")

    if config.server_url:
        click.echo(f"Server: {config.server_url}")

    # Load and show layer count
    try:
        xml_content = get_capabilities_xml(config)
        caps = parse_capabilities(xml_content)
        click.echo(f"Layers: {len(caps.get_queryable_layers())} queryable")
        click.echo(f"Service: {caps.service_title}")
    except Exception as e:
        click.echo(f"Error loading capabilities: {e}", err=True)


# ============================================================================
# Server Management Commands
# ============================================================================

@cli.group()
def server():
    """Manage WMS server connections.
    
    Register multiple WMS servers and manage their capabilities.
    Supports CAC/auth-protected servers via manual capabilities import.
    """
    pass


@server.command('add')
@click.argument('name')
@click.argument('url')
@click.option('--no-fetch', is_flag=True, help='Skip fetching capabilities (register URL only)')
@click.option('--caps-file', '-c', type=click.Path(exists=True),
              help='Local capabilities XML file (for CAC/auth-protected servers)')
@click.option('--ssh-tunnel', help='SSH tunnel: user@host:local_port:remote_host:remote_port')
@click.option('--notes', '-n', help='Notes about this server (e.g., "Requires VPN")')
def server_add(name, url, no_fetch, caps_file, ssh_tunnel, notes):
    """Register a named WMS server.
    
    For servers requiring special authentication (CAC card, client certs, etc.),
    download the capabilities XML manually and provide it with --caps-file.
    
    \b
    Examples:
        wms server add prod https://prod.example.com/wms
        wms server add staging https://staging.example.com/wms --no-fetch
        wms server add afweather https://afweather.mil/wms --caps-file ./caps.xml
        wms server add internal http://localhost:8080/wms --ssh-tunnel user@bastion:8080:internal:80
    """
    try:
        fetch = not no_fetch and not caps_file
        
        server_config = add_server(
            name=name,
            url=url,
            fetch_caps=fetch,
            caps_file=caps_file,
            ssh_tunnel=ssh_tunnel,
            notes=notes
        )
        
        click.echo(f"✓ Added server '{name}'")
        click.echo(f"  URL: {url}")
        
        if server_config.has_capabilities():
            # Show summary
            caps = get_server_capabilities(name)
            if caps:
                click.echo(f"  Service: {caps.service_title}")
                click.echo(f"  Layers: {len(caps.get_queryable_layers())} queryable")
                click.echo(f"  Source: {server_config.caps_source}")
        else:
            click.echo(f"  Status: No capabilities (use 'wms server fetch {name}' or 'wms server fetch-interactive {name}')")
        
        if notes:
            click.echo(f"  Notes: {notes}")
            
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@server.command('remove')
@click.argument('name')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
def server_remove(name, yes):
    """Remove a registered server.
    
    Example:
        wms server remove staging
    """
    server_config = get_server(name)
    if not server_config:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)
    
    if not yes:
        click.confirm(f"Remove server '{name}' ({server_config.url})?", abort=True)
    
    if remove_server(name):
        click.echo(f"✓ Removed server '{name}'")
    else:
        click.echo(f"Error: Failed to remove server '{name}'", err=True)
        sys.exit(1)


@server.command('list')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed info')
def server_list(verbose):
    """List all registered servers.
    
    Example:
        wms server list
        wms server list -v
    """
    servers = list_servers()
    
    if not servers:
        click.echo("No servers registered.")
        click.echo("\nUse 'wms server add <name> <url>' to register a server.")
        return
    
    click.echo(f"Registered servers ({len(servers)}):\n")
    
    for srv in servers:
        if verbose:
            click.echo(f"  {srv.name}")
            click.echo(f"    URL: {srv.url}")
            
            if srv.has_capabilities():
                caps = get_server_capabilities(srv.name)
                if caps:
                    click.echo(f"    Service: {caps.service_title}")
                    click.echo(f"    Layers: {len(caps.get_queryable_layers())} queryable")
                click.echo(f"    Last fetched: {srv.last_fetched}")
                click.echo(f"    Caps source: {srv.caps_source}")
                if srv.original_caps_file:
                    click.echo(f"    Original file: {srv.original_caps_file}")
            else:
                click.echo(f"    Status: ⚠ No capabilities")
            
            if srv.ssh_tunnel:
                click.echo(f"    SSH tunnel: {srv.ssh_tunnel}")
            if srv.notes:
                click.echo(f"    Notes: {srv.notes}")
            click.echo()
        else:
            status = "✓" if srv.has_capabilities() else "⚠"
            click.echo(f"  {status} {srv.name:20} {srv.url}")


@server.command('fetch')
@click.argument('name')
@click.option('--caps-file', '-c', type=click.Path(exists=True),
              help='Update from local file instead of fetching from URL')
def server_fetch(name, caps_file):
    """Refresh capabilities for a server.
    
    For servers requiring special authentication, download capabilities
    manually and provide with --caps-file.
    
    \b
    Examples:
        wms server fetch prod
        wms server fetch afweather --caps-file ~/Downloads/caps.xml
    """
    server_config = get_server(name)
    if not server_config:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)
    
    try:
        click.echo(f"Fetching capabilities for '{name}'...")
        
        updated = fetch_server_capabilities(name, caps_file=caps_file)
        
        click.echo(f"✓ Updated capabilities for '{name}'")
        
        caps = get_server_capabilities(name)
        if caps:
            click.echo(f"  Service: {caps.service_title}")
            click.echo(f"  Layers: {len(caps.get_queryable_layers())} queryable")
        
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@server.command('fetch-interactive')
@click.argument('name')
@click.option('--watch-dir', '-w', default='~/Downloads',
              help='Directory to watch for downloaded file')
@click.option('--timeout', '-t', default=300, type=int,
              help='Seconds to wait for download (default: 300)')
@click.option('--keep-file', is_flag=True,
              help='Keep the downloaded file (default: delete after import)')
def server_fetch_interactive(name, watch_dir, timeout, keep_file):
    """Fetch capabilities via browser with automatic import.
    
    Opens the GetCapabilities URL in your default browser. After you
    complete authentication (CAC, SSO, etc.) and the file downloads,
    it is automatically detected and imported.
    
    This is the recommended method for CAC-protected servers.
    
    \b
    Examples:
        wms server fetch-interactive afweather
        wms server fetch-interactive afweather --watch-dir ~/Desktop
        wms server fetch-interactive afweather --timeout 600
    """
    import os
    import time
    
    server_config = get_server(name)
    if not server_config:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        click.echo(f"Run 'wms server add {name} <url> --no-fetch' to register it first.", err=True)
        sys.exit(1)
    
    try:
        from .browser_fetch import fetch_via_browser, build_capabilities_url
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    # Build URL
    caps_url = build_capabilities_url(server_config.url)
    
    # Print instructions
    click.echo(f"\n{'='*60}")
    click.echo(f"Interactive Fetch: {name}")
    click.echo(f"{'='*60}")
    click.echo(f"\nServer URL: {server_config.url}")
    click.echo(f"Opening:    {caps_url}")
    click.echo(f"\nWatching:   {Path(watch_dir).expanduser()}")
    click.echo(f"Timeout:    {timeout} seconds")
    click.echo(f"\n{'='*60}")
    click.echo("INSTRUCTIONS:")
    click.echo("  1. Browser will open the GetCapabilities URL")
    click.echo("  2. Complete authentication (CAC, login, etc.)")
    click.echo("  3. When the XML appears in browser:")
    click.echo("     • Right-click → Save As...")
    click.echo("     • Or File → Save Page As...")
    click.echo(f"     • Save to: {Path(watch_dir).expanduser()}")
    click.echo("  4. Tool will auto-detect and import the file")
    click.echo(f"\n  Alternative: Press Ctrl+C to cancel, then use:")
    click.echo(f"    ./wms server update-caps {name} <path-to-file>")
    click.echo(f"{'='*60}\n")
    
    if not click.confirm("Ready to open browser?", default=True):
        click.echo("Cancelled.")
        sys.exit(0)
    
    click.echo("\nOpening browser now...")
    
    # Watch for download
    def on_found(path):
        click.echo(f"\n✓ Found: {path}")
    
    try:
        downloaded_file = fetch_via_browser(
            url=caps_url,
            watch_dir=watch_dir,
            timeout=timeout,
            on_found=on_found
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ImportError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    
    if not downloaded_file:
        click.echo(f"\n✗ Timeout after {timeout} seconds.", err=True)
        click.echo("\nTroubleshooting:", err=True)
        click.echo("  - Make sure the file downloaded to the watched directory", err=True)
        click.echo("  - Try increasing --timeout", err=True)
        click.echo("  - Or use 'wms server update-caps' with the file path manually", err=True)
        sys.exit(1)
    
    # Validate the file
    click.echo("Validating capabilities XML...")
    try:
        with open(downloaded_file, 'r', encoding='utf-8') as f:
            xml_content = f.read()
        
        caps = parse_capabilities(xml_content)
        layer_count = len(caps.get_queryable_layers())
        
        click.echo(f"  Service: {caps.service_title}")
        click.echo(f"  Layers:  {layer_count} queryable")
        
    except Exception as e:
        click.echo(f"Error parsing capabilities: {e}", err=True)
        click.echo(f"File saved at: {downloaded_file}", err=True)
        sys.exit(1)
    
    # Import to server config
    click.echo(f"\nImporting to server '{name}'...")
    try:
        update_server_caps_from_file(name, downloaded_file)
        click.echo(f"✓ Successfully imported capabilities for '{name}'")
    except Exception as e:
        click.echo(f"Error importing: {e}", err=True)
        sys.exit(1)
    
    # Optionally delete the downloaded file
    if not keep_file:
        try:
            os.remove(downloaded_file)
            click.echo(f"✓ Cleaned up downloaded file")
        except Exception as e:
            click.echo(f"Note: Could not delete {downloaded_file}: {e}")
    else:
        click.echo(f"Downloaded file kept at: {downloaded_file}")
    
    click.echo(f"\n{'='*60}")
    click.echo(f"Done! You can now use:")
    click.echo(f"  wms layers --server {name}")
    click.echo(f"  wms diff <other-server> {name}")
    click.echo(f"  wms inspect <query> --server {name}")
    click.echo(f"{'='*60}\n")


@server.command('update-caps')
@click.argument('name')
@click.argument('caps_file', type=click.Path(exists=True))
def server_update_caps(name, caps_file):
    """Update capabilities from a local file.
    
    Shorthand for 'wms server fetch <name> --caps-file <file>'.
    Useful for CAC/auth-protected servers.
    
    \b
    Example:
        wms server update-caps afweather ~/Downloads/capabilities.xml
    """
    server_config = get_server(name)
    if not server_config:
        click.echo(f"Error: Server '{name}' not found.", err=True)
        sys.exit(1)
    
    try:
        click.echo(f"Importing capabilities for '{name}'...")
        
        update_server_caps_from_file(name, caps_file)
        
        click.echo(f"✓ Updated capabilities for '{name}'")
        
        caps = get_server_capabilities(name)
        if caps:
            click.echo(f"  Service: {caps.service_title}")
            click.echo(f"  Layers: {len(caps.get_queryable_layers())} queryable")
        
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def build_url(base_url: str, params: dict) -> str:
    """Build a URL with query parameters"""
    from urllib.parse import urlencode
    return f"{base_url}?{urlencode(params)}"


# ============================================================================
# Diff Command
# ============================================================================

def _resolve_capabilities_source(source: str):
    """
    Resolve a source string to WMSCapabilities.
    
    Source can be (checked in this order):
    1. Registered server name (e.g., "prod", "afweather")
    2. Local file path (e.g., "./capabilities.xml", "~/Downloads/caps.xml")
    3. URL (e.g., "https://server.com/wms") - fetches live
    """
    from .wms_client import WMSClient
    
    # 1. Check if it's a registered server
    server = get_server(source)
    if server:
        caps = get_server_capabilities(source)
        if caps is None:
            raise ValueError(
                f"Server '{source}' has no capabilities. "
                f"Run 'wms server fetch {source} --caps-file <file>' to add them."
            )
        return caps
    
    # 2. Check if it's a file (expand ~ for home directory)
    path = Path(source).expanduser()
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return parse_capabilities(f.read())
    
    # 3. Check if it's a URL (fetch live - requires network access)
    if source.startswith('http://') or source.startswith('https://'):
        try:
            client = WMSClient(source)
            return client.get_capabilities()
        except Exception as e:
            raise ValueError(
                f"Failed to fetch capabilities from {source}: {e}\n"
                f"If this server requires authentication, download capabilities "
                f"manually and provide the file path instead."
            )
    
    raise ValueError(
        f"Unknown source: {source}\n"
        f"Expected one of:\n"
        f"  - Registered server name (see 'wms server list')\n"
        f"  - Path to capabilities XML file\n"
        f"  - HTTP(S) URL to WMS server"
    )


@cli.command('diff')
@click.argument('source_a')
@click.argument('source_b')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed changes including dimension values')
@click.option('--layers-only', is_flag=True, help='Only compare layers, skip service metadata')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--layer', '-l', 'layer_name', help='Deep diff a specific layer')
@click.option('--summary', '-s', is_flag=True, help='Show summary only')
@click.option('--output', '-o', 'output_file', type=click.Path(), help='Save diff to file')
@click.option('--filter', '-f', 'filter_type', type=click.Choice(['added', 'removed', 'modified', 'all']), 
              default='all', help='Filter by change type')
@click.option('--show-unchanged', is_flag=True, help='Also list unchanged layers')
@click.option('--stats', is_flag=True, help='Show statistics and percentages')
def diff_cmd(source_a, source_b, verbose, layers_only, output_json, layer_name, summary, 
             output_file, filter_type, show_unchanged, stats):
    """Compare capabilities between two WMS servers.
    
    SOURCE_A and SOURCE_B can be registered server names, file paths, or URLs.
    
    \b
    Examples:
        wms diff prod staging                    # Basic comparison
        wms diff prod staging -v                 # Verbose with details
        wms diff prod staging --layers-only     # Skip service metadata
        wms diff prod staging --layer GFS_Temp  # Single layer deep diff
        wms diff prod staging --json            # JSON output
        wms diff prod staging --stats           # Show statistics
        wms diff prod staging -f added          # Only show added layers
        wms diff prod staging -o diff.txt       # Save to file
        wms diff ./old.xml ./new.xml            # Compare local files
    """
    from .diff import compare_capabilities, compare_single_layer
    from .diff_formatter import (
        format_diff_text, format_diff_json, format_diff_summary,
        format_layer_diff_text, format_layer_diff_json,
        format_diff_verbose, format_diff_stats
    )
    
    try:
        click.echo(f"Loading {source_a}...")
        caps_a = _resolve_capabilities_source(source_a)
        click.echo(f"Loading {source_b}...")
        caps_b = _resolve_capabilities_source(source_b)
        
        click.echo(f"Comparing {len(caps_a.get_queryable_layers())} vs {len(caps_b.get_queryable_layers())} layers...\n")
        
        # Single layer diff
        if layer_name:
            layers_a = {l.name: l for l in caps_a.get_queryable_layers()}
            layers_b = {l.name: l for l in caps_b.get_queryable_layers()}
            
            if layer_name not in layers_a and layer_name not in layers_b:
                # Try fuzzy match
                click.echo(f"Layer '{layer_name}' not found exactly. Searching...")
                engine_a = FuzzySearchEngine(caps_a)
                engine_b = FuzzySearchEngine(caps_b)
                results_a = engine_a.search(layer_name, limit=3)
                results_b = engine_b.search(layer_name, limit=3)
                
                click.echo(f"\nSimilar layers in {source_a}:")
                for r in results_a[:3]:
                    click.echo(f"  {r.layer.name}")
                click.echo(f"\nSimilar layers in {source_b}:")
                for r in results_b[:3]:
                    click.echo(f"  {r.layer.name}")
                sys.exit(1)
            
            layer_diff = compare_single_layer(
                layers_a.get(layer_name),
                layers_b.get(layer_name),
                source_a, source_b
            )
            
            output = format_layer_diff_json(layer_diff) if output_json else \
                     format_layer_diff_text(layer_diff, source_a, source_b, verbose=verbose)
            
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(output)
                click.echo(f"Saved to {output_file}")
            else:
                click.echo(output)
            return
        
        # Full comparison
        diff_result = compare_capabilities(caps_a, caps_b, source_a, source_b)
        
        # Apply filter
        if filter_type != 'all':
            diff_result = _filter_diff(diff_result, filter_type)
        
        # Generate output
        if output_json:
            output = format_diff_json(diff_result)
        elif summary:
            output = format_diff_summary(diff_result)
        elif stats:
            output = format_diff_stats(diff_result, caps_a, caps_b)
        elif verbose:
            output = format_diff_verbose(diff_result, layers_only=layers_only, 
                                         show_unchanged=show_unchanged)
        else:
            output = format_diff_text(diff_result, layers_only=layers_only)
        
        # Output to file or stdout
        if output_file:
            with open(output_file, 'w') as f:
                f.write(output)
            click.echo(f"Diff saved to {output_file}")
            click.echo(format_diff_summary(diff_result))
        else:
            click.echo(output)
            
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _filter_diff(diff, filter_type: str):
    """Filter diff results by change type."""
    from .diff import CapabilitiesDiff
    
    filtered = CapabilitiesDiff(
        source_a=diff.source_a,
        source_b=diff.source_b,
        service=diff.service,
        layers_unchanged=diff.layers_unchanged
    )
    
    if filter_type == 'added':
        filtered.layers_added = diff.layers_added
    elif filter_type == 'removed':
        filtered.layers_removed = diff.layers_removed
    elif filter_type == 'modified':
        filtered.layers_modified = diff.layers_modified
    else:
        filtered.layers_added = diff.layers_added
        filtered.layers_removed = diff.layers_removed
        filtered.layers_modified = diff.layers_modified
    
    return filtered


# ============================================================================
# Inspect Command
# ============================================================================

def _format_layer_detail(layer) -> str:
    """Format layer details for display."""
    lines = []
    
    lines.append(f"Layer: {layer.name}")
    lines.append(f"Title: {layer.title}")
    
    if layer.abstract:
        lines.append(f"Abstract: {layer.abstract}")
    
    lines.append(f"Queryable: {layer.queryable}")
    lines.append("")
    
    # CRS
    if layer.crs_list:
        lines.append(f"CRS ({len(layer.crs_list)}):")
        for crs in layer.crs_list[:10]:
            lines.append(f"  {crs}")
        if len(layer.crs_list) > 10:
            lines.append(f"  ... and {len(layer.crs_list) - 10} more")
        lines.append("")
    
    # Bounding box
    if layer.geographic_bbox:
        bb = layer.geographic_bbox
        lines.append(f"Geographic Bounds: [{bb.minx}, {bb.miny}] to [{bb.maxx}, {bb.maxy}]")
        lines.append("")
    
    # Dimensions
    if layer.dimensions:
        lines.append(f"Dimensions ({len(layer.dimensions)}):")
        for name, dim in layer.dimensions.items():
            lines.append(f"  {name}:")
            lines.append(f"    Units: {dim.units}")
            lines.append(f"    Default: {dim.default}")
            lines.append(f"    Values: {len(dim.values)} values")
            if dim.values:
                preview = dim.values[:5]
                suffix = '...' if len(dim.values) > 5 else ''
                lines.append(f"    Preview: {', '.join(preview)}{suffix}")
        lines.append("")
    
    # Styles
    if layer.styles:
        lines.append(f"Styles ({len(layer.styles)}):")
        for style in layer.styles:
            lines.append(f"  {style.name}: {style.title}")
        lines.append("")
    
    return "\n".join(lines)


def _layer_to_json(layer) -> str:
    """Convert layer to JSON."""
    import json
    
    data = {
        "name": layer.name,
        "title": layer.title,
        "abstract": layer.abstract,
        "queryable": layer.queryable,
        "crs_list": layer.crs_list,
        "dimensions": {
            name: {
                "units": dim.units,
                "default": dim.default,
                "values": dim.values,
                "values_count": len(dim.values)
            }
            for name, dim in layer.dimensions.items()
        },
        "styles": [
            {"name": s.name, "title": s.title}
            for s in layer.styles
        ]
    }
    
    if layer.geographic_bbox:
        bb = layer.geographic_bbox
        data["geographic_bbox"] = {
            "minx": bb.minx, "miny": bb.miny,
            "maxx": bb.maxx, "maxy": bb.maxy
        }
    
    return json.dumps(data, indent=2)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--server', '-s', 'server_name', help='Server to query (default: current init)')
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
def inspect(query, server_name, output_json):
    """Show detailed information about a layer.
    
    QUERY is fuzzy-matched to find the layer.
    
    \b
    Examples:
        wms inspect gfs temp
        wms inspect GFS_Temperature_in_C
        wms inspect gfs temp --server prod
        wms inspect gfs temp --json
    """
    try:
        # Resolve capabilities source
        if server_name:
            caps = get_server_capabilities(server_name)
            if caps is None:
                click.echo(f"Error: Server '{server_name}' has no capabilities.", err=True)
                sys.exit(1)
        else:
            resolver, config = get_resolver()
            caps = resolver.capabilities
        
        query_str = ' '.join(query)
        
        # Find layer (exact match first, then fuzzy)
        layer = None
        for l in caps.get_queryable_layers():
            if l.name == query_str or l.name.lower() == query_str.lower():
                layer = l
                break
        
        if not layer:
            # Fuzzy search
            engine = FuzzySearchEngine(caps)
            results = engine.search(query_str, limit=1)
            if results:
                layer = results[0].layer
        
        if not layer:
            click.echo(f"No layer found matching: {query_str}", err=True)
            sys.exit(1)
        
        if output_json:
            click.echo(_layer_to_json(layer))
        else:
            click.echo(_format_layer_detail(layer))
            
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--output', '-o', help='Output filename')
@click.option('--width', '-w', default=800, help='Image width')
@click.option('--height', '-h', default=600, help='Image height')
@click.option('--debug', '-d', is_flag=True, help='Show resolved URL without fetching')
def map(query, output, width, height, debug):
    """Fetch a map image (GetMap).

    QUERY is fuzzy-matched to find the best layer.

    Examples:
        wms map gfs temp
        wms map galwem cloud 850
        wms map hrrr precip +6h
        wms map gfs wind contour
        wms map gfs temp --debug
    """
    resolver, config = get_resolver()
    query_str = ' '.join(query)

    try:
        # Resolve the query
        resolved = resolver.resolve(query_str)

        # Show what we resolved to
        click.echo(f"→ Resolved: {resolved.layer.name}")
        click.echo(f"  Style: {resolved.style}")

        for dim_name, value in resolved.dimensions.items():
            click.echo(f"  {dim_name}: {value}")

        if resolved.confidence < 0.7:
            click.echo(f"  (confidence: {resolved.confidence:.0%})")

        # Build dimension kwargs
        dim_kwargs = {}
        for dim_name, value in resolved.dimensions.items():
            param_name = resolved.get_dimension_param_name(dim_name)
            dim_kwargs[param_name] = value

        # Build the URL params
        bbox_str = ','.join(str(x) for x in resolved.bbox)
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetMap',
            'LAYERS': resolved.layer.name,
            'BBOX': bbox_str,
            'WIDTH': width,
            'HEIGHT': height,
            'CRS': resolved.crs,
            'FORMAT': 'image/png',
            'STYLES': resolved.style,
            **{k.upper(): v for k, v in dim_kwargs.items()}
        }

        if debug:
            # Just show the URL
            url = build_url(config.server_url, params)
            click.echo(f"\nURL:\n{url}")
            return

        # Fetch the map
        click.echo("Fetching...")

        client = WMSClient(config.server_url)
        image_data = client.get_map(
            layer=resolved.layer.name,
            bbox=resolved.bbox,
            width=width,
            height=height,
            crs=resolved.crs,
            styles=resolved.style,
            **dim_kwargs
        )

        # Generate filename
        if not output:
            parts = [resolved.layer.name, resolved.style]
            for dim_name, value in resolved.dimensions.items():
                parts.append(sanitize_filename(value))
            output = '_'.join(parts[:4]) + '.png'

        # Save to file
        with open(output, 'wb') as f:
            f.write(image_data)

        size_kb = len(image_data) / 1024
        click.echo(f"✓ Saved: {output} ({size_kb:.1f} KB)")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--output', '-o', help='Output filename')
@click.option('--zoom', '-z', default=3, help='Tile zoom level')
@click.option('--debug', '-d', is_flag=True, help='Show resolved URL without fetching')
def tile(query, output, zoom, debug):
    """Fetch a random tile (GetGTile).

    QUERY is fuzzy-matched to find the best layer.

    Examples:
        wms tile galwem cloud
        wms tile gfs temp
        wms tile hrrr --zoom 5
        wms tile gfs temp --debug
    """
    resolver, config = get_resolver()
    query_str = ' '.join(query)

    try:
        # Resolve the query
        resolved = resolver.resolve(query_str)

        # Generate random tile coordinates for the zoom level
        max_tiles = 2 ** zoom
        tilerow = random.randint(0, max_tiles - 1)
        tilecol = random.randint(0, max_tiles - 1)

        # Show what we resolved to
        click.echo(f"→ Resolved: {resolved.layer.name}")
        click.echo(f"  Tile: z={zoom}, row={tilerow}, col={tilecol}")

        for dim_name, value in resolved.dimensions.items():
            click.echo(f"  {dim_name}: {value}")

        # Build dimension kwargs
        dim_kwargs = {}
        for dim_name, value in resolved.dimensions.items():
            param_name = resolved.get_dimension_param_name(dim_name)
            dim_kwargs[param_name] = value

        # Build URL params
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetGTile',
            'LAYER': resolved.layer.name,
            'TILEZOOM': zoom,
            'TILEROW': tilerow,
            'TILECOL': tilecol,
            'CRS': 'EPSG:900913',
            'FORMAT': 'image/png; mode=8bit',
            'STYLE': resolved.style,
            'TRANSPARENT': 'TRUE',
            **{k.upper(): v for k, v in dim_kwargs.items()}
        }

        if debug:
            url = build_url(config.server_url, params)
            click.echo(f"\nURL:\n{url}")
            return

        # Fetch the tile
        click.echo("Fetching...")

        client = WMSClient(config.server_url)
        image_data = client.get_gtile(
            layer=resolved.layer.name,
            tilezoom=zoom,
            tilerow=tilerow,
            tilecol=tilecol,
            style=resolved.style,
            **dim_kwargs
        )

        # Generate filename
        if not output:
            output = f"{resolved.layer.name}_z{zoom}_r{tilerow}_c{tilecol}.png"

        # Save to file
        with open(output, 'wb') as f:
            f.write(image_data)

        size_kb = len(image_data) / 1024
        click.echo(f"✓ Saved: {output} ({size_kb:.1f} KB)")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--output', '-o', help='Output filename')
@click.option('--debug', '-d', is_flag=True, help='Show resolved URL without fetching')
def legend(query, output, debug):
    """Fetch legend graphic for a layer.

    Examples:
        wms legend gfs temp
        wms legend galwem cloud
        wms legend hrrr --debug
    """
    resolver, config = get_resolver()
    query_str = ' '.join(query)

    try:
        # Resolve the query
        resolved = resolver.resolve(query_str)

        click.echo(f"→ Resolved: {resolved.layer.name}")
        click.echo(f"  Style: {resolved.style}")

        # Build URL params
        params = {
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetLegendGraphic',
            'LAYER': resolved.layer.name,
            'STYLE': resolved.style,
            'FORMAT': 'image/png'
        }

        if debug:
            url = build_url(config.server_url, params)
            click.echo(f"\nURL:\n{url}")
            return

        # Fetch the legend
        click.echo("Fetching...")

        client = WMSClient(config.server_url)
        image_data = client.get_legend_graphic(
            layer=resolved.layer.name,
            style=resolved.style
        )

        # Generate filename
        if not output:
            output = f"{resolved.layer.name}_legend.png"

        # Save to file
        with open(output, 'wb') as f:
            f.write(image_data)

        size_kb = len(image_data) / 1024
        click.echo(f"✓ Saved: {output} ({size_kb:.1f} KB)")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=False)
@click.option('--limit', '-n', default=20, help='Maximum results to show')
@click.option('--server', '-s', 'server_name', help='Server to query (default: current init)')
def layers(query, limit, server_name):
    """List available layers, optionally filtered.

    \b
    Examples:
        wms layers                    # List all layers (from init'd server)
        wms layers gfs                # Search for GFS layers
        wms layers cloud              # Search for cloud-related layers
        wms layers --server prod      # List from 'prod' server
        wms layers gfs --server int   # Search 'int' server for GFS
    """
    try:
        # Get capabilities from server or current init
        if server_name:
            caps = get_server_capabilities(server_name)
            if caps is None:
                click.echo(f"Error: Server '{server_name}' has no capabilities.", err=True)
                click.echo(f"Run 'wms server fetch {server_name}' or 'wms server fetch-interactive {server_name}'", err=True)
                sys.exit(1)
        else:
            resolver, config = get_resolver()
            caps = resolver.capabilities
        
        # Create a resolver for this capabilities
        from .resolver import QueryResolver
        resolver = QueryResolver(caps)
        
        query_str = ' '.join(query) if query else None
        results = resolver.list_layers(query_str, limit=limit)

        if not results:
            if query_str:
                click.echo(f"No layers found matching: {query_str}")
            else:
                click.echo("No queryable layers found")
            return

        # Show results
        source_label = f" (from {server_name})" if server_name else ""
        if query_str:
            click.echo(f"Layers matching '{query_str}'{source_label}:\n")
        else:
            click.echo(f"Available layers ({len(results)} shown){source_label}:\n")

        for result in results:
            layer = result.layer
            dims = list(layer.dimensions.keys())
            dim_str = f" [{', '.join(dims)}]" if dims else ""

            if query_str:
                click.echo(f"  {result.score:5.1f}  {layer.name}{dim_str}")
            else:
                click.echo(f"  {layer.name}{dim_str}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('query', nargs=-1, required=True)
@click.option('--workers', '-w', default=20, help='Number of parallel workers')
@click.option('--dry-run', is_flag=True, help='Show requests without executing')
@click.option('--output', '-o', default='wms_output', help='Output directory')
def hammer(query, workers, dry_run, output):
    """Hammer all layers matching query.

    Generates all dimension combinations and fetches them in parallel.

    Examples:
        wms hammer gfs
        wms hammer galwem cloud
        wms hammer hrrr --workers 10
    """
    resolver, config = get_resolver()
    query_str = ' '.join(query)

    try:
        # Find all matching layers
        results = resolver.list_layers(query_str, limit=100)

        if not results:
            click.echo(f"No layers found matching: {query_str}")
            sys.exit(1)

        # Filter to good matches (score > 50)
        matching_layers = [r.layer for r in results if r.score > 50]

        if not matching_layers:
            click.echo(f"No confident matches for: {query_str}")
            click.echo("Try a more specific query.")
            sys.exit(1)

        click.echo(f"→ Found {len(matching_layers)} layers matching '{query_str}':")
        for layer in matching_layers[:10]:
            click.echo(f"  - {layer.name}")
        if len(matching_layers) > 10:
            click.echo(f"  ... and {len(matching_layers) - 10} more")

        # Import and run hammer
        from .hammer import WMSHammer
        import argparse

        # Build args for hammer
        args = argparse.Namespace(
            url=config.server_url,
            glob=None,  # We'll pass layer names directly
            layer=None,
            list_layers=False,
            workers=workers,
            output=output,
            max_timesteps=0,
            latest_run=False,
            tile_mode=False,
            dry_run=dry_run,
            verbose=False,
            random_tiles=False,
            no_save=False,
            single_forecast=False,
            num_random_tiles=100,
            timeout=30
        )

        # Get capabilities
        xml_content = get_capabilities_xml(config)
        caps = parse_capabilities(xml_content)

        # Create hammer and run for each layer
        hammer_instance = WMSHammer(args, caps)

        # Override layer filtering to use our matches
        hammer_instance.layers = matching_layers

        click.echo(f"\nHammering with {workers} workers...")
        if dry_run:
            click.echo("(dry run - no requests will be made)")

        hammer_instance.run()

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point"""
    cli()


if __name__ == '__main__':
    main()
