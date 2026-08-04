/* REQ-8094-HEAT-DASHBOARD-LINK-20260726
 * Adds a real navigation entry from the 220.12 workbench to the heat-centric
 * dashboard running on the operator workstation. The target is deliberately
 * configurable through the script tag's data-url attribute so a future
 * same-origin deployment can switch to /heat-dashboard/ without rebuilding
 * the React page.
 */
(() => {
  if (window.__BF_HEAT_DASHBOARD_LINK__) return;
  window.__BF_HEAT_DASHBOARD_LINK__ = true;

  const currentScript = document.currentScript;
  const configuredUrl =
    currentScript?.dataset?.url ||
    window.__BF_HEAT_DASHBOARD_URL__ ||
    "http://127.0.0.1:8890/heat";

  let dashboardUrl;
  try {
    dashboardUrl = new URL(configuredUrl, window.location.href);
    if (!["http:", "https:"].includes(dashboardUrl.protocol)) {
      throw new Error("unsupported protocol");
    }
  } catch (_error) {
    console.error("炉次仪表盘地址配置无效");
    return;
  }

  const style = document.createElement("style");
  style.id = "req-8094-heat-dashboard-link-20260726";
  style.textContent = `
    .bottom-nav.bf-has-heat-dashboard{
      grid-template-columns:repeat(6,minmax(0,1fr))!important
    }
    .nav-btn.bf-heat-dashboard-link{
      position:relative;
      min-width:0;
      text-decoration:none;
      border-color:rgba(83,181,165,.82);
      background:linear-gradient(180deg,rgba(24,68,66,.98),rgba(8,35,39,.98));
      color:#d9f3ee
    }
    .nav-btn.bf-heat-dashboard-link:hover,
    .nav-btn.bf-heat-dashboard-link:focus-visible{
      border-color:#70d4c2;
      background:linear-gradient(180deg,#2f776f,#174b48);
      color:#fff;
      outline:none;
      box-shadow:0 0 16px rgba(83,190,173,.4),inset 0 0 14px rgba(113,217,201,.18)
    }
    .nav-btn.bf-heat-dashboard-link .nav-icon{color:#87ddce}
    .nav-btn.bf-heat-dashboard-link span:last-child{
      overflow:visible!important;
      white-space:normal!important;
      text-overflow:clip!important;
      text-align:center
    }
    .nav-btn.bf-heat-dashboard-link:after{
      content:"本机";
      position:absolute;
      top:3px;
      right:5px;
      padding:1px 4px;
      border:1px solid rgba(129,220,204,.44);
      border-radius:3px;
      color:#9be1d5;
      font:9px/1.2 SimSun,"宋体",serif
    }
    @media(max-width:600px){
      .bottom-nav.bf-has-heat-dashboard{
        gap:3px!important;
        padding:4px!important
      }
      .bottom-nav.bf-has-heat-dashboard .nav-btn{
        min-width:0!important;
        min-height:54px!important;
        padding:2px!important;
        flex-direction:column;
        gap:2px!important;
        font-size:11px!important;
        line-height:1.06
      }
      .bottom-nav.bf-has-heat-dashboard .nav-icon{font-size:19px!important}
      .bottom-nav.bf-has-heat-dashboard .nav-btn span:last-child{
        overflow:visible!important;
        white-space:normal!important;
        text-overflow:clip!important;
        text-align:center
      }
      .nav-btn.bf-heat-dashboard-link:after{display:none}
      .bottom-nav.bf-has-heat-dashboard .nav-btn.bf-heat-dashboard-link{
        position:sticky!important;
        left:0;
        z-index:4;
        box-shadow:8px 0 12px rgba(1,8,19,.82)
      }
    }
  `;
  document.head.appendChild(style);

  const attach = () => {
    const nav = document.querySelector(".bottom-nav");
    if (!nav) return;
    nav.classList.add("bf-has-heat-dashboard");
    let link = nav.querySelector("[data-bf-heat-dashboard-link]");
    if (!link) {
      link = document.createElement("a");
      link.className = "nav-btn bf-heat-dashboard-link";
      link.dataset.bfHeatDashboardLink = "true";
      link.dataset.testid = "heat-dashboard-link";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.innerHTML =
        '<span class="nav-icon" aria-hidden="true">▤</span><span>炉次分析</span>';
    }
    link.href = dashboardUrl.href;
    link.setAttribute(
      "aria-label",
      "打开本机炉次质量与133点传感器分析仪表盘"
    );
    link.title = "打开本机炉次仪表盘；若无法访问，请先启动本机8890服务";

    const overviewButton = nav.querySelector(".nav-btn:not([data-bf-heat-dashboard-link])");
    if (overviewButton?.nextSibling !== link) {
      overviewButton?.after(link);
    }
  };

  let queued = false;
  const scheduleAttach = () => {
    if (queued) return;
    queued = true;
    queueMicrotask(() => {
      queued = false;
      attach();
    });
  };

  attach();
  const root = document.getElementById("root") || document.body;
  new MutationObserver(scheduleAttach).observe(root, {
    childList: true,
    subtree: true,
  });
})();
