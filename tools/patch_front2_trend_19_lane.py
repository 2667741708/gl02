"""Install the 19-variable foreman-style lane chart on the front2 trend page.

Requirement: REQ-TREND-19-LANE-MERGE-20260807.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "高炉前端数据" / "front2" / "frontend_dashboard_front2.server.html"
MARKER = "REQ-TREND-19-LANE-MERGE-20260807"


LANE_OVERRIDE = r'''
/* REQ-TREND-19-LANE-MERGE-20260807: one foreman-style plane for all 19 Chronos targets. */
const TREND_LANE_COLORS=['#2f8cff','#23c8a5','#ffbd3d','#ff6b5e','#8eb4ff','#38d9f5','#74d65c','#ff8a3d','#d0e75a','#e06a9c','#5ea8ff','#29d2c0','#f0a83a','#e96363','#9acb55','#4cc2ff','#f58f49','#70d687','#c4a6ff'];
function trendLaneNumber(id,value){const shown=displayValue(id,value),number=Number(shown);return Number.isFinite(number)?number:null}
function trendLaneStats(buf,id,minutes){const values=vals(buf,id,minutes).map(value=>trendLaneNumber(id,value)).filter(Number.isFinite).sort((a,b)=>a-b);if(!values.length)return{median:0,scale:1};const medianValue=quantileSorted(values,.5),q10=quantileSorted(values,.1),q90=quantileSorted(values,.9),scale=Math.max(Math.abs(q90-q10),Math.abs(medianValue||0)*.008,.0001);return{median:medianValue,scale}}
function trendLaneOption(buf,ids,minutes,extra={}){const historyMinutes=Number(extra.historyMinutes||minutes||480),reserveMinutes=Number(extra.reserveMinutes||120),historyTimes=(buf.timestamps||[]).slice(-historyMinutes);if(!historyTimes.length)return null;const current=historyTimes[historyTimes.length-1],currentMs=new Date(current).getTime(),start=historyTimes[0],end=new Date(currentMs+reserveMinutes*60000).toISOString(),top=96,bottom=4,spacing=ids.length>1?(top-bottom)/(ids.length-1):92,centers=ids.map((_,index)=>top-index*spacing),stats=Object.fromEntries(ids.map(id=>[id,trendLaneStats(buf,id,historyMinutes)])),project=(id,raw)=>{const index=ids.indexOf(id),stat=stats[id],deviation=Math.max(-1.4,Math.min(1.4,(raw-stat.median)/stat.scale));return centers[index]+deviation*spacing*.32},series=[];ids.forEach((id,index)=>{const row=ROW_BY_ID[id]||{id,name:id,unit:''},historyValues=vals(buf,id,historyMinutes),historyData=historyTimes.map((timestamp,valueIndex)=>{const raw=trendLaneNumber(id,historyValues[valueIndex]);return[timestamp,raw===null?null:project(id,raw),raw,'历史',id]}),color=TREND_LANE_COLORS[index%TREND_LANE_COLORS.length];series.push({id:`${id}-history`,name:row.name,type:'line',smooth:.12,showSymbol:false,connectNulls:false,sampling:'lttb',lineStyle:{width:2.15,color},emphasis:{focus:'series',lineStyle:{width:3.4}},blur:{lineStyle:{opacity:.18}},data:historyData});const allFutureTimes=buf.forecastTimestamps||[],forecastValues=buf[`${id}__forecast`]||[],futureData=allFutureTimes.map((timestamp,futureIndex)=>[timestamp,forecastValues[futureIndex]]).filter(item=>{const ms=new Date(item[0]).getTime();return Number.isFinite(ms)&&ms>=currentMs&&ms<=currentMs+reserveMinutes*60000}).map(item=>{const raw=trendLaneNumber(id,item[1]);return[item[0],raw===null?null:project(id,raw),raw,'预测',id]}).filter(validPoint);if(futureData.length){const lastHistory=[...historyData].reverse().find(point=>Number.isFinite(Number(point[2])));if(lastHistory&&new Date(futureData[0][0]).getTime()>currentMs)futureData.unshift([current,lastHistory[1],lastHistory[2],'预测',id]);series.push({id:`${id}-forecast`,name:row.name,type:'line',smooth:.12,showSymbol:false,connectNulls:false,lineStyle:{width:1.9,type:'dashed',color},emphasis:{focus:'series',lineStyle:{width:3.2}},blur:{lineStyle:{opacity:.18}},data:futureData,z:5})}});if(series[0])series[0].markArea={silent:true,itemStyle:{color:'rgba(36,122,214,.12)'},label:{color:'#bfe8ff',fontSize:11},data:[[{name:'预测区',xAxis:current},{xAxis:end}]]};return{backgroundColor:'transparent',animation:false,color:TREND_LANE_COLORS,legend:{type:'scroll',top:1,left:8,right:8,itemWidth:14,itemHeight:7,itemGap:8,textStyle:{color:'#b8d2e9',fontSize:9},pageIconColor:'#fff',pageIconInactiveColor:'rgba(118,128,145,.36)',pageTextStyle:{color:'#8fb4d5',fontSize:9},data:ids.map(id=>ROW_BY_ID[id]?.name||id)},grid:{left:94,right:18,top:43,bottom:32},tooltip:{trigger:'axis',confine:true,backgroundColor:'rgba(3,14,29,.96)',borderColor:'#1f7cc2',textStyle:{color:'#eaf6ff',fontSize:11},extraCssText:'max-height:70vh;overflow-y:auto;',axisPointer:{type:'line',lineStyle:{color:'#dcecff',width:1}},formatter:parameters=>{const rows=(parameters||[]).filter(parameter=>parameter.value&&Number.isFinite(Number(parameter.value[2]))),seen=new Set(),content=[];rows.forEach(parameter=>{const value=parameter.value,id=value[4],status=value[3],key=`${id}-${status}`;if(seen.has(key))return;seen.add(key);const row=ROW_BY_ID[id]||{name:id,unit:''},raw=Number(value[2]),digits=Math.abs(raw)>=1000?0:Math.abs(raw)>=100?1:2;content.push(`${parameter.marker}${row.name}（${status}）：<b>${raw.toLocaleString('zh-CN',{maximumFractionDigits:digits})}</b>${displayUnit(id,row.unit||'')}`)});return rows.length?`${fmtTime(rows[0].value[0],'full')}<br/>${content.join('<br/>')}`:''}},xAxis:{type:'time',min:start,max:end,boundaryGap:false,axisLine:{lineStyle:{color:'#2a6fa7'}},axisLabel:{color:'#a8c3dd',formatter:value=>fmtTime(value,'hm'),fontSize:10,hideOverlap:true},splitLine:{show:false}},yAxis:{type:'value',min:bottom,max:top,interval:spacing,axisLine:{show:true,lineStyle:{color:'#2a6fa7'}},axisTick:{show:false},axisLabel:{color:'#c7dbed',fontSize:10,margin:8,formatter:value=>{let nearest=0;centers.forEach((center,index)=>{if(Math.abs(center-value)<Math.abs(centers[nearest]-value))nearest=index});return ROW_BY_ID[ids[nearest]]?.name||ids[nearest]}},splitLine:{show:true,lineStyle:{color:'rgba(79,143,193,.18)',type:'dashed'}}},dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}]}}
;(function(){if(document.getElementById('trend-19-lane-merge-style'))return;const element=document.createElement('style');element.id='trend-19-lane-merge-style';element.textContent=`.trend-chart-stack.trend-lane-single{display:grid!important;grid-template-rows:minmax(0,1fr)!important;gap:0!important;min-height:0!important;overflow:hidden!important}.trend-chart-stack.trend-lane-single>.panel{height:100%!important;min-height:0!important}.trend-chart-stack.trend-lane-single>.panel>.panel-body{min-height:0!important;overflow:hidden!important;padding:4px 6px 6px!important}.trend-chart-stack.trend-lane-single .trend-lane-chart{height:100%!important;min-height:0!important}@media(max-width:1100px){.trend-chart-stack.trend-lane-single{min-height:760px!important;overflow:visible!important}}`;document.head.appendChild(element)})();
TrendTab=function({buf,requestChronos,predStatus,autoPredictMinutes,setAutoPredictMinutes}){const[displayMinutes,setDisplayMinutes]=useState(480),predictHorizonMinutes=120,mins=displayMinutes,avail=Math.min(mins,buf.timestamps.length||mins),predictIds=TREND_PREDICT_IDS,rows=trendRows(buf,avail,predictIds),ins=[...trendInsights('gas',mins,buf),...trendInsights('heat',mins,buf),...trendInsights('flow',mins,buf)].slice(0,4),requestAll=()=>requestChronos?.(predictIds);return <div className="screen trend-grid vertical-analysis"><div className="toolbar trend-toolbar"><div className="seg">{[[60,'1小时'],[240,'4小时'],[480,'8小时']].map(item=><button key={item[0]} className={displayMinutes===item[0]?'active':''} onClick={()=>setDisplayMinutes(item[0])}>{item[1]}</button>)}</div><div className="forecast-badge">展示窗口：最近 {displayMinutes/60}小时 / 可用 {avail} 分钟</div><div className="forecast-badge">预测输入：按目标自动取2小时或8小时 / 预测未来{predictHorizonMinutes}分钟</div><div className="forecast-badge">高炉大模型预测：自动间隔 {autoPredictMinutes?`${autoPredictMinutes}分钟`:'关闭'}</div><label className="forecast-badge">自动<select value={autoPredictMinutes} onChange={event=>setAutoPredictMinutes?.(Number(event.target.value))} style={{marginLeft:6,background:'#041d3a',color:'#dcecff',border:'1px solid #247cc1',borderRadius:4,height:24}}><option value={0}>关闭</option><option value={5}>5分钟</option><option value={10}>10分钟</option><option value={15}>15分钟</option><option value={30}>30分钟</option></select></label><div style={{flex:1}}></div><button className="forecast-btn" onClick={requestAll} disabled={predStatus==='running'}>{predStatus==='running'?'高炉大模型预测中':'生成全部未来曲线'}</button></div><div className="trend-chart-stack trend-lane-single"><Panel title="19个核心变量趋势与预测" note="工长趋势式同一平面：实线为历史，虚线为预测；悬停查看原始值"><ChartBox option={trendLaneOption(buf,predictIds,mins,{historyMinutes:mins,reserveMinutes:predictHorizonMinutes})} className="trend-lane-chart"/></Panel></div><div className="trend-analysis-stack"><Panel title="高炉大模型预测分析"><ChronosPanel buf={buf} ids={predictIds} predStatus={predStatus}/></Panel><Panel title="关键指标变化"><table className="table trend-table"><thead><tr><th>指标</th><th>当前</th><th>窗口起点</th><th>{displayMinutes/60}小时变化</th><th>预测终点</th><th>结论</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{row.name}</td><td>{fmtNum(row.v,2)}</td><td>{fmtNum((row.v??0)-(row.dc??0),2)}</td><td className={(row.dc||0)>0?'text-bad':'text-good'}>{fmtNum(row.dc,2)}</td><td>{displayNum(row.id,forecastEnd(buf,row.id),2)}</td><td>{row.note}</td></tr>)}</tbody></table></Panel><Panel title="趋势解读"><div className="trend-insights">{ins.map((text,index)=><div className="evidence-item" key={index}>{text}</div>)}</div></Panel></div></div>};
'''

MISSING_SERIES_RETURN = "dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}]}}"
BROKEN_SERIES_RETURN = "dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}],series}"
FIXED_SERIES_RETURN = "dataZoom:[{type:'inside',filterMode:'none',zoomOnMouseWheel:true,moveOnMouseMove:true}],series}}"
LANE_OVERRIDE = LANE_OVERRIDE.replace(MISSING_SERIES_RETURN, FIXED_SERIES_RETURN)
LANE_OVERRIDE = LANE_OVERRIDE.replace(BROKEN_SERIES_RETURN, FIXED_SERIES_RETURN)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch() -> bool:
    text = TARGET.read_text(encoding="utf-8")
    if MARKER in text:
        if BROKEN_SERIES_RETURN in text:
            TARGET.write_text(text.replace(BROKEN_SERIES_RETURN, FIXED_SERIES_RETURN, 1), encoding="utf-8", newline="")
            print(f"Repaired lane function closure: {TARGET}")
            return True
        if MISSING_SERIES_RETURN in text:
            TARGET.write_text(text.replace(MISSING_SERIES_RETURN, FIXED_SERIES_RETURN, 1), encoding="utf-8", newline="")
            print(f"Repaired missing lane series: {TARGET}")
            return True
        print(f"Already patched: {TARGET}")
        return False

    old_map = "chronosMap={PI_mean:'PI',DP_total_mean:'DP_total',DP_lower_mean:'DP_lower',DP_upper_mean:'DP_upper',GasUtil_mean:'GasUtil',T_top_selected_mean:'T_top',T_top_mean:'T_top',T_top_A_mean:'T_top_A',T_top_B_mean:'T_top_B',T_top_C_mean:'T_top_C',T_top_D_mean:'T_top_D',Q_blast_mean:'Q_blast',T_blast_mean:'T_blast',P_top_mean:'P_top',PCI_mean:'PCI_rate'},normId=id=>chronosMap[id]||id"
    new_map = "chronosMap={P_top_mean:'P_top',P_top_gas_A_mean:'P_top_gas_A',P_top_gas_B_mean:'P_top_gas_B',P_top_gas_C_mean:'P_top_gas_C',P_top_gas_D_mean:'P_top_gas_D',T_top_selected_mean:'T_top',T_top_mean:'T_top',T_top_A_mean:'T_top_A',T_top_B_mean:'T_top_B',T_top_C_mean:'T_top_C',T_top_D_mean:'T_top_D',Q_blast_mean:'Q_blast',P_blast_cold_mean:'P_blast_cold',P_blast_mean:'P_blast',T_blast_mean:'T_blast',PI_mean:'PI',DP_total_mean:'DP_total',DP_upper_mean:'DP_upper',DP_lower_mean:'DP_lower',GasUtil_mean:'GasUtil',PCI_mean:'PCI_rate'},normId=id=>chronosMap[id]||String(id||'').replace(/_mean$/,'')"
    text = replace_once(text, old_map, new_map, "Chronos result map")

    old_targets = "target_ids:['PI','DP_total','DP_lower','DP_upper','GasUtil','T_top','T_top_A','T_top_B','T_top_C','T_top_D']"
    text = replace_once(text, old_targets, "target_ids:TREND_PREDICT_IDS", "automatic target list")

    old_filter = "target_ids:(ids||[]).filter(id=>['PI','DP_total','DP_lower','DP_upper','GasUtil','T_top','T_top_A','T_top_B','T_top_C','T_top_D'].includes(id))"
    new_filter = "target_ids:(ids||[]).filter(id=>TREND_PREDICT_IDS.includes(id))"
    text = replace_once(text, old_filter, new_filter, "manual target filter")

    anchor = "function firstValidHistoryTime(option,curMs,fallback)"
    text = replace_once(text, anchor, f"{LANE_OVERRIDE}\n{anchor}", "lane component anchor")
    TARGET.write_text(text, encoding="utf-8", newline="")
    print(f"Patched: {TARGET}")
    return True


if __name__ == "__main__":
    patch()
