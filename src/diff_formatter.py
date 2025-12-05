#!/usr/bin/env python3
"""
Output formatting for WMS capabilities diffs.
Supports text (with colors), JSON, and summary formats.
"""

import json
import sys
from dataclasses import asdict
from typing import List

from .diff import (
    CapabilitiesDiff, LayerDiff, DimensionDiff, StyleDiff,
    ServiceDiff, PropertyChange, ChangeType
)


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'


def _supports_color() -> bool:
    """Check if terminal supports color output."""
    # Check if stdout is a tty
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    
    # Check for NO_COLOR environment variable
    import os
    if os.environ.get('NO_COLOR'):
        return False
    
    return True


def _color(text: str, color: str) -> str:
    """Wrap text in color codes if supported."""
    if _supports_color():
        return f"{color}{text}{Colors.RESET}"
    return text


def format_diff_text(diff: CapabilitiesDiff, layers_only: bool = False) -> str:
    """
    Format diff as human-readable text with colors.
    
    Args:
        diff: CapabilitiesDiff to format
        layers_only: If True, skip service-level changes
    
    Returns:
        Formatted string
    """
    lines = []
    
    # Header
    lines.append(_color(f"Comparing: {diff.source_a} → {diff.source_b}", Colors.BOLD))
    lines.append("")
    
    # Service changes
    if not layers_only and diff.service.changes:
        lines.append(_color("Service Changes:", Colors.CYAN))
        for change in diff.service.changes:
            lines.append(f"  {change}")
        lines.append("")
    
    # Format changes
    if not layers_only and (diff.service.formats_added or diff.service.formats_removed):
        lines.append(_color("Format Changes:", Colors.CYAN))
        for fmt in diff.service.formats_added:
            lines.append(_color(f"  + {fmt}", Colors.GREEN))
        for fmt in diff.service.formats_removed:
            lines.append(_color(f"  - {fmt}", Colors.RED))
        lines.append("")
    
    # Layer summary
    lines.append(_color("Layers:", Colors.CYAN))
    
    if not diff.layers_added and not diff.layers_removed and not diff.layers_modified:
        lines.append(_color("  No layer changes", Colors.DIM))
    else:
        # Added layers
        for name in diff.layers_added:
            lines.append(_color(f"  + {name}", Colors.GREEN))
        
        # Removed layers
        for name in diff.layers_removed:
            lines.append(_color(f"  - {name}", Colors.RED))
        
        # Modified layers
        for layer_diff in diff.layers_modified:
            lines.append(_color(f"  ~ {layer_diff.name}", Colors.YELLOW))
            lines.extend(_format_layer_changes(layer_diff, indent=4))
    
    lines.append("")
    
    # Summary line
    lines.append(_color("Summary:", Colors.BOLD))
    added = _color(str(len(diff.layers_added)), Colors.GREEN)
    removed = _color(str(len(diff.layers_removed)), Colors.RED)
    modified = _color(str(len(diff.layers_modified)), Colors.YELLOW)
    lines.append(f"  {added} added, {removed} removed, {modified} modified, {diff.layers_unchanged} unchanged")
    
    return "\n".join(lines)


