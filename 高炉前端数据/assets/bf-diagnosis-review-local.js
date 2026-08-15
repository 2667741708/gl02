(function(){
  "use strict";
  function boot(){
  if(window.__BF_DIAGNOSIS_REVIEW_LOCAL__) return;
  window.__BF_DIAGNOSIS_REVIEW_LOCAL__=true;

  var LABELS={normal:"正常顺行",lowline:"低料线",edge:"边缘煤气流发展",center:"边缘不足/中心过吹",channel:"管道行程",cold:"热制度下行",hot:"热制度上行",column:"崩滑料/悬料"};
  var EVIDENCE_LABELS={
    low_body_temperature:"炉体温度偏低",
    low_blast_pressure:"风压偏低",
    operation_heat_reduction:"操作减热",
    high_body_temperature:"炉体温度偏高",
    high_blast_pressure:"风压偏高",
    operation_heat_increase:"操作加热",
    low_top_temperature:"炉顶温度偏低",
    high_top_temperature:"炉顶温度偏高",
    low_gas_utilization:"煤气利用率偏低",
    high_gas_utilization:"煤气利用率偏高",
    low_permeability:"透气性偏低",
    high_permeability:"透气性偏高",
    burden_descent_abnormal:"料柱下降异常",
    pressure_difference_high:"压差偏高",
    pressure_difference_low:"压差偏低",
    sync_pending:"等待数据同步",
    window_coverage_low:"诊断窗口数据覆盖不足"
  };
  var VARIABLE_LABELS={
    P_top:"综合顶压",P_top_gas_A:"上升管压力A",P_top_gas_B:"上升管压力B",P_top_gas_C:"上升管压力C",P_top_gas_D:"上升管压力D",
    T_top:"综合顶温",T_top_A:"顶温A",T_top_B:"顶温B",T_top_C:"顶温C",T_top_D:"顶温D",
    Q_blast:"冷风流量",P_blast_cold:"冷风压力",P_blast:"热风压力",T_blast:"热风温度",
    PI:"透气性指数",DP_total:"全炉压差",DP_upper:"上部压差",DP_lower:"下部压差",GasUtil:"煤气利用率",
    L:"料线",L_south:"南探尺料线",L_north:"北探尺料线",PCI_rate:"实际喷煤速率",PCI_set:"喷煤设定",
    O2_rate:"富氧率",Q_O2:"富氧流量",TFT:"理论燃烧温度",T_taphole_1:"1号铁口温度",T_taphole_2:"2号铁口温度",
    Hopper_weight:"料罐重量",Hopper_weight_set:"料罐重量设定",P_N2:"氮气压力",Q_N2:"氮气流量"
  };
  var state={data:null,context:null,openedKey:"",submitting:false,lastFocus:null,timer:null};
  var root=document.createElement("div");
  root.id="bf-diagnosis-review-root";
  root.innerHTML='<button class="bfdr-badge bfdr-hidden" type="button" aria-haspopup="dialog"></button><div class="bfdr-backdrop bfdr-hidden"><section class="bfdr-dialog" role="dialog" aria-modal="true" aria-labelledby="bfdr-title"><header class="bfdr-header"><div><div class="bfdr-kicker">异常炉况 · 高组长人工复核</div><h2 class="bfdr-title" id="bfdr-title">等待诊断数据</h2></div><button class="bfdr-close" type="button" aria-label="关闭异常复核弹窗">×</button></header><div class="bfdr-scroll"><div class="bfdr-summary"></div><section class="bfdr-section"><h3>主要诊断证据</h3><div class="bfdr-evidence-wrap"></div></section><section class="bfdr-section"><h3>其他炉况候选分数</h3><div class="bfdr-score-list"></div></section><section class="bfdr-auth bfdr-hidden"><h3>高组长登录后可提交复核</h3><div class="bfdr-grid"><label class="bfdr-field"><span>账号</span><input class="bfdr-input bfdr-user" autocomplete="username"></label><label class="bfdr-field"><span>密码</span><input class="bfdr-input bfdr-password" type="password" autocomplete="current-password"></label></div><div class="bfdr-actions"><button class="bfdr-button bfdr-button-primary bfdr-login" type="button">登录并复核</button></div><div class="bfdr-status bfdr-auth-status" role="status" aria-live="polite"></div></section><form class="bfdr-form bfdr-hidden"><h3>人工复核标注</h3><div class="bfdr-verdicts"><label class="bfdr-verdict"><input type="radio" name="bfdr-verdict" value="correct">诊断正确</label><label class="bfdr-verdict"><input type="radio" name="bfdr-verdict" value="incorrect">诊断不正确</label><label class="bfdr-verdict"><input type="radio" name="bfdr-verdict" value="uncertain">暂无法判断</label></div><div class="bfdr-grid bfdr-correction bfdr-hidden"><label class="bfdr-field"><span>实际主炉况（必选）</span><select class="bfdr-select bfdr-main"><option value="">请选择</option></select></label><label class="bfdr-field"><span>实际次炉况（可选）</span><select class="bfdr-select bfdr-secondary"><option value="">不选择</option></select></label></div><div class="bfdr-grid bfdr-human-inputs"><label class="bfdr-field"><span>高炉长人工匹配分（可选，0-100）</span><input class="bfdr-input bfdr-human-score" type="number" min="0" max="100" step="1" inputmode="numeric" placeholder="不填写则记为未打分"></label><label class="bfdr-field"><span>高炉长建议（可选）</span><textarea class="bfdr-textarea bfdr-suggestion" maxlength="2000" placeholder="可提交现场建议；不填写可直接关闭弹窗"></textarea></label></div><label class="bfdr-field bfdr-field-full"><span>补充备注（可选）</span><textarea class="bfdr-textarea bfdr-note" maxlength="2000" placeholder="记录判断依据、现场观察或后续关注事项"></textarea></label><div class="bfdr-actions"><button class="bfdr-button bfdr-button-primary bfdr-submit" type="submit">提交复核</button><button class="bfdr-button bfdr-logout" type="button">退出登录</button></div><div class="bfdr-status bfdr-submit-status" role="status" aria-live="polite"></div></form></div></section></div>';
  document.body.appendChild(root);

  var badge=root.querySelector(".bfdr-badge"),backdrop=root.querySelector(".bfdr-backdrop"),dialog=root.querySelector(".bfdr-dialog"),closeBtn=root.querySelector(".bfdr-close"),summary=root.querySelector(".bfdr-summary"),evidenceWrap=root.querySelector(".bfdr-evidence-wrap"),scoreList=root.querySelector(".bfdr-score-list"),authBox=root.querySelector(".bfdr-auth"),form=root.querySelector(".bfdr-form"),correction=root.querySelector(".bfdr-correction"),mainSelect=root.querySelector(".bfdr-main"),secondarySelect=root.querySelector(".bfdr-secondary"),submitBtn=root.querySelector(".bfdr-submit");
  Object.keys(LABELS).forEach(function(key){
    var one=document.createElement("option"),two=document.createElement("option");
    one.value=two.value=key;one.textContent=two.textContent=LABELS[key];mainSelect.appendChild(one);secondarySelect.appendChild(two);
  });

  function escapeHtml(value){return String(value==null?"":value).replace(/[&<>"']/g,function(ch){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];});}
  function scoreText(value){if(value==null||value==="")return "--";var n=Number(value);return Number.isFinite(n)?n.toFixed(1):"--";}
  function formatTime(value){try{return new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}).format(new Date(value));}catch(_){return String(value||"");}}
  function coverageText(value){
    value=value||{};var ratio=value.coverage_ratio;
    if(ratio==null) ratio=value.ratio;
    if(ratio!=null){var n=Number(ratio);if(Number.isFinite(n)) return (n<=1?n*100:n).toFixed(1)+"%"+(value.available&&value.expected?"（"+value.available+"/"+value.expected+"）":"");}
    if(value.observed_variables&&value.expected_variables) return value.observed_variables+"/"+value.expected_variables;
    return "未提供";
  }
  function chineseDisplayName(value,fallback){
    var text=String(value==null?"":value).trim();
    if(!text) return fallback||"证据";
    if(EVIDENCE_LABELS[text]) return EVIDENCE_LABELS[text];
    if(VARIABLE_LABELS[text]) return VARIABLE_LABELS[text];
    if(LABELS[text]) return LABELS[text];
    if(/[\u3400-\u9fff]/.test(text)) return text;
    if(/^[a-z][a-z0-9_]*(?:\.[a-z0-9_-]+)?$/i.test(text)) return fallback||"诊断证据";
    return text;
  }
  function evidenceText(item){
    if(typeof item==="string") return chineseDisplayName(item,"诊断证据");
    if(!item||typeof item!=="object") return String(item||"");
    var title=chineseDisplayName(item.display_label||item.label||item.title||item.variable||item.name||item.rule,"诊断证据");
    var detail=item.detail||item.text||item.message||item.description||item.reason||item.value||"";
    return title+(detail?"："+detail:"");
  }
  function contextUrl(){
    var query=new URLSearchParams(location.search),out=new URLSearchParams();
    if(query.get("fixture")){out.set("fixture",query.get("fixture"));out.set("case_id",query.get("case_id")||"default");}
    return "/api/diagnosis-review-context"+(out.toString()?"?"+out.toString():"");
  }
  function openedStorageKey(key){return "bfdr-opened:"+key;}
  function closeModal(){backdrop.classList.add("bfdr-hidden");document.body.classList.remove("bfdr-modal-open");if(state.lastFocus&&state.lastFocus.focus) state.lastFocus.focus();}
  function openModal(){state.lastFocus=document.activeElement;backdrop.classList.remove("bfdr-hidden");document.body.classList.add("bfdr-modal-open");setTimeout(function(){closeBtn.focus();},0);}
  function setStatus(node,message,type){node.textContent=message||"";node.classList.toggle("bfdr-error",type==="error");node.classList.toggle("bfdr-success",type==="success");}
  function render(){
    var data=state.data,ctx=state.context;
    if(!data||!ctx||!ctx.available){badge.classList.add("bfdr-hidden");closeModal();return;}
    if(!ctx.is_abnormal){badge.classList.add("bfdr-hidden");closeModal();state.openedKey="";return;}
    root.querySelector(".bfdr-title").textContent=ctx.main_display_label||LABELS[ctx.main_label]||ctx.main_label;
    var mainDisplayScore=Object.prototype.hasOwnProperty.call(ctx,"display_main_score")?ctx.display_main_score:ctx.main_score,hotSource=ctx.score_sources&&ctx.score_sources.hot,scoreSourceNote=hotSource?'热制度上行统一采用ABC33 '+escapeHtml(hotSource.rule_id||"B4")+'分数；缺失或过期时显示“--”，不回退旧八类分数。':'';
    summary.innerHTML='<div class="bfdr-meta"><div class="bfdr-meta-item"><span class="bfdr-label">诊断时间</span><span class="bfdr-value">'+escapeHtml(formatTime(ctx.diagnosis_ts))+'</span></div><div class="bfdr-meta-item"><span class="bfdr-label">异常段开始</span><span class="bfdr-value">'+escapeHtml(formatTime(ctx.episode_start_ts))+'</span></div><div class="bfdr-meta-item"><span class="bfdr-label">数据覆盖率</span><span class="bfdr-value">'+escapeHtml(coverageText(ctx.data_coverage))+'</span></div></div><div class="bfdr-primary-score"><div class="bfdr-primary-name">当前主诊断：'+escapeHtml(ctx.main_display_label||LABELS[ctx.main_label]||ctx.main_label)+'</div><div class="bfdr-primary-number">'+escapeHtml(scoreText(mainDisplayScore))+' 分</div><div class="bfdr-score-note">诊断把握分表示规则符合度，不是统计概率。请结合现场工况和全部候选分数进行复核。'+scoreSourceNote+'</div></div>';
    var evidence=Array.isArray(ctx.evidence)?ctx.evidence:[];
    evidenceWrap.innerHTML=evidence.length?'<ul class="bfdr-evidence">'+evidence.map(function(item){return '<li>'+escapeHtml(evidenceText(item))+'</li>';}).join("")+'</ul>':'<div class="bfdr-empty">本次快照未提供文字证据，请结合分数和现场状态判断。</div>';
    var candidates=Array.isArray(ctx.candidates)?ctx.candidates:[];
    scoreList.innerHTML=candidates.map(function(item){var n=Math.max(0,Math.min(100,Number(item.score)||0)),name=chineseDisplayName(item.display_label||item.label||LABELS[item.key]||item.key,"其他炉况");return '<div class="bfdr-score-row"><span class="bfdr-score-name">'+escapeHtml(name)+'</span><span class="bfdr-score-track" aria-hidden="true"><span class="bfdr-score-bar" style="width:'+n+'%"></span></span><span class="bfdr-score-value">'+escapeHtml(scoreText(item.score))+'</span></div>';}).join("");
    var auth=data.auth||{},reviewed=!!data.reviewed_by_current_user,canSubmit=!!auth.can_submit,loginRequired=auth.login_required!==false;
    root.querySelector(".bfdr-login").classList.remove("bfdr-hidden");
    authBox.classList.toggle("bfdr-hidden",canSubmit||!loginRequired);
    form.classList.toggle("bfdr-hidden",!canSubmit||reviewed);
    root.querySelector(".bfdr-logout").classList.toggle("bfdr-hidden",!auth.authenticated);
    if(reviewed){badge.textContent="异常已复核 · "+(ctx.main_display_label||LABELS[ctx.main_label]);badge.classList.add("bfdr-hidden");}
    else{badge.textContent="异常待复核 · "+(ctx.main_display_label||LABELS[ctx.main_label])+" · "+scoreText(mainDisplayScore)+"分";badge.classList.remove("bfdr-hidden");}
    if(loginRequired&&auth.authenticated&&!canSubmit){authBox.classList.remove("bfdr-hidden");authBox.querySelector("h3").textContent="当前角色无权提交复核";root.querySelector(".bfdr-login").classList.add("bfdr-hidden");}
    var hasOpened=localStorage.getItem(openedStorageKey(ctx.episode_key))==="1";
    if(!reviewed&&!hasOpened){localStorage.setItem(openedStorageKey(ctx.episode_key),"1");state.openedKey=ctx.episode_key;openModal();}
  }
  async function refresh(){
    try{var resp=await fetch(contextUrl(),{cache:"no-store",credentials:"same-origin"});var body=await resp.json();if(!resp.ok||!body.ok) throw new Error(body.error||"诊断复核数据读取失败");if(!body.enabled){clearInterval(state.timer);return;}state.data=body;state.context=body.context;render();}
    catch(error){if(!state.context){badge.textContent="异常复核数据暂不可用，点击重试";badge.classList.remove("bfdr-hidden");}badge.dataset.error=String(error.message||error);}
  }
  badge.addEventListener("click",function(){if(badge.dataset.error) refresh();if(state.context&&state.context.is_abnormal) openModal();});
  closeBtn.addEventListener("click",closeModal);
  backdrop.addEventListener("mousedown",function(event){if(event.target===backdrop) closeModal();});
  document.addEventListener("keydown",function(event){
    if(backdrop.classList.contains("bfdr-hidden")) return;
    if(event.key==="Escape"){event.preventDefault();closeModal();return;}
    if(event.key==="Tab"){var focusable=Array.prototype.slice.call(dialog.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled])')).filter(function(el){return el.offsetParent!==null;});if(!focusable.length)return;var first=focusable[0],last=focusable[focusable.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}
  });
  root.querySelector(".bfdr-login").addEventListener("click",async function(){
    var button=this,status=root.querySelector(".bfdr-auth-status");button.disabled=true;setStatus(status,"正在登录…");
    try{var resp=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({username:root.querySelector(".bfdr-user").value,password:root.querySelector(".bfdr-password").value})});var body=await resp.json();if(!resp.ok||!body.ok)throw new Error(body.message||body.error||"登录失败");root.querySelector(".bfdr-password").value="";setStatus(status,"登录成功。","success");await refresh();}
    catch(error){setStatus(status,error.message||"登录失败，请重试。","error");}finally{button.disabled=false;}
  });
  root.querySelector(".bfdr-logout").addEventListener("click",async function(){await fetch("/api/auth/logout",{method:"POST",credentials:"same-origin"});await refresh();});
  form.addEventListener("change",function(){var selected=form.querySelector('input[name="bfdr-verdict"]:checked');correction.classList.toggle("bfdr-hidden",!selected||selected.value!=="incorrect");});
  form.addEventListener("submit",async function(event){
    event.preventDefault();if(state.submitting||!state.context)return;var selected=form.querySelector('input[name="bfdr-verdict"]:checked'),status=root.querySelector(".bfdr-submit-status");
    if(!selected){setStatus(status,"请选择复核结论。","error");return;}if(selected.value==="incorrect"&&!mainSelect.value){setStatus(status,"诊断不正确时必须选择实际主炉况。","error");mainSelect.focus();return;}if(mainSelect.value&&secondarySelect.value===mainSelect.value){setStatus(status,"实际主炉况与次炉况不能相同。","error");return;}
    state.submitting=true;submitBtn.disabled=true;submitBtn.textContent="正在提交…";setStatus(status,"正在保存复核事件…");
    var ctx=state.context,payload={episode_key:ctx.episode_key,snapshot_id:ctx.snapshot_id,snapshot_source:ctx.snapshot_source,verdict:selected.value,corrected_main_label:selected.value==="incorrect"?mainSelect.value:null,corrected_secondary_label:selected.value==="incorrect"?(secondarySelect.value||null):null,human_match_score:root.querySelector(".bfdr-human-score").value,suggestion:root.querySelector(".bfdr-suggestion").value,note:root.querySelector(".bfdr-note").value,idempotency_key:"review-"+(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random().toString(16).slice(2)),source_page:location.pathname+location.search,fixture_label:ctx.fixture_label,fixture_case_id:ctx.fixture_case_id};
    try{var resp=await fetch("/api/diagnosis-reviews",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(payload)});var body=await resp.json();if(!resp.ok||!body.ok)throw new Error(body.error||"提交失败");setStatus(status,body.created?"复核已保存到事件库。":"该复核请求已保存，无需重复提交。","success");await refresh();setTimeout(closeModal,900);}
    catch(error){setStatus(status,(error.message||"提交失败")+"。请检查后重试。","error");}finally{state.submitting=false;submitBtn.disabled=false;submitBtn.textContent="提交复核";}
  });
  window.addEventListener("bf:diagnosis-review-fixture",refresh);
  refresh();state.timer=setInterval(refresh,5000);
  }
  function bootWhenBodyReady(){if(!document.body)return false;boot();return true;}
  if(!bootWhenBodyReady()){
    var bootPoll=setInterval(function(){if(bootWhenBodyReady())clearInterval(bootPoll);},50);
    document.addEventListener("DOMContentLoaded",function(){if(bootWhenBodyReady())clearInterval(bootPoll);},{once:true});
  }
})();
