from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path


TARGET = Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html")

CSS = r"""
.core-grouped-metrics{height:100%;display:grid!important;grid-template-rows:30px 1fr 18px!important;gap:5px!important;min-height:0}
.core-metric-tabs{display:grid;grid-template-columns:1fr 1fr;gap:5px;min-width:0}
.core-metric-tabs button{height:30px;border:1px solid rgba(45,126,199,.72);border-radius:5px;background:rgba(5,28,56,.86);color:#b9cde3;font-size:11px;font-weight:900;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.core-metric-tabs button.active{color:#fff;border-color:#25a6ff;background:linear-gradient(180deg,#1056ae,#082d72);box-shadow:0 0 12px rgba(37,146,255,.34),inset 0 0 12px rgba(76,168,255,.18)}
.core-group-page{min-height:0;display:grid;gap:5px;overflow:hidden}
.core-metric-group{min-height:0;display:grid;grid-template-rows:20px 1fr;border:1px solid rgba(34,105,171,.5);border-radius:5px;background:rgba(4,23,47,.45);overflow:hidden}
.core-group-title{height:20px;display:flex;align-items:center;justify-content:space-between;padding:0 7px;color:#edf7ff;font-size:12px;font-weight:900;background:linear-gradient(90deg,rgba(10,55,100,.88),rgba(4,25,52,.62));border-bottom:1px solid rgba(35,112,180,.38)}
.core-group-title b{font-family:Consolas,"Courier New",monospace;color:#8fcfff;font-size:11px}
.core-group-rows{min-height:0;display:grid;gap:2px;padding:3px}
.core-group-row{grid-template-columns:20px minmax(56px,1fr) minmax(66px,80px) 28px 40px 42px 50px!important;gap:2px!important;min-height:0!important;padding:1px 3px!important}
.core-group-row .metric-name{font-size:10.8px!important}
.core-group-row .metric-value{font-size:11.4px!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.core-group-row .metric-unit,.core-group-row .metric-status,.core-group-row .metric-delta{font-size:9.3px!important}
.core-group-row .spark{width:42px!important;height:12px!important}
.core-metric-note{font-size:10.5px!important;line-height:18px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
"""

JS = r"""
const CORE_METRIC_GROUPS=[{title:'煤气顶压',items:[{id:'P_top'},{id:'P_top_gas_A',name:'顶压A',unit:'kPa'},{id:'P_top_gas_B',name:'顶压B',unit:'kPa'},{id:'P_top_gas_C',name:'顶压C',unit:'kPa'},{id:'P_top_gas_D',name:'顶压D',unit:'kPa'}]},{title:'热制度',items:[{id:'GasUtil'},{id:'TFT'},{id:'T_blast'},{id:'T_top_A'},{id:'T_top_B'},{id:'T_top_C'},{id:'T_top_D'}]},{title:'送风供氧',items:[{id:'Q_blast'},{id:'P_blast_cold'},{id:'P_blast'},{id:'O2_rate'},{id:'Q_O2'}]},{title:'压差透气',items:[{id:'PI'},{id:'DP_upper'},{id:'DP_lower'},{id:'DP_total'}]},{title:'料线',items:[{id:'L'},{id:'L_south'},{id:'L_north'}]},{title:'喷煤',items:[{id:'PCI_rate'},{id:'PCI_set'}]},{title:'出铁口温度',items:[{id:'T_taphole_1'},{id:'T_taphole_2'}]}];
const CORE_METRIC_PAGES=[CORE_METRIC_GROUPS.slice(0,4),CORE_METRIC_GROUPS.slice(4)];
function coreMetricRowMeta(item){const r=ROW_BY_ID[item.id]||{name:item.id,unit:item.unit||''};return{name:item.name||r.name||item.id,unit:item.unit||r.unit||''}}
function CoreMetricRow({buf,item,index}){const meta=coreMetricRowMeta(item),v=latest(buf,item.id),z=rollingIqrDeviation(buf,item.id,v),st=iqrStatus(z),digits=item.id==='PI'||item.id==='L'||item.id==='L_south'||item.id==='L_north'?2:1;return <div className="metric-row core-group-row" key={item.id}><div className="metric-no mono">{String(index+1).padStart(2,'0')}</div><div className="metric-name">{meta.name}</div><div className="metric-value">{displayNum(item.id,v,digits)}</div><div className="metric-unit">{displayUnit(item.id,meta.unit)}</div><div className="metric-status"><span className={`metric-dot ${st.tone}`}></span>{st.label}</div><ChartBox option={sparkOption(buf,item.id)} className="spark"/><div className={`metric-delta ${st.tone==='bad'?'text-bad':st.tone==='warn'?'text-warn':''}`}>偏离 {z!==null&&z>=0?'+':''}{fmtNum(z,2)}</div></div>}
function MetricRows({buf,diagnosis}){const[page,setPage]=useState(0),groups=CORE_METRIC_PAGES[page]||CORE_METRIC_PAGES[0];let offset=page===0?0:CORE_METRIC_PAGES[0].reduce((n,g)=>n+g.items.length,0);return <div className="metric-list core-grouped-metrics"><div className="core-metric-tabs"><button className={page===0?'active':''} onClick={()=>setPage(0)}>顶压 / 热制度 / 送风 / 压差</button><button className={page===1?'active':''} onClick={()=>setPage(1)}>料线 / 喷煤 / 出铁口</button></div><div className="core-group-page">{groups.map(group=>{const start=offset;offset+=group.items.length;return <div className="core-metric-group" key={group.title}><div className="core-group-title"><span>{group.title}</span><b>{group.items.length}</b></div><div className="core-group-rows">{group.items.map((item,i)=><CoreMetricRow buf={buf} diagnosis={diagnosis} item={item} index={start+i} key={item.id}/>)}</div></div>})}</div><div className="muted core-metric-note">核心28变量按7类工艺分组；切换页只改变展示，不改变诊断和趋势数据来源。</div></div>}
"""

FINAL_OVERRIDE_MARK = "/* OPS-8093-CORE-GROUPS-FINAL-SAFE */"
SPARK_OVERRIDE_MARK = "/* OPS-8093-CORE-SPARK-30MIN-THIN-V2 */"

FINAL_OVERRIDE = rf"""
{FINAL_OVERRIDE_MARK}
CoreMetricRow=function({{buf,item,index}}){{const meta=coreMetricRowMeta(item),v=latest(buf,item.id),z=rollingIqrDeviation(buf,item.id,v),st=iqrStatus(z),digits=item.id==='PI'||item.id==='L'||item.id==='L_south'||item.id==='L_north'?2:1;return <div className="metric-row core-group-row" key={{item.id}}><div className="metric-no mono">{{String(index+1).padStart(2,'0')}}</div><div className="metric-name">{{meta.name}}</div><div className="metric-value">{{displayNum(item.id,v,digits)}}</div><div className="metric-unit">{{displayUnit(item.id,meta.unit)}}</div><div className="metric-status"><span className={{`metric-dot ${{st.tone}}`}}></span>{{st.label}}</div><ChartBox option={{sparkOption(buf,item.id)}} className="spark"/><div className={{`metric-delta ${{st.tone==='bad'?'text-bad':st.tone==='warn'?'text-warn':''}}`}}>偏离 {{z!==null&&z>=0?'+':''}}{{fmtNum(z,2)}}</div></div>}}
MetricRows=function({{buf,diagnosis}}){{const[page,setPage]=useState(0),groups=CORE_METRIC_PAGES[page]||CORE_METRIC_PAGES[0];let offset=page===0?0:CORE_METRIC_PAGES[0].reduce((n,g)=>n+g.items.length,0);return <div className="metric-list core-grouped-metrics"><div className="core-metric-tabs"><button className={{page===0?'active':''}} onClick={{()=>setPage(0)}}>顶压 / 热制度 / 送风 / 压差</button><button className={{page===1?'active':''}} onClick={{()=>setPage(1)}}>料线 / 喷煤 / 出铁口</button></div><div className="core-group-page">{{groups.map(group=>{{const start=offset;offset+=group.items.length;return <div className="core-metric-group" key={{group.title}}><div className="core-group-title"><span>{{group.title}}</span><b>{{group.items.length}}</b></div><div className="core-group-rows">{{group.items.map((item,i)=><CoreMetricRow buf={{buf}} item={{item}} index={{start+i}} key={{item.id}}/>)}}</div></div>}})}}</div><div className="muted core-metric-note">核心28变量按7类工艺分组；切换页只改变展示，不改变诊断和趋势数据来源。</div></div>}}
"""

SPARK_OVERRIDE = rf"""
{SPARK_OVERRIDE_MARK}
var CORE_SPARK_MINUTES=30;
var CORE_SPARK_LINE_WIDTH=1.45;
sparkOption=function(b,id){{const o=lineOption(b,[id],CORE_SPARK_MINUTES,'',{{width:CORE_SPARK_LINE_WIDTH}});return o?{{...o,grid:{{left:0,right:0,top:2,bottom:2}},legend:{{show:false}},xAxis:{{...o.xAxis,show:false}},yAxis:[{{...o.yAxis[0],show:false}}],tooltip:{{show:false}}}}:null}}
;(function(){{if(document.getElementById('ops-core-spark-30min-style'))return;const el=document.createElement('style');el.id='ops-core-spark-30min-style';el.textContent='.core-group-row{{grid-template-columns:20px minmax(52px,1fr) minmax(62px,78px) 24px 36px 56px 44px!important}}.core-group-row .spark{{width:56px!important;height:12px!important}}@media(max-width:1366px),(max-height:760px){{.core-group-row{{grid-template-columns:18px minmax(50px,1fr) minmax(56px,68px) 0 minmax(30px,34px) 48px 0!important}}.core-group-row .spark{{width:48px!important;height:11px!important}}}}@media(max-height:680px){{.core-group-row{{grid-template-columns:18px minmax(48px,1fr) minmax(54px,66px) 0 minmax(28px,32px) 44px 0!important}}.core-group-row .spark{{width:44px!important;height:10px!important}}}}';document.head.appendChild(el)}})();
;(function(){{const apply=()=>{{const old=document.getElementById('ops-core-spark-30min-style-v2');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-spark-30min-style-v2';el.textContent='.overview-cad-grid .core-group-row{{grid-template-columns:20px minmax(50px,1fr) minmax(60px,76px) 22px 34px 60px 42px!important}}.overview-cad-grid .core-group-row .spark{{width:60px!important;min-width:60px!important;height:12px!important}}@media(max-width:1366px),(max-height:760px){{.overview-cad-grid .core-group-row{{grid-template-columns:18px minmax(48px,1fr) minmax(54px,66px) 0 minmax(28px,32px) 52px 0!important}}.overview-cad-grid .core-group-row .spark{{width:52px!important;min-width:52px!important;height:11px!important}}}}@media(max-height:680px){{.overview-cad-grid .core-group-row{{grid-template-columns:18px minmax(46px,1fr) minmax(52px,64px) 0 minmax(26px,30px) 48px 0!important}}.overview-cad-grid .core-group-row .spark{{width:48px!important;min-width:48px!important;height:10px!important}}}}';document.head.appendChild(el)}};apply();setTimeout(apply,0);setTimeout(apply,500)}})();
"""

FURNACE_LAYER_MARK = "/* OPS-8093-FURNACE-LAYER-CALLOUTS */"
DENSITY_SPARK_MARK = "/* OPS-8093-CORE-DENSITY-SPARK-V3 */"
DIAGNOSIS_COLOR_MARK = "/* OPS-8093-DIAGNOSIS-NORMAL-GREEN */"
FURNACE_POINT_ANCHOR_MARK = "/* OPS-8093-FURNACE-POINT-ANCHORS-V2 */"
FURNACE_FOLLOW_ANCHOR_MARK = "/* OPS-8093-FURNACE-FOLLOW-ANCHORS-V3 */"
CAD_TOOLTIP_FALLBACK_MARK = "/* OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK */"
CORE_TWO_COLUMN_MARK = "/* OPS-8093-CORE-TWO-COLUMN-V4 */"
CORE_TWO_COLUMN_BALANCED_MARK = "/* OPS-8093-CORE-TWO-COLUMN-V4-BALANCED-14-14 */"
CORE_TWO_COLUMN_LARGE_MARK = "/* OPS-8093-CORE-TWO-COLUMN-V5-FILL-LARGE */"
CORE_TWO_COLUMN_LARGE_REQUIRED = ".overview-cad-grid .core-two-column-v4 .core-group-row .metric-status{display:none!important}"
CORE_VALUE_ALIGN_MARK = "/* OPS-8093-CORE-VALUE-ALIGN-V6 */"
CORE_VALUE_ALIGN_REQUIRED = 'font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important'
CORE_TWO_PAGE_V7_MARK = "/* OPS-8093-CORE-TWO-PAGE-V7 */"
CORE_TWO_PAGE_V7_REQUIRED = "MetricRows=function BFCoreMetricRowsV7"
CORE_TWO_PAGE_V7_SPECIFICITY_MARK = "/* OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX */"
CORE_TWO_PAGE_V7_SPECIFICITY_REQUIRED = ".core-metric-tabs-v7 button{gap:4px!important;padding:0 6px!important;font-size:11.2px!important}"
CORE_SPARK_GAP_V10_MARK = "/* OPS-8093-CORE-SPARK-GAP-V10 */"
CORE_SPARK_GAP_V10_REQUIRED = "ops-core-spark-gap-v10"
OVERVIEW_LARGE_TREND_V8_MARK = "/* OPS-8093-OVERVIEW-LARGE-TREND-V8 */"
# Keep the deployment patch compatible with the current v14 header-action button.
# The accessible label is the stable contract shared by both supported layouts.
OVERVIEW_LARGE_TREND_V8_REQUIRED = 'aria-label="进入趋势分析"'
OVERVIEW_DECISION_HUB_V11_MARK = "/* OPS-8093-OVERVIEW-DECISION-HUB-V11 */"
OVERVIEW_DECISION_HUB_V11_REQUIRED = "OverviewRight=function BFOverviewRightDecisionHubV11"
OVERVIEW_THREE_COLUMN_V12_MARK = "/* OPS-8093-OVERVIEW-THREE-COLUMN-V12 */"
OVERVIEW_THREE_COLUMN_V12_REQUIRED = "OverviewRight=function BFOverviewRightThreeColumnV12"
AUTO_MONITOR_DOCK_MD_V9_MARK = "/* OPS-8093-AUTO-MONITOR-DOCK-MD-V9 */"
AUTO_MONITOR_DOCK_MD_V9_REQUIRED = "window.__BF_AUTO_MONITOR_DOCK_MD_V9__=true"
CAD_GHOST_BANDS_MARK = "/* OPS-8093-CAD-GHOST-BANDS-FIX */"
OPTIMIZATION_NOTE_REMOVED_MARK = "/* OPS-8093-OPTIMIZATION-NOTE-REMOVED */"

