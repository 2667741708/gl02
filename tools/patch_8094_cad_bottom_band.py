"""Patch a V4 dashboard HTML so its CAD canvas reaches the panel bottom.

The caller controls the deployment scope.  This utility only patches the HTML
path it receives and never modifies shared assets or service configuration.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


MARKER = "BUG-BF3D-CAD-BOTTOM-BAND-20260804"
REVISION_MARKER = "BUG-BF3D-CAD-PANEL-BODY-GAP-20260804-R2"
STYLE_ID = "bf3d-cad-bottom-band-fix-20260804"

PATCH_BLOCK = f'''<!-- {MARKER} / {REVISION_MARKER}: keep the CAD canvas flush with the furnace panel bottom. -->
<script>
(function () {{
  if (window.__BF_CAD_BOTTOM_BAND_FIX_20260804_R2__) return;
  window.__BF_CAD_BOTTOM_BAND_FIX_20260804_R2__ = true;
  const applyStyle = () => {{
    const previous = document.getElementById("{STYLE_ID}");
    if (previous) previous.remove();
    const style = document.createElement("style");
    style.id = "{STYLE_ID}";
    style.textContent = `
      .overview-cad-grid.overview-three-column-v12 > .overview-furnace-panel-v12 > .panel-body {{
        padding-bottom: 0 !important;
      }}
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
    """Return R2-patched HTML and whether the page was inserted or upgraded."""

    if REVISION_MARKER in html:
        return html, False
    if "OPS-8093-CAD-GHOST-BANDS-FIX" not in html:
        raise ValueError("target page is missing the expected CAD ghost-band fix marker")
    if "ops-cad-ghost-bands-fix" not in html:
        raise ValueError("target page is missing the expected CAD ghost-band style id")
    closing_body = "</body>"
    if closing_body not in html:
        raise ValueError("target page has no closing body tag")
    if MARKER in html:
        legacy_start = html.find(f"<!-- {MARKER}:")
        if legacy_start < 0:
            raise ValueError("existing CAD bottom-band marker has no replaceable legacy block")
        legacy_end = html.find("</script>", legacy_start)
        if legacy_end < 0:
            raise ValueError("existing CAD bottom-band block has no closing script tag")
        legacy_end += len("</script>")
        return html[:legacy_start] + PATCH_BLOCK + html[legacy_end:].lstrip("\r\n"), True
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
    parser.add_argument("--scope", choices=("8093", "8094"), default="8094")
    args = parser.parse_args()
    changed = patch_file(args.path)
    print(
        {
            "changed": changed,
            "path": str(args.path),
            "scope": args.scope,
            "marker": MARKER,
            "revision_marker": REVISION_MARKER,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