def _format_layer_changes(layer_diff: LayerDiff, indent: int = 2) -> List[str]:
    """Format changes within a layer."""
    lines = []
    prefix = " " * indent
    
    # Property changes
    for change in layer_diff.changes:
        lines.append(f"{prefix}{change}")
    
    # CRS changes
    for crs in layer_diff.crs_added:
        lines.append(_color(f"{prefix}CRS added: {crs}", Colors.GREEN))
    for crs in layer_diff.crs_removed:
        lines.append(_color(f"{prefix}CRS removed: {crs}", Colors.RED))
    
    # Dimension changes
    for dim in layer_diff.dimensions:
        if dim.status == ChangeType.ADDED:
            lines.append(_color(f"{prefix}Dimension '{dim.name}' added", Colors.GREEN))
        elif dim.status == ChangeType.REMOVED:
            lines.append(_color(f"{prefix}Dimension '{dim.name}' removed", Colors.RED))
        elif dim.status == ChangeType.MODIFIED:
            lines.append(_color(f"{prefix}Dimension '{dim.name}' modified:", Colors.YELLOW))
            if dim.values_added:
                lines.append(f"{prefix}  +{len(dim.values_added)} values")
            if dim.values_removed:
                lines.append(f"{prefix}  -{len(dim.values_removed)} values")
            if dim.default_changed:
                old, new = dim.default_changed
                lines.append(f"{prefix}  default: '{old}' → '{new}'")
    
    # Style changes
    for style in layer_diff.styles:
        if style.status == ChangeType.ADDED:
            lines.append(_color(f"{prefix}Style '{style.name}' added", Colors.GREEN))
        elif style.status == ChangeType.REMOVED:
            lines.append(_color(f"{prefix}Style '{style.name}' removed", Colors.RED))
        elif style.status == ChangeType.MODIFIED:
            lines.append(_color(f"{prefix}Style '{style.name}' modified", Colors.YELLOW))
    
    return lines


