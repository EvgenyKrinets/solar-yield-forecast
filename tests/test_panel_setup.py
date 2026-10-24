"""Regression checks for the zero-touch Home Assistant dashboard setup."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "solar_yield_forecast"


def _constant(source: str, name: str):
    tree = ast.parse(source)
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    return ast.literal_eval(assignment.value)


def test_sidebar_panel_version_and_dependencies_are_consistent() -> None:
    manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
    source = (INTEGRATION / "__init__.py").read_text(encoding="utf-8")
    frontend = (INTEGRATION / "frontend" / "solar-comparison-card.js").read_text(
        encoding="utf-8"
    )

    assert {"frontend", "http", "lovelace", "panel_custom"} <= set(
        manifest["dependencies"]
    )
    assert _constant(source, "FRONTEND_VERSION") == manifest["version"]
    panel_tag = _constant(source, "PANEL_TAG")
    assert re.search(rf"const SOLAR_PANEL_TAG='{re.escape(panel_tag)}';", frontend)
    assert "await panel_custom.async_register_panel(" in source
    assert "frontend.async_remove_panel(hass, PANEL_URL)" in source


def test_dashboard_configuration_is_not_a_card_only_yaml_document() -> None:
    frontend = (INTEGRATION / "frontend" / "solar-comparison-card.js").read_text(
        encoding="utf-8"
    )
    assert "function solarManagedDashboardConfig" in frontend
    assert "views:[{" in frontend
    assert "cards:[solarPanelCardConfig(config)]" in frontend
    example = (ROOT / "dashboard.yaml").read_text(encoding="utf-8")
    assert example.startswith("title: Solar Yield Forecast\nviews:\n")
    assert "    cards:\n" in example

