import json
import os
from pathlib import Path
from typing import Optional, Dict, Any


class Preferences:
    """Manages application preferences (saved settings)."""

    PREFS_DIR = Path.home() / ".digisign"
    PREFS_FILE = PREFS_DIR / "preferences.json"

    @classmethod
    def _ensure_dir(cls) -> None:
        """Ensure preferences directory exists."""
        cls.PREFS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls) -> Dict[str, Any]:
        """Load preferences from disk."""
        cls._ensure_dir()
        if cls.PREFS_FILE.exists():
            try:
                with open(cls.PREFS_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    @classmethod
    def save(cls, prefs: Dict[str, Any]) -> None:
        """Save preferences to disk."""
        cls._ensure_dir()
        try:
            with open(cls.PREFS_FILE, "w") as f:
                json.dump(prefs, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to save preferences: {e}")

    @classmethod
    def get_signature_image_path(cls) -> Optional[str]:
        """Get the last used signature image path."""
        prefs = cls.load()
        path = prefs.get("signature_image_path")
        # Validate that file still exists
        if path and os.path.isfile(path):
            return path
        return None

    @classmethod
    def set_signature_image_path(cls, path: Optional[str]) -> None:
        """Save the signature image path."""
        prefs = cls.load()
        prefs["signature_image_path"] = path
        cls.save(prefs)

    @classmethod
    def get_selected_certificate_thumbprint(cls) -> Optional[str]:
        """Get the last selected certificate thumbprint."""
        prefs = cls.load()
        return prefs.get("selected_certificate_thumbprint")

    @classmethod
    def set_selected_certificate_thumbprint(cls, thumbprint: Optional[str]) -> None:
        """Save the selected certificate thumbprint."""
        prefs = cls.load()
        prefs["selected_certificate_thumbprint"] = thumbprint
        cls.save(prefs)

    @classmethod
    def get_selected_certificate_friendly_name(cls) -> Optional[str]:
        """Get the last selected certificate friendly name (fallback if thumbprint not found)."""
        prefs = cls.load()
        return prefs.get("selected_certificate_friendly_name")

    @classmethod
    def set_selected_certificate_friendly_name(cls, friendly_name: Optional[str]) -> None:
        """Save the selected certificate friendly name."""
        prefs = cls.load()
        prefs["selected_certificate_friendly_name"] = friendly_name
        cls.save(prefs)

    @classmethod
    def get_selected_certificate_path(cls) -> Optional[str]:
        """Get the last selected certificate file path."""
        prefs = cls.load()
        path = prefs.get("selected_certificate_path")
        if path and os.path.isfile(path):
            return path
        return None

    @classmethod
    def set_selected_certificate_path(cls, path: Optional[str]) -> None:
        """Save the selected certificate file path."""
        prefs = cls.load()
        prefs["selected_certificate_path"] = path
        cls.save(prefs)

    @classmethod
    def get_signature_declaration(cls) -> Optional[str]:
        """Get the saved signature declaration."""
        prefs = cls.load()
        return prefs.get("signature_declaration")

    @classmethod
    def set_signature_declaration(cls, declaration: Optional[str]) -> None:
        """Save the signature declaration."""
        prefs = cls.load()
        prefs["signature_declaration"] = declaration
        cls.save(prefs)

    @classmethod
    def get_canvas_width(cls) -> int:
        """Get the saved canvas width, or default to 680."""
        prefs = cls.load()
        return prefs.get("canvas_width", 680)

    @classmethod
    def set_canvas_width(cls, width: int) -> None:
        """Save the canvas width."""
        prefs = cls.load()
        prefs["canvas_width"] = width
        cls.save(prefs)

    @classmethod
    def get_canvas_height(cls) -> int:
        """Get the saved canvas height, or default to 900."""
        prefs = cls.load()
        return prefs.get("canvas_height", 900)

    @classmethod
    def set_canvas_height(cls, height: int) -> None:
        """Save the canvas height."""
        prefs = cls.load()
        prefs["canvas_height"] = height
        cls.save(prefs)
