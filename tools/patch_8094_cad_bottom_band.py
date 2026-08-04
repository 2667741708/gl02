"""Patch the independent 8094 preview HTML so its CAD canvas reaches the stage bottom.

This patch is intentionally scoped to the 8094 copied preview page.  It does not
modify the 8093 source page, the shared billboard adapter, or any service.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


MARKER = "BUG-BF3D-CAD-BOTTOM-BAND-20260804"
STYLE_ID = "bf3d-cad-bottom-band-fix-20260804"

PATCH_BLOCK = f'''<!-- {MARKER}: keep the 8094 CAD canvas flush with the stage bottom. -->
<script>
(function () {{
  if (window.__BF_CAD_BOTTOM_BAND_FIX_20260804__) return;
  window.__BF_CAD_BOTTOM_BAND_FIX_20260804__ = true;
  const applyStyle = () => {{
    const previous = document.getElementById("{STYLE_ID}");
    if (previous) previous.remove();
    const style = document.createElement("style");
    style.id = "{STYLE_ID}";
    style.textContent = `
      .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer {{
        inset: 2% 24% 0 24% !important;
        left: 24% !important;
        right: 24% !important;
        top: 2% !important;
        bottom: 0 !important;
      }}
      @media (max-width: 1366px), (max-height: 760px) {{
        .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer {{
          inset: 4% 24% 0 24% !important;
          left: 24% !important;
          right: 24% !important;
          top: 4% !important;
          bottom: 0 !important;
        }}
      }}
    `;
    document.head.appendChild(style);
  }};
  applyStyle();
  [0, 800, 2000, 4000].forEach((delay) => setTimeout(applyStyle, delay));
  window.addEventListener("resize", applyStyle);
}})();
</script>
'''


def patch_page(html: str) -> tuple[str, bool]:
    """Return patched HTML and whether a new block was inserted."""

    if MARKER in html:
        return html, False
    if "OPS-8093-CAD-GHOST-BANDS-FIX" not in html:
        raise ValueError("8094 page is missing the expected CAD ghost-band fix marker")
    if "ops-cad-ghost-bands-fix" not in html:
        raise ValueError("8094 page is missing the expected CAD ghost-band style id")
    closing_body = "</body>"
    if closing_body not in html:
        raise ValueError("8094 page has no closing body tag")
    return html.replace(closing_body, PATCH_BLOCK + closing_body, 1), True


def patch_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    patched, changed = patch_page(original)
    if not changed:
        return False
    temporary = path.with_name(path.name + ".codex-tmp")
    temporary.write_text(patched, encoding="utf-8", newline="")
    os.replace(temporary, path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()
    changed = patch_file(args.path)
    print({"changed": changed, "path": str(args.path), "marker": MARKER})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
