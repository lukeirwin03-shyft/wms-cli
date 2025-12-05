#!/usr/bin/env python3
"""
WMS Capabilities Comparison Engine.
Compares two WMS GetCapabilities documents and identifies differences.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
from enum import Enum

from .wms_parser import WMSCapabilities, Layer, Dimension, Style


class ChangeType(Enum):
    """Type of change detected."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class PropertyChange:
    """A single property change."""
    property_name: str
    old_value: Any
    new_value: Any
    
    def __str__(self):
        if self.old_value is None:
            return f"{self.property_name}: added '{self.new_value}'"
        elif self.new_value is None:
            return f"{self.property_name}: removed '{self.old_value}'"
        else:
            return f"{self.property_name}: '{self.old_value}' → '{self.new_value}'"


@dataclass
class DimensionDiff:
    """Diff for a single dimension."""
    name: str
    status: ChangeType
    changes: List[PropertyChange] = field(default_factory=list)
    values_added: List[str] = field(default_factory=list)
    values_removed: List[str] = field(default_factory=list)
    default_changed: Optional[Tuple[str, str]] = None  # (old, new)


@dataclass
class StyleDiff:
    """Diff for a single style."""
    name: str
    status: ChangeType
    changes: List[PropertyChange] = field(default_factory=list)


@dataclass
class LayerDiff:
    """Diff for a single layer."""
    name: str
    status: ChangeType
    changes: List[PropertyChange] = field(default_factory=list)
    dimensions: List[DimensionDiff] = field(default_factory=list)
    styles: List[StyleDiff] = field(default_factory=list)
    crs_added: List[str] = field(default_factory=list)
    crs_removed: List[str] = field(default_factory=list)


@dataclass
class ServiceDiff:
    """Diff for service-level metadata."""
    changes: List[PropertyChange] = field(default_factory=list)
    formats_added: List[str] = field(default_factory=list)
    formats_removed: List[str] = field(default_factory=list)


@dataclass
class CapabilitiesDiff:
    """Complete diff between two capabilities documents."""
    source_a: str  # Server name or URL
    source_b: str
    
    # Service-level differences
    service: ServiceDiff = field(default_factory=ServiceDiff)
    
    # Layer differences
    layers_added: List[str] = field(default_factory=list)
    layers_removed: List[str] = field(default_factory=list)
    layers_modified: List[LayerDiff] = field(default_factory=list)
    layers_unchanged: int = 0
    
    @property
    def total_changes(self) -> int:
        """Total number of layer changes."""
        return len(self.layers_added) + len(self.layers_removed) + len(self.layers_modified)
    
    @property
    def has_changes(self) -> bool:
        """Check if there are any differences."""
        return self.total_changes > 0 or len(self.service.changes) > 0


def compare_capabilities(
    caps_a: WMSCapabilities,
    caps_b: WMSCapabilities,
    source_a: str = "A",
    source_b: str = "B"
) -> CapabilitiesDiff:
    """
    Compare two WMS capabilities documents.
    
    Args:
        caps_a: First capabilities (typically "old" or "baseline")
        caps_b: Second capabilities (typically "new" or "comparison")
        source_a: Label for first source
        source_b: Label for second source
    
    Returns:
        CapabilitiesDiff with all differences
    """
    diff = CapabilitiesDiff(source_a=source_a, source_b=source_b)
    
    # Compare service metadata
    diff.service = _compare_service(caps_a, caps_b)
    
    # Get layer names
    layers_a = {l.name: l for l in caps_a.get_queryable_layers()}
    layers_b = {l.name: l for l in caps_b.get_queryable_layers()}
    
    names_a = set(layers_a.keys())
    names_b = set(layers_b.keys())
    
    # Find added/removed
    diff.layers_added = sorted(names_b - names_a)
    diff.layers_removed = sorted(names_a - names_b)
    
    # Compare common layers
    common = names_a & names_b
    for name in sorted(common):
        layer_diff = _compare_layer(layers_a[name], layers_b[name])
        if layer_diff.status == ChangeType.MODIFIED:
            diff.layers_modified.append(layer_diff)
        else:
            diff.layers_unchanged += 1
    
    return diff


def _compare_service(caps_a: WMSCapabilities, caps_b: WMSCapabilities) -> ServiceDiff:
    """Compare service-level metadata."""
    diff = ServiceDiff()
    
    # Compare basic properties
    if caps_a.service_title != caps_b.service_title:
        diff.changes.append(PropertyChange(
            "service_title", caps_a.service_title, caps_b.service_title
        ))
    
    if caps_a.service_abstract != caps_b.service_abstract:
        diff.changes.append(PropertyChange(
            "service_abstract", caps_a.service_abstract, caps_b.service_abstract
        ))
    
    if caps_a.version != caps_b.version:
        diff.changes.append(PropertyChange(
            "version", caps_a.version, caps_b.version
        ))
    
    # Compare formats
    formats_a = set(caps_a.get_map_formats)
    formats_b = set(caps_b.get_map_formats)
    diff.formats_added = sorted(formats_b - formats_a)
    diff.formats_removed = sorted(formats_a - formats_b)
    
    return diff


