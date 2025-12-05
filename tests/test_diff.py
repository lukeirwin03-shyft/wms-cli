#!/usr/bin/env python3
"""Tests for WMS capabilities diff engine."""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diff import (
    compare_capabilities, compare_single_layer,
    CapabilitiesDiff, LayerDiff, ChangeType,
    _compare_layer, _compare_dimensions, _compare_styles
)
from wms_parser import (
    WMSCapabilities, Layer, Dimension, Style, BoundingBox
)


def make_dimension(name: str, values: list = None, default: str = None, units: str = "ISO8601") -> Dimension:
    """Helper to create a dimension for testing."""
    return Dimension(
        name=name,
        units=units,
        default=default,
        values=values or []
    )


def make_style(name: str, title: str = None) -> Style:
    """Helper to create a style for testing."""
    return Style(
        name=name,
        title=title or name
    )


def make_layer(name: str, **kwargs) -> Layer:
    """Helper to create a layer for testing."""
    layer = Layer(
        name=name,
        title=kwargs.get('title', name),
        queryable=kwargs.get('queryable', True),
        dimensions=kwargs.get('dimensions', {}),
        styles=kwargs.get('styles', []),
        crs_list=kwargs.get('crs_list', ['EPSG:4326']),
    )
    return layer


def make_caps(layers: list, **kwargs) -> WMSCapabilities:
    """Helper to create capabilities for testing."""
    root = Layer(name=None, title="Root")
    root.children = layers
    for layer in layers:
        layer.parent = root
    
    return WMSCapabilities(
        version="1.3.0",
        service_title=kwargs.get('title', "Test Service"),
        service_abstract=kwargs.get('abstract', None),
        root_layer=root,
        get_map_formats=kwargs.get('formats', ['image/png'])
    )


class TestCompareCapabilities:
    """Tests for compare_capabilities function."""
    
    def test_identical_capabilities(self):
        """Identical capabilities should produce empty diff."""
        layer1 = make_layer("Layer1")
        layer2 = make_layer("Layer2")
        
        caps_a = make_caps([layer1, layer2])
        caps_b = make_caps([make_layer("Layer1"), make_layer("Layer2")])
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert not diff.has_changes
        assert len(diff.layers_added) == 0
        assert len(diff.layers_removed) == 0
        assert len(diff.layers_modified) == 0
        assert diff.layers_unchanged == 2
    
    def test_added_layer(self):
        """Should detect added layers."""
        caps_a = make_caps([make_layer("Layer1")])
        caps_b = make_caps([make_layer("Layer1"), make_layer("Layer2")])
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert diff.layers_added == ["Layer2"]
        assert len(diff.layers_removed) == 0
        assert diff.has_changes
    
    def test_removed_layer(self):
        """Should detect removed layers."""
        caps_a = make_caps([make_layer("Layer1"), make_layer("Layer2")])
        caps_b = make_caps([make_layer("Layer1")])
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert len(diff.layers_added) == 0
        assert diff.layers_removed == ["Layer2"]
        assert diff.has_changes
    
    def test_multiple_changes(self):
        """Should detect multiple types of changes."""
        caps_a = make_caps([
            make_layer("Layer1"),
            make_layer("Layer2"),
            make_layer("Layer3"),
        ])
        caps_b = make_caps([
            make_layer("Layer1"),  # unchanged
            # Layer2 removed
            make_layer("Layer4"),  # added
        ])
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert diff.layers_added == ["Layer4"]
        assert diff.layers_removed == ["Layer2", "Layer3"]
        assert diff.layers_unchanged == 1


