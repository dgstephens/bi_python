"""Image rendering for BinInventory CLI.

Supports three modes (set in ~/.binventory/config.json as "image_mode"):
  "none"  — no images shown (default, fastest)
  "ansi"  — colored Unicode block art via rich-pixels + Pillow
  "ascii" — monochrome ASCII art via ascii_magic + Pillow
"""

from io import BytesIO
from typing import Optional

import requests as _requests
from rich.console import Console

console = Console()

# Rendering width as a fraction of terminal width
_WIDTH_FRACTION = 0.5


def _target_width() -> int:
    return max(40, int(console.width * _WIDTH_FRACTION))


def render_image(url: str, mode: str) -> None:
    """Download *url* and render it according to *mode*. Silently skips on any error."""
    if not url or mode == "none":
        return

    img = _download(url)
    if img is None:
        return

    if mode == "ansi":
        _render_ansi(img)
    elif mode == "ascii":
        _render_ascii(img)


def _download(url: str):
    """Return a PIL Image or None on failure."""
    try:
        from PIL import Image
        resp = _requests.get(url, timeout=10)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")
    except ImportError:
        console.print("  [dim](Pillow not installed — run: pip install Pillow)[/dim]")
    except Exception:
        console.print("  [dim](Image could not be loaded)[/dim]")
    return None


def _render_ansi(img) -> None:
    """Render using rich-pixels half-block characters with ANSI color."""
    try:
        from rich_pixels import Pixels
        w = _target_width()
        # Terminal characters are ~2× taller than wide; 0.75 gives a natural aspect ratio
        aspect = img.height / img.width
        h = max(1, int(w * aspect * 0.75))
        pixels = Pixels.from_image(img, resize=(w, h))
        console.print(pixels)
    except ImportError:
        console.print("  [dim](rich-pixels not installed — run: pip install rich-pixels)[/dim]")
    except Exception as e:
        console.print(f"  [dim](ANSI render failed: {e})[/dim]")


def _render_ascii(img) -> None:
    """Render as monochrome ASCII art."""
    try:
        import ascii_magic
        w = _target_width()
        output = ascii_magic.from_pillow_image(img)
        ascii_magic.to_terminal(output, columns=w)
        print()  # newline after ascii_magic output
    except ImportError:
        console.print("  [dim](ascii_magic not installed — run: pip install ascii_magic)[/dim]")
    except Exception as e:
        console.print(f"  [dim](ASCII render failed: {e})[/dim]")