def _compare_layer(layer_a: Layer, layer_b: Layer) -> LayerDiff:
    """Compare two layers with the same name."""
    diff = LayerDiff(name=layer_a.name, status=ChangeType.UNCHANGED)
    
    # Compare basic properties
    if layer_a.title != layer_b.title:
        diff.changes.append(PropertyChange("title", layer_a.title, layer_b.title))
    
    if layer_a.abstract != layer_b.abstract:
        diff.changes.append(PropertyChange("abstract", layer_a.abstract, layer_b.abstract))
    
    if layer_a.queryable != layer_b.queryable:
        diff.changes.append(PropertyChange("queryable", layer_a.queryable, layer_b.queryable))
    
    # Compare CRS
    crs_a = set(layer_a.crs_list)
    crs_b = set(layer_b.crs_list)
    diff.crs_added = sorted(crs_b - crs_a)
    diff.crs_removed = sorted(crs_a - crs_b)
    
    # Compare dimensions
    diff.dimensions = _compare_dimensions(layer_a.dimensions, layer_b.dimensions)
    
    # Compare styles
    diff.styles = _compare_styles(layer_a.styles, layer_b.styles)
    
    # Determine if modified
    if (diff.changes or diff.dimensions or diff.styles or 
        diff.crs_added or diff.crs_removed):
        diff.status = ChangeType.MODIFIED
    
    return diff


def _compare_dimensions(
    dims_a: Dict[str, Dimension],
    dims_b: Dict[str, Dimension]
) -> List[DimensionDiff]:
    """Compare dimension dictionaries."""
    diffs = []
    
    names_a = set(dims_a.keys())
    names_b = set(dims_b.keys())
    
    # Added dimensions
    for name in sorted(names_b - names_a):
        diffs.append(DimensionDiff(name=name, status=ChangeType.ADDED))
    
    # Removed dimensions
    for name in sorted(names_a - names_b):
        diffs.append(DimensionDiff(name=name, status=ChangeType.REMOVED))
    
    # Modified dimensions
    for name in sorted(names_a & names_b):
        dim_a, dim_b = dims_a[name], dims_b[name]
        dim_diff = DimensionDiff(name=name, status=ChangeType.UNCHANGED)
        
        # Compare values
        vals_a = set(dim_a.values)
        vals_b = set(dim_b.values)
        dim_diff.values_added = sorted(vals_b - vals_a)
        dim_diff.values_removed = sorted(vals_a - vals_b)
        
        # Compare default
        if dim_a.default != dim_b.default:
            dim_diff.default_changed = (dim_a.default, dim_b.default)
        
        # Compare units
        if dim_a.units != dim_b.units:
            dim_diff.changes.append(PropertyChange("units", dim_a.units, dim_b.units))
        
        if dim_diff.values_added or dim_diff.values_removed or dim_diff.default_changed or dim_diff.changes:
            dim_diff.status = ChangeType.MODIFIED
            diffs.append(dim_diff)
    
    return diffs


def _compare_styles(styles_a: List[Style], styles_b: List[Style]) -> List[StyleDiff]:
    """Compare style lists."""
    diffs = []
    
    dict_a = {s.name: s for s in styles_a}
    dict_b = {s.name: s for s in styles_b}
    
    names_a = set(dict_a.keys())
    names_b = set(dict_b.keys())
    
    # Added styles
    for name in sorted(names_b - names_a):
        diffs.append(StyleDiff(name=name, status=ChangeType.ADDED))
    
    # Removed styles
    for name in sorted(names_a - names_b):
        diffs.append(StyleDiff(name=name, status=ChangeType.REMOVED))
    
    # Modified styles
    for name in sorted(names_a & names_b):
        style_a, style_b = dict_a[name], dict_b[name]
        style_diff = StyleDiff(name=name, status=ChangeType.UNCHANGED)
        
        if style_a.title != style_b.title:
            style_diff.changes.append(PropertyChange("title", style_a.title, style_b.title))
        
        if style_diff.changes:
            style_diff.status = ChangeType.MODIFIED
            diffs.append(style_diff)
    
    return diffs


def compare_single_layer(
    layer_a: Optional[Layer],
    layer_b: Optional[Layer],
    source_a: str = "A",
    source_b: str = "B"
) -> LayerDiff:
    """
    Deep comparison of a single layer.
    
    Useful for detailed inspection of one specific layer.
    Handles case where layer exists in only one source.
    
    Args:
        layer_a: Layer from first source (or None)
        layer_b: Layer from second source (or None)
        source_a: Label for first source
        source_b: Label for second source
    
    Returns:
        LayerDiff with comparison results
    
    Raises:
        ValueError: If both layers are None
    """
    if layer_a is None and layer_b is None:
        raise ValueError("At least one layer must be provided")
    
    if layer_a is None:
        return LayerDiff(name=layer_b.name, status=ChangeType.ADDED)
    
    if layer_b is None:
        return LayerDiff(name=layer_a.name, status=ChangeType.REMOVED)
    
    return _compare_layer(layer_a, layer_b)