FURNACE_LAYER_OVERRIDE = r"""
/* OPS-8093-FURNACE-LAYER-CALLOUTS */
const FURNACE_LAYER_GROUPS=[{title:'煤气顶压',pos:'pos-left-top',items:[{id:'P_top',name:'综合顶压'},{id:'P_top_gas_A',name:'上升管压A',unit:'kPa'},{id:'P_top_gas_B',name:'上升管压B',unit:'kPa'},{id:'P_top_gas_C',name:'上升管压C',unit:'kPa'},{id:'P_top_gas_D',name:'上升管压D',unit:'kPa'}]},{title:'压差透气',pos:'pos-left-mid',items:[{id:'PI',name:'透气性指数'},{id:'DP_upper',name:'上部压差'},{id:'DP_lower',name:'下部压差'},{id:'DP_total',name:'总压差'}]},{title:'喷煤',pos:'pos-left-low',items:[{id:'PCI_rate',name:'喷煤率'},{id:'PCI_set',name:'喷煤设定'}]},{title:'料线',pos:'pos-right-top',items:[{id:'L',name:'雷达探尺'},{id:'L_south',name:'南尺'},{id:'L_north',name:'北尺'}]},{title:'热制度',pos:'pos-right-mid',items:[{id:'GasUtil',name:'煤气利用率'},{id:'TFT',name:'理论燃烧温度'},{id:'T_blast',name:'热风温度'},{id:'T_top_A',name:'顶温A'},{id:'T_top_B',name:'顶温B'},{id:'T_top_C',name:'顶温C'},{id:'T_top_D',name:'顶温D'}]},{title:'送风供氧',pos:'pos-right-low',items:[{id:'Q_blast',name:'冷风流量'},{id:'P_blast_cold',name:'冷风压力'},{id:'P_blast',name:'热风压力'},{id:'O2_rate',name:'富氧率'},{id:'Q_O2',name:'富氧流量'}]},{title:'出铁口温度',pos:'pos-right-bottom',items:[{id:'T_taphole_1',name:'1#铁口温度参考'},{id:'T_taphole_2',name:'2#铁口温度参考'}]}];
function furnaceLayerMeta(item){const r=ROW_BY_ID[item.id]||{name:item.id,unit:item.unit||''};return{name:item.name||r.name||item.id,unit:item.unit||r.unit||''}}
function furnaceLayerDigits(id){return id==='PI'||id==='L'||id==='L_south'||id==='L_north'?2:1}
function FurnaceLayerCard({group,buf}){return <div className={`furnace-layer-card ${group.pos}`} data-layer={group.title}><div className="furnace-layer-head"><span>{group.title}</span></div><div className="furnace-layer-rows">{group.items.map(item=>{const meta=furnaceLayerMeta(item),v=latest(buf,item.id),unit=displayUnit(item.id,meta.unit),digits=furnaceLayerDigits(item.id),value=displayNum(item.id,v,digits);return <div className="furnace-layer-row" key={item.id} title={`${meta.name} ${value}${unit}`}><span className="furnace-layer-name">{meta.name}</span><span className="furnace-layer-value">{value}</span><span className="furnace-layer-unit">{unit}</span></div>})}</div></div>}
function FurnaceLayerCallouts({buf}){return <div className="furnace-layer-callouts" aria-label="核心变量工艺分层">{FURNACE_LAYER_GROUPS.map(group=><FurnaceLayerCard key={group.title} group={group} buf={buf}/>)}</div>}
FurnaceGraphic=function({diagnosis,buf}){return <div className="furnace-wrap is-3d centered-cad furnace-layer-wrap"><div className="furnace-stage-3d cad-stage layered-cad-stage"><CadFurnaceViewer buf={buf}/><FurnaceLayerCallouts buf={buf}/><div className="furnace-3d-scene legacy-furnace-scene" style={{display:'none'}}><ParticleFurnaceCanvas diagnosis={diagnosis} buf={buf}/></div></div></div>};
;(function(){if(document.getElementById('ops-furnace-layer-callouts-style'))return;const el=document.createElement('style');el.id='ops-furnace-layer-callouts-style';el.textContent=`
.furnace-layer-wrap{height:100%!important}
.layered-cad-stage{position:relative!important;overflow:hidden!important;background:radial-gradient(circle at 50% 45%,rgba(64,108,92,.24),transparent 58%),linear-gradient(180deg,rgba(10,26,28,.72),rgba(4,13,20,.94))!important;border-color:rgba(74,135,118,.34)!important}
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{left:28%!important;right:28%!important;top:1%!important;bottom:5%!important;inset:1% 28% 5% 28%!important;z-index:2!important;border-radius:4px!important;background:radial-gradient(circle at 50% 38%,rgba(71,130,113,.22),transparent 58%),linear-gradient(180deg,rgba(2,12,17,.2),rgba(0,0,0,.2))!important}
.furnace-layer-callouts{position:absolute;inset:0;z-index:12;pointer-events:none;font-family:SimSun,"宋体",serif}
.furnace-layer-card{position:absolute;width:clamp(122px,24%,156px);padding:5px 6px 5px 7px;border-left:2px solid #d9bd4b;background:linear-gradient(180deg,rgba(12,28,25,.94),rgba(4,16,17,.92));box-shadow:0 8px 18px rgba(0,0,0,.34),inset 0 0 16px rgba(95,146,122,.1);color:#e8fff1;pointer-events:none}
.furnace-layer-card:after{content:"";position:absolute;top:50%;width:44px;height:1px;background:linear-gradient(90deg,rgba(219,190,74,.9),rgba(219,190,74,.1))}
.furnace-layer-card[class*="pos-left"]:after{left:100%}
.furnace-layer-card[class*="pos-right"]:after{right:100%;transform:scaleX(-1)}
.furnace-layer-head{height:18px;display:flex;align-items:center;justify-content:space-between;gap:6px;color:#ffd65b;font-size:13px;font-weight:900;line-height:1}
.furnace-layer-head b{color:#b9ecff;font-size:10px;font-family:Consolas,"Courier New",monospace}
.furnace-layer-rows{display:grid;gap:1px}
.furnace-layer-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(28px,42px) minmax(18px,36px);align-items:center;gap:3px;min-height:13px;font-size:10.5px;line-height:1.08;color:#d8f2e3}
.furnace-layer-name,.furnace-layer-value,.furnace-layer-unit{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.furnace-layer-name{font-weight:800}
.furnace-layer-value{font-family:Consolas,"Courier New",monospace;text-align:right;color:#eafff4;font-weight:900}
.furnace-layer-unit{color:#9bd9bd;text-align:left;font-family:Consolas,"Courier New",monospace;font-size:9.5px}
.furnace-layer-card.pos-left-top{left:8px;top:8%}
.furnace-layer-card.pos-left-mid{left:8px;top:36%}
.furnace-layer-card.pos-left-low{left:8px;top:69%}
.furnace-layer-card.pos-right-top{right:8px;top:6%}
.furnace-layer-card.pos-right-mid{right:8px;top:26%}
.furnace-layer-card.pos-right-low{right:8px;top:57%}
.furnace-layer-card.pos-right-bottom{right:8px;top:79%}
@media(max-width:1366px),(max-height:760px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{left:27%!important;right:27%!important;inset:1% 27% 5% 27%!important}
  .furnace-layer-card{width:clamp(116px,24%,132px);padding:4px 5px 4px 6px}
  .furnace-layer-card:after{width:28px}
  .furnace-layer-head{height:16px;font-size:12px}
  .furnace-layer-row{grid-template-columns:minmax(0,1fr) minmax(26px,38px) minmax(16px,30px);min-height:11px;font-size:9.3px;gap:2px}
  .furnace-layer-unit{font-size:8.6px}
  .furnace-layer-card.pos-left-top{top:7%}.furnace-layer-card.pos-left-mid{top:36%}.furnace-layer-card.pos-left-low{top:70%}
  .furnace-layer-card.pos-right-top{top:6%}.furnace-layer-card.pos-right-mid{top:25%}.furnace-layer-card.pos-right-low{top:58%}.furnace-layer-card.pos-right-bottom{top:80%}
}
@media(max-height:680px){
  .furnace-layer-card{width:112px;padding:3px 4px}
  .furnace-layer-head{height:14px;font-size:11px}
  .furnace-layer-row{min-height:10px;font-size:8.6px}
  .furnace-layer-unit{display:none}
  .furnace-layer-row{grid-template-columns:minmax(0,1fr) minmax(24px,36px)}
}
`;document.head.appendChild(el)})();
"""

