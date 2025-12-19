#!/usr/bin/env python3
"""
WMS Hammer - Performance Testing Tool

A performance testing tool for WMS servers with live dashboard output.
Tracks per-layer statistics and generates reports.
"""

import argparse
import sys
import time
import json
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import fnmatch
from itertools import product

from .wms_client import WMSClient
from .wms_parser import WMSCapabilities, Layer


@dataclass
class LayerStats:
    """Statistics for a single layer"""
    name: str
    total: int = 0
    success: int = 0
    failed: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    total_bytes: int = 0
    response_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def avg_time(self) -> float:
        return self.total_time / self.success if self.success > 0 else 0.0

    @property
    def avg_bytes(self) -> float:
        return self.total_bytes / self.success if self.success > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return (self.success / self.total * 100) if self.total > 0 else 0.0

    def percentile(self, p: float) -> float:
        """Calculate the p-th percentile of response times"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * p / 100)
        idx = min(idx, len(sorted_times) - 1)
        return sorted_times[idx]


@dataclass
class HammerStats:
    """Overall hammer statistics"""
    start_time: float = 0.0
    end_time: float = 0.0
    total_requests: int = 0
    completed: int = 0
    successful: int = 0
    failed: int = 0
    total_bytes: int = 0
    response_times: List[float] = field(default_factory=list)
    layers: Dict[str, LayerStats] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time if self.start_time else 0.0

    @property
    def requests_per_sec(self) -> float:
        return self.completed / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def bytes_per_sec(self) -> float:
        return self.total_bytes / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return (self.successful / self.completed * 100) if self.completed > 0 else 0.0

    def percentile(self, p: float) -> float:
        """Calculate the p-th percentile of all response times"""
        if not self.response_times:
            return 0.0
        sorted_times = sorted(self.response_times)
        idx = int(len(sorted_times) * p / 100)
        idx = min(idx, len(sorted_times) - 1)
        return sorted_times[idx]


def format_bytes(num_bytes: int) -> str:
    """Format bytes as human-readable string"""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / 1024 / 1024:.1f} MB"
    else:
        return f"{num_bytes / 1024 / 1024 / 1024:.1f} GB"


class Dashboard:
    """Live terminal dashboard for hammer progress"""

    def __init__(self, stats: HammerStats, layer_names: List[str]):
        self.stats = stats
        self.layer_names = layer_names
        self.lock = threading.Lock()
        self._stop = False
        self._thread = None

    def start(self):
        """Start the dashboard refresh thread"""
        self._stop = False
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        # Hide cursor
        sys.stdout.write('\033[?25l')
        sys.stdout.flush()

    def stop(self):
        """Stop the dashboard"""
        self._stop = True
        if self._thread:
            self._thread.join(timeout=1)
        # Show cursor
        sys.stdout.write('\033[?25h')
        sys.stdout.flush()

    def _refresh_loop(self):
        """Refresh dashboard periodically"""
        while not self._stop:
            self._render()
            time.sleep(0.1)

    def _render(self):
        """Render the dashboard"""
        with self.lock:
            lines = self._build_display()

        # Move cursor to top and clear
        output = '\033[H\033[J'  # Home + clear screen
        output += '\n'.join(lines)
        sys.stdout.write(output)
        sys.stdout.flush()

    def _build_display(self) -> List[str]:
        """Build display lines"""
        lines = []

        # Header
        lines.append('\033[1;36m' + '=' * 70 + '\033[0m')
        lines.append('\033[1;36m  WMS HAMMER - Performance Testing\033[0m')
        lines.append('\033[1;36m' + '=' * 70 + '\033[0m')
        lines.append('')

        # Progress bar
        progress = self.stats.completed / self.stats.total_requests if self.stats.total_requests > 0 else 0
        bar_width = 50
        filled = int(bar_width * progress)
        bar = '█' * filled + '░' * (bar_width - filled)
        pct = progress * 100
        lines.append(f'  Progress: [{bar}] {pct:5.1f}%')
        lines.append('')

        # Stats row
        elapsed = self.stats.elapsed
        rps = self.stats.requests_per_sec
        total_bytes = format_bytes(self.stats.total_bytes)
        throughput = format_bytes(int(self.stats.bytes_per_sec)) + '/s'
        lines.append(f'  \033[1mCompleted:\033[0m {self.stats.completed:,}/{self.stats.total_requests:,}   '
                    f'\033[1;32mSuccess:\033[0m {self.stats.successful:,}   '
                    f'\033[1;31mFailed:\033[0m {self.stats.failed:,}   '
                    f'\033[1mTime:\033[0m {elapsed:.1f}s   '
                    f'\033[1mReq/s:\033[0m {rps:.1f}')
        lines.append(f'  \033[1mData:\033[0m {total_bytes}   '
                    f'\033[1mThroughput:\033[0m {throughput}')
        lines.append('')

        # Per-layer stats table
        lines.append('\033[1m  Layer                                    OK    Fail   Avg(ms)  Status\033[0m')
        lines.append('  ' + '-' * 66)

        # Show top layers (limit to fit terminal)
        max_layers = 15
        sorted_layers = sorted(
            self.stats.layers.values(),
            key=lambda x: x.total - x.success - x.failed,  # In-progress first
            reverse=True
        )

        for layer_stat in sorted_layers[:max_layers]:
            name = layer_stat.name[:38].ljust(38)
            ok = layer_stat.success
            fail = layer_stat.failed
            avg_ms = layer_stat.avg_time * 1000

            # Status indicator
            in_progress = layer_stat.total - layer_stat.success - layer_stat.failed
            if in_progress > 0:
                status = f'\033[1;33m⟳ {in_progress}\033[0m'
            elif fail > 0:
                status = '\033[1;31m✗\033[0m'
            elif ok > 0:
                status = '\033[1;32m✓\033[0m'
            else:
                status = ' '

            # Color coding for failures
            fail_str = f'\033[1;31m{fail:5}\033[0m' if fail > 0 else f'{fail:5}'
            ok_str = f'\033[1;32m{ok:5}\033[0m' if ok > 0 else f'{ok:5}'

            lines.append(f'  {name} {ok_str} {fail_str}  {avg_ms:7.0f}   {status}')

        if len(sorted_layers) > max_layers:
            lines.append(f'  ... and {len(sorted_layers) - max_layers} more layers')

        lines.append('')
        lines.append('\033[2m  Press Ctrl+C to abort\033[0m')

        return lines


class WMSHammer:
    """Performance testing tool for WMS servers"""

    def __init__(self, args, capabilities: Optional[WMSCapabilities] = None):
        self.base_url = args.url
        self.output_dir = Path(args.output) if args.output else None
        self.glob_pattern = getattr(args, 'glob', '*')
        self.max_workers = args.workers
        self.dry_run = args.dry_run
        self.tile_mode = getattr(args, 'tile_mode', False)
        self.width = getattr(args, 'width', 800)
        self.height = getattr(args, 'height', 600)
        self.max_timesteps = getattr(args, 'max_timesteps', 10)
        self.latest_run_only = getattr(args, 'latest_run_only', False)
        self.save_images = args.output is not None  # Save only if output dir specified
        self.report_file = getattr(args, 'report', None)

        # Tile options
        self.random_tiles = getattr(args, 'random_tiles', None)
        self.tile_zoom = getattr(args, 'tile_zoom', 0)
        self.tile_count = getattr(args, 'tile_count', 100)

        # Layer targeting
        self.specific_layer = getattr(args, 'layer', None)
        self.list_layers = getattr(args, 'list_layers', False)

        self._capabilities = capabilities
        self.layers: List[Layer] = []

        # Statistics
        self.stats = HammerStats()
        self.stats_lock = threading.Lock()

    def run(self):
        """Main execution"""
        # Setup phase (before dashboard)
        print('\033[1;36mWMS Hammer - Performance Testing\033[0m')
        print(f'URL: {self.base_url}')
        print()

        # Get layers
        if self.layers:
            filtered_layers = self.layers
            print(f'Using {len(filtered_layers)} pre-loaded layers')
        else:
            if self._capabilities:
                caps = self._capabilities
            else:
                print('Fetching capabilities...')
                try:
                    with WMSClient(self.base_url) as client:
                        caps = client.get_capabilities()
                except Exception as e:
                    print(f'\033[1;31mError:\033[0m Failed to fetch capabilities: {e}')
                    return 1

            queryable = caps.get_queryable_layers()
            print(f'Found {len(queryable)} queryable layers')

            if self.list_layers:
                self._list_layers(queryable)
                return 0

            if self.specific_layer:
                layer = next((l for l in queryable if l.name == self.specific_layer), None)
                if not layer:
                    print(f'\033[1;31mError:\033[0m Layer "{self.specific_layer}" not found')
                    return 1
                filtered_layers = [layer]
            else:
                filtered_layers = self._filter_layers(queryable)

        if not filtered_layers:
            print('No layers match the pattern!')
            return 0

        print(f'Testing {len(filtered_layers)} layers')

        # Generate requests
        all_requests = []
        if self.random_tiles:
            for layer in filtered_layers:
                requests = self._generate_random_tile_requests(layer)
                all_requests.extend(requests)
        else:
            for layer in filtered_layers:
                requests = self._generate_requests_for_layer(layer)
                all_requests.extend(requests)

        self.stats.total_requests = len(all_requests)
        print(f'Generated {len(all_requests):,} requests')
        print(f'Workers: {self.max_workers}')
        print()

        if self.dry_run:
            print('\033[1;33mDRY RUN\033[0m - Not executing requests')
            self._show_sample_requests(all_requests)
            return 0

        # Initialize layer stats
        for layer in filtered_layers:
            layer_reqs = [r for r in all_requests if r['layer'].name == layer.name]
            self.stats.layers[layer.name] = LayerStats(name=layer.name, total=len(layer_reqs))

        # Create output directory
        if self.save_images:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Start dashboard
        dashboard = Dashboard(self.stats, [l.name for l in filtered_layers])

        self.stats.start_time = time.time()
        dashboard.start()

        try:
            self._execute_requests(all_requests)
        except KeyboardInterrupt:
            pass
        finally:
            self.stats.end_time = time.time()
            dashboard.stop()

        # Clear screen and show final report
        print('\033[H\033[J', end='')
        self._show_report()

        # Save report if requested
        if self.report_file:
            self._save_report(self.report_file)

        return 0 if self.stats.failed == 0 else 1

    def _list_layers(self, layers: List[Layer]) -> None:
        """List all queryable layers"""
        print(f'\nAvailable Layers ({len(layers)} total):')
        print('=' * 60)
        for i, layer in enumerate(layers, 1):
            dims = ', '.join(layer.dimensions.keys()) if layer.dimensions else 'none'
            print(f'{i:3}. {layer.name}')
            print(f'     Dimensions: {dims}')
        print('=' * 60)

    def _filter_layers(self, layers: List[Layer]) -> List[Layer]:
        """Filter layers by glob pattern"""
        if self.glob_pattern == '*':
            return layers
        return [l for l in layers if fnmatch.fnmatch(l.name.upper(), self.glob_pattern.upper())]

    def _generate_random_tile_requests(self, layer: Layer) -> List[Dict[str, Any]]:
        """Generate random tile requests"""
        import random

        requests = []
        styles = [s.name for s in layer.styles] if layer.styles else ['default']
        max_tile = 2 ** self.tile_zoom - 1
        tiles_per_style = max(1, self.tile_count // len(styles))

        for style in styles:
            for _ in range(tiles_per_style):
                req = {
                    'layer': layer,
                    'style': style,
                    'tilezoom': self.tile_zoom,
                    'tilerow': random.randint(0, max_tile),
                    'tilecol': random.randint(0, max_tile),
                    'crs': 'EPSG:900913',
                    'dimensions': {}
                }
                requests.append(req)
        return requests

    def _generate_requests_for_layer(self, layer: Layer) -> List[Dict[str, Any]]:
        """Generate all request combinations for a layer"""
        dim_values = {}

        if 'RUN' in layer.dimensions:
            run_dim = layer.dimensions['RUN']
            if self.latest_run_only and run_dim.values:
                dim_values['DIM_RUN'] = [run_dim.values[-1]]
            elif run_dim.values:
                dim_values['DIM_RUN'] = run_dim.values
            elif run_dim.default:
                dim_values['DIM_RUN'] = [run_dim.default]

        if 'FORECAST' in layer.dimensions:
            forecast_dim = layer.dimensions['FORECAST']
            if forecast_dim.values:
                values = forecast_dim.values[:self.max_timesteps] if self.max_timesteps > 0 else forecast_dim.values
                dim_values['DIM_FORECAST'] = values
            elif forecast_dim.default:
                dim_values['DIM_FORECAST'] = [forecast_dim.default]

        if 'TIME' in layer.dimensions:
            time_dim = layer.dimensions['TIME']
            if time_dim.values:
                values = time_dim.values[:self.max_timesteps] if self.max_timesteps > 0 else time_dim.values
                dim_values['TIME'] = values
            elif time_dim.default:
                dim_values['TIME'] = [time_dim.default]

        if 'ELEVATION' in layer.dimensions:
            elev_dim = layer.dimensions['ELEVATION']
            if elev_dim.values:
                dim_values['ELEVATION'] = elev_dim.values
            elif elev_dim.default:
                dim_values['ELEVATION'] = [elev_dim.default]

        styles = [s.name for s in layer.styles] if layer.styles else ['default']
        crs = layer.crs_list[0] if layer.crs_list else 'CRS:84'
        if self.tile_mode:
            crs = 'EPSG:900913'
        bbox = self._get_bbox(layer)

        requests = []
        if not dim_values:
            for style in styles:
                requests.append({'layer': layer, 'style': style, 'crs': crs, 'bbox': bbox, 'dimensions': {}})
        else:
            keys = list(dim_values.keys())
            values = list(dim_values.values())
            for style in styles:
                for combo in product(*values):
                    dims = dict(zip(keys, combo))
                    requests.append({'layer': layer, 'style': style, 'crs': crs, 'bbox': bbox, 'dimensions': dims})
        return requests

    def _get_bbox(self, layer: Layer) -> tuple:
        """Get bounding box for layer"""
        if layer.geographic_bbox:
            bbox = layer.geographic_bbox
            return (bbox.minx, bbox.miny, bbox.maxx, bbox.maxy)
        if layer.bounding_boxes:
            bbox = list(layer.bounding_boxes.values())[0]
            return (bbox.minx, bbox.miny, bbox.maxx, bbox.maxy)
        return (-180, -90, 180, 90)

    def _execute_requests(self, requests: List[Dict[str, Any]]):
        """Execute requests with threading"""
        with WMSClient(self.base_url) as client:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {executor.submit(self._execute_single_request, client, req): req for req in requests}

                for future in as_completed(futures):
                    req = futures[future]
                    try:
                        future.result()
                    except Exception:
                        pass  # Already handled in _execute_single_request

    def _execute_single_request(self, client: WMSClient, req: Dict[str, Any]):
        """Execute a single request and track stats"""
        layer = req['layer']
        start = time.time()
        success = False
        error_msg = None
        content_length = 0

        try:
            if 'tilezoom' in req:
                image_data = client.get_gtile(
                    layer=layer.name,
                    tilezoom=req['tilezoom'],
                    tilerow=req['tilerow'],
                    tilecol=req['tilecol'],
                    crs=req['crs'],
                    style=req['style'],
                    **req['dimensions']
                )
            elif self.tile_mode:
                image_data = client.get_gtile(
                    layer=layer.name,
                    tilezoom=0, tilerow=0, tilecol=0,
                    crs=req['crs'],
                    style=req['style'],
                    **req['dimensions']
                )
            else:
                image_data = client.get_map(
                    layer=layer.name,
                    bbox=req['bbox'],
                    width=self.width,
                    height=self.height,
                    crs=req['crs'],
                    styles=req['style'],
                    **req['dimensions']
                )
            success = True
            content_length = len(image_data)

            if self.save_images:
                filename = self._generate_filename(layer.name, req['style'], req['dimensions'])
                filepath = self.output_dir / filename
                with open(filepath, 'wb') as f:
                    f.write(image_data)

        except Exception as e:
            error_msg = str(e)

        elapsed = time.time() - start

        # Update stats thread-safely
        with self.stats_lock:
            self.stats.completed += 1
            layer_stats = self.stats.layers[layer.name]

            if success:
                self.stats.successful += 1
                self.stats.total_bytes += content_length
                self.stats.response_times.append(elapsed)
                layer_stats.success += 1
                layer_stats.total_time += elapsed
                layer_stats.total_bytes += content_length
                layer_stats.response_times.append(elapsed)
                layer_stats.min_time = min(layer_stats.min_time, elapsed)
                layer_stats.max_time = max(layer_stats.max_time, elapsed)
            else:
                self.stats.failed += 1
                layer_stats.failed += 1
                if error_msg and len(layer_stats.errors) < 5:
                    layer_stats.errors.append(error_msg)

    def _generate_filename(self, layer_name: str, style: str, dimensions: Dict[str, str]) -> str:
        """Generate filename for saved image"""
        parts = [layer_name]
        if style != 'default':
            parts.append(style)
        for key, value in dimensions.items():
            clean = value.replace(':', '-').replace('/', '-').replace(' ', '_')
            parts.append(f'{key}_{clean}')
        return '_'.join(parts) + '.png'

    def _show_sample_requests(self, requests: List[Dict[str, Any]]):
        """Show sample requests for dry run"""
        print('\nSample requests (first 5):')
        for i, req in enumerate(requests[:5], 1):
            dims = ', '.join(f'{k}={v}' for k, v in req['dimensions'].items())
            print(f'\n{i}. {req["layer"].name}')
            print(f'   Style: {req["style"]}')
            print(f'   Dimensions: {dims or "none"}')
        if len(requests) > 5:
            print(f'\n... and {len(requests) - 5} more requests')

    def _show_report(self):
        """Show final report"""
        s = self.stats

        print('\033[1;36m' + '=' * 70 + '\033[0m')
        print('\033[1;36m  WMS HAMMER - Final Report\033[0m')
        print('\033[1;36m' + '=' * 70 + '\033[0m')
        print()
        print(f'  \033[1mURL:\033[0m {self.base_url}')
        print(f'  \033[1mDuration:\033[0m {s.elapsed:.2f} seconds')
        print(f'  \033[1mWorkers:\033[0m {self.max_workers}')
        print()

        # Overall stats
        print('\033[1m  OVERALL STATISTICS\033[0m')
        print('  ' + '-' * 40)
        print(f'  Total Requests:    {s.total_requests:,}')
        print(f'  Successful:        \033[1;32m{s.successful:,}\033[0m ({s.success_rate:.1f}%)')
        print(f'  Failed:            \033[1;31m{s.failed:,}\033[0m ({100 - s.success_rate:.1f}%)')
        print(f'  Requests/sec:      {s.requests_per_sec:.1f}')
        print(f'  Data Transferred:  {format_bytes(s.total_bytes)}')
        print(f'  Throughput:        {format_bytes(int(s.bytes_per_sec))}/s')
        print()

        # Latency distribution
        if s.response_times:
            print('\033[1m  LATENCY DISTRIBUTION\033[0m')
            print('  ' + '-' * 40)
            print(f'  p50 (median):      {s.percentile(50) * 1000:.0f} ms')
            print(f'  p95:               {s.percentile(95) * 1000:.0f} ms')
            print(f'  p99:               {s.percentile(99) * 1000:.0f} ms')
            print(f'  Min:               {min(s.response_times) * 1000:.0f} ms')
            print(f'  Max:               {max(s.response_times) * 1000:.0f} ms')
            print()

        # Per-layer breakdown
        print('\033[1m  PER-LAYER BREAKDOWN\033[0m')
        print('  ' + '-' * 66)
        print('  Layer                                  Total    OK  Fail  Avg(ms)')
        print('  ' + '-' * 66)

        sorted_layers = sorted(s.layers.values(), key=lambda x: x.failed, reverse=True)
        for ls in sorted_layers:
            name = ls.name[:36].ljust(36)
            avg_ms = ls.avg_time * 1000

            # Highlight failures
            if ls.failed > 0:
                fail_str = f'\033[1;31m{ls.failed:5}\033[0m'
            else:
                fail_str = f'{ls.failed:5}'

            print(f'  {name} {ls.total:5} {ls.success:5} {fail_str} {avg_ms:8.1f}')

            # Show errors for failed layers
            if ls.errors:
                for err in ls.errors[:2]:
                    err_short = err[:60] + '...' if len(err) > 60 else err
                    print(f'    \033[2m→ {err_short}\033[0m')

        print('  ' + '-' * 66)
        print()

        if self.save_images:
            total_size = sum(f.stat().st_size for f in self.output_dir.rglob('*.png'))
            print(f'  \033[1mOutput:\033[0m {self.output_dir} ({total_size / 1024 / 1024:.2f} MB)')
            print()

        print('\033[1;36m' + '=' * 70 + '\033[0m')

    def _save_report(self, filepath: str):
        """Save report to JSON file"""
        s = self.stats
        report = {
            'url': self.base_url,
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': s.elapsed,
            'workers': self.max_workers,
            'summary': {
                'total_requests': s.total_requests,
                'successful': s.successful,
                'failed': s.failed,
                'success_rate': s.success_rate,
                'requests_per_second': s.requests_per_sec,
                'total_bytes': s.total_bytes,
                'bytes_per_second': s.bytes_per_sec,
                'latency_ms': {
                    'p50': s.percentile(50) * 1000,
                    'p95': s.percentile(95) * 1000,
                    'p99': s.percentile(99) * 1000,
                    'min': min(s.response_times) * 1000 if s.response_times else None,
                    'max': max(s.response_times) * 1000 if s.response_times else None
                }
            },
            'layers': {}
        }

        for name, ls in s.layers.items():
            report['layers'][name] = {
                'total': ls.total,
                'success': ls.success,
                'failed': ls.failed,
                'success_rate': ls.success_rate,
                'total_bytes': ls.total_bytes,
                'avg_bytes': ls.avg_bytes,
                'latency_ms': {
                    'avg': ls.avg_time * 1000,
                    'p50': ls.percentile(50) * 1000,
                    'p95': ls.percentile(95) * 1000,
                    'p99': ls.percentile(99) * 1000,
                    'min': ls.min_time * 1000 if ls.min_time != float('inf') else None,
                    'max': ls.max_time * 1000 if ls.max_time > 0 else None
                },
                'errors': ls.errors
            }

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        print(f'  \033[1mReport saved:\033[0m {filepath}')


def main():
    parser = argparse.ArgumentParser(
        description='WMS Hammer - Performance testing for WMS servers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s https://example.com/wms              # Test all layers (metrics only)
  %(prog)s https://example.com/wms -g "GFS*"    # Test layers matching pattern
  %(prog)s https://example.com/wms -w 50        # Use 50 concurrent workers
  %(prog)s https://example.com/wms -o ./images  # Save images to disk
  %(prog)s https://example.com/wms -r report.json  # Save JSON report

Metrics tracked:
  - Response time (avg, p50, p95, p99, min, max)
  - Throughput (requests/sec, bytes/sec)
  - Success/failure rates
  - Data transferred per request
'''
    )

    parser.add_argument('url', help='WMS service base URL')
    parser.add_argument('-g', '--glob', default='*', help='Glob pattern for layer names (default: *)')
    parser.add_argument('-o', '--output', default=None, help='Save images to directory (omit for metrics only)')
    parser.add_argument('-w', '--workers', type=int, default=20, help='Number of concurrent workers (default: 20)')
    parser.add_argument('-t', '--max-timesteps', type=int, default=10, help='Max timesteps per layer (default: 10)')
    parser.add_argument('--width', type=int, default=800, help='Image width in pixels (default: 800)')
    parser.add_argument('--height', type=int, default=600, help='Image height in pixels (default: 600)')
    parser.add_argument('--tile-mode', action='store_true', help='Use GetGTile instead of GetMap')
    parser.add_argument('--latest-run', dest='latest_run_only', action='store_true', help='Test only the latest model run')
    parser.add_argument('--dry-run', action='store_true', help='Preview requests without executing')
    parser.add_argument('-l', '--layer', help='Target a specific layer by name')
    parser.add_argument('--list-layers', action='store_true', help='List available layers and exit')
    parser.add_argument('--random-tiles', action='store_true', help='Generate random tile requests')
    parser.add_argument('--tile-zoom', type=int, default=0, help='Tile zoom level for random tiles (default: 0)')
    parser.add_argument('--tile-count', type=int, default=100, help='Number of random tiles per layer (default: 100)')
    parser.add_argument('-r', '--report', help='Save JSON performance report to file')

    args = parser.parse_args()
    hammer = WMSHammer(args)
    return hammer.run()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('\n\nAborted by user')
        sys.exit(130)