class TestCompareLayer:
    """Tests for layer comparison."""
    
    def test_modified_layer_title(self):
        """Should detect title changes."""
        layer_a = make_layer("Layer1", title="Old Title")
        layer_b = make_layer("Layer1", title="New Title")
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert len(diff.changes) == 1
        assert diff.changes[0].property_name == "title"
    
    def test_modified_layer_dimension(self):
        """Should detect dimension changes."""
        dim_a = make_dimension("TIME", values=["t1", "t2"])
        dim_b = make_dimension("TIME", values=["t1", "t2", "t3"])
        
        layer_a = make_layer("Layer1", dimensions={"TIME": dim_a})
        layer_b = make_layer("Layer1", dimensions={"TIME": dim_b})
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert len(diff.dimensions) == 1
        assert diff.dimensions[0].name == "TIME"
        assert diff.dimensions[0].values_added == ["t3"]
    
    def test_added_dimension(self):
        """Should detect new dimensions."""
        dim = make_dimension("ELEVATION", values=["850", "500"])
        
        layer_a = make_layer("Layer1", dimensions={})
        layer_b = make_layer("Layer1", dimensions={"ELEVATION": dim})
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert len(diff.dimensions) == 1
        assert diff.dimensions[0].status == ChangeType.ADDED
    
    def test_removed_dimension(self):
        """Should detect removed dimensions."""
        dim = make_dimension("ELEVATION", values=["850", "500"])
        
        layer_a = make_layer("Layer1", dimensions={"ELEVATION": dim})
        layer_b = make_layer("Layer1", dimensions={})
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert len(diff.dimensions) == 1
        assert diff.dimensions[0].status == ChangeType.REMOVED
    
    def test_modified_layer_style(self):
        """Should detect style changes."""
        style_a = [make_style("default", "Default Style")]
        style_b = [
            make_style("default", "Default Style"),
            make_style("rainbow", "Rainbow Style")
        ]
        
        layer_a = make_layer("Layer1", styles=style_a)
        layer_b = make_layer("Layer1", styles=style_b)
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert any(s.name == "rainbow" and s.status == ChangeType.ADDED 
                   for s in diff.styles)
    
    def test_crs_changes(self):
        """Should detect CRS changes."""
        layer_a = make_layer("Layer1", crs_list=["EPSG:4326", "EPSG:3857"])
        layer_b = make_layer("Layer1", crs_list=["EPSG:4326", "EPSG:900913"])
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert "EPSG:900913" in diff.crs_added
        assert "EPSG:3857" in diff.crs_removed
    
    def test_unchanged_layer(self):
        """Identical layers should be unchanged."""
        layer_a = make_layer("Layer1", title="Same", crs_list=["EPSG:4326"])
        layer_b = make_layer("Layer1", title="Same", crs_list=["EPSG:4326"])
        
        diff = _compare_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.UNCHANGED


class TestCompareDimensions:
    """Tests for dimension comparison."""
    
    def test_dimension_values_added(self):
        """Should detect added dimension values."""
        dim_a = make_dimension("TIME", values=["t1", "t2"])
        dim_b = make_dimension("TIME", values=["t1", "t2", "t3", "t4"])
        
        diffs = _compare_dimensions({"TIME": dim_a}, {"TIME": dim_b})
        
        assert len(diffs) == 1
        assert diffs[0].status == ChangeType.MODIFIED
        assert diffs[0].values_added == ["t3", "t4"]
    
    def test_dimension_values_removed(self):
        """Should detect removed dimension values."""
        dim_a = make_dimension("TIME", values=["t1", "t2", "t3"])
        dim_b = make_dimension("TIME", values=["t1"])
        
        diffs = _compare_dimensions({"TIME": dim_a}, {"TIME": dim_b})
        
        assert len(diffs) == 1
        assert diffs[0].values_removed == ["t2", "t3"]
    
    def test_dimension_default_changed(self):
        """Should detect changed defaults."""
        dim_a = make_dimension("TIME", values=["t1", "t2"], default="t1")
        dim_b = make_dimension("TIME", values=["t1", "t2"], default="t2")
        
        diffs = _compare_dimensions({"TIME": dim_a}, {"TIME": dim_b})
        
        assert len(diffs) == 1
        assert diffs[0].default_changed == ("t1", "t2")