DENSITY_SPARK_OVERRIDE = r"""
/* OPS-8093-CORE-DENSITY-SPARK-V3 */
var CORE_SPARK_MINUTES=30;
var CORE_SPARK_LINE_WIDTH=1.55;
function coreSparkMinSpan(id,nums){const r=ROW_BY_ID[id]||{},u=displayUnit(id,r.unit||''),abs=Math.max(...nums.map(v=>Math.abs(v)),1);if(id==='PI')return Math.max(.04,abs*.0015);if(u==='℃')return Math.max(.35,abs*.0012);if(u==='kPa')return Math.max(.10,abs*.0012);if(u==='%')return Math.max(.18,abs*.0015);return Math.max(.12,abs*.0012)}
sparkOption=function(b,id){const minutes=CORE_SPARK_MINUTES,times=(b.timestamps||[]).slice(-minutes);if(!times.length)return null;const raw=vals(b,id,minutes),data=times.map((t,i)=>[t,displayValue(id,raw[i])]).filter(validPoint);if(!data.length)return null;const nums=data.map(p=>Number(p[1])).filter(Number.isFinite);if(!nums.length)return null;const lo=Math.min(...nums),hi=Math.max(...nums),center=(lo+hi)/2,minSpan=coreSparkMinSpan(id,nums),span=Math.max(hi-lo,minSpan),pad=Math.max(span*.10,minSpan*.12),r=ROW_BY_ID[id]||{name:id,unit:''};return{backgroundColor:'transparent',color:['#72b2ff'],animation:false,grid:{left:0,right:0,top:1,bottom:1},legend:{show:false},tooltip:{show:false},xAxis:{type:'time',show:false,min:data[0][0],max:data[data.length-1][0]},yAxis:[{type:'value',show:false,scale:true,min:center-span/2-pad,max:center+span/2+pad}],series:[{name:r.name||id,type:'line',smooth:false,showSymbol:false,connectNulls:true,clip:true,lineStyle:{width:CORE_SPARK_LINE_WIDTH,color:'#73b4ff',shadowBlur:2,shadowColor:'rgba(115,180,255,.45)'},areaStyle:{opacity:.06,color:'#2f8cff'},data}]}}
;(function(){const apply=()=>{const old=document.getElementById('ops-core-density-spark-v3');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-density-spark-v3';el.textContent=`
.overview-cad-grid{grid-template-columns:minmax(350px,27.5%) minmax(560px,44.5%) minmax(330px,28%)!important;gap:6px!important}
.overview-cad-grid>.panel:first-child .panel-body{padding:6px!important}
.overview-cad-grid .core-grouped-metrics{grid-template-rows:26px 1fr 13px!important;gap:3px!important}
.overview-cad-grid .core-metric-tabs{gap:4px!important}
.overview-cad-grid .core-metric-tabs button{height:26px!important;font-size:10px!important;padding:0 4px!important}
.overview-cad-grid .core-group-page{gap:3px!important}
.overview-cad-grid .core-metric-group{grid-template-rows:17px 1fr!important;border-radius:4px!important}
.overview-cad-grid .core-group-title{height:17px!important;font-size:11px!important;padding:0 5px!important}
.overview-cad-grid .core-group-rows{gap:1px!important;padding:2px!important}
.overview-cad-grid .core-group-row{grid-template-columns:18px minmax(58px,1fr) minmax(52px,62px) minmax(30px,34px) 74px!important;gap:2px!important;height:18px!important;min-height:0!important;padding:0 3px!important}
.overview-cad-grid .core-group-row .metric-unit,.overview-cad-grid .core-group-row .metric-delta{display:none!important}
.overview-cad-grid .core-group-row .metric-name{font-size:9.8px!important;line-height:1!important}
.overview-cad-grid .core-group-row .metric-value{font-size:10.6px!important;line-height:1!important}
.overview-cad-grid .core-group-row .metric-status{font-size:9.4px!important;gap:3px!important;line-height:1!important}
.overview-cad-grid .core-group-row .metric-dot{width:9px!important;height:9px!important}
.overview-cad-grid .core-group-row .spark{width:74px!important;min-width:74px!important;height:14px!important}
.overview-cad-grid .core-metric-note{font-size:9.6px!important;line-height:13px!important;height:13px!important}
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:.5% 25% 3% 25%!important}
.furnace-layer-card{width:clamp(118px,22%,138px)!important}
.furnace-layer-card:after{width:36px!important}
@media(min-width:1500px){
  .overview-cad-grid .core-group-row{grid-template-columns:20px minmax(72px,1fr) minmax(58px,72px) minmax(34px,40px) 86px!important;height:19px!important}
  .overview-cad-grid .core-group-row .spark{width:86px!important;min-width:86px!important;height:15px!important}
  .overview-cad-grid .core-group-row .metric-name{font-size:10.4px!important}
  .overview-cad-grid .core-group-row .metric-value{font-size:11.2px!important}
  .overview-cad-grid .core-group-row .metric-status{font-size:9.8px!important}
}
@media(max-width:1366px),(max-height:760px){
  .overview-cad-grid{grid-template-columns:minmax(350px,27%) minmax(560px,45%) minmax(330px,28%)!important}
  .overview-cad-grid .core-group-row{grid-template-columns:18px minmax(54px,1fr) minmax(50px,60px) minmax(28px,32px) 72px!important;height:18px!important}
  .overview-cad-grid .core-group-row .spark{width:72px!important;min-width:72px!important;height:14px!important}
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:.5% 25% 3% 25%!important}
  .furnace-layer-card{width:118px!important}
}
@media(max-height:680px){
  .overview-cad-grid .core-group-row{height:16px!important;grid-template-columns:18px minmax(50px,1fr) minmax(48px,58px) minmax(26px,30px) 66px!important}
  .overview-cad-grid .core-group-row .spark{width:66px!important;min-width:66px!important;height:12px!important}
  .overview-cad-grid .core-group-title{height:15px!important}
  .overview-cad-grid .core-metric-group{grid-template-rows:15px 1fr!important}
}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CORE_TWO_PAGE_V7_SPECIFICITY_OVERRIDE = r"""
/* OPS-8093-CORE-TWO-PAGE-V7-SPECIFICITY-FIX */
;(function(){const apply=()=>{const old=document.getElementById('ops-core-two-page-v7-specificity-fix');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-two-page-v7-specificity-fix';el.textContent=`
.overview-cad-grid .core-page-v7 .core-group-row .metric-no{font-size:15px!important;line-height:1!important;color:#a9d3ff!important}
.overview-cad-grid .core-page-v7 .core-group-row .metric-name{min-width:0!important;font-family:SimSun,"宋体",serif!important;font-size:16px!important;line-height:1.08!important;font-weight:900!important;color:#eef7ff!important;white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important}
.overview-cad-grid .core-page-v7 .core-group-row .metric-value{justify-self:start!important;width:112px!important;min-width:112px!important;max-width:112px!important;font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important;font-size:19px!important;line-height:1!important;font-weight:900!important;text-align:left!important;font-variant-numeric:tabular-nums!important;font-feature-settings:"tnum" 1,"lnum" 1!important;letter-spacing:0!important;white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important;color:#f7fbff!important;text-shadow:0 0 8px rgba(124,184,255,.48)!important}
.overview-cad-grid .core-page-v7 .core-group-row .metric-status{display:flex!important;align-items:center!important;gap:5px!important;font-family:SimSun,"宋体",serif!important;font-size:13px!important;line-height:1!important;white-space:nowrap!important}
.overview-cad-grid .core-page-v7 .core-group-row .metric-dot{width:11px!important;height:11px!important;flex:0 0 auto!important}
.overview-cad-grid .core-page-v7 .core-group-row .metric-unit,.overview-cad-grid .core-page-v7 .core-group-row .metric-delta{display:none!important}
.overview-cad-grid .core-page-v7 .core-group-row .spark{justify-self:stretch!important;width:100%!important;min-width:0!important;height:24px!important;margin-left:4px!important;overflow:visible!important}
@media(min-width:1500px){.overview-cad-grid .core-page-v7 .core-group-row .metric-name{font-size:17px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-value{width:128px!important;min-width:128px!important;max-width:128px!important;font-size:20px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-status{font-size:14px!important}.overview-cad-grid .core-page-v7 .core-group-row .spark{height:27px!important}}
@media(max-width:1366px),(max-height:760px){.overview-cad-grid .core-page-v7 .core-group-row .metric-no{font-size:12.8px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-name{font-size:14px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-value{width:92px!important;min-width:92px!important;max-width:92px!important;font-size:17px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-status{display:none!important}.overview-cad-grid .core-page-v7 .core-group-row .spark{height:19px!important;margin-left:4px!important}}
@media(max-height:680px){.overview-cad-grid .core-page-v7 .core-group-row .metric-no{font-size:11.5px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-name{font-size:12.5px!important}.overview-cad-grid .core-page-v7 .core-group-row .metric-value{width:78px!important;min-width:78px!important;max-width:78px!important;font-size:14.5px!important}.overview-cad-grid .core-page-v7 .core-group-row .spark{height:15px!important;margin-left:3px!important}}
@media(max-width:1366px),(max-height:760px){.overview-cad-grid .core-page-v7 .core-metric-tabs-v7 button{gap:4px!important;padding:0 6px!important;font-size:11.2px!important}.overview-cad-grid .core-page-v7 .core-metric-tabs-v7 button b{font-size:12px!important}}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CORE_SPARK_GAP_V10_OVERRIDE = r"""
/* OPS-8093-CORE-SPARK-GAP-V10 */
;(function(){const apply=()=>{const old=document.getElementById('ops-core-spark-gap-v10');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-spark-gap-v10';el.textContent='.overview-cad-grid .core-page-v7 .core-group-row .spark{margin-left:0!important}';document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

OVERVIEW_LARGE_TREND_V8_OVERRIDE = r"""
/* OPS-8093-OVERVIEW-LARGE-TREND-V8 */
/* REQ-8093-FAST-IN-APP-NAV-20260715 */
function OverviewLargeTrendV8({buf,items,trendNote}){return <Panel title="趋势分析 / 事件时间线" note="最近120分钟 + 未来120分钟预测" className="overview-large-trend-panel"><button className="overview-trend-jump-v13" type="button" onClick={()=>overviewDecisionNavigateV11('trend')} aria-label="进入趋势分析"><span>进入趋势分析</span><b aria-hidden="true">›</b></button><div className="overview-large-trend-v8"><div className="overview-large-chart-v8"><ChartBox option={forecastOption(buf,['DP_total','P_top','PI','T_top'],120,'',{historyMinutes:120,reserveMinutes:120})}/></div><aside className="overview-large-events-v8"><div className="overview-large-notes-v8">{(trendNote||[]).map((x,i)=><div className="basis-item" key={i}><span>{x}</span></div>)}</div><OverviewTimeline items={items||[]}/></aside></div></Panel>}
OverviewRight=function BFOverviewRightV8({diagnosis,buf,items,trendNote}){const d=getDiag(diagnosis),rule=RULE_KNOWLEDGE[d.label]||RULE_KNOWLEDGE.normal,rec=getRec(diagnosis);return <div className="overview-right overview-right-v8"><Panel title="当前诊断"><DiagnosisSummary diagnosis={diagnosis}/></Panel><Panel title="主要依据"><div className="basis-list">{rule.evidence.slice(0,3).map((x,i)=><div className="basis-item" key={i}><span>{x}{i===0?'，结合实时窗口偏离判断':i===1?'，与近15分钟波动同步校验':'，用于确认中心/边缘变化方向'}</span></div>)}</div></Panel><Panel title="优化建议"><div className="card-list">{[...rec.immediate,...rec.followup].slice(0,3).map((x,i)=><div className="suggest-card" key={i}><div className="suggest-icon">{['✺','✣','▰'][i]}</div><div><div className="suggest-title">{['优化送风制度','调整布料策略','加强喷煤调控'][i]}</div><div className="suggest-text">{x}。执行后复查 {rec.observe.slice(0,2).join('、')}。</div></div></div>)}</div></Panel></div>}
OverviewTab=function BFOverviewTabLargeTrendV8({buf,diagnosis,replay,onControl,currentTime,wsStatus}){const d=getDiag(diagnosis),rec=getRec(diagnosis),items=timeline(d,buf),trendNote=[`实时诊断：${LABELS[d.label]}。`,`调控建议：${workerText(rec.immediate[0]||rec.goal)}`,`复查关注：${rec.observe.slice(0,3).join('、')||'风压、顶压、压差'}`];return <div className="screen overview-grid overview-cad-grid overview-large-trend-grid-v8"><Panel title="核心指标"><MetricRows buf={buf}/></Panel><Panel title="炉况总览"><FurnaceGraphic diagnosis={diagnosis} buf={buf}/></Panel><OverviewRight diagnosis={diagnosis} buf={buf} items={items} trendNote={trendNote}/><OverviewLargeTrendV8 buf={buf} items={items} trendNote={trendNote}/></div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-overview-large-trend-v8');if(old)old.remove();const el=document.createElement('style');el.id='ops-overview-large-trend-v8';el.textContent=`
.overview-cad-grid.overview-large-trend-grid-v8{grid-template-columns:minmax(450px,34%) minmax(455px,38%) minmax(300px,28%)!important;grid-template-rows:minmax(0,58%) minmax(220px,42%)!important;gap:8px!important}
.overview-large-trend-panel{position:relative!important}.overview-trend-jump-v13{position:absolute;z-index:6;top:3px;right:7px;height:24px;display:inline-flex;align-items:center;gap:6px;padding:0 7px;border:1px solid rgba(92,176,255,.64);border-radius:4px;background:rgba(8,52,99,.9);color:#d9efff;font-family:SimSun,"宋体",serif;font-size:11px;font-weight:900;cursor:pointer}.overview-trend-jump-v13 b{font-family:Arial,sans-serif;font-size:20px;line-height:1;color:#85caff}.overview-trend-jump-v13:hover,.overview-trend-jump-v13:focus-visible{border-color:#68c6ff;background:#0d5da8;color:#fff;outline:none;box-shadow:0 0 10px rgba(55,164,255,.36)}
.overview-cad-grid.overview-large-trend-grid-v8>section:nth-child(1){grid-column:1!important;grid-row:1 / 3!important}.overview-cad-grid.overview-large-trend-grid-v8>section:nth-child(2){grid-column:2!important;grid-row:1!important}
.overview-cad-grid.overview-large-trend-grid-v8>.overview-right-v8{grid-column:3!important;grid-row:1!important;height:100%!important;display:grid!important;grid-template-rows:minmax(94px,34%) minmax(66px,22%) minmax(112px,44%)!important;gap:8px!important;min-height:0!important;overflow:hidden!important}.overview-cad-grid.overview-large-trend-grid-v8>.overview-right-v8>.panel{min-height:0!important;height:100%!important}
.overview-cad-grid.overview-large-trend-grid-v8>.overview-large-trend-panel{grid-column:2 / 4!important;grid-row:2!important;min-height:0!important}.overview-large-trend-panel .panel-body{padding:6px!important;min-height:0!important}
.overview-large-trend-v8{height:100%!important;min-height:0!important;display:grid!important;grid-template-columns:minmax(0,78%) minmax(190px,22%)!important;gap:8px!important}.overview-large-chart-v8{min-width:0!important;min-height:0!important;overflow:hidden!important}.overview-large-chart-v8 .chart{height:100%!important;min-height:0!important}
.overview-large-events-v8{min-width:0!important;min-height:0!important;display:grid!important;grid-template-rows:auto minmax(0,1fr)!important;gap:6px!important;overflow:hidden!important}.overview-large-notes-v8{display:grid!important;gap:4px!important}.overview-large-notes-v8 .basis-item{grid-template-columns:7px minmax(0,1fr)!important;gap:6px!important;font-size:11px!important;line-height:1.25!important}.overview-large-notes-v8 .basis-item:before{width:6px!important;height:6px!important;margin-top:4px!important}
.overview-large-events-v8 .overview-timeline{grid-template-columns:42px minmax(0,1fr)!important;column-gap:6px!important}.overview-large-events-v8 .time-rail{gap:7px!important}.overview-large-events-v8 .time-dot{width:13px!important;height:13px!important}.overview-large-events-v8 .time-row{grid-template-columns:38px minmax(0,1fr)!important;gap:5px!important;line-height:1.08!important}.overview-large-events-v8 .time-row b{font-size:11px!important}.overview-large-events-v8 .time-row strong{font-size:11px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}.overview-large-events-v8 .time-row span{display:none!important}
@media(max-width:1366px),(max-height:760px){.overview-cad-grid.overview-large-trend-grid-v8{grid-template-columns:minmax(450px,34%) minmax(455px,38%) minmax(300px,28%)!important;grid-template-rows:minmax(0,56%) minmax(210px,44%)!important}.overview-large-trend-v8{grid-template-columns:minmax(0,76%) minmax(154px,24%)!important;gap:6px!important}.overview-large-events-v8 .time-row strong{font-size:10px!important}.overview-large-notes-v8 .basis-item{font-size:10px!important}.overview-large-trend-panel .panel-head{height:29px!important;flex-basis:29px!important}.overview-large-trend-panel .panel-title{font-size:13px!important}.overview-large-trend-panel .panel-note{font-size:10px!important}}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

OVERVIEW_DECISION_HUB_V11_OVERRIDE = r"""
/* OPS-8093-OVERVIEW-DECISION-HUB-V11 */
function overviewDecisionNavigateV11(hash){if(!hash)return;const index=NAVS.findIndex(item=>item[0]===hash),buttons=document.querySelectorAll('.bottom-nav .nav-btn'),button=index>=0?buttons[index]:null;if(button){button.click();return}window.location.hash=hash}
OverviewRight=function BFOverviewRightDecisionHubV11({diagnosis}){const d=getDiag(diagnosis),rec=getRec(diagnosis),score=Math.max(0,Math.min(100,Number(d.score)||0)),actions=[...rec.immediate,...rec.followup].filter(Boolean).slice(0,2),titles=['优化送风制度','调整布料策略'];return <div className="overview-right overview-right-v11"><Panel title="炉况诊断" note="点击查看详情" className="overview-diagnosis-panel-v11"><button className="overview-diagnosis-button-v11" type="button" onClick={()=>overviewDecisionNavigateV11('diagnosis')} aria-label="进入炉况诊断"><div className="overview-diagnosis-copy-v11"><div className="diag-line">主诊断：<b className={diagnosisToneClass(d.label,d.score)}>{LABELS[d.label]}</b></div><div className="diag-line">次诊断：<b className={`secondary ${secondaryDiagnosisToneClass(d.secondary)}`}>{d.secondary?LABELS[d.secondary]:'暂无明显并发'}</b></div></div><span className="overview-jump-arrow-v11" aria-hidden="true">›</span></button></Panel><Panel title="优化建议" note="两条重点建议" className="overview-suggestions-panel-v11"><div className="overview-suggestion-list-v11">{actions.map((action,index)=><button className="overview-suggestion-v11" type="button" key={`${action}-${index}`} onClick={()=>overviewDecisionNavigateV11('optimization')} aria-label={`查看参数优化建议：${titles[index]||'重点建议'}`}><span className="overview-suggestion-index-v11">0{index+1}</span><span className="overview-suggestion-copy-v11"><b>{titles[index]||'重点建议'}</b><span>{action}</span></span><span className="overview-jump-arrow-v11" aria-hidden="true">›</span></button>)}</div></Panel></div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-overview-decision-hub-v11');if(old)old.remove();const el=document.createElement('style');el.id='ops-overview-decision-hub-v11';el.textContent=`
.overview-cad-grid.overview-large-trend-grid-v8{grid-template-columns:minmax(400px,30%) minmax(505px,42%) minmax(300px,28%)!important}.overview-cad-grid.overview-large-trend-grid-v8>.overview-right-v11{grid-column:3!important;grid-row:1!important;height:100%!important;display:grid!important;grid-template-rows:minmax(118px,42%) minmax(142px,58%)!important;gap:8px!important;min-height:0!important;overflow:hidden!important}.overview-right-v11>.panel{min-height:0!important;height:100%!important}.overview-right-v11 .panel-head{padding:0 12px!important}.overview-right-v11 .panel-note{font-size:11px!important}.overview-right-v11 .panel-body{padding:8px!important}.overview-diagnosis-button-v11{width:100%;height:100%;display:grid;grid-template-columns:minmax(0,1fr) 26px;align-items:center;gap:8px;border:1px solid rgba(62,150,232,.44);border-radius:5px;background:linear-gradient(90deg,rgba(8,44,84,.9),rgba(3,22,46,.82));color:#eaf6ff;text-align:left;padding:10px 12px;cursor:pointer}.overview-diagnosis-button-v11:hover,.overview-diagnosis-button-v11:focus-visible,.overview-suggestion-v11:hover,.overview-suggestion-v11:focus-visible{border-color:#4db7ff;background:linear-gradient(90deg,rgba(12,70,129,.92),rgba(5,34,69,.9));outline:none;box-shadow:inset 0 0 16px rgba(48,157,255,.18)}.overview-diagnosis-copy-v11{display:grid;gap:5px;min-width:0}.overview-right-v11 .diag-line{font-size:19px!important;line-height:1.1!important}.overview-right-v11 .diag-line b{font-size:21px!important;margin-left:7px!important}.overview-right-v11 .confidence{grid-template-columns:62px minmax(0,1fr) 36px!important;gap:7px!important;margin-top:2px!important;font-size:11px!important}.overview-right-v11 .confidence .bar{height:8px!important}.overview-jump-arrow-v11{color:#84caff;font-family:Arial,sans-serif;font-size:30px;line-height:1;text-align:center}.overview-suggestion-list-v11{height:100%;display:grid;grid-template-rows:repeat(2,minmax(0,1fr));gap:7px}.overview-suggestion-v11{min-width:0;display:grid;grid-template-columns:30px minmax(0,1fr) 22px;align-items:center;gap:8px;border:1px solid rgba(46,128,205,.56);border-radius:5px;background:linear-gradient(90deg,rgba(7,39,75,.9),rgba(3,22,47,.84));color:#eaf6ff;text-align:left;padding:7px 9px;cursor:pointer}.overview-suggestion-index-v11{width:26px;height:26px;display:grid;place-items:center;border:1px solid rgba(94,174,255,.62);border-radius:4px;color:#bfe5ff;font-family:"D-DIN","Bahnschrift","Arial",sans-serif;font-size:12px;font-weight:900;background:rgba(22,86,151,.34)}.overview-suggestion-copy-v11{min-width:0;display:grid;gap:3px}.overview-suggestion-copy-v11 b{font-family:SimSun,"宋体",serif;font-size:15px;color:#f1f8ff}.overview-suggestion-copy-v11 span{font-family:SimSun,"宋体",serif;font-size:11px;line-height:1.25;color:#bad2e8;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}@media(max-width:1366px),(max-height:760px){.overview-cad-grid.overview-large-trend-grid-v8{grid-template-columns:minmax(400px,30%) minmax(505px,42%) minmax(300px,28%)!important}.overview-cad-grid.overview-large-trend-grid-v8>.overview-right-v11{grid-template-rows:minmax(94px,42%) minmax(110px,58%)!important;gap:6px!important}.overview-right-v11 .panel-head{height:28px!important;flex-basis:28px!important;padding:0 9px!important}.overview-right-v11 .panel-title{font-size:14px!important}.overview-right-v11 .panel-body{padding:5px!important}.overview-diagnosis-button-v11{padding:6px 8px!important}.overview-right-v11 .diag-line{font-size:15px!important}.overview-right-v11 .diag-line b{font-size:17px!important}.overview-right-v11 .confidence{font-size:10px!important}.overview-suggestion-v11{padding:5px 6px!important;gap:6px!important}.overview-suggestion-copy-v11 b{font-size:12.5px!important}.overview-suggestion-copy-v11 span{font-size:10px!important}.overview-suggestion-index-v11{width:22px!important;height:22px!important;font-size:10px!important}.overview-jump-arrow-v11{font-size:23px!important}}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

OVERVIEW_THREE_COLUMN_V12_OVERRIDE = r"""
/* OPS-8093-OVERVIEW-THREE-COLUMN-V12 */
OverviewRight=function BFOverviewRightThreeColumnV12({diagnosis,buf,items,trendNote}){const d=getDiag(diagnosis),rec=getRec(diagnosis),score=Math.max(0,Math.min(100,Number(d.score)||0)),actions=[...rec.immediate,...rec.followup].filter(Boolean).slice(0,2),titles=['优化送风制度','调整布料策略'];return <aside className="overview-right-v12"><div className="overview-decision-hub-v12"><Panel title="炉况诊断" note="点击查看详情" className="overview-diagnosis-panel-v12"><button className="overview-diagnosis-button-v11" type="button" onClick={()=>overviewDecisionNavigateV11('diagnosis')} aria-label="进入炉况诊断"><div className="overview-diagnosis-copy-v11"><div className="diag-line">主诊断：<b className={diagnosisToneClass(d.label,d.score)}>{LABELS[d.label]}</b></div><div className="diag-line">次诊断：<b className={`secondary ${secondaryDiagnosisToneClass(d.secondary)}`}>{d.secondary?LABELS[d.secondary]:'暂无明显并发'}</b></div></div><span className="overview-jump-arrow-v11" aria-hidden="true">›</span></button></Panel><Panel title="优化建议" note="两条重点建议" className="overview-suggestions-panel-v12"><div className="overview-suggestion-list-v11">{actions.map((action,index)=><button className="overview-suggestion-v11" type="button" key={`${action}-${index}`} onClick={()=>overviewDecisionNavigateV11('optimization')} aria-label={`查看参数优化建议：${titles[index]||'重点建议'}`}><span className="overview-suggestion-index-v11">0{index+1}</span><span className="overview-suggestion-copy-v11"><b>{titles[index]||'重点建议'}</b><span>{action}</span></span><span className="overview-jump-arrow-v11" aria-hidden="true">›</span></button>)}</div></Panel></div><OverviewLargeTrendV8 buf={buf} items={items} trendNote={trendNote}/></aside>}
OverviewTab=function BFOverviewTabThreeColumnV12({buf,diagnosis,replay,onControl,currentTime,wsStatus}){const d=getDiag(diagnosis),rec=getRec(diagnosis),items=timeline(d,buf),trendNote=[`实时诊断：${LABELS[d.label]}。`,`调控建议：${workerText(rec.immediate[0]||rec.goal)}`,`复查关注：${rec.observe.slice(0,3).join('、')||'风压、顶压、压差'}`];return <div className="screen overview-grid overview-cad-grid overview-three-column-v12"><Panel title="核心指标"><MetricRows buf={buf}/></Panel><Panel title="炉况总览" className="overview-furnace-panel-v12"><FurnaceGraphic diagnosis={diagnosis} buf={buf}/></Panel><OverviewRight diagnosis={diagnosis} buf={buf} items={items} trendNote={trendNote}/></div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-overview-three-column-v12');if(old)old.remove();const el=document.createElement('style');el.id='ops-overview-three-column-v12';el.textContent=`
.overview-cad-grid.overview-three-column-v12{grid-template-columns:minmax(360px,25%) minmax(590px,47%) minmax(330px,28%)!important;grid-template-rows:minmax(0,1fr)!important;gap:8px!important}.overview-cad-grid.overview-three-column-v12>section:nth-child(1){grid-column:1!important;grid-row:1!important}.overview-cad-grid.overview-three-column-v12>.overview-furnace-panel-v12{grid-column:2!important;grid-row:1!important}.overview-cad-grid.overview-three-column-v12>.overview-right-v12{grid-column:3!important;grid-row:1!important;height:100%!important;display:grid!important;grid-template-rows:minmax(0,60%) minmax(0,40%)!important;gap:8px!important;min-height:0!important;overflow:hidden!important}.overview-decision-hub-v12{display:grid!important;grid-template-rows:minmax(108px,42%) minmax(132px,58%)!important;gap:8px!important;min-height:0!important}.overview-right-v12 .panel{min-height:0!important;height:100%!important}.overview-right-v12 .panel-head{height:31px!important;flex-basis:31px!important;padding:0 10px!important}.overview-right-v12 .panel-body{padding:7px!important}.overview-right-v12 .panel-title{font-size:15px!important}.overview-right-v12 .panel-note{font-size:10px!important}.overview-right-v12 .diag-line{font-size:17px!important}.overview-right-v12 .diag-line b{font-size:19px!important}.overview-right-v12 .confidence{grid-template-columns:58px minmax(0,1fr) 34px!important;font-size:10px!important}.overview-right-v12 .overview-large-trend-panel{min-height:0!important}.overview-right-v12 .overview-large-trend-panel .panel-head{height:29px!important;flex-basis:29px!important}.overview-right-v12 .overview-large-trend-v8{grid-template-columns:1fr!important;grid-template-rows:minmax(120px,65%) minmax(0,35%)!important;gap:5px!important}.overview-right-v12 .overview-large-events-v8{grid-template-rows:minmax(0,1fr)!important}.overview-right-v12 .overview-large-notes-v8{display:none!important}.overview-right-v12 .overview-large-events-v8 .overview-timeline{grid-template-columns:32px minmax(0,1fr)!important;column-gap:4px!important}.overview-right-v12 .overview-large-events-v8 .time-rail{gap:4px!important}.overview-right-v12 .overview-large-events-v8 .time-dot{width:10px!important;height:10px!important}.overview-right-v12 .overview-large-events-v8 .time-row{grid-template-columns:34px minmax(0,1fr)!important;gap:4px!important}.overview-right-v12 .overview-large-events-v8 .time-row b,.overview-right-v12 .overview-large-events-v8 .time-row strong{font-size:9.5px!important}.overview-right-v12 .overview-large-events-v8 .time-row span{display:none!important}@media(max-width:1500px),(max-height:760px){.overview-cad-grid.overview-three-column-v12{grid-template-columns:minmax(340px,25%) minmax(560px,47%) minmax(300px,28%)!important;gap:6px!important}.overview-cad-grid.overview-three-column-v12>.overview-right-v12{gap:6px!important}.overview-decision-hub-v12{grid-template-rows:minmax(92px,42%) minmax(108px,58%)!important;gap:6px!important}.overview-right-v12 .panel-head{height:27px!important;flex-basis:27px!important}.overview-right-v12 .panel-body{padding:5px!important}.overview-right-v12 .diag-line{font-size:14px!important}.overview-right-v12 .diag-line b{font-size:16px!important}.overview-right-v12 .overview-large-trend-v8{grid-template-rows:minmax(96px,64%) minmax(0,36%)!important}.overview-right-v12 .overview-large-trend-panel .panel-note{display:none!important}}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

AUTO_MONITOR_DOCK_MD_V9_OVERRIDE = r"""
/* OPS-8093-AUTO-MONITOR-DOCK-MD-V9 */
;(function(){if(window.__BF_AUTO_MONITOR_DOCK_MD_V9__)return;window.__BF_AUTO_MONITOR_DOCK_MD_V9__=true;const esc=value=>String(value==null?'':value).replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));const markdown=value=>{const text=esc(value).replace(/\r\n/g,'\n').trim();if(!text)return'';return text.split(/\n{2,}/).map(block=>{const lines=block.split('\n').map(x=>x.trim()).filter(Boolean);if(!lines.length)return'';if(/^#{1,3}\s+/.test(lines[0]))return'<h4>'+lines[0].replace(/^#{1,3}\s+/,'')+'</h4>'+(lines.slice(1).length?'<p>'+lines.slice(1).join('<br>')+'</p>':'');if(lines.every(x=>/^[-*•]\s+/.test(x)))return'<ul>'+lines.map(x=>'<li>'+x.replace(/^[-*•]\s+/,'')+'</li>').join('')+'</ul>';if(lines.every(x=>/^\d+\.\s+/.test(x)))return'<ol>'+lines.map(x=>'<li>'+x.replace(/^\d+\.\s+/,'')+'</li>').join('')+'</ol>';return'<p>'+lines.join('<br>')+'</p>'}).join('').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>')};const apply=()=>{let box=document.getElementById('bf-auto-monitor');if(!box)return;let style=document.getElementById('ops-auto-monitor-dock-md-v9');if(!style){style=document.createElement('style');style.id='ops-auto-monitor-dock-md-v9';style.textContent=`
#bf-auto-monitor{display:none!important}#bf-auto-monitor.bf-auto-open{position:fixed!important;right:12px!important;left:auto!important;top:104px!important;bottom:90px!important;width:min(420px,calc(100vw - 24px))!important;max-width:calc(100vw - 24px)!important;max-height:none!important;display:flex!important;flex-direction:column!important;z-index:100001!important}#bf-auto-monitor.bf-auto-open .bf-auto-body{flex:1 1 auto!important;min-height:0!important;max-height:none!important}#bf-auto-monitor.bf-auto-open .bf-auto-head{cursor:default!important}.bf-auto-head .bf-auto-close-v9{margin-left:8px;width:24px;height:24px;border:1px solid rgba(130,205,255,.5);background:rgba(5,28,56,.9);color:#dcecff;border-radius:4px;cursor:pointer}.bf-auto-summary.bf-auto-md{max-height:96px!important;overflow:auto!important;line-height:1.38!important}.bf-auto-summary.bf-auto-md p{margin:3px 0}.bf-auto-summary.bf-auto-md h4{margin:4px 0;color:#edf7ff;font-size:12px}.bf-auto-summary.bf-auto-md ul,.bf-auto-summary.bf-auto-md ol{margin:3px 0 3px 18px;padding:0}.bf-auto-summary.bf-auto-md strong{color:#fff}.bf-auto-summary.bf-auto-md code{color:#9fd5ff;font-family:Consolas,"Courier New",monospace}#bf-auto-trigger{width:34px;height:34px;border:1px solid rgba(84,181,255,.78);border-radius:5px;background:rgba(6,39,77,.88);color:#bfe8ff;font-size:18px;line-height:1;cursor:pointer;box-shadow:0 0 10px rgba(25,143,255,.28)}#bf-auto-trigger:hover{background:#0f5ba8;color:#fff}
`;document.head.appendChild(style)};box.style.left='';box.style.top='';box.style.right='';const oldHead=box.querySelector('.bf-auto-head');if(oldHead&&!oldHead.dataset.v9){const head=oldHead.cloneNode(true);head.dataset.v9='1';oldHead.replaceWith(head);const oldButton=head.querySelector('#bf-auto-toggle');if(oldButton){oldButton.id='';oldButton.className='bf-auto-close-v9';oldButton.textContent='×';oldButton.title='关闭自动值守抽屉';oldButton.addEventListener('click',()=>box.classList.remove('bf-auto-open'))}}const refresh=document.querySelector('.topbar .refresh');if(refresh&&!refresh.querySelector('#bf-auto-trigger')){refresh.textContent='';const trigger=document.createElement('button');trigger.id='bf-auto-trigger';trigger.type='button';trigger.title='打开自动诊断值守';trigger.setAttribute('aria-label','打开自动诊断值守');trigger.textContent='◉';trigger.addEventListener('click',()=>{box.classList.add('bf-auto-open');box.classList.remove('bf-auto-collapsed')});refresh.appendChild(trigger)}box.querySelectorAll('.bf-auto-summary:not([data-md-v9])').forEach(node=>{const raw=(node.textContent||'').trim();node.dataset.mdV9='1';node.classList.add('bf-auto-md');node.innerHTML=markdown(raw)||'<span class="bf-auto-muted">-</span>'})};apply();setInterval(apply,350)})();
"""

DIAGNOSIS_COLOR_OVERRIDE = r"""
/* OPS-8093-DIAGNOSIS-NORMAL-GREEN */
function diagnosisToneClass(label,score){if(!label||label==='normal'||label==='none')return'text-good bf-diag-normal';const n=Number(score);return n>=70?'text-bad bf-diag-abnormal-high':'text-warn bf-diag-abnormal-watch'}
function secondaryDiagnosisToneClass(label){return label&&label!=='normal'?'text-warn bf-diag-secondary-abnormal':'text-good bf-diag-no-secondary'}
DiagnosisSummary=function BFDiagnosisSummaryNormalGreen({diagnosis}){const d=getDiag(diagnosis),rec=getRec(diagnosis),ev=(d.evidence.length?d.evidence.map(e=>e.text||String(e)):(RULE_KNOWLEDGE[d.label]?.evidence||[]).slice(0,3)).map(typeof workerText==='function'?workerText:(x=>x));const mainCls=diagnosisToneClass(d.label,d.score),secondaryCls=secondaryDiagnosisToneClass(d.secondary);return <div className="diagnosis-hero bf-diagnosis-normal-green"><div><div className="diag-line">主诊断：<b className={mainCls}>{LABELS[d.label]}</b></div><div className="diag-line">次诊断：<b className={`secondary ${secondaryCls}`}>{d.secondary?LABELS[d.secondary]:'暂无明显并发'}</b></div></div><div className="evidence-list">{ev.slice(0,4).map((x,i)=><div className="evidence-item" key={i}><b>依据 {i+1}</b>：{x}</div>)}<div className="evidence-item"><b>目标</b>：{typeof workerText==='function'?workerText(rec.goal):rec.goal}</div></div></div>}
DiagnosisConclusion=function BFDiagnosisConclusionNormalGreen({diagnosis}){const d=getDiag(diagnosis),score=Math.max(0,Math.min(100,Number(d.score)||0)),mainCls=diagnosisToneClass(d.label,d.score),secondaryCls=secondaryDiagnosisToneClass(d.secondary);return <div className="diag-conclusion bf-diagnosis-normal-green"><MiniFurnaceIcon/><div className="diag-conclusion-lines"><div className="diag-line">主诊断：<b className={mainCls}>{LABELS[d.label]}</b></div><div className="diag-line">次诊断：<b className={`secondary ${secondaryCls}`}>{d.secondary?LABELS[d.secondary]:'暂无明显并发'}</b></div></div></div>}
;(function(){if(window.__BF_DIAGNOSIS_NORMAL_GREEN__)return;window.__BF_DIAGNOSIS_NORMAL_GREEN__=true;const applyStyle=()=>{if(document.getElementById('ops-diagnosis-normal-green-style'))return;const el=document.createElement('style');el.id='ops-diagnosis-normal-green-style';el.textContent=`
.bf-diagnosis-normal-green .diag-line b.bf-diag-normal,
.bf-diagnosis-normal-green .diag-line b.bf-diag-no-secondary,
.overview-right.rebalanced .diag-line b.bf-diag-normal,
.overview-right.rebalanced .diag-line b.bf-diag-no-secondary,
.diag-conclusion-lines .diag-line b.bf-diag-normal,
.diag-conclusion-lines .diag-line b.bf-diag-no-secondary,
#bf-auto-monitor .bf-diag-normal-green,
#bf-auto-monitor .bf-diag-no-secondary{color:#38e47a!important;text-shadow:0 0 8px rgba(56,228,122,.45)!important}
.bf-diagnosis-normal-green .diag-line b.bf-diag-abnormal-watch,
.overview-right.rebalanced .diag-line b.bf-diag-abnormal-watch,
.diag-conclusion-lines .diag-line b.bf-diag-abnormal-watch,
#bf-auto-monitor .bf-diag-abnormal-watch{color:#ffb21b!important;text-shadow:0 0 8px rgba(255,178,27,.42)!important}
.bf-diagnosis-normal-green .diag-line b.bf-diag-abnormal-high,
.overview-right.rebalanced .diag-line b.bf-diag-abnormal-high,
.diag-conclusion-lines .diag-line b.bf-diag-abnormal-high,
#bf-auto-monitor .bf-diag-abnormal-high{color:#ff4f63!important;text-shadow:0 0 8px rgba(255,79,99,.45)!important}
`;document.head.appendChild(el)};
const cleanAutoDiagClasses=el=>{el.classList.remove('bf-diag-normal-green','bf-diag-no-secondary','bf-diag-abnormal-watch','bf-diag-abnormal-high')};
const paintAutoMonitor=()=>{const root=document.getElementById('bf-auto-monitor');if(!root)return;root.querySelectorAll('.bf-diag-normal-green,.bf-diag-no-secondary,.bf-diag-abnormal-watch,.bf-diag-abnormal-high').forEach(cleanAutoDiagClasses);root.querySelectorAll('b,span,strong,em,div').forEach(el=>{const text=(el.textContent||'').trim(),lower=text.toLowerCase();if(!text||text.length>18)return;if(/正常顺行|正常运行/.test(text)||/^normal(?:\b|\s*\/)/i.test(text))el.classList.add('bf-diag-normal-green');if(/暂无明显并发|无明显并发|暂无并发/.test(text))el.classList.add('bf-diag-no-secondary');if(/炉凉|炉热|低料线|边缘|中心|管道|崩滑|悬料|cold|hot|lowline|edge|center|channel|column/.test(lower)){const m=text.match(/\/\s*([0-9]+(?:\.[0-9]+)?)/),score=m?Number(m[1]):80;el.classList.add(score>=70?'bf-diag-abnormal-high':'bf-diag-abnormal-watch')}})};
applyStyle();paintAutoMonitor();setInterval(paintAutoMonitor,800);new MutationObserver(paintAutoMonitor).observe(document.documentElement,{childList:true,subtree:true,characterData:true})})();
"""

FURNACE_POINT_ANCHOR_OVERRIDE = r"""
/* OPS-8093-FURNACE-POINT-ANCHORS-V2 */
const FURNACE_LAYER_POINT_LAYOUT={
  '煤气顶压':{side:'left',card:[2,11],target:[29,19],anchors:[[44,18]]},
  '压差透气':{side:'left',card:[2,42],target:[29,48],anchors:[[44,48]]},
  '喷煤':{side:'left',card:[2,72],target:[29,76],anchors:[[44,74]]},
  '料线':{side:'right',card:[75,5],target:[72,12],anchors:[[52,11]]},
  '热制度':{side:'right',card:[75,28],target:[72,36],anchors:[[57,34]]},
  '送风供氧':{side:'right',card:[75,57],target:[72,66],anchors:[[57,66]]},
  '出铁口温度':{side:'right',card:[75,79],targets:[[72,84],[72,89]],anchors:[[50,86],[55,88]],anchorLabels:['1#','2#']}
};
function FurnaceLayerPointCard({group,buf}){return <div className={`furnace-layer-card point-card ${group.pos} side-${group.side||'right'}`} data-layer={group.title} style={{left:`${group.card[0]}%`,top:`${group.card[1]}%`}}><div className="furnace-layer-head"><span>{group.title}</span></div><div className="furnace-layer-rows">{group.items.map(item=>{const meta=furnaceLayerMeta(item),v=latest(buf,item.id),unit=displayUnit(item.id,meta.unit),digits=furnaceLayerDigits(item.id),value=displayNum(item.id,v,digits);return <div className="furnace-layer-row" key={item.id} title={`${meta.name} ${value}${unit}`}><span className="furnace-layer-name">{meta.name}</span><span className="furnace-layer-value">{value}</span><span className="furnace-layer-unit">{unit}</span></div>})}</div></div>}
FurnaceLayerCallouts=function BFPointAnchoredFurnaceLayerCallouts({buf}){const groups=FURNACE_LAYER_GROUPS.map(g=>({...g,...FURNACE_LAYER_POINT_LAYOUT[g.title]}));return <div className="furnace-layer-callouts point-anchored" aria-label="核心变量真实点位工艺标注"><svg className="furnace-layer-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{groups.flatMap(group=>{const anchors=group.anchors||[],targets=group.targets||anchors.map(()=>group.target);return anchors.map((p,i)=>{const t=targets[i]||group.target||p,label=(group.anchorLabels||[])[i];return <g key={`${group.title}-${i}`}><line className="furnace-layer-line" x1={p[0]} y1={p[1]} x2={t[0]} y2={t[1]}/><circle className="furnace-layer-pin" cx={p[0]} cy={p[1]} r={1.05}/>{label&&<text className="furnace-layer-anchor-label" x={p[0]+1.5} y={p[1]+1.1}>{label}</text>}</g>})})}</svg>{groups.map(group=><FurnaceLayerPointCard key={group.title} group={group} buf={buf}/>)}</div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-furnace-point-anchors-v2');if(old)old.remove();const el=document.createElement('style');el.id='ops-furnace-point-anchors-v2';el.textContent=`
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:7% 34% 10% 34%!important;z-index:2!important}
.furnace-layer-callouts.point-anchored{position:absolute;inset:0;z-index:14;pointer-events:none;font-family:SimSun,"宋体",serif}
.furnace-layer-lines{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.furnace-layer-line{stroke:#d9bd4b;stroke-width:.22;stroke-opacity:.82;vector-effect:non-scaling-stroke}
.furnace-layer-pin{fill:#ffe270;stroke:#08131b;stroke-width:.25;filter:drop-shadow(0 0 4px rgba(255,218,70,.75))}
.furnace-layer-anchor-label{fill:#fff0a0;font-size:2.4px;font-weight:900;text-shadow:0 0 4px rgba(255,218,70,.7)}
.furnace-layer-callouts.point-anchored .furnace-layer-card{width:clamp(120px,21%,146px)!important;padding:5px 6px 5px 7px!important;border-left:2px solid #d9bd4b!important;border-radius:3px!important;background:linear-gradient(180deg,rgba(12,28,25,.92),rgba(4,16,17,.88))!important;box-shadow:0 8px 18px rgba(0,0,0,.28),inset 0 0 14px rgba(95,146,122,.08)!important}
.furnace-layer-callouts.point-anchored .furnace-layer-card:after{display:none!important}
.furnace-layer-callouts.point-anchored .furnace-layer-card.side-right{border-left-color:#d9bd4b!important}
.furnace-layer-callouts.point-anchored .furnace-layer-card.side-left{border-left-color:#d9bd4b!important}
.furnace-layer-callouts.point-anchored .furnace-layer-head{height:17px!important;font-size:12.5px!important}
.furnace-layer-callouts.point-anchored .furnace-layer-row{min-height:12px!important;font-size:9.8px!important;grid-template-columns:minmax(0,1fr) minmax(34px,48px) minmax(18px,34px)!important}
@media(min-width:1500px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:6% 35% 10% 35%!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-card{width:clamp(132px,20%,158px)!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-head{font-size:13px!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-row{font-size:10.4px!important}
}
@media(max-width:1366px),(max-height:760px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:7% 34% 11% 34%!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-card{width:116px!important;padding:4px 5px 4px 6px!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-head{height:15px!important;font-size:11.2px!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-row{min-height:10.5px!important;font-size:8.8px!important;grid-template-columns:minmax(0,1fr) minmax(28px,40px) minmax(14px,28px)!important}
  .furnace-layer-anchor-label{font-size:2.1px}
}
@media(max-height:680px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:8% 35% 12% 35%!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-card{width:108px!important;padding:3px 4px!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-head{height:14px!important;font-size:10.5px!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-row{min-height:9.5px!important;font-size:8.2px!important;grid-template-columns:minmax(0,1fr) minmax(24px,36px)!important}
  .furnace-layer-callouts.point-anchored .furnace-layer-unit{display:none!important}
}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

FURNACE_FOLLOW_ANCHOR_OVERRIDE = r"""
/* OPS-8093-FURNACE-FOLLOW-ANCHORS-V3 */
const FURNACE_LAYER_FOLLOW_CONFIG={
  '煤气顶压':{side:'left',ids:['P_top','P_top_gas_A','P_top_gas_B','P_top_gas_C','P_top_gas_D']},
  '压差透气':{side:'left',ids:['PI','DP_upper','DP_lower','DP_total']},
  '喷煤':{side:'left',ids:['PCI_rate','PCI_set']},
  '料线':{side:'right',ids:['L','L_south','L_north']},
  '热制度':{side:'right',ids:['T_body_L14_A','T_body_L14_C','T_body_L14_E','T_body_L14_G']},
  '送风供氧':{side:'right',ids:['Q_blast','P_blast_cold','P_blast','O2_rate','Q_O2']},
  '出铁口温度':{side:'right',ids:['T_taphole_1','T_taphole_2'],multi:true,labels:['1#','2#']}
};
function FurnaceLayerFollowCard({group,buf}){return <div className={`furnace-layer-card follow-card side-${group.follow.side}`} data-layer={group.title} data-side={group.follow.side}><div className="furnace-layer-head"><span>{group.title}</span></div><div className="furnace-layer-rows">{group.items.map(item=>{const meta=furnaceLayerMeta(item),v=latest(buf,item.id),unit=displayUnit(item.id,meta.unit),digits=furnaceLayerDigits(item.id),value=displayNum(item.id,v,digits);return <div className="furnace-layer-row" key={item.id} title={`${meta.name} ${value}${unit}`}><span className="furnace-layer-name">{meta.name}</span><span className="furnace-layer-value">{value}</span><span className="furnace-layer-unit">{unit}</span></div>})}</div></div>}
FurnaceLayerCallouts=function BFModelFollowFurnaceLayerCallouts({buf}){const groups=FURNACE_LAYER_GROUPS.map(g=>({...g,follow:FURNACE_LAYER_FOLLOW_CONFIG[g.title]||{side:'right',ids:g.items.map(x=>x.id)}}));return <div className="furnace-layer-callouts follow-model" aria-label="核心变量跟随高炉本体点位标注"><svg className="furnace-follow-lines" aria-hidden="true">{groups.flatMap(group=>{const ids=group.follow.multi?group.follow.ids:[group.follow.ids[0]||group.items[0]?.id];return ids.map((id,i)=><g data-layer={group.title} data-anchor-index={i} key={`${group.title}-${id}-${i}`}><line className="furnace-follow-line"/><circle className="furnace-follow-pin" r="5"/>{group.follow.labels?.[i]&&<text className="furnace-follow-label">{group.follow.labels[i]}</text>}</g>)})}</svg>{groups.map(group=><FurnaceLayerFollowCard key={group.title} group={group} buf={buf}/>)}</div>}
;(function(){if(window.__BF_FURNACE_FOLLOW_ANCHORS_V3__)return;window.__BF_FURNACE_FOLLOW_ANCHORS_V3__=true;const CONFIG={...FURNACE_LAYER_FOLLOW_CONFIG};const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));function applyStyle(){const old=document.getElementById('ops-furnace-follow-anchors-v3');if(old)old.remove();const el=document.createElement('style');el.id='ops-furnace-follow-anchors-v3';el.textContent=`
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:7% 34% 10% 34%!important;z-index:2!important}
.furnace-layer-callouts.follow-model{position:absolute;inset:0;z-index:16;pointer-events:none;font-family:SimSun,"宋体",serif}
.furnace-follow-lines{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
.furnace-follow-line{stroke:#d9bd4b;stroke-width:1;stroke-opacity:.78;vector-effect:non-scaling-stroke}
.furnace-follow-pin{fill:#ffe270;stroke:#08131b;stroke-width:1.2;filter:drop-shadow(0 0 4px rgba(255,218,70,.75))}
.furnace-follow-label{fill:#fff0a0;font-size:14px;font-weight:900;text-shadow:0 0 4px rgba(255,218,70,.75)}
.furnace-layer-callouts.follow-model .furnace-layer-card{position:absolute!important;width:clamp(120px,21%,146px)!important;padding:5px 6px 5px 7px!important;border-left:2px solid #d9bd4b!important;border-radius:3px!important;background:linear-gradient(180deg,rgba(12,28,25,.92),rgba(4,16,17,.88))!important;box-shadow:0 8px 18px rgba(0,0,0,.28),inset 0 0 14px rgba(95,146,122,.08)!important;color:#e8fff1!important}
.furnace-layer-callouts.follow-model .furnace-layer-card:after{display:none!important}
.furnace-layer-callouts.follow-model .furnace-layer-head{height:17px!important;font-size:12.5px!important}
.furnace-layer-callouts.follow-model .furnace-layer-row{min-height:12px!important;font-size:9.8px!important;grid-template-columns:minmax(0,1fr) minmax(34px,48px) minmax(18px,34px)!important}
@media(min-width:1500px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:6% 35% 10% 35%!important}
  .furnace-layer-callouts.follow-model .furnace-layer-card{width:clamp(132px,20%,158px)!important}
  .furnace-layer-callouts.follow-model .furnace-layer-head{font-size:13px!important}
  .furnace-layer-callouts.follow-model .furnace-layer-row{font-size:10.4px!important}
}
@media(max-width:1366px),(max-height:760px){
  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{inset:7% 34% 11% 34%!important}
  .furnace-layer-callouts.follow-model .furnace-layer-card{width:116px!important;padding:4px 5px 4px 6px!important}
  .furnace-layer-callouts.follow-model .furnace-layer-head{height:15px!important;font-size:11.2px!important}
  .furnace-layer-callouts.follow-model .furnace-layer-row{min-height:10.5px!important;font-size:8.8px!important;grid-template-columns:minmax(0,1fr) minmax(28px,40px) minmax(14px,28px)!important}
  .furnace-follow-label{font-size:12px}
}
`;document.head.appendChild(el)}function objectById(v,id){return(v?.hitObjects||[]).find(o=>o.userData?.sensorId===id)||(v?.sensorObjects||[]).find(o=>o.userData?.sensorId===id)}function projectObj(v,obj,stageRect){if(!v?.renderer||!v?.camera||!obj)return null;const rect=v.renderer.domElement.getBoundingClientRect(),p=obj.position.clone().project(v.camera);if(!Number.isFinite(p.x)||!Number.isFinite(p.y)||p.z<-1.2||p.z>1.2)return null;return{x:rect.left+(p.x+1)*rect.width/2-stageRect.left,y:rect.top+(1-p.y)*rect.height/2-stageRect.top,z:p.z}}function groupPoints(v,cfg,stageRect){const ids=cfg.ids||[];const pts=ids.map(id=>projectObj(v,objectById(v,id),stageRect)).filter(Boolean);if(!pts.length)return[];return cfg.multi?pts:[{x:pts.reduce((a,p)=>a+p.x,0)/pts.length,y:pts.reduce((a,p)=>a+p.y,0)/pts.length,z:pts.reduce((a,p)=>a+p.z,0)/pts.length}]}function deconflict(items,stageH){const gap=10;items.sort((a,b)=>a.desired-b.desired);for(const item of items){item.top=clamp(item.desired,8,stageH-item.h-8)}for(let i=1;i<items.length;i++){items[i].top=Math.max(items[i].top,items[i-1].top+items[i-1].h+gap)}const overflow=items.length?items[items.length-1].top+items[items.length-1].h+8-stageH:0;if(overflow>0){for(let i=items.length-1;i>=0;i--){items[i].top-=overflow}for(let i=items.length-2;i>=0;i--){items[i].top=Math.min(items[i].top,items[i+1].top-items[i].h-gap)}for(const item of items){item.top=clamp(item.top,8,stageH-item.h-8)}}}function sync(){const root=document.querySelector('.furnace-layer-callouts.follow-model'),stage=document.querySelector('.layered-cad-stage'),svg=document.querySelector('.furnace-follow-lines'),v=window.__BF_CAD_FURNACE_VIEWER;if(!root||!stage||!svg||!v?.renderer||!v?.camera)return;const stageRect=stage.getBoundingClientRect(),w=stageRect.width,h=stageRect.height;if(w<1||h<1)return;svg.setAttribute('viewBox',`0 0 ${w} ${h}`);const cardItems=[];root.querySelectorAll('.furnace-layer-card[data-layer]').forEach(card=>{const layer=card.dataset.layer,cfg=CONFIG[layer]||{},pts=groupPoints(v,cfg,stageRect);if(!pts.length)return;const anchor={x:pts.reduce((a,p)=>a+p.x,0)/pts.length,y:pts.reduce((a,p)=>a+p.y,0)/pts.length},side=cfg.side||card.dataset.side||'right',cw=card.offsetWidth||128,ch=card.offsetHeight||64,left=side==='left'?12:w-cw-14;cardItems.push({layer,cfg,pts,anchor,side,card,cw,ch,h:ch,left,desired:anchor.y-ch/2})});deconflict(cardItems.filter(x=>x.side==='left'),h);deconflict(cardItems.filter(x=>x.side!=='left'),h);for(const item of cardItems){item.card.style.left=`${item.left}px`;item.card.style.top=`${item.top}px`;const edgeX=item.side==='left'?item.left+item.cw:item.left,baseY=item.top+Math.min(item.ch-14,Math.max(16,item.ch/2));item.pts.forEach((p,i)=>{const g=svg.querySelector(`g[data-layer="${CSS.escape(item.layer)}"][data-anchor-index="${i}"]`),line=g?.querySelector('line'),pin=g?.querySelector('circle'),label=g?.querySelector('text');if(!g||!line||!pin)return;const edgeY=item.cfg.multi?item.top+20+i*18:baseY;line.setAttribute('x1',p.x.toFixed(1));line.setAttribute('y1',p.y.toFixed(1));line.setAttribute('x2',edgeX.toFixed(1));line.setAttribute('y2',edgeY.toFixed(1));pin.setAttribute('cx',p.x.toFixed(1));pin.setAttribute('cy',p.y.toFixed(1));if(label){label.setAttribute('x',(p.x+10).toFixed(1));label.setAttribute('y',(p.y+5).toFixed(1))}})}}applyStyle();let raf=0;const loop=()=>{sync();raf=requestAnimationFrame(loop)};loop();window.addEventListener('resize',sync);window.__BF_FURNACE_FOLLOW_ANCHORS_SYNC__=sync})();
"""

CAD_TOOLTIP_FALLBACK_OVERRIDE = r"""
/* OPS-8093-CAD-TOOLTIP-SAFE-FALLBACK */
if(typeof cadSensorTooltip!=='function'){window.cadSensorTooltip=function(buf,id){const row=ROW_BY_ID[id]||{name:id,unit:''},v=latest(buf||{},id),z=rollingIqrDeviation(buf||{},id,v),st=iqrStatus(z),digits=id==='PI'||id==='L'||id==='L_south'||id==='L_north'?2:1;return `<strong>${row.name||id}</strong><div class="value">${displayNum(id,v,digits)} ${displayUnit(id,row.unit||'')}</div><div>点位：<b>${id}</b></div><div>状态：${st.label}，基线偏离 ${z!==null&&z>=0?'+':''}${fmtNum(z,2)}</div><div class="muted">CAD GLB 节点：SENSOR_${id}</div>`}}
;(function(){if(window.__BF_CAD_TOOLTIP_EMPTY_GUARD__)return;window.__BF_CAD_TOOLTIP_EMPTY_GUARD__=true;setInterval(()=>{const tip=document.querySelector('.cad-furnace-tooltip');if(tip&&getComputedStyle(tip).display!=='none'&&!(tip.textContent||'').trim())tip.style.display='none'},160)})();
"""

CORE_TWO_COLUMN_OVERRIDE = r"""
/* OPS-8093-CORE-TWO-COLUMN-V4 */
/* OPS-8093-CORE-TWO-COLUMN-V4-BALANCED-14-14 */
function coreMetricGroupByTitleV4(title){return (CORE_METRIC_GROUPS||[]).find(g=>g.title===title)}
const CORE_METRIC_LEFT_GROUPS_V4=['煤气顶压','送风供氧','喷煤','出铁口温度'].map(coreMetricGroupByTitleV4).filter(Boolean);
const CORE_METRIC_RIGHT_GROUPS_V4=['热制度','料线','压差透气'].map(coreMetricGroupByTitleV4).filter(Boolean);
function coreMetricCountV4(groups){return groups.reduce((n,g)=>n+g.items.length,0)}
function CoreMetricColumnV4({buf,groups,startIndex,title,side}){let offset=startIndex;const count=coreMetricCountV4(groups);return <div className="core-metric-column-v4" data-side={side} data-count={count}><div className="core-column-head-v4"><span>{title}</span><b>{count}项</b></div>{groups.map(group=>{const start=offset;offset+=group.items.length;return <div className="core-metric-group" key={group.title}><div className="core-group-title"><span>{group.title}</span><b>{group.items.length}</b></div><div className="core-group-rows">{group.items.map((item,i)=><CoreMetricRow buf={buf} item={item} index={start+i} key={item.id||item.name}/>)}</div></div>})}</div>}
MetricRows=function({buf}){const left=CORE_METRIC_LEFT_GROUPS_V4,right=CORE_METRIC_RIGHT_GROUPS_V4,leftCount=coreMetricCountV4(left);return <div className="metric-list core-grouped-metrics core-two-column-v4"><div className="core-two-column-grid-v4"><CoreMetricColumnV4 buf={buf} groups={left} startIndex={0} title="顶压 / 送风 / 喷煤 / 出铁口" side="left"/><CoreMetricColumnV4 buf={buf} groups={right} startIndex={leftCount} title="热制度 / 料线 / 压差" side="right"/></div><div className="muted core-metric-note">核心28变量按两列均衡展示：左列14项，右列14项；只改变展示，不改变诊断和趋势数据来源。</div></div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-core-two-column-v4');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-two-column-v4';el.textContent=`
.overview-cad-grid .core-grouped-metrics.core-two-column-v4{grid-template-rows:1fr 14px!important;gap:4px!important;min-height:0!important}
.core-two-column-grid-v4{min-height:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:5px;overflow:hidden}
.core-metric-column-v4{min-height:0;display:flex;flex-direction:column;gap:3px;overflow:hidden}
.core-column-head-v4{height:23px;min-height:23px;display:flex;align-items:center;justify-content:space-between;padding:0 7px;border:1px solid rgba(69,138,218,.64);border-radius:5px;background:linear-gradient(180deg,rgba(27,82,164,.86),rgba(8,42,90,.82));color:#eef7ff;font-size:13px;font-weight:900}
.core-column-head-v4 b{font-family:Consolas,"Courier New",monospace;color:#9ed8ff;font-size:12px}
.core-two-column-v4 .core-metric-group{display:grid!important;grid-template-rows:19px auto!important;gap:0!important;min-height:0!important;flex:0 0 auto;border-radius:5px!important}
.core-two-column-v4 .core-group-title{height:19px!important;padding:0 6px!important;font-size:12px!important}
.core-two-column-v4 .core-group-title b{font-size:11px!important}
.core-two-column-v4 .core-group-rows{display:grid!important;grid-auto-rows:22px!important;gap:2px!important;padding:2px!important;min-height:0!important}
.overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:20px minmax(48px,1fr) minmax(58px,76px) 0 minmax(34px,40px) minmax(48px,56px) 0!important;gap:2px!important;height:22px!important;min-height:22px!important;padding:1px 3px!important}
.core-two-column-v4 .metric-no{font-size:12px!important;color:#9fccff!important}
.core-two-column-v4 .metric-name{font-size:12.2px!important;font-weight:900!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.core-two-column-v4 .metric-value{font-size:13.1px!important;font-weight:900!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.core-two-column-v4 .metric-status{font-size:11px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
.core-two-column-v4 .metric-unit,.core-two-column-v4 .metric-delta{display:none!important}
.core-two-column-v4 .spark{width:54px!important;min-width:54px!important;height:15px!important}
.core-two-column-v4 .core-metric-note{height:14px!important;line-height:14px!important;font-size:11px!important}
@media(min-width:1500px){
  .core-two-column-grid-v4{gap:7px}
  .core-column-head-v4{height:25px;min-height:25px;font-size:14px}
  .core-two-column-v4 .core-group-rows{grid-auto-rows:24px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:22px minmax(62px,1fr) minmax(68px,86px) 0 minmax(38px,44px) minmax(58px,66px) 0!important;height:24px!important;min-height:24px!important}
  .core-two-column-v4 .metric-name{font-size:13px!important}
  .core-two-column-v4 .metric-value{font-size:14px!important}
  .core-two-column-v4 .metric-status{font-size:11.8px!important}
  .core-two-column-v4 .spark{width:64px!important;min-width:64px!important;height:16px!important}
}
@media(max-width:1366px),(max-height:760px){
  .overview-cad-grid .core-grouped-metrics.core-two-column-v4{gap:3px!important}
  .core-two-column-grid-v4{gap:4px}
  .core-column-head-v4{height:21px;min-height:21px;padding:0 5px;font-size:12px}
  .core-column-head-v4 b{font-size:11px}
  .core-two-column-v4 .core-metric-group{grid-template-rows:18px auto!important}
  .core-two-column-v4 .core-group-title{height:18px!important;font-size:11.2px!important;padding:0 5px!important}
  .core-two-column-v4 .core-group-rows{grid-auto-rows:20px!important;gap:1px!important;padding:2px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:18px minmax(42px,1fr) minmax(50px,64px) 0 minmax(30px,35px) minmax(44px,50px) 0!important;height:20px!important;min-height:20px!important;gap:2px!important;padding:1px 2px!important}
  .core-two-column-v4 .metric-no{font-size:11px!important}
  .core-two-column-v4 .metric-name{font-size:11.1px!important}
  .core-two-column-v4 .metric-value{font-size:12px!important}
  .core-two-column-v4 .metric-status{font-size:10.2px!important}
  .core-two-column-v4 .spark{width:48px!important;min-width:48px!important;height:13px!important}
  .core-two-column-v4 .core-metric-note{font-size:10.2px!important}
}
@media(max-height:680px){
  .core-column-head-v4{height:19px;min-height:19px;font-size:11px}
  .core-two-column-v4 .core-group-title{height:16px!important;font-size:10.5px!important}
  .core-two-column-v4 .core-group-rows{grid-auto-rows:18px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:17px minmax(40px,1fr) minmax(48px,60px) 0 minmax(28px,32px) minmax(40px,46px) 0!important;height:18px!important;min-height:18px!important}
  .core-two-column-v4 .metric-name{font-size:10.2px!important}
  .core-two-column-v4 .metric-value{font-size:11px!important}
  .core-two-column-v4 .metric-status{font-size:9.5px!important}
  .core-two-column-v4 .spark{width:44px!important;min-width:44px!important;height:11px!important}
}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CORE_TWO_COLUMN_LARGE_OVERRIDE = r"""
/* OPS-8093-CORE-TWO-COLUMN-V5-FILL-LARGE */
CoreMetricColumnV4=function BFCoreMetricColumnV5({buf,groups,startIndex,title,side}){let offset=startIndex;const count=coreMetricCountV4(groups);return <div className="core-metric-column-v4" data-side={side} data-count={count}><div className="core-column-head-v4"><span>{title}</span><b>{count}项</b></div>{groups.map(group=>{const start=offset;offset+=group.items.length;return <div className="core-metric-group" style={{'--rows':String(group.items.length),flex:`${group.items.length} ${group.items.length} 0`}} key={group.title}><div className="core-group-title"><span>{group.title}</span><b>{group.items.length}</b></div><div className="core-group-rows">{group.items.map((item,i)=><CoreMetricRow buf={buf} item={item} index={start+i} key={item.id||item.name}/>)}</div></div>})}</div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-core-two-column-v5-fill-large');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-two-column-v5-fill-large';el.textContent=`
.overview-cad-grid .core-grouped-metrics.core-two-column-v4{grid-template-rows:minmax(0,1fr) 18px!important;gap:6px!important}
.core-two-column-v4 .core-two-column-grid-v4{height:100%!important;gap:7px!important;align-items:stretch!important}
.core-two-column-v4 .core-metric-column-v4{height:100%!important;display:flex!important;flex-direction:column!important;gap:5px!important;overflow:hidden!important}
.core-two-column-v4 .core-column-head-v4{height:30px!important;min-height:30px!important;padding:0 10px!important;font-size:15px!important;border-radius:6px!important}
.core-two-column-v4 .core-column-head-v4 b{font-size:14px!important}
.core-two-column-v4 .core-metric-group{grid-template-rows:25px minmax(0,1fr)!important;flex:var(--rows) var(--rows) 0!important;min-height:0!important}
.core-two-column-v4 .core-group-title{height:25px!important;padding:0 8px!important;font-size:15px!important}
.core-two-column-v4 .core-group-title b{font-size:13px!important}
.core-two-column-v4 .core-group-rows{height:100%!important;display:grid!important;grid-template-rows:repeat(var(--rows),minmax(29px,1fr))!important;gap:3px!important;padding:3px!important;min-height:0!important}
.overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:27px minmax(74px,1fr) minmax(82px,98px) minmax(42px,52px) minmax(76px,92px)!important;height:auto!important;min-height:29px!important;gap:4px!important;padding:2px 5px!important;align-items:center!important}
.core-two-column-v4 .metric-no{font-size:14px!important;line-height:1!important;color:#a9d3ff!important}
.core-two-column-v4 .metric-name{font-size:15px!important;line-height:1.06!important;font-weight:900!important;color:#eef7ff!important}
.core-two-column-v4 .metric-value{font-size:17px!important;line-height:1!important;font-weight:900!important;color:#f7fbff!important;text-shadow:0 0 8px rgba(124,184,255,.55)!important}
.core-two-column-v4 .metric-status{font-size:12.5px!important;line-height:1!important}
.core-two-column-v4 .metric-dot{width:12px!important;height:12px!important}
.core-two-column-v4 .spark{width:86px!important;min-width:86px!important;height:20px!important}
.core-two-column-v4 .core-metric-note{height:18px!important;line-height:18px!important;font-size:12.5px!important}
.overview-cad-grid{grid-template-columns:minmax(460px,34%) minmax(470px,38%) minmax(315px,28%)!important}
.overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:27px minmax(78px,1fr) minmax(86px,104px) minmax(82px,98px)!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .metric-status{display:none!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .metric-name{font-size:15px!important;line-height:1.06!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{font-size:17px!important;line-height:1!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .metric-no{font-size:14px!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .spark{width:92px!important;min-width:92px!important;height:20px!important}
@media(min-width:1500px){
  .core-two-column-v4 .core-column-head-v4{height:33px!important;min-height:33px!important;font-size:16px!important}
  .core-two-column-v4 .core-column-head-v4 b{font-size:15px!important}
  .core-two-column-v4 .core-metric-group{grid-template-rows:28px minmax(0,1fr)!important}
  .core-two-column-v4 .core-group-title{height:28px!important;font-size:16px!important}
  .core-two-column-v4 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(33px,1fr))!important;gap:4px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:30px minmax(92px,1fr) minmax(92px,112px) minmax(46px,58px) minmax(92px,112px)!important;min-height:33px!important}
  .core-two-column-v4 .metric-no{font-size:15px!important}
  .core-two-column-v4 .metric-name{font-size:16px!important}
  .core-two-column-v4 .metric-value{font-size:18.5px!important}
  .core-two-column-v4 .metric-status{font-size:13.2px!important}
  .core-two-column-v4 .spark{width:108px!important;min-width:108px!important;height:22px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:30px minmax(108px,1fr) minmax(104px,126px) minmax(106px,126px)!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-name{font-size:16px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{font-size:18.5px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-no{font-size:15px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{width:120px!important;min-width:120px!important;height:22px!important}
}
@media(max-width:1366px),(max-height:760px){
  .core-two-column-v4 .core-column-head-v4{height:27px!important;min-height:27px!important;font-size:13.8px!important;padding:0 7px!important}
  .core-two-column-v4 .core-column-head-v4 b{font-size:12.6px!important}
  .core-two-column-v4 .core-metric-group{grid-template-rows:22px minmax(0,1fr)!important}
  .core-two-column-v4 .core-group-title{height:22px!important;font-size:13.6px!important;padding:0 7px!important}
  .core-two-column-v4 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(25px,1fr))!important;gap:2px!important;padding:2px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:24px minmax(64px,1fr) minmax(72px,88px) minmax(38px,46px) minmax(66px,78px)!important;min-height:25px!important;gap:3px!important;padding:2px 4px!important}
  .core-two-column-v4 .metric-no{font-size:12.8px!important}
  .core-two-column-v4 .metric-name{font-size:13.6px!important}
  .core-two-column-v4 .metric-value{font-size:15.8px!important}
  .core-two-column-v4 .metric-status{font-size:11.6px!important}
  .core-two-column-v4 .metric-dot{width:10px!important;height:10px!important}
  .core-two-column-v4 .spark{width:74px!important;min-width:74px!important;height:18px!important}
  .overview-cad-grid{grid-template-columns:minmax(450px,34%) minmax(455px,38%) minmax(300px,28%)!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:24px minmax(68px,1fr) minmax(74px,92px) minmax(70px,84px)!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-name{font-size:13.8px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{font-size:15.9px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-no{font-size:12.9px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{width:78px!important;min-width:78px!important;height:18px!important}
}
@media(max-height:680px){
  .core-two-column-v4 .core-column-head-v4{height:23px!important;min-height:23px!important;font-size:12.6px!important}
  .core-two-column-v4 .core-metric-group{grid-template-rows:19px minmax(0,1fr)!important}
  .core-two-column-v4 .core-group-title{height:19px!important;font-size:12px!important}
  .core-two-column-v4 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(21px,1fr))!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:21px minmax(54px,1fr) minmax(62px,76px) minmax(32px,40px) minmax(54px,66px)!important;min-height:21px!important}
  .core-two-column-v4 .metric-name{font-size:12px!important}
  .core-two-column-v4 .metric-value{font-size:14px!important}
  .core-two-column-v4 .metric-status{font-size:10.2px!important}
  .core-two-column-v4 .spark{width:62px!important;min-width:62px!important;height:15px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:21px minmax(56px,1fr) minmax(64px,78px) minmax(54px,68px)!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-name{font-size:12.2px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{font-size:14.2px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{width:64px!important;min-width:64px!important;height:15px!important}
}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CORE_VALUE_ALIGN_OVERRIDE = r"""
/* OPS-8093-CORE-VALUE-ALIGN-V6 */
;(function(){const apply=()=>{const old=document.getElementById('ops-core-value-align-v6');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-value-align-v6';el.textContent=`
.overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:27px minmax(78px,1fr) 104px 98px!important;column-gap:4px!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{justify-self:start!important;text-align:left!important;width:104px!important;min-width:104px!important;max-width:104px!important;font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important;font-variant-numeric:tabular-nums!important;font-feature-settings:"tnum" 1,"lnum" 1!important;letter-spacing:0!important;white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important}
.overview-cad-grid .core-two-column-v4 .core-group-row .spark{justify-self:start!important;margin-left:6px!important}
@media(min-width:1500px){
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:30px minmax(108px,1fr) 126px 126px!important;column-gap:4px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{width:126px!important;min-width:126px!important;max-width:126px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{margin-left:6px!important}
}
@media(max-width:1366px),(max-height:760px){
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:24px minmax(68px,1fr) 92px 84px!important;column-gap:4px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{width:92px!important;min-width:92px!important;max-width:92px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{margin-left:6px!important}
}
@media(max-height:680px){
  .overview-cad-grid .core-two-column-v4 .core-group-row{grid-template-columns:21px minmax(56px,1fr) 78px 68px!important;column-gap:3px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .metric-value{width:78px!important;min-width:78px!important;max-width:78px!important}
  .overview-cad-grid .core-two-column-v4 .core-group-row .spark{margin-left:4px!important}
}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CORE_TWO_PAGE_V7_OVERRIDE = r"""
/* OPS-8093-CORE-TWO-PAGE-V7 */
const CORE_METRIC_PAGES_V7=[
  {title:'顶压 / 送风 / 喷煤 / 出铁口',groups:CORE_METRIC_LEFT_GROUPS_V4,startIndex:0},
  {title:'热制度 / 料线 / 压差',groups:CORE_METRIC_RIGHT_GROUPS_V4,startIndex:14}
];
function coreSparkOptionV7(buf,item){const id=metricItemIds(item)[0],minutes=30,times=(buf.timestamps||[]).slice(-minutes);if(!times.length)return null;const raw=vals(buf,id,minutes),data=times.map((t,i)=>[t,displayValue(id,raw[i])]).filter(validPoint);if(!data.length)return null;const nums=data.map(p=>Number(p[1])).filter(Number.isFinite);if(!nums.length)return null;const lo=Math.min(...nums),hi=Math.max(...nums),center=(lo+hi)/2,minSpan=coreSparkMinSpan(id,nums),span=Math.max(hi-lo,minSpan),pad=Math.max(span*.14,minSpan*.16),row=ROW_BY_ID[id]||{name:id};return{backgroundColor:'transparent',animation:false,grid:{left:1,right:1,top:2,bottom:2},legend:{show:false},tooltip:{show:false},xAxis:{type:'time',show:false,min:data[0][0],max:data[data.length-1][0]},yAxis:[{type:'value',show:false,scale:true,min:center-span/2-pad,max:center+span/2+pad}],series:[{name:row.name||id,type:'line',smooth:false,showSymbol:false,connectNulls:true,clip:true,lineStyle:{width:1.4,color:'#78b6ff',shadowBlur:2,shadowColor:'rgba(120,182,255,.42)'},areaStyle:{opacity:.08,color:'#2f8cff'},data}]}}
CoreMetricRow=function BFCoreMetricRowV7({buf,item,index}){const ids=metricItemIds(item),key=ids.join('|'),z=metricItemDeviation(buf,item),st=iqrStatus(z);return <div className="metric-row core-group-row" key={key}><div className="metric-no mono">{String(index+1).padStart(2,'0')}</div><div className="metric-name" title={metricItemName(item)}>{metricItemName(item)}</div><div className="metric-value" title={metricItemValue(buf,item)}>{metricItemValue(buf,item)}</div><div className="metric-status"><span className={`metric-dot ${st.tone}`}></span>{st.label}</div><ChartBox option={coreSparkOptionV7(buf,item)} className="spark"/></div>}
MetricRows=function BFCoreMetricRowsV7({buf}){const[page,setPage]=useState(0),current=CORE_METRIC_PAGES_V7[page]||CORE_METRIC_PAGES_V7[0];let offset=current.startIndex;return <div className="metric-list core-grouped-metrics core-page-v7"><div className="core-metric-tabs-v7" role="tablist" aria-label="核心变量分页">{CORE_METRIC_PAGES_V7.map((item,i)=><button key={item.title} className={page===i?'active':''} aria-selected={page===i} onClick={()=>setPage(i)}><span>{item.title}</span><b>14项</b></button>)}</div><div className="core-page-v7-content">{current.groups.map(group=>{const start=offset;offset+=group.items.length;return <div className="core-metric-group" key={group.title} style={{'--rows':String(group.items.length)}}><div className="core-group-title"><span>{group.title}</span><b>{group.items.length}</b></div><div className="core-group-rows">{group.items.map((item,i)=><CoreMetricRow buf={buf} item={item} index={start+i} key={item.id||item.name}/>)}</div></div>})}</div><div className="muted core-metric-note">核心28变量按工艺分为两页展示，每页14项；曲线为最近30分钟有效数据。</div></div>}
;(function(){const apply=()=>{const old=document.getElementById('ops-core-two-page-v7');if(old)old.remove();const el=document.createElement('style');el.id='ops-core-two-page-v7';el.textContent=`
.overview-cad-grid .core-grouped-metrics.core-page-v7{grid-template-rows:38px minmax(0,1fr) 20px!important;gap:6px!important;min-height:0!important}
.core-page-v7 .core-metric-tabs-v7{display:grid!important;grid-template-columns:minmax(0,1fr) minmax(0,1fr)!important;gap:7px!important;min-height:0!important}
.core-page-v7 .core-metric-tabs-v7 button{min-width:0!important;height:38px!important;display:flex!important;align-items:center!important;justify-content:space-between!important;gap:8px!important;padding:0 11px!important;border:1px solid rgba(74,137,218,.72)!important;border-radius:6px!important;background:rgba(7,31,67,.92)!important;color:#cdddf2!important;font-family:SimSun,"宋体",serif!important;font-size:15px!important;font-weight:900!important;letter-spacing:0!important;white-space:nowrap!important;cursor:pointer!important}
.core-page-v7 .core-metric-tabs-v7 button.active{border-color:#73b6ff!important;background:linear-gradient(180deg,rgba(56,111,215,.9),rgba(22,57,136,.9))!important;color:#f3f8ff!important;box-shadow:inset 0 0 14px rgba(96,164,255,.22)!important}
.core-page-v7 .core-metric-tabs-v7 b{flex:0 0 auto!important;color:#a9d3ff!important;font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important;font-size:15px!important;font-variant-numeric:tabular-nums!important}
.core-page-v7 .core-page-v7-content{min-height:0!important;display:flex!important;flex-direction:column!important;gap:6px!important;overflow:hidden!important}
/* BUG-8093-CORE-METRIC-GROUP-CLIP-20260715: include one title-row weight per process group so its last metric row is not clipped. */
.core-page-v7 .core-metric-group{display:grid!important;grid-template-rows:27px minmax(0,1fr)!important;flex:calc(var(--rows) + 1) 1 0!important;min-height:0!important;border-radius:6px!important;overflow:hidden!important}
.core-page-v7 .core-group-title{height:27px!important;min-height:27px!important;padding:0 10px!important;font-size:16px!important}
.core-page-v7 .core-group-title b{font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important;font-size:14px!important}
.core-page-v7 .core-group-rows{height:100%!important;display:grid!important;grid-template-rows:repeat(var(--rows),minmax(32px,1fr))!important;gap:3px!important;padding:3px!important;min-height:0!important}
.overview-cad-grid .core-page-v7 .core-group-row{grid-template-columns:31px minmax(112px,1fr) 112px 62px minmax(138px,168px)!important;column-gap:6px!important;height:auto!important;min-height:32px!important;padding:2px 7px!important;align-items:center!important}
.core-page-v7 .metric-no{font-size:15px!important;line-height:1!important;color:#a9d3ff!important}
.core-page-v7 .metric-name{min-width:0!important;font-family:SimSun,"宋体",serif!important;font-size:16px!important;line-height:1.08!important;font-weight:900!important;color:#eef7ff!important;white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important}
.core-page-v7 .metric-value{justify-self:start!important;width:112px!important;min-width:112px!important;max-width:112px!important;font-family:"D-DIN","Bahnschrift","Arial",sans-serif!important;font-size:19px!important;line-height:1!important;font-weight:900!important;font-variant-numeric:tabular-nums!important;font-feature-settings:"tnum" 1,"lnum" 1!important;letter-spacing:0!important;white-space:nowrap!important;overflow:visible!important;text-overflow:clip!important;color:#f7fbff!important;text-shadow:0 0 8px rgba(124,184,255,.48)!important}
.core-page-v7 .metric-status{display:flex!important;align-items:center!important;gap:5px!important;font-family:SimSun,"宋体",serif!important;font-size:13px!important;line-height:1!important;white-space:nowrap!important}
.core-page-v7 .metric-dot{width:11px!important;height:11px!important;flex:0 0 auto!important}.core-page-v7 .metric-unit,.core-page-v7 .metric-delta{display:none!important}
.core-page-v7 .spark{justify-self:stretch!important;width:100%!important;min-width:0!important;height:24px!important;margin-left:4px!important;overflow:visible!important}
.core-page-v7 .core-metric-note{height:20px!important;line-height:20px!important;font-size:13px!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
@media(min-width:1500px){.overview-cad-grid .core-page-v7 .core-group-row{grid-template-columns:34px minmax(138px,1fr) 128px 70px minmax(172px,208px)!important;min-height:36px!important;padding:3px 9px!important}.core-page-v7 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(36px,1fr))!important}.core-page-v7 .metric-name{font-size:17px!important}.core-page-v7 .metric-value{width:128px!important;min-width:128px!important;max-width:128px!important;font-size:20px!important}.core-page-v7 .metric-status{font-size:14px!important}.core-page-v7 .spark{height:27px!important}.core-page-v7 .core-group-title{height:29px!important;min-height:29px!important;font-size:17px!important}}
@media(max-height:900px) and (min-width:1367px){.overview-cad-grid .core-grouped-metrics.core-page-v7{grid-template-rows:34px minmax(0,1fr)!important;gap:4px!important}.core-page-v7 .core-metric-tabs-v7 button{height:34px!important}.core-page-v7 .core-page-v7-content{gap:4px!important}.core-page-v7 .core-metric-group{grid-template-rows:23px minmax(0,1fr)!important}.core-page-v7 .core-group-title{height:23px!important;min-height:23px!important;font-size:14px!important}.core-page-v7 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(29px,1fr))!important;gap:2px!important;padding:2px!important}.overview-cad-grid .core-page-v7 .core-group-row{min-height:29px!important;padding-top:2px!important;padding-bottom:2px!important}.core-page-v7 .core-metric-note{display:none!important}}
@media(max-width:1366px),(max-height:760px){.overview-cad-grid .core-grouped-metrics.core-page-v7{grid-template-rows:27px minmax(0,1fr)!important;gap:3px!important}.core-page-v7 .core-metric-tabs-v7{gap:5px!important}.core-page-v7 .core-metric-tabs-v7 button{height:27px!important;padding:0 6px!important;font-size:11.2px!important}.core-page-v7 .core-metric-tabs-v7 b{font-size:12px!important}.core-page-v7 .core-page-v7-content{gap:3px!important}.core-page-v7 .core-metric-group{grid-template-rows:18px minmax(0,1fr)!important}.core-page-v7 .core-group-title{height:18px!important;min-height:18px!important;padding:0 6px!important;font-size:11.8px!important}.core-page-v7 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(22px,1fr))!important;gap:1px!important;padding:1px!important}.overview-cad-grid .core-page-v7 .core-group-row{grid-template-columns:24px minmax(98px,1fr) 92px minmax(94px,116px)!important;column-gap:4px!important;min-height:22px!important;padding:1px 5px!important}.core-page-v7 .metric-name{font-size:12.5px!important}.core-page-v7 .metric-value{width:92px!important;min-width:92px!important;max-width:92px!important;font-size:15px!important}.core-page-v7 .metric-status{display:none!important}.core-page-v7 .spark{height:15px!important;margin-left:4px!important}.core-page-v7 .core-metric-note{display:none!important}}
@media(max-height:680px){.overview-cad-grid .core-grouped-metrics.core-page-v7{grid-template-rows:27px minmax(0,1fr)!important;gap:3px!important}.core-page-v7 .core-metric-tabs-v7 button{height:27px!important;font-size:11.5px!important}.core-page-v7 .core-metric-group{grid-template-rows:18px minmax(0,1fr)!important}.core-page-v7 .core-group-title{height:18px!important;min-height:18px!important;font-size:11.8px!important}.core-page-v7 .core-group-rows{grid-template-rows:repeat(var(--rows),minmax(20px,1fr))!important;gap:1px!important}.overview-cad-grid .core-page-v7 .core-group-row{grid-template-columns:21px minmax(82px,1fr) 78px minmax(76px,90px)!important;min-height:20px!important;padding:1px 4px!important}.core-page-v7 .metric-name{font-size:12.5px!important}.core-page-v7 .metric-value{width:78px!important;min-width:78px!important;max-width:78px!important;font-size:14.5px!important}.core-page-v7 .spark{height:15px!important;margin-left:3px!important}.core-page-v7 .core-metric-note{display:none!important}}
`;document.head.appendChild(el)};apply();setTimeout(apply,0);setTimeout(apply,500)})();
"""

CAD_GHOST_BANDS_OVERRIDE = r"""
/* OPS-8093-CAD-GHOST-BANDS-FIX */
;(function(){if(window.__BF_CAD_GHOST_BANDS_FIX__)return;window.__BF_CAD_GHOST_BANDS_FIX__=true;const applyStyle=()=>{const old=document.getElementById('ops-cad-ghost-bands-fix');if(old)old.remove();const el=document.createElement('style');el.id='ops-cad-ghost-bands-fix';el.textContent=`
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage{overflow:visible!important}
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer{inset:3% 24% 5% 24%!important;left:24%!important;right:24%!important;top:3%!important;bottom:5%!important;background:transparent!important;box-shadow:none!important;border-color:transparent!important}
.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer canvas{background:transparent!important;display:block!important}
@media(min-width:1500px){.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer{inset:2% 24% 5% 24%!important;left:24%!important;right:24%!important;top:2%!important;bottom:5%!important}}
@media(max-width:1366px),(max-height:760px){.furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .furnace-stage-3d.cad-stage.layered-cad-stage .cad-furnace-viewer{inset:4% 24% 6% 24%!important;left:24%!important;right:24%!important;top:4%!important;bottom:6%!important}}
`;document.head.appendChild(el)};const syncRenderer=()=>{const v=window.__BF_CAD_FURNACE_VIEWER,canvas=document.querySelector('.cad-furnace-viewer canvas');if(canvas)canvas.style.background='transparent';if(v?.renderer){if(typeof v.renderer.setClearAlpha==='function')v.renderer.setClearAlpha(0);if(typeof v.renderer.setClearColor==='function')v.renderer.setClearColor(0x000000,0);v.renderer.domElement.style.background='transparent'}};applyStyle();setTimeout(applyStyle,0);setTimeout(applyStyle,800);setTimeout(applyStyle,2000);syncRenderer();requestAnimationFrame(syncRenderer);setInterval(syncRenderer,500);window.addEventListener('resize',syncRenderer)})();
"""

OPTIMIZATION_NOTE_REMOVED_OVERRIDE = r"""
/* OPS-8093-OPTIMIZATION-NOTE-REMOVED */
;(function(){if(document.getElementById('ops-optimization-note-removed'))return;const el=document.createElement('style');el.id='ops-optimization-note-removed';el.textContent='.optimization-screen.focused .focus-principle{display:none!important}';document.head.appendChild(el)})();
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def last_index(text: str, *needles: str) -> int:
    return max((text.rfind(needle) for needle in needles), default=-1)


def needs_final_group_override(text: str) -> bool:
    compact_idx = text.rfind('MetricRows=function({buf}){return <div className="metric-list compact-core-metrics"')
    grouped_idx = last_index(
        text,
        "function MetricRows({buf,diagnosis}){",
        "MetricRows=function({buf}){const[page,setPage]=useState(0),groups=CORE_METRIC_PAGES",
        "MetricRows=function({buf,diagnosis}){",
        FINAL_OVERRIDE_MARK,
    )
    unsafe_core_row = "baselineMap(diagnosis)" in text and FINAL_OVERRIDE_MARK not in text
    return unsafe_core_row or (compact_idx >= 0 and grouped_idx < compact_idx)


def needs_spark_override(text: str) -> bool:
    return SPARK_OVERRIDE_MARK not in text


def needs_furnace_layer_override(text: str) -> bool:
    return FURNACE_LAYER_MARK not in text


def needs_density_spark_override(text: str) -> bool:
    return DENSITY_SPARK_MARK not in text


def needs_diagnosis_color_override(text: str) -> bool:
    return DIAGNOSIS_COLOR_MARK not in text


def needs_furnace_point_anchor_override(text: str) -> bool:
    return FURNACE_POINT_ANCHOR_MARK not in text


def needs_furnace_follow_anchor_override(text: str) -> bool:
    return FURNACE_FOLLOW_ANCHOR_MARK not in text


def needs_cad_tooltip_fallback(text: str) -> bool:
    return CAD_TOOLTIP_FALLBACK_MARK not in text


def needs_core_two_column_override(text: str) -> bool:
    return CORE_TWO_COLUMN_MARK not in text


def needs_core_two_column_balanced_marker(text: str) -> bool:
    return CORE_TWO_COLUMN_BALANCED_MARK not in text


def needs_core_two_column_large_override(text: str) -> bool:
    return CORE_TWO_COLUMN_LARGE_MARK not in text or CORE_TWO_COLUMN_LARGE_REQUIRED not in text


def needs_core_value_align_override(text: str) -> bool:
    return CORE_VALUE_ALIGN_MARK not in text or CORE_VALUE_ALIGN_REQUIRED not in text


def needs_core_two_page_v7_override(text: str) -> bool:
    return CORE_TWO_PAGE_V7_MARK not in text or CORE_TWO_PAGE_V7_REQUIRED not in text


def needs_core_two_page_v7_specificity_override(text: str) -> bool:
    return CORE_TWO_PAGE_V7_SPECIFICITY_MARK not in text or CORE_TWO_PAGE_V7_SPECIFICITY_REQUIRED not in text


def needs_core_spark_gap_v10_override(text: str) -> bool:
    return CORE_SPARK_GAP_V10_MARK not in text or CORE_SPARK_GAP_V10_REQUIRED not in text


def needs_overview_large_trend_v8_override(text: str) -> bool:
    return OVERVIEW_LARGE_TREND_V8_MARK not in text or OVERVIEW_LARGE_TREND_V8_REQUIRED not in text


def needs_overview_decision_hub_v11_override(text: str) -> bool:
    return OVERVIEW_DECISION_HUB_V11_MARK not in text or OVERVIEW_DECISION_HUB_V11_REQUIRED not in text


def needs_overview_three_column_v12_override(text: str) -> bool:
    return OVERVIEW_THREE_COLUMN_V12_MARK not in text or OVERVIEW_THREE_COLUMN_V12_REQUIRED not in text


def needs_auto_monitor_dock_md_v9_override(text: str) -> bool:
    return AUTO_MONITOR_DOCK_MD_V9_MARK not in text or AUTO_MONITOR_DOCK_MD_V9_REQUIRED not in text


def needs_cad_ghost_bands_fix(text: str) -> bool:
    return CAD_GHOST_BANDS_MARK not in text


def needs_optimization_note_removed(text: str) -> bool:
    return OPTIMIZATION_NOTE_REMOVED_MARK not in text


def remove_optimization_note(text: str) -> str:
    return text.replace(
        "<div className=\"focus-principle\">{opt.isNormal?'正常炉况不生成满屏操作建议，只保留默认运行和关键观察项。':'只展示最强的1-3条核心建议，其余作为观察备选，避免同屏建议过载。'}</div>",
        "",
    )


def upgrade_balanced_core_columns(text: str) -> str:
    replacements = {
        "const CORE_METRIC_LEFT_GROUPS_V4=['煤气顶压','热制度','送风供氧'].map(coreMetricGroupByTitleV4).filter(Boolean);": "const CORE_METRIC_LEFT_GROUPS_V4=['煤气顶压','送风供氧','喷煤','出铁口温度'].map(coreMetricGroupByTitleV4).filter(Boolean);",
        "const CORE_METRIC_RIGHT_GROUPS_V4=['料线','喷煤','出铁口温度','压差透气'].map(coreMetricGroupByTitleV4).filter(Boolean);": "const CORE_METRIC_RIGHT_GROUPS_V4=['热制度','料线','压差透气'].map(coreMetricGroupByTitleV4).filter(Boolean);",
        'title="顶压 / 热制度 / 送风"': 'title="顶压 / 送风 / 喷煤 / 出铁口"',
        'title="料线 / 喷煤 / 出铁口 / 压差"': 'title="热制度 / 料线 / 压差"',
        "核心28变量按两列展示：左列17项，右列11项；只改变展示，不改变诊断和趋势数据来源。": "核心28变量按两列均衡展示：左列14项，右列14项；只改变展示，不改变诊断和趋势数据来源。",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    if CORE_TWO_COLUMN_MARK in text and CORE_TWO_COLUMN_BALANCED_MARK not in text:
        text = text.replace(CORE_TWO_COLUMN_MARK, CORE_TWO_COLUMN_MARK + "\n" + CORE_TWO_COLUMN_BALANCED_MARK, 1)
    return text


def upgrade_furnace_layer_selectors(text: str) -> str:
    text = text.replace(
        ".layered-cad-stage .cad-furnace-viewer{left:28%!important;right:28%!important;top:1%!important;bottom:5%!important;inset:1% 28% 5% 28%!important;",
        ".furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{left:28%!important;right:28%!important;top:1%!important;bottom:5%!important;inset:1% 28% 5% 28%!important;",
    )
    text = text.replace(
        "  .layered-cad-stage .cad-furnace-viewer{left:27%!important;right:27%!important;inset:1% 27% 5% 27%!important}",
        "  .furnace-wrap.is-3d.centered-cad.furnace-layer-wrap .layered-cad-stage .cad-furnace-viewer{left:27%!important;right:27%!important;inset:1% 27% 5% 27%!important}",
    )
    return text


def upgrade_diagnosis_color_override(text: str) -> str:
    old = "const paintAutoMonitor=()=>{const root=document.getElementById('bf-auto-monitor');if(!root)return;root.querySelectorAll('.bf-diag-normal-green,.bf-diag-no-secondary,.bf-diag-abnormal-watch,.bf-diag-abnormal-high').forEach(cleanAutoDiagClasses);root.querySelectorAll('b,span,strong,em,div').forEach(el=>{const text=(el.textContent||'').trim();if(!text||text.length>18)return;if(/正常顺行|正常运行/.test(text))el.classList.add('bf-diag-normal-green');if(/暂无明显并发|无明显并发|暂无并发/.test(text))el.classList.add('bf-diag-no-secondary')})};"
    new = "const paintAutoMonitor=()=>{const root=document.getElementById('bf-auto-monitor');if(!root)return;root.querySelectorAll('.bf-diag-normal-green,.bf-diag-no-secondary,.bf-diag-abnormal-watch,.bf-diag-abnormal-high').forEach(cleanAutoDiagClasses);root.querySelectorAll('b,span,strong,em,div').forEach(el=>{const text=(el.textContent||'').trim(),lower=text.toLowerCase();if(!text||text.length>18)return;if(/正常顺行|正常运行/.test(text)||/^normal(?:\\b|\\s*\\/)/i.test(text))el.classList.add('bf-diag-normal-green');if(/暂无明显并发|无明显并发|暂无并发/.test(text))el.classList.add('bf-diag-no-secondary');if(/炉凉|炉热|低料线|边缘|中心|管道|崩滑|悬料|cold|hot|lowline|edge|center|channel|column/.test(lower)){const m=text.match(/\\/\\s*([0-9]+(?:\\.[0-9]+)?)/),score=m?Number(m[1]):80;el.classList.add(score>=70?'bf-diag-abnormal-high':'bf-diag-abnormal-watch')}})};"
    return text.replace(old, new)


def upgrade_cad_tooltip_fallback(text: str) -> str:
    return text.replace(
        "if(typeof cadSensorTooltip!=='function'){var cadSensorTooltip=function(buf,id){",
        "if(typeof cadSensorTooltip!=='function'){window.cadSensorTooltip=function(buf,id){",
    )


def upgrade_fast_in_app_navigation(text: str) -> str:
    """Remove full-page reloads from internal 8093 route changes."""
    text = text.replace(
        "function overviewDecisionNavigateV11(hash){if(!hash)return;window.location.hash=hash;window.location.reload()}",
        "function overviewDecisionNavigateV11(hash){if(!hash)return;const index=NAVS.findIndex(item=>item[0]===hash),buttons=document.querySelectorAll('.bottom-nav .nav-btn'),button=index>=0?buttons[index]:null;if(button){button.click();return}window.location.hash=hash}",
    )
    text = text.replace(
        "function optWorkbenchNavigate(hash){\n  if(!hash)return;\n  window.location.hash=hash;\n  window.location.reload();\n}",
        "function optWorkbenchNavigate(hash){\n  if(!hash)return;\n  overviewDecisionNavigateV11(hash);\n}",
    )
    return text


def insert_after_line_containing(text: str, index: int, block: str) -> str:
    line_end = text.find("\n", index)
    if line_end < 0:
        line_end = len(text)
    return text[:line_end] + "\n" + block.strip() + text[line_end:]


def insert_after_last_compact_override(text: str) -> str:
    compact_idx = text.rfind('MetricRows=function({buf}){return <div className="metric-list compact-core-metrics"')
    if compact_idx < 0:
        return text
    return insert_after_line_containing(text, compact_idx, FINAL_OVERRIDE)


def insert_after_last_metric_override(text: str, block: str) -> str:
    metric_idx = last_index(
        text,
        "MetricRows=function({buf,diagnosis}){",
        "MetricRows=function({buf}){const[page,setPage]=useState(0),groups=CORE_METRIC_PAGES",
        "function MetricRows({buf,diagnosis}){",
    )
    if metric_idx >= 0:
        return insert_after_line_containing(text, metric_idx, block)
    script_idx = text.rfind("</script>")
    if script_idx >= 0:
        return text[:script_idx] + block.strip() + "\n" + text[script_idx:]
    return text + "\n" + block.strip() + "\n"


def insert_before_render_call(text: str, block: str) -> str:
    render_idx = text.rfind("window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();")
    if render_idx >= 0:
        return text[:render_idx] + block.strip() + "\n" + text[render_idx:]
    return insert_after_last_metric_override(text, block)


def upsert_before_render_call(text: str, mark: str, block: str) -> str:
    start = text.find(mark)
    if start < 0:
        return insert_before_render_call(text, block)
    render_idx = text.find("window.__BF_RENDER_APP__&&window.__BF_RENDER_APP__();", start)
    next_mark = text.find("\n/* OPS-8093-", start + len(mark))
    if next_mark >= 0 and (render_idx < 0 or next_mark < render_idx):
        return text[:start] + block.strip() + text[next_mark:]
    if render_idx >= 0:
        return text[:start] + block.strip() + "\n" + text[render_idx:]
    return text[:start] + block.strip() + "\n"


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"missing target: {TARGET}")
    before_hash = sha256(TARGET)
    text = TARGET.read_bytes().decode("utf-8", errors="strict")
    next_text = text
    if "CORE_METRIC_GROUPS" not in text or "core-grouped-metrics" not in text:
        start = text.find("function MetricRows")
        end = text.find("function FurnaceGraphic", start)
        if start < 0 or end < 0:
            raise SystemExit("MetricRows replacement point not found")
        next_text = text[:start] + JS.strip() + "\n" + text[end:]
        next_text = next_text.replace("</style>", CSS.strip() + "\n</style>", 1)
    if needs_final_group_override(next_text):
        next_text = insert_after_last_compact_override(next_text)
    if needs_spark_override(next_text):
        next_text = insert_after_last_metric_override(next_text, SPARK_OVERRIDE)
    if needs_furnace_layer_override(next_text):
        next_text = insert_before_render_call(next_text, FURNACE_LAYER_OVERRIDE)
    if needs_density_spark_override(next_text):
        next_text = insert_before_render_call(next_text, DENSITY_SPARK_OVERRIDE)
    if needs_diagnosis_color_override(next_text):
        next_text = insert_before_render_call(next_text, DIAGNOSIS_COLOR_OVERRIDE)
    if needs_furnace_point_anchor_override(next_text):
        next_text = insert_before_render_call(next_text, FURNACE_POINT_ANCHOR_OVERRIDE)
    if needs_furnace_follow_anchor_override(next_text):
        next_text = insert_before_render_call(next_text, FURNACE_FOLLOW_ANCHOR_OVERRIDE)
    if needs_cad_tooltip_fallback(next_text):
        next_text = insert_before_render_call(next_text, CAD_TOOLTIP_FALLBACK_OVERRIDE)
    if needs_core_two_column_override(next_text):
        next_text = insert_before_render_call(next_text, CORE_TWO_COLUMN_OVERRIDE)
    if needs_core_two_column_large_override(next_text):
        next_text = upsert_before_render_call(next_text, CORE_TWO_COLUMN_LARGE_MARK, CORE_TWO_COLUMN_LARGE_OVERRIDE)
    if needs_core_value_align_override(next_text):
        next_text = upsert_before_render_call(next_text, CORE_VALUE_ALIGN_MARK, CORE_VALUE_ALIGN_OVERRIDE)
    if needs_core_two_page_v7_override(next_text):
        next_text = upsert_before_render_call(next_text, CORE_TWO_PAGE_V7_MARK, CORE_TWO_PAGE_V7_OVERRIDE)
    if needs_core_two_page_v7_specificity_override(next_text):
        next_text = upsert_before_render_call(next_text, CORE_TWO_PAGE_V7_SPECIFICITY_MARK, CORE_TWO_PAGE_V7_SPECIFICITY_OVERRIDE)
    if needs_core_spark_gap_v10_override(next_text):
        next_text = upsert_before_render_call(next_text, CORE_SPARK_GAP_V10_MARK, CORE_SPARK_GAP_V10_OVERRIDE)
    if needs_overview_large_trend_v8_override(next_text):
        next_text = upsert_before_render_call(next_text, OVERVIEW_LARGE_TREND_V8_MARK, OVERVIEW_LARGE_TREND_V8_OVERRIDE)
    if needs_overview_decision_hub_v11_override(next_text):
        next_text = upsert_before_render_call(next_text, OVERVIEW_DECISION_HUB_V11_MARK, OVERVIEW_DECISION_HUB_V11_OVERRIDE)
    if needs_overview_three_column_v12_override(next_text):
        next_text = upsert_before_render_call(next_text, OVERVIEW_THREE_COLUMN_V12_MARK, OVERVIEW_THREE_COLUMN_V12_OVERRIDE)
    if needs_auto_monitor_dock_md_v9_override(next_text):
        next_text = upsert_before_render_call(next_text, AUTO_MONITOR_DOCK_MD_V9_MARK, AUTO_MONITOR_DOCK_MD_V9_OVERRIDE)
    if needs_cad_ghost_bands_fix(next_text):
        next_text = insert_before_render_call(next_text, CAD_GHOST_BANDS_OVERRIDE)
    next_text = remove_optimization_note(next_text)
    if needs_optimization_note_removed(next_text):
        next_text = insert_before_render_call(next_text, OPTIMIZATION_NOTE_REMOVED_OVERRIDE)
    next_text = upgrade_balanced_core_columns(next_text)
    next_text = upgrade_furnace_layer_selectors(next_text)
    next_text = upgrade_diagnosis_color_override(next_text)
    next_text = upgrade_cad_tooltip_fallback(next_text)
    next_text = upgrade_fast_in_app_navigation(next_text)
    if next_text == text:
        print(f"ALREADY_PATCHED\t{TARGET}\t{TARGET.stat().st_size}\t{before_hash}")
        return
    backup = TARGET.with_name(f"{TARGET.name}.bak_8093_core_metric_groups_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(TARGET, backup)
    TARGET.write_bytes(next_text.encode("utf-8"))
    print(f"BACKUP\t{backup}\t{backup.stat().st_size}\t{sha256(backup)}")
    print(f"UPDATED\t{TARGET}\t{TARGET.stat().st_size}\t{before_hash}\t{sha256(TARGET)}")


if __name__ == "__main__":
    main()