def format_diff_json(diff: CapabilitiesDiff) -> str:
    """
    Format diff as JSON.
    
    Args:
        diff: CapabilitiesDiff to format
    
    Returns:
        JSON string
    """
    def convert(obj):
        """Convert objects to JSON-serializable format."""
        if isinstance(obj, ChangeType):
            return obj.value
        if hasattr(obj, '__dataclass_fields__'):
            return {k: convert(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [convert(i) for i in obj]
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, tuple):
            return list(obj)
        return obj
    
    data = convert(diff)
    return json.dumps(data, indent=2)


def format_diff_summary(diff: CapabilitiesDiff) -> str:
    """
    Format diff as brief summary.
    
    Args:
        diff: CapabilitiesDiff to format
    
    Returns:
        Brief summary string
    """
    lines = [
        f"Comparing: {diff.source_a} → {diff.source_b}",
        f"Layers: +{len(diff.layers_added)} -{len(diff.layers_removed)} ~{len(diff.layers_modified)} ={diff.layers_unchanged}",
        f"Service changes: {len(diff.service.changes)}",
        f"Format changes: +{len(diff.service.formats_added)} -{len(diff.service.formats_removed)}"
    ]
    return "\n".join(lines)


def format_layer_diff_text(layer_diff: LayerDiff, source_a: str, source_b: str, verbose: bool = False) -> str:
    """
    Format a single layer diff in detail.
    
    Args:
        layer_diff: LayerDiff to format
        source_a: Label for first source
        source_b: Label for second source
        verbose: If True, show all details including dimension values
    
    Returns:
        Formatted string
    """
    lines = []
    
    lines.append(_color(f"Layer: {layer_diff.name}", Colors.BOLD))
    lines.append(f"Comparing: {source_a} → {source_b}")
    lines.append(f"Status: {layer_diff.status.value}")
    lines.append("")
    
    if layer_diff.status == ChangeType.ADDED:
        lines.append(_color("Layer exists only in second source", Colors.GREEN))
    elif layer_diff.status == ChangeType.REMOVED:
        lines.append(_color("Layer exists only in first source", Colors.RED))
    elif layer_diff.status == ChangeType.UNCHANGED:
        lines.append(_color("No changes detected", Colors.DIM))
    else:
        lines.extend(_format_layer_changes_verbose(layer_diff, indent=0) if verbose 
                     else _format_layer_changes(layer_diff, indent=0))
    
    return "\n".join(lines)


def _format_layer_changes_verbose(layer_diff: LayerDiff, indent: int = 2) -> List[str]:
    """Format changes within a layer with full details."""
    lines = []
    prefix = " " * indent
    
    # Property changes
    if layer_diff.changes:
        lines.append(f"{prefix}{_color('Property Changes:', Colors.CYAN)}")
        for change in layer_diff.changes:
            lines.append(f"{prefix}  {change}")
    
    # CRS changes
    if layer_diff.crs_added or layer_diff.crs_removed:
        lines.append(f"{prefix}{_color('CRS Changes:', Colors.CYAN)}")
        for crs in layer_diff.crs_added:
            lines.append(_color(f"{prefix}  + {crs}", Colors.GREEN))
        for crs in layer_diff.crs_removed:
            lines.append(_color(f"{prefix}  - {crs}", Colors.RED))
    
    # Dimension changes with full details
    if layer_diff.dimensions:
        lines.append(f"{prefix}{_color('Dimension Changes:', Colors.CYAN)}")
        for dim in layer_diff.dimensions:
            if dim.status == ChangeType.ADDED:
                lines.append(_color(f"{prefix}  + {dim.name} (new dimension)", Colors.GREEN))
            elif dim.status == ChangeType.REMOVED:
                lines.append(_color(f"{prefix}  - {dim.name} (removed)", Colors.RED))
            elif dim.status == ChangeType.MODIFIED:
                lines.append(_color(f"{prefix}  ~ {dim.name}:", Colors.YELLOW))
                if dim.default_changed:
                    old, new = dim.default_changed
                    lines.append(f"{prefix}      default: '{old}' → '{new}'")
                if dim.values_added:
                    lines.append(_color(f"{prefix}      +{len(dim.values_added)} values added:", Colors.GREEN))
                    # Show up to 10 values
                    for v in dim.values_added[:10]:
                        lines.append(f"{prefix}        + {v}")
                    if len(dim.values_added) > 10:
                        lines.append(f"{prefix}        ... and {len(dim.values_added) - 10} more")
                if dim.values_removed:
                    lines.append(_color(f"{prefix}      -{len(dim.values_removed)} values removed:", Colors.RED))
                    for v in dim.values_removed[:10]:
                        lines.append(f"{prefix}        - {v}")
                    if len(dim.values_removed) > 10:
                        lines.append(f"{prefix}        ... and {len(dim.values_removed) - 10} more")
                for change in dim.changes:
                    lines.append(f"{prefix}      {change}")
    
    # Style changes
    if layer_diff.styles:
        lines.append(f"{prefix}{_color('Style Changes:', Colors.CYAN)}")
        for style in layer_diff.styles:
            if style.status == ChangeType.ADDED:
                lines.append(_color(f"{prefix}  + {style.name}", Colors.GREEN))
            elif style.status == ChangeType.REMOVED:
                lines.append(_color(f"{prefix}  - {style.name}", Colors.RED))
            elif style.status == ChangeType.MODIFIED:
                lines.append(_color(f"{prefix}  ~ {style.name}:", Colors.YELLOW))
                for change in style.changes:
                    lines.append(f"{prefix}      {change}")
    
    return lines


def format_diff_verbose(diff: CapabilitiesDiff, layers_only: bool = False, 
                        show_unchanged: bool = False) -> str:
    """
    Format diff with verbose output showing all details.
    
    Args:
        diff: CapabilitiesDiff to format
        layers_only: If True, skip service-level changes
        show_unchanged: If True, also list unchanged layers
    
    Returns:
        Formatted string with full details
    """
    lines = []
    
    # Header with box
    lines.append(_color("╔" + "═" * 58 + "╗", Colors.BOLD))
    lines.append(_color(f"║  WMS CAPABILITIES DIFF", Colors.BOLD))
    lines.append(_color("╠" + "═" * 58 + "╣", Colors.BOLD))
    lines.append(_color(f"║  Source A: {diff.source_a[:45]}", Colors.BOLD))
    lines.append(_color(f"║  Source B: {diff.source_b[:45]}", Colors.BOLD))
    lines.append(_color("╚" + "═" * 58 + "╝", Colors.BOLD))
    lines.append("")
    
    # Service changes (detailed)
    if not layers_only:
        if diff.service.changes or diff.service.formats_added or diff.service.formats_removed:
            lines.append(_color("━━━ SERVICE CHANGES ━━━", Colors.CYAN))
            
            if diff.service.changes:
                lines.append(_color("\nMetadata:", Colors.CYAN))
                for change in diff.service.changes:
                    lines.append(f"  {change}")
            
            if diff.service.formats_added:
                lines.append(_color("\nFormats Added:", Colors.GREEN))
                for fmt in diff.service.formats_added:
                    lines.append(f"  + {fmt}")
            
            if diff.service.formats_removed:
                lines.append(_color("\nFormats Removed:", Colors.RED))
                for fmt in diff.service.formats_removed:
                    lines.append(f"  - {fmt}")
            
            lines.append("")
    
    # Layer changes
    lines.append(_color("━━━ LAYER CHANGES ━━━", Colors.CYAN))
    lines.append("")
    
    # Added layers
    if diff.layers_added:
        lines.append(_color(f"ADDED ({len(diff.layers_added)}):", Colors.GREEN))
        for name in diff.layers_added:
            lines.append(_color(f"  + {name}", Colors.GREEN))
        lines.append("")
    
    # Removed layers
    if diff.layers_removed:
        lines.append(_color(f"REMOVED ({len(diff.layers_removed)}):", Colors.RED))
        for name in diff.layers_removed:
            lines.append(_color(f"  - {name}", Colors.RED))
        lines.append("")
    
    # Modified layers (with full details)
    if diff.layers_modified:
        lines.append(_color(f"MODIFIED ({len(diff.layers_modified)}):", Colors.YELLOW))
        for layer_diff in diff.layers_modified:
            lines.append("")
            lines.append(_color(f"  ┌─ {layer_diff.name}", Colors.YELLOW))
            verbose_changes = _format_layer_changes_verbose(layer_diff, indent=4)
            lines.extend(verbose_changes)
            lines.append(_color(f"  └─────────────────────────────────────", Colors.DIM))
        lines.append("")
    
    # Unchanged layers (if requested)
    if show_unchanged and diff.layers_unchanged > 0:
        lines.append(_color(f"UNCHANGED: {diff.layers_unchanged} layers", Colors.DIM))
        lines.append("")
    
    # Summary
    lines.append(_color("━━━ SUMMARY ━━━", Colors.CYAN))
    total = len(diff.layers_added) + len(diff.layers_removed) + len(diff.layers_modified) + diff.layers_unchanged
    lines.append(f"  Total layers compared: {total}")
    lines.append(f"  {_color(f'+{len(diff.layers_added)} added', Colors.GREEN)}")
    lines.append(f"  {_color(f'-{len(diff.layers_removed)} removed', Colors.RED)}")
    lines.append(f"  {_color(f'~{len(diff.layers_modified)} modified', Colors.YELLOW)}")
    lines.append(f"  {_color(f'={diff.layers_unchanged} unchanged', Colors.DIM)}")
    
    return "\n".join(lines)


def format_diff_stats(diff: CapabilitiesDiff, caps_a=None, caps_b=None) -> str:
    """
    Format diff with statistics and percentages.
    
    Args:
        diff: CapabilitiesDiff to format
        caps_a: Optional first capabilities for additional stats
        caps_b: Optional second capabilities for additional stats
    
    Returns:
        Statistics summary
    """
    lines = []
    
    lines.append(_color("═══ DIFF STATISTICS ═══", Colors.BOLD))
    lines.append("")
    lines.append(f"Source A: {diff.source_a}")
    lines.append(f"Source B: {diff.source_b}")
    lines.append("")
    
    # Layer counts
    total_a = len(diff.layers_removed) + len(diff.layers_modified) + diff.layers_unchanged
    total_b = len(diff.layers_added) + len(diff.layers_modified) + diff.layers_unchanged
    
    lines.append(_color("── Layer Counts ──", Colors.CYAN))
    lines.append(f"  Layers in A: {total_a}")
    lines.append(f"  Layers in B: {total_b}")
    lines.append(f"  Difference:  {total_b - total_a:+d}")
    lines.append("")
    
    # Change breakdown
    total_changes = len(diff.layers_added) + len(diff.layers_removed) + len(diff.layers_modified)
    total_layers = total_changes + diff.layers_unchanged
    
    lines.append(_color("── Change Breakdown ──", Colors.CYAN))
    
    if total_layers > 0:
        added_pct = (len(diff.layers_added) / total_layers) * 100
        removed_pct = (len(diff.layers_removed) / total_layers) * 100
        modified_pct = (len(diff.layers_modified) / total_layers) * 100
        unchanged_pct = (diff.layers_unchanged / total_layers) * 100
        
        lines.append(f"  Added:     {len(diff.layers_added):4d}  ({added_pct:5.1f}%) {_bar(added_pct, Colors.GREEN)}")
        lines.append(f"  Removed:   {len(diff.layers_removed):4d}  ({removed_pct:5.1f}%) {_bar(removed_pct, Colors.RED)}")
        lines.append(f"  Modified:  {len(diff.layers_modified):4d}  ({modified_pct:5.1f}%) {_bar(modified_pct, Colors.YELLOW)}")
        lines.append(f"  Unchanged: {diff.layers_unchanged:4d}  ({unchanged_pct:5.1f}%) {_bar(unchanged_pct, Colors.DIM)}")
    else:
        lines.append("  No layers to compare")
    
    lines.append("")
    
    # Modification details
    if diff.layers_modified:
        lines.append(_color("── Modification Details ──", Colors.CYAN))
        
        dim_changes = sum(len(l.dimensions) for l in diff.layers_modified)
        style_changes = sum(len(l.styles) for l in diff.layers_modified)
        crs_changes = sum(len(l.crs_added) + len(l.crs_removed) for l in diff.layers_modified)
        prop_changes = sum(len(l.changes) for l in diff.layers_modified)
        
        lines.append(f"  Dimension changes: {dim_changes}")
        lines.append(f"  Style changes:     {style_changes}")
        lines.append(f"  CRS changes:       {crs_changes}")
        lines.append(f"  Property changes:  {prop_changes}")
        lines.append("")
    
    # Service changes
    if diff.service.changes or diff.service.formats_added or diff.service.formats_removed:
        lines.append(_color("── Service Changes ──", Colors.CYAN))
        lines.append(f"  Metadata changes: {len(diff.service.changes)}")
        lines.append(f"  Formats added:    {len(diff.service.formats_added)}")
        lines.append(f"  Formats removed:  {len(diff.service.formats_removed)}")
        lines.append("")
    
    # Overall assessment
    lines.append(_color("── Assessment ──", Colors.CYAN))
    if total_changes == 0:
        lines.append(_color("  ✓ No differences found - capabilities are identical", Colors.GREEN))
    elif len(diff.layers_removed) > len(diff.layers_added):
        lines.append(_color("  ⚠ Net reduction in layers", Colors.YELLOW))
    elif len(diff.layers_added) > len(diff.layers_removed):
        lines.append(_color("  ✓ Net increase in layers", Colors.GREEN))
    
    change_ratio = (total_changes / total_layers * 100) if total_layers > 0 else 0
    if change_ratio > 50:
        lines.append(_color(f"  ⚠ High change ratio: {change_ratio:.1f}% of layers affected", Colors.YELLOW))
    elif change_ratio > 20:
        lines.append(_color(f"  ● Moderate change ratio: {change_ratio:.1f}% of layers affected", Colors.BLUE))
    else:
        lines.append(_color(f"  ✓ Low change ratio: {change_ratio:.1f}% of layers affected", Colors.GREEN))
    
    return "\n".join(lines)


def _bar(percentage: float, color: str, width: int = 20) -> str:
    """Create a simple bar graph."""
    filled = int(percentage / 100 * width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return _color(bar, color)


def format_layer_diff_json(layer_diff: LayerDiff) -> str:
    """
    Format a single layer diff as JSON.
    
    Args:
        layer_diff: LayerDiff to format
    
    Returns:
        JSON string
    """
    def convert(obj):
        if isinstance(obj, ChangeType):
            return obj.value
        if hasattr(obj, '__dataclass_fields__'):
            return {k: convert(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [convert(i) for i in obj]
        if isinstance(obj, tuple):
            return list(obj)
        return obj
    
    return json.dumps(convert(layer_diff), indent=2)

