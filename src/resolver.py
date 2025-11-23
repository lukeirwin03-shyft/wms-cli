#!/usr/bin/env python3
"""
Query resolver for WMS CLI.
Resolves fuzzy user input into valid WMS queries.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

from .wms_parser import WMSCapabilities, Layer, BoundingBox, Dimension
from .fuzzy import FuzzySearchEngine, SearchResult


@dataclass
class ResolvedQuery:
    """Fully resolved WMS query with validated parameters"""
    layer: Layer                      # Resolved layer object
    style: str                        # Validated style name
    dimensions: Dict[str, str]        # Validated dimension values
    crs: str                          # Coordinate reference system
    bbox: Tuple[float, float, float, float]  # (minx, miny, maxx, maxy)
    confidence: float                 # Match confidence (0-1)
    alternatives: List[Layer] = field(default_factory=list)  # Other matches

    def get_dimension_param_name(self, dim_name: str) -> str:
        """Get the WMS parameter name for a dimension"""
        # TIME and ELEVATION don't get DIM_ prefix
        if dim_name in ('TIME', 'ELEVATION'):
            return dim_name
        return f'DIM_{dim_name}'


class QueryResolver:
    """
    Resolves fuzzy user input into valid WMS queries.

    Takes user input like "gfs temp 850 +6h" and resolves it to:
    - Layer: GFS_Temperature
    - Style: default
    - Dimensions: ELEVATION=850, DIM_FORECAST=PT6H, DIM_RUN=<latest>
    """

    # Patterns for extracting dimensions from query
    FORECAST_PATTERNS = [
        (r'\+(\d+)h\b', lambda m: f'PT{m.group(1)}H'),           # +6h → PT6H
        (r'\+(\d+)d\b', lambda m: f'P{m.group(1)}D'),            # +2d → P2D
        (r'pt(\d+)h\b', lambda m: f'PT{m.group(1)}H'),           # pt6h → PT6H
        (r'p(\d+)d\b', lambda m: f'P{m.group(1)}D'),             # p2d → P2D
        (r'(\d+)\s*hr?\b', lambda m: f'PT{m.group(1)}H'),        # 6h, 6hr → PT6H
    ]

    ELEVATION_PATTERN = r'\b(\d+)\s*(hpa|mb)?\b'  # 850, 850hpa, 500mb

    def __init__(self, capabilities: WMSCapabilities):
        """
        Initialize resolver with capabilities.

        Args:
            capabilities: Parsed WMSCapabilities object
        """
        self.capabilities = capabilities
        self.search_engine = FuzzySearchEngine(capabilities)

    def resolve(self, query: str) -> ResolvedQuery:
        """
        Resolve fuzzy input to valid WMS query.

        Args:
            query: User input (e.g., "gfs temp 850 +6h contour")

        Returns:
            ResolvedQuery with validated parameters

        Raises:
            ValueError: If no matching layer found
        """
        # Extract and remove special tokens from query
        remaining_query, extracted = self._extract_special_tokens(query)

        # Search for matching layer
        results = self.search_engine.search(remaining_query, limit=10)

        if not results:
            raise ValueError(f"No layers found matching: {query}")

        # Best match
        best = results[0]
        layer = best.layer

        # Resolve style
        style = self._resolve_style(extracted.get('style'), layer)

        # Resolve dimensions
        dimensions = self._resolve_dimensions(extracted, layer)

        # Get CRS and bbox
        crs = self._get_preferred_crs(layer)
        bbox = self._get_bbox(layer, crs)

        # Alternatives (next best matches)
        alternatives = [r.layer for r in results[1:5]]

        return ResolvedQuery(
            layer=layer,
            style=style,
            dimensions=dimensions,
            crs=crs,
            bbox=bbox,
            confidence=best.score / 100.0,
            alternatives=alternatives
        )

    def _extract_special_tokens(self, query: str) -> Tuple[str, Dict]:
        """
        Extract special tokens (elevation, forecast, style) from query.

        Returns:
            Tuple of (remaining query, extracted values dict)
        """
        extracted = {}
        remaining = query.lower()

        # Extract forecast patterns
        for pattern, converter in self.FORECAST_PATTERNS:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match:
                extracted['forecast'] = converter(match)
                remaining = re.sub(pattern, '', remaining, flags=re.IGNORECASE)
                break

        # Extract elevation (standalone numbers that look like pressure levels)
        # Common levels: 1000, 925, 850, 700, 500, 300, 250, 200, 150, 100
        elev_match = re.search(self.ELEVATION_PATTERN, remaining, re.IGNORECASE)
        if elev_match:
            value = elev_match.group(1)
            # Only treat as elevation if it's a plausible pressure level
            if int(value) in [1013, 1000, 975, 950, 925, 900, 875, 850, 825, 800,
                              775, 750, 725, 700, 650, 600, 550, 500, 450, 400,
                              350, 300, 250, 200, 150, 100, 70, 50, 30, 20, 10]:
                extracted['elevation'] = value
                remaining = re.sub(self.ELEVATION_PATTERN, '', remaining,
                                   count=1, flags=re.IGNORECASE)

        # Extract style keywords (common style patterns)
        style_keywords = ['contour', 'filled', 'wind', 'barbs', 'arrows',
                         'streamlines', 'vectors']
        for kw in style_keywords:
            if kw in remaining:
                extracted['style_hint'] = kw
                remaining = remaining.replace(kw, '')
                break

        # Clean up remaining query
        remaining = ' '.join(remaining.split())

        return remaining, extracted

    def _resolve_style(self, style_hint: Optional[str], layer: Layer) -> str:
        """
        Resolve style name for layer.

        Args:
            style_hint: Optional style hint from query
            layer: Target layer

        Returns:
            Valid style name
        """
        if not layer.styles:
            return 'default'

        # Get available style names
        style_names = [s.name for s in layer.styles]

        # If no hint, use default or first style
        if not style_hint:
            if 'default' in style_names:
                return 'default'
            return style_names[0]

        # Try to match hint to style name
        hint_lower = style_hint.lower()
        for style in layer.styles:
            if hint_lower in style.name.lower() or hint_lower in style.title.lower():
                return style.name

        # Fallback to default
        if 'default' in style_names:
            return 'default'
        return style_names[0]

    def _resolve_dimensions(self, extracted: Dict, layer: Layer) -> Dict[str, str]:
        """
        Resolve dimension values for layer.

        Uses extracted values from query and fills in defaults.

        Args:
            extracted: Extracted dimension values from query
            layer: Target layer

        Returns:
            Dict of dimension name → value
        """
        dimensions = {}

        for dim_name, dim in layer.dimensions.items():
            value = None

            # Check if we extracted this dimension
            if dim_name == 'ELEVATION' and 'elevation' in extracted:
                value = self._validate_dimension_value(
                    extracted['elevation'], dim
                )
            elif dim_name == 'FORECAST' and 'forecast' in extracted:
                value = self._validate_dimension_value(
                    extracted['forecast'], dim
                )
            elif dim_name == 'RUN':
                # Always use latest (last value or default)
                value = dim.default or (dim.values[-1] if dim.values else None)
            elif dim_name == 'TIME':
                # Use default or latest
                value = dim.default or (dim.values[-1] if dim.values else None)

            # Use default if we didn't set a value
            if value is None and dim.default:
                value = dim.default
            elif value is None and dim.values:
                # Use first value as fallback
                value = dim.values[0]

            if value:
                dimensions[dim_name] = value

        return dimensions

    def _validate_dimension_value(self, value: str, dim: Dimension) -> Optional[str]:
        """
        Validate and possibly correct a dimension value.

        Args:
            value: Proposed value
            dim: Dimension definition

        Returns:
            Valid value or None
        """
        # Exact match
        if value in dim.values:
            return value

        # Case-insensitive match
        value_upper = value.upper()
        for v in dim.values:
            if v.upper() == value_upper:
                return v

        # For numeric values, find closest
        try:
            target = float(value)
            closest = None
            min_diff = float('inf')

            for v in dim.values:
                try:
                    diff = abs(float(v) - target)
                    if diff < min_diff:
                        min_diff = diff
                        closest = v
                except ValueError:
                    continue

            if closest and min_diff < 100:  # Reasonable threshold
                return closest
        except ValueError:
            pass

        # Return None if no valid match
        return None

    def _get_preferred_crs(self, layer: Layer) -> str:
        """Get preferred CRS for layer"""
        # Preference order
        preferred = ['CRS:84', 'EPSG:4326', 'EPSG:3857', 'EPSG:900913']

        for crs in preferred:
            if crs in layer.crs_list:
                return crs

        # Fallback to first available
        if layer.crs_list:
            return layer.crs_list[0]

        return 'CRS:84'

    def _get_bbox(self, layer: Layer, crs: str) -> Tuple[float, float, float, float]:
        """Get bounding box for layer and CRS"""
        # Try to get bbox for specific CRS
        if crs in layer.bounding_boxes:
            bb = layer.bounding_boxes[crs]
            return (bb.minx, bb.miny, bb.maxx, bb.maxy)

        # Use geographic bbox
        if layer.geographic_bbox:
            bb = layer.geographic_bbox
            return (bb.minx, bb.miny, bb.maxx, bb.maxy)

        # Default global extent
        return (-180, -90, 180, 90)

    def list_layers(self, query: Optional[str] = None, limit: int = 50) -> List[SearchResult]:
        """
        List layers, optionally filtered by query.

        Args:
            query: Optional filter query
            limit: Maximum results

        Returns:
            List of SearchResult
        """
        if query:
            return self.search_engine.search(query, limit=limit)

        # Return all layers with score 100
        from .fuzzy import SearchResult
        return [
            SearchResult(layer=layer, score=100.0, matched_on=layer.name)
            for layer in self.search_engine.get_all_layers()[:limit]
        ]
