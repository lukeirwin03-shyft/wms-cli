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
    init_from_file, init_from_server, WMSConfig
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


def build_url(base_url: str, params: dict) -> str:
    """Build a URL with query parameters"""
    from urllib.parse import urlencode
    return f"{base_url}?{urlencode(params)}"


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
def layers(query, limit):
    """List available layers, optionally filtered.

    Examples:
        wms layers           # List all layers
        wms layers gfs       # Search for GFS layers
        wms layers cloud     # Search for cloud-related layers
    """
    resolver, config = get_resolver()
    query_str = ' '.join(query) if query else None

    try:
        results = resolver.list_layers(query_str, limit=limit)

        if not results:
            if query_str:
                click.echo(f"No layers found matching: {query_str}")
            else:
                click.echo("No queryable layers found")
            return

        # Show results
        if query_str:
            click.echo(f"Layers matching '{query_str}':\n")
        else:
            click.echo(f"Available layers ({len(results)} shown):\n")

        for result in results:
            layer = result.layer
            dims = list(layer.dimensions.keys())
            dim_str = f" [{', '.join(dims)}]" if dims else ""

            if query_str:
                click.echo(f"  {result.score:5.1f}  {layer.name}{dim_str}")
            else:
                click.echo(f"  {layer.name}{dim_str}")

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
