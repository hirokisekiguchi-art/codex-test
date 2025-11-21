"""Utility helpers for working with notebook style presets.

The module intentionally keeps the API surface small so that it can be used
from a Gradio callback or any other UI layer.  There are four public helpers:

``save_preset``
    Persist a preset to the preset storage directory.
``list_presets``
    Return basic metadata about every preset for a notebook/preset type pair.
``validate_style_settings``
    Perform lightweight validation of a style settings dictionary.
``import_preset_from_file``
    Load a preset from a user provided file and validate its contents before
    saving.

The functions are completely framework agnostic.  Instead of raising Gradio
errors directly, failures are represented as human readable strings that can be
displayed in the UI's status text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Mapping, MutableMapping


PRESET_STORAGE_ROOT = Path("presets")


def _normalise_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Preset name must not be empty.")
    return cleaned


def _preset_directory(notebook_name: str, preset_type: str) -> Path:
    if not notebook_name:
        raise ValueError("notebook_name must be provided")
    if not preset_type:
        raise ValueError("preset_type must be provided")

    directory = PRESET_STORAGE_ROOT / notebook_name / preset_type
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_preset(
    preset_name: str,
    style_settings: Mapping[str, object],
    notebook_name: str,
    preset_type: str,
) -> Path:
    """Persist ``style_settings`` as a JSON file on disk.

    The file layout is compatible with :func:`import_preset_from_file` and
    stores the ``preset_name`` alongside the style settings payload.
    """

    directory = _preset_directory(notebook_name, preset_type)
    preset_name = _normalise_name(preset_name)

    payload = {"name": preset_name, "settings": dict(style_settings)}
    output_path = directory / f"{preset_name}.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output_path


def list_presets(notebook_name: str, preset_type: str) -> List[dict]:
    """Return every preset stored for the given notebook and type."""

    directory = _preset_directory(notebook_name, preset_type)
    entries: List[dict] = []
    for path in sorted(directory.glob("*.json")):
        entries.append({"name": path.stem, "path": str(path)})
    return entries


def validate_style_settings(style_settings: Mapping[str, object]) -> List[str]:
    """Validate the style settings structure.

    Returns a list of human friendly error messages.  An empty list indicates
    that the payload is valid and can be persisted.
    """

    errors: List[str] = []
    if not isinstance(style_settings, MutableMapping):
        return ["Style settings must be provided as a mapping object."]

    required_numeric_fields = {
        "font_size": (6, 72),
        "line_height": (0.8, 3.0),
    }
    allowed_themes = {"light", "dark", "system"}

    for key in ("name", "settings"):
        if key in style_settings:
            errors.append(
                f"Style settings should not contain the reserved key '{key}'."
            )

    for field, (minimum, maximum) in required_numeric_fields.items():
        value = style_settings.get(field)
        if value is None:
            errors.append(f"Missing required style field '{field}'.")
            continue
        if not isinstance(value, (int, float)):
            errors.append(f"'{field}' must be a number.")
            continue
        if not (minimum <= float(value) <= maximum):
            errors.append(
                f"'{field}' must be between {minimum:g} and {maximum:g}. (got {value})"
            )

    theme = style_settings.get("theme")
    if theme is None:
        errors.append("Missing required style field 'theme'.")
    elif not isinstance(theme, str):
        errors.append("'theme' must be a string.")
    else:
        theme_normalised = theme.lower().strip()
        if theme_normalised not in allowed_themes:
            formatted = ", ".join(sorted(allowed_themes))
            errors.append(f"'theme' must be one of: {formatted}.")

    accent = style_settings.get("accent_color")
    if accent is not None:
        if not isinstance(accent, str):
            errors.append("'accent_color' must be provided as a hex string.")
        elif not accent.startswith("#") or len(accent) not in (4, 7):
            errors.append(
                "'accent_color' must be a valid hex colour such as '#0af' or '#12ab45'."
            )

    return errors


def _load_json_payload(file: object) -> Mapping[str, object]:
    if hasattr(file, "read"):
        file.seek(0)
        payload_text = file.read()
        if isinstance(payload_text, bytes):
            payload_text = payload_text.decode("utf-8")
    else:
        payload_text = Path(file).read_text(encoding="utf-8")

    return json.loads(payload_text)


def import_preset_from_file(
    file: object,
    notebook_name: str,
    preset_type: str,
):
    """Import a preset JSON file and return UI friendly status information.

    The return payload is a dictionary with ``status``, ``message`` and
    ``presets`` keys so callers can display the outcome and immediately refresh
    their preset list.
    """

    try:
        payload = _load_json_payload(file)
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "Could not read the provided file.",
            "presets": None,
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "message": f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno}).",
            "presets": None,
        }

    missing_keys = [key for key in ("name", "settings") if key not in payload]
    if missing_keys:
        missing = ", ".join(missing_keys)
        return {
            "status": "error",
            "message": f"Preset file is missing required keys: {missing}.",
            "presets": None,
        }

    preset_name = payload["name"]
    style_settings = payload["settings"]
    validation_errors = validate_style_settings(style_settings)
    if validation_errors:
        joined_errors = "\n".join(validation_errors)
        return {
            "status": "error",
            "message": f"The preset could not be imported:\n{joined_errors}",
            "presets": None,
        }

    save_preset(preset_name, style_settings, notebook_name, preset_type)
    presets = list_presets(notebook_name, preset_type)
    return {
        "status": "success",
        "message": f"Imported preset '{preset_name}'.",
        "presets": presets,
    }

