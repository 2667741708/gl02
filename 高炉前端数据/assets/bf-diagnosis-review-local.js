(function(){
  "use strict";
  if(window.__BF_DIAGNOSIS_REVIEW_LOCAL__) return;
  window.__BF_DIAGNOSIS_REVIEW_LOCAL__=true;

  var LABELS={normal:"正常顺行",cold:"热制度下行",hot:"热制度上行",lowline:"低料线",channel:"管道行程",hanging:"悬料",slip:"崩料",gas_abnormal:"煤气流异常"};
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
  function scoreText(value){var n=Number(value);return Number.isFinite(n)?n.toFixed(1):"0.0";}
  function formatTime(value){try{return new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}).format(new Date(value));}catch(_){return String(value||"");}}
  function coverageText(value){
    value=value||{};var ratio=value.coverage_ratio;
    if(ratio==null) ratio=value.ratio;
    if(ratio!=null){var n=Number(ratio);if(Number.isFinite(n)) return (n<=1?n*100:n).toFixed(1)+"%"+(value.available&&value.expected?"（"+value.available+"/"+value.expected+"）":"");}
    if(value.observed_variables&&value.expected_variables) return value.observed_variables+"/"+value.expected_variables;
    return "未提供";
  }
  function evidenceText(item){
    if(typeof item==="string") return item;
    if(!item||typeof item!=="object") return String(item||"");
    var title=item.title||item.variable||item.name||item.rule||"证据";
    var detail=item.detail||item.message||item.description||item.reason||item.value||"";
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
    summary.innerHTML='<div class="bfdr-meta"><div class="bfdr-meta-item"><span class="bfdr-label">诊断时间</span><span class="bfdr-value">'+escapeHtml(formatTime(ctx.diagnosis_ts))+'</span></div><div class="bfdr-meta-item"><span class="bfdr-label">异常段开始</span><span class="bfdr-value">'+escapeHtml(formatTime(ctx.episode_start_ts))+'</span></div><div class="bfdr-meta-item"><span class="bfdr-label">数据覆盖率</span><span class="bfdr-value">'+escapeHtml(coverageText(ctx.data_coverage))+'</span></div></div><div class="bfdr-primary-score"><div class="bfdr-primary-name">当前主诊断：'+escapeHtml(ctx.main_display_label||LABELS[ctx.main_label]||ctx.main_label)+'</div><div class="bfdr-primary-number">'+escapeHtml(scoreText(ctx.main_score))+' 分</div><div class="bfdr-score-note">诊断把握分表示规则符合度，不是统计概率。请结合现场工况和全部候选分数进行复核。</div></div>';
    var evidence=Array.isArray(ctx.evidence)?ctx.evidence:[];
    evidenceWrap.innerHTML=evidence.length?'<ul class="bfdr-evidence">'+evidence.map(function(item){return '<li>'+escapeHtml(evidenceText(item))+'</li>';}).join("")+'</ul>':'<div class="bfdr-empty">本次快照未提供文字证据，请结合分数和现场状态判断。</div>';
    var candidates=Array.isArray(ctx.candidates)?ctx.candidates:[];
    scoreList.innerHTML=candidates.map(function(item){var n=Math.max(0,Math.min(100,Number(item.score)||0));return '<div class="bfdr-score-row"><span class="bfdr-score-name">'+escapeHtml(item.label||LABELS[item.key]||item.key)+'</span><span class="bfdr-score-track" aria-hidden="true"><span class="bfdr-score-bar" style="width:'+n+'%"></span></span><span class="bfdr-score-value">'+escapeHtml(scoreText(item.score))+'</span></div>';}).join("");
    var auth=data.auth||{},reviewed=!!data.reviewed_by_current_user;
    authBox.classList.toggle("bfdr-hidden",!!auth.authenticated);
    form.classList.toggle("bfdr-hidden",!auth.authenticated||!auth.can_submit||reviewed);
    if(reviewed){badge.textContent="异常已复核 · "+(ctx.main_display_label||LABELS[ctx.main_label]);badge.classList.add("bfdr-hidden");}
    else{badge.textContent="异常待复核 · "+(ctx.main_display_label||LABELS[ctx.main_label])+" · "+scoreText(ctx.main_score)+"分";badge.classList.remove("bfdr-hidden");}
    if(auth.authenticated&&!auth.can_submit){authBox.classList.remove("bfdr-hidden");authBox.querySelector("h3").textContent="当前角色无权提交复核";root.querySelector(".bfdr-login").classList.add("bfdr-hidden");}
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
    state.submitting=true;submitBtn.disabled=true;submitBtn.textContent="正在提交…";setStatus(status,"正在保存本机复核事件…");
    var ctx=state.context,payload={episode_key:ctx.episode_key,snapshot_id:ctx.snapshot_id,snapshot_source:ctx.snapshot_source,verdict:selected.value,corrected_main_label:selected.value==="incorrect"?mainSelect.value:null,corrected_secondary_label:selected.value==="incorrect"?(secondarySelect.value||null):null,human_match_score:root.querySelector(".bfdr-human-score").value,suggestion:root.querySelector(".bfdr-suggestion").value,note:root.querySelector(".bfdr-note").value,idempotency_key:"review-"+(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random().toString(16).slice(2)),source_page:location.pathname+location.search,fixture_label:ctx.fixture_label,fixture_case_id:ctx.fixture_case_id};
    try{var resp=await fetch("/api/diagnosis-reviews",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(payload)});var body=await resp.json();if(!resp.ok||!body.ok)throw new Error(body.error||"提交失败");setStatus(status,body.created?"复核已保存到本机事件库。":"该复核请求已保存，无需重复提交。","success");await refresh();setTimeout(closeModal,900);}
    catch(error){setStatus(status,(error.message||"提交失败")+"。请检查后重试。","error");}finally{state.submitting=false;submitBtn.disabled=false;submitBtn.textContent="提交复核";}
  });
  window.addEventListener("bf:diagnosis-review-fixture",refresh);
  refresh();state.timer=setInterval(refresh,5000);
})();