class TestCompareStyles:
    """Tests for style comparison."""
    
    def test_style_added(self):
        """Should detect added styles."""
        styles_a = [make_style("default")]
        styles_b = [make_style("default"), make_style("rainbow")]
        
        diffs = _compare_styles(styles_a, styles_b)
        
        assert len(diffs) == 1
        assert diffs[0].name == "rainbow"
        assert diffs[0].status == ChangeType.ADDED
    
    def test_style_removed(self):
        """Should detect removed styles."""
        styles_a = [make_style("default"), make_style("old_style")]
        styles_b = [make_style("default")]
        
        diffs = _compare_styles(styles_a, styles_b)
        
        assert len(diffs) == 1
        assert diffs[0].name == "old_style"
        assert diffs[0].status == ChangeType.REMOVED
    
    def test_style_title_changed(self):
        """Should detect style title changes."""
        styles_a = [make_style("default", "Old Title")]
        styles_b = [make_style("default", "New Title")]
        
        diffs = _compare_styles(styles_a, styles_b)
        
        assert len(diffs) == 1
        assert diffs[0].status == ChangeType.MODIFIED


class TestServiceComparison:
    """Tests for service-level comparison."""
    
    def test_service_title_change(self):
        """Should detect service metadata changes."""
        caps_a = make_caps([], title="Service v1")
        caps_b = make_caps([], title="Service v2")
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert len(diff.service.changes) == 1
        assert diff.service.changes[0].property_name == "service_title"
        assert diff.has_changes
    
    def test_format_changes(self):
        """Should detect format changes."""
        caps_a = make_caps([], formats=['image/png', 'image/jpeg'])
        caps_b = make_caps([], formats=['image/png', 'image/webp'])
        
        diff = compare_capabilities(caps_a, caps_b)
        
        assert 'image/webp' in diff.service.formats_added
        assert 'image/jpeg' in diff.service.formats_removed


class TestCompareSingleLayer:
    """Tests for compare_single_layer function."""
    
    def test_layer_added(self):
        """Should handle layer that only exists in second source."""
        layer_b = make_layer("NewLayer")
        
        diff = compare_single_layer(None, layer_b)
        
        assert diff.status == ChangeType.ADDED
        assert diff.name == "NewLayer"
    
    def test_layer_removed(self):
        """Should handle layer that only exists in first source."""
        layer_a = make_layer("OldLayer")
        
        diff = compare_single_layer(layer_a, None)
        
        assert diff.status == ChangeType.REMOVED
        assert diff.name == "OldLayer"
    
    def test_both_none_raises(self):
        """Should raise error if both layers are None."""
        with pytest.raises(ValueError):
            compare_single_layer(None, None)
    
    def test_layer_comparison(self):
        """Should compare two existing layers."""
        layer_a = make_layer("Layer1", title="Old")
        layer_b = make_layer("Layer1", title="New")
        
        diff = compare_single_layer(layer_a, layer_b)
        
        assert diff.status == ChangeType.MODIFIED
        assert diff.name == "Layer1"


class TestCapabilitiesDiffProperties:
    """Tests for CapabilitiesDiff properties."""
    
    def test_total_changes(self):
        """Should calculate total changes correctly."""
        diff = CapabilitiesDiff(
            source_a="A", source_b="B",
            layers_added=["L1", "L2"],
            layers_removed=["L3"],
            layers_modified=[LayerDiff(name="L4", status=ChangeType.MODIFIED)]
        )
        
        assert diff.total_changes == 4
    
    def test_has_changes_with_layers(self):
        """Should detect layer changes."""
        diff = CapabilitiesDiff(
            source_a="A", source_b="B",
            layers_added=["L1"]
        )
        
        assert diff.has_changes
    
    def test_has_changes_with_service(self):
        """Should detect service-only changes."""
        from diff import ServiceDiff, PropertyChange
        
        diff = CapabilitiesDiff(
            source_a="A", source_b="B",
            service=ServiceDiff(
                changes=[PropertyChange("title", "old", "new")]
            )
        )
        
        assert diff.has_changes
    
    def test_no_changes(self):
        """Should detect no changes."""
        diff = CapabilitiesDiff(
            source_a="A", source_b="B",
            layers_unchanged=10
        )
        
        assert not diff.has_changes


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

