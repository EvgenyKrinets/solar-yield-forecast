"""Regression tests for the Home Assistant options-flow lifecycle."""

from __future__ import annotations

import ast
from pathlib import Path


CONFIG_FLOW = (
    Path(__file__).parents[1]
    / "custom_components"
    / "solar_yield_forecast"
    / "config_flow.py"
)


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    return next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name
    )


def test_options_flow_uses_config_entry_injected_by_home_assistant() -> None:
    """The flow must not expect ConfigEntry during object construction."""
    tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
    config_flow = _class(tree, "SolarYieldConfigFlow")
    options_flow = _class(tree, "SolarYieldOptionsFlow")

    factory = next(
        node
        for node in config_flow.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "async_get_options_flow"
    )
    created = next(
        node.value
        for node in ast.walk(factory)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
    )
    assert created.args == []
    assert created.keywords == []

    constructor = next(
        node
        for node in options_flow.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    assert [argument.arg for argument in constructor.args.args] == ["self"]

    init_step = next(
        node
        for node in options_flow.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_step_init"
    )
    assert any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        and node.attr == "config_entry"
        for node in ast.walk(init_step)
    )


def test_number_selectors_use_home_assistant_compatible_configuration() -> None:
    """Coordinate precision and optional units must pass HA selector validation."""
    source = CONFIG_FLOW.read_text(encoding="utf-8")

    assert '_number(-90, 90, "any", "°")' in source
    assert '_number(-180, 180, "any", "°")' in source
    assert "0.00001" not in source
    assert 'if unit is not None:' in source


def test_home_assistant_location_is_default_and_manual_fallback_remains() -> None:
    source = CONFIG_FLOW.read_text(encoding="utf-8")

    assert "selector.CountrySelector(" not in source
    assert "API_GEOCODING" not in source
    assert "_site_from_home" in source
    assert "hass.config.latitude" in source
    assert "hass.config.longitude" in source
    assert "_home_placeholders" in source
    assert "async_step_manual" in source
    assert "CONF_MANUAL_COORDINATES" in source
    assert 'step_id="user"' in source
    assert 'step_id="init"' in source
