from __future__ import annotations

from datetime import datetime
from pathlib import Path


TARGETS = [
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html"),
    Path(r"F:\炽穹·高炉炼铁大模型V3\高炉前端数据\frontend_dashboard_v3.server.html"),
    Path(r"F:\高炉炼铁项目-real-sensor-v2_V3_AUTO_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html"),
]

MARK_START = "<!-- OPS-8093-RESPONSIVE-OVERVIEW:start -->"
MARK_END = "<!-- OPS-8093-RESPONSIVE-OVERVIEW:end -->"

CSS = r"""
/* OPS-8093-RESPONSIVE-OVERVIEW: keep overview core metrics readable on common desktop sizes */
.metric-row>*{min-width:0!important}
.metric-name,.metric-unit,.metric-status,.metric-delta{white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.metric-status{justify-content:flex-start!important}
.metric-dot{flex:0 0 auto!important}
.spark{max-width:100%!important;overflow:hidden!important}
.spark>div,.spark canvas{max-width:100%!important}
@media(max-width:1366px),(max-height:760px){
  .overview-grid{grid-template-columns:minmax(360px,29%) minmax(520px,43%) minmax(330px,28%)!important;gap:6px!important}
  .panel-head{height:31px!important;flex-basis:31px!important}
  .panel-title{font-size:15px!important}
  .metric-list{gap:2px!important}
  .compact-core-metrics .metric-row{grid-template-columns:18px minmax(58px,1fr) minmax(58px,68px) 0 minmax(30px,34px) minmax(34px,42px) 0!important;gap:3px!important;padding:1px 3px!important}
  .compact-core-metrics .metric-unit,.compact-core-metrics .metric-delta{display:none!important}
  .compact-core-metrics .metric-status{font-size:10px!important}
  .compact-core-metrics .metric-name{font-size:10px!important}
  .compact-core-metrics .metric-value{font-size:10.8px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
  .compact-core-metrics .spark{width:40px!important;height:11px!important}
  .core-grouped-metrics{grid-template-rows:28px 1fr 16px!important;gap:4px!important}
  .core-metric-tabs button{height:28px!important;font-size:10px!important;padding:0 4px!important}
  .core-group-page{gap:4px!important}
  .core-metric-group{grid-template-rows:18px 1fr!important}
  .core-group-title{height:18px!important;font-size:11px!important;padding:0 5px!important}
  .core-group-rows{gap:1px!important;padding:2px!important}
  .core-group-row{grid-template-columns:18px minmax(54px,1fr) minmax(58px,70px) 0 minmax(30px,34px) minmax(32px,40px) 0!important;gap:2px!important}
  .core-group-row .metric-unit,.core-group-row .metric-delta{display:none!important}
  .core-group-row .metric-status{font-size:9.6px!important}
  .core-group-row .metric-name{font-size:9.8px!important}
  .core-group-row .metric-value{font-size:10.6px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
  .core-group-row .spark{width:38px!important;height:11px!important}
  .core-metric-note{font-size:9.5px!important;line-height:16px!important}
}
@media(max-width:1180px){
  .app{min-width:0!important}
  .main{overflow:auto!important}
  .overview-grid{width:1180px!important;grid-template-columns:350px 510px 300px!important}
  .bottom-nav{min-width:1180px!important}
}
@media(max-height:680px){
  .panel-body{padding:5px!important}
  .compact-core-metrics .metric-row,.core-group-row{padding:0 3px!important}
  .compact-core-metrics .metric-name,.core-group-row .metric-name{font-size:9.2px!important}
  .compact-core-metrics .metric-value,.core-group-row .metric-value{font-size:10px!important}
  .compact-core-metrics .metric-status,.core-group-row .metric-status{font-size:9px!important}
  .compact-core-metrics .spark,.core-group-row .spark{height:10px!important}
}
"""

BLOCK = f"""{MARK_START}
<script id="ops-responsive-overview-css">
(function(){{
  if(document.getElementById('ops-responsive-overview-style'))return;
  const el=document.createElement('style');
  el.id='ops-responsive-overview-style';
  el.textContent={CSS!r};
  document.head.appendChild(el);
}})();
</script>
{MARK_END}"""


def replace_block(text: str) -> tuple[str, bool]:
    start = text.find(MARK_START)
    if start >= 0:
        end = text.find(MARK_END, start)
        if end >= 0:
            end += len(MARK_END)
            return text[:start] + BLOCK + text[end:], True
    marker = "</body>"
    idx = text.lower().rfind(marker)
    if idx >= 0:
        return text[:idx] + BLOCK + "\n" + text[idx:], False
    return text + "\n" + BLOCK + "\n", False


def main() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in TARGETS:
        if not path.exists():
            print(f"missing\t{path}")
            continue
        text = path.read_text(encoding="utf-8")
        new_text, replaced = replace_block(text)
        if new_text == text:
            print(f"unchanged\t{path}")
            continue
        backup = path.with_name(path.name + f".bak_responsive_overview_{stamp}")
        backup.write_text(text, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
        action = "replaced" if replaced else "inserted"
        print(f"{action}\t{path}\tbackup={backup}")


if __name__ == "__main__":
    main()
