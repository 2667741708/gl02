(function(){
  "use strict";
  if(window.__BF_DIAGNOSIS_MANUAL_SCORE_LOCAL__) return;
  window.__BF_DIAGNOSIS_MANUAL_SCORE_LOCAL__=true;

  var LABELS={normal:"正常顺行",lowline:"低料线",edge:"边缘煤气流发展",center:"边缘不足/中心过吹",channel:"管道行程",cold:"热制度下行",hot:"热制度上行",column:"崩滑料/悬料"};
  var ALIASES={"正常顺行":"normal","低料线":"lowline","边缘煤气流发展":"edge","边缘不足/中心过吹":"center","管道行程":"channel","炉凉":"cold","热制度下行":"cold","炉热":"hot","热制度上行":"hot","崩滑料/悬料":"column"};
  var state={context:null,data:null,targetLabel:null,lastFocus:null,submitting:false};
  var root=document.createElement("div");
  root.id="bf-diagnosis-manual-score-root";
  root.innerHTML='<div class="bfdms-backdrop bfdms-hidden"><section class="bfdms-dialog" role="dialog" aria-modal="true" aria-labelledby="bfdms-title"><header class="bfdms-header"><div><div class="bfdms-kicker">高炉长人工评分 · 当前诊断时间点</div><h2 class="bfdms-title" id="bfdms-title">炉况人工评分</h2></div><button class="bfdms-close" type="button" aria-label="关闭高炉长评分弹窗">×</button></header><div class="bfdms-scroll"><div class="bfdms-summary"></div><p class="bfdms-note">系统诊断分保持不变。人工评分作为同一诊断时间点的独立记录保存；直接关闭不会写入评分，仪表盘显示“未打分”。</p><section class="bfdms-auth bfdms-hidden"><h3>登录后可提交高炉长评分</h3><div class="bfdms-grid"><label class="bfdms-field"><span>账号</span><input class="bfdms-input bfdms-user" autocomplete="username"></label><label class="bfdms-field"><span>密码</span><input class="bfdms-input bfdms-password" type="password" autocomplete="current-password"></label></div><div class="bfdms-actions"><button class="bfdms-button bfdms-primary bfdms-login" type="button">登录并评分</button><button class="bfdms-button bfdms-cancel" type="button">关闭</button></div><div class="bfdms-status bfdms-auth-status" role="status" aria-live="polite"></div></section><form class="bfdms-form bfdms-hidden"><h3>填写人工判断</h3><div class="bfdms-grid"><label class="bfdms-field"><span>人工匹配分（0-100，可选）</span><input class="bfdms-input bfdms-score" type="number" min="0" max="100" step="1" inputmode="numeric" placeholder="不填写则为未打分"></label><label class="bfdms-field bfdms-field-full"><span>高炉长建议（可选）</span><textarea class="bfdms-textarea bfdms-suggestion" maxlength="2000" placeholder="填写现场建议；评分和建议至少填写一项"></textarea></label></div><div class="bfdms-actions"><button class="bfdms-button bfdms-primary bfdms-submit" type="submit">保存评分/建议</button><button class="bfdms-button bfdms-cancel" type="button">关闭且不保存</button><button class="bfdms-button bfdms-logout" type="button">退出登录</button></div><div class="bfdms-status bfdms-submit-status" role="status" aria-live="polite"></div></form></div></section></div>';
  document.body.appendChild(root);
  var backdrop=root.querySelector(".bfdms-backdrop"),dialog=root.querySelector(".bfdms-dialog"),closeButton=root.querySelector(".bfdms-close"),summary=root.querySelector(".bfdms-summary"),authBox=root.querySelector(".bfdms-auth"),form=root.querySelector(".bfdms-form"),submitButton=root.querySelector(".bfdms-submit");

  function escapeHtml(value){return String(value==null?"":value).replace(/[&<>"']/g,function(ch){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];});}
  function formatTime(value){try{return new Intl.DateTimeFormat("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false}).format(new Date(value));}catch(_){return String(value||"");}}
  function contextUrl(){var input=new URLSearchParams(location.search),out=new URLSearchParams();if(input.get("fixture")){out.set("fixture",input.get("fixture"));out.set("case_id",input.get("case_id")||"default");}return "/api/diagnosis-review-context"+(out.toString()?"?"+out.toString():"");}
  function setStatus(node,message,type){node.textContent=message||"";node.classList.toggle("bfdms-error",type==="error");node.classList.toggle("bfdms-success",type==="success");}
  function close(){backdrop.classList.add("bfdms-hidden");document.body.classList.remove("bfdms-modal-open");state.targetLabel=null;if(state.lastFocus&&state.lastFocus.focus)state.lastFocus.focus();}
  function open(){state.lastFocus=document.activeElement;backdrop.classList.remove("bfdms-hidden");document.body.classList.add("bfdms-modal-open");setTimeout(function(){closeButton.focus();},0);}
  function render(){
    var ctx=state.context,data=state.data,key=state.targetLabel;if(!ctx||!key)return;
    var systemScore=Number((ctx.raw_scores||{})[key]||0),auth=data.auth||{};
    root.querySelector(".bfdms-title").textContent="人工评分："+(LABELS[key]||key);
    summary.innerHTML='<div class="bfdms-meta"><div class="bfdms-meta-item"><span class="bfdms-label">对应诊断时间</span><span class="bfdms-value">'+escapeHtml(formatTime(ctx.diagnosis_ts))+'</span></div><div class="bfdms-meta-item"><span class="bfdms-label">系统规则符合度</span><span class="bfdms-value">'+escapeHtml(systemScore.toFixed(1))+' 分</span></div><div class="bfdms-meta-item"><span class="bfdms-label">系统主诊断</span><span class="bfdms-value">'+escapeHtml(ctx.main_display_label||LABELS[ctx.main_label]||ctx.main_label)+'</span></div><div class="bfdms-meta-item"><span class="bfdms-label">评分状态</span><span class="bfdms-value">未打分</span></div></div>';
    authBox.classList.toggle("bfdms-hidden",!!auth.authenticated);
    form.classList.toggle("bfdms-hidden",!auth.authenticated||!auth.can_submit);
    if(auth.authenticated&&!auth.can_submit){authBox.classList.remove("bfdms-hidden");authBox.querySelector("h3").textContent="当前角色无权提交高炉长评分";root.querySelector(".bfdms-login").classList.add("bfdms-hidden");}
  }
  async function loadContext(){var response=await fetch(contextUrl(),{cache:"no-store",credentials:"same-origin"}),body=await response.json();if(!response.ok||!body.ok)throw new Error(body.error||"诊断评分上下文读取失败");if(!body.context||!body.context.available)throw new Error("当前没有可评分的诊断时间点");state.data=body;state.context=body.context;render();}
  async function openForLabel(key){if(!LABELS[key])return;state.targetLabel=key;root.querySelector(".bfdms-score").value="";root.querySelector(".bfdms-suggestion").value="";setStatus(root.querySelector(".bfdms-submit-status"),"");try{await loadContext();open();}catch(error){state.targetLabel=null;window.alert(error.message||"无法打开人工评分");}}
  function installTargets(){
    document.querySelectorAll(".diag-rank-card").forEach(function(card){
      var name=card.querySelector(".diag-rank-name"),key=name&&ALIASES[String(name.textContent||"").trim()];if(!key)return;
      name.textContent=LABELS[key];card.dataset.bfdmsLabel=key;card.setAttribute("role","button");card.setAttribute("tabindex","0");card.setAttribute("aria-label","为"+LABELS[key]+"提交高炉长评分");
    });
  }
  document.addEventListener("click",function(event){var card=event.target.closest&&event.target.closest(".diag-rank-card[data-bfdms-label]");if(card)openForLabel(card.dataset.bfdmsLabel);});
  document.addEventListener("keydown",function(event){
    var card=event.target.closest&&event.target.closest(".diag-rank-card[data-bfdms-label]");if(card&&(event.key==="Enter"||event.key===" ")){event.preventDefault();openForLabel(card.dataset.bfdmsLabel);return;}
    if(!backdrop.classList.contains("bfdms-hidden")&&event.key==="Escape"){event.preventDefault();close();}
  });
  closeButton.addEventListener("click",close);root.querySelectorAll(".bfdms-cancel").forEach(function(button){button.addEventListener("click",close);});backdrop.addEventListener("mousedown",function(event){if(event.target===backdrop)close();});
  root.querySelector(".bfdms-login").addEventListener("click",async function(){var button=this,status=root.querySelector(".bfdms-auth-status");button.disabled=true;setStatus(status,"正在登录…");try{var response=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify({username:root.querySelector(".bfdms-user").value,password:root.querySelector(".bfdms-password").value})}),body=await response.json();if(!response.ok||!body.ok)throw new Error(body.message||body.error||"登录失败");root.querySelector(".bfdms-password").value="";setStatus(status,"登录成功。","success");await loadContext();}catch(error){setStatus(status,error.message||"登录失败，请重试。","error");}finally{button.disabled=false;}});
  root.querySelector(".bfdms-logout").addEventListener("click",async function(){await fetch("/api/auth/logout",{method:"POST",credentials:"same-origin"});await loadContext();});
  form.addEventListener("submit",async function(event){
    event.preventDefault();if(state.submitting||!state.context||!state.targetLabel)return;var status=root.querySelector(".bfdms-submit-status"),score=root.querySelector(".bfdms-score").value,suggestion=root.querySelector(".bfdms-suggestion").value.trim();
    if(score===""&&!suggestion){setStatus(status,"请填写人工匹配分或建议；如不填写可直接关闭。","error");return;}var numeric=score===""?null:Number(score);if(numeric!==null&&(!Number.isInteger(numeric)||numeric<0||numeric>100)){setStatus(status,"人工匹配分必须是0到100的整数。","error");return;}
    state.submitting=true;submitButton.disabled=true;submitButton.textContent="正在保存…";setStatus(status,"正在保存对应时间点的人工记录…");var ctx=state.context,payload={snapshot_id:ctx.snapshot_id,snapshot_source:ctx.snapshot_source,target_label:state.targetLabel,human_match_score:score,suggestion:suggestion,idempotency_key:"manual-score-"+(crypto.randomUUID?crypto.randomUUID():Date.now()+"-"+Math.random().toString(16).slice(2)),source_page:location.pathname+location.search,fixture_label:ctx.fixture_label,fixture_case_id:ctx.fixture_case_id};
    try{var response=await fetch("/api/diagnosis-manual-scores",{method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",body:JSON.stringify(payload)}),body=await response.json();if(!response.ok||!body.ok)throw new Error(body.error||"保存失败");setStatus(status,body.created?"人工评分/建议已保存。":"该请求已保存，无需重复提交。","success");setTimeout(close,900);}catch(error){setStatus(status,(error.message||"保存失败")+"。请检查后重试。","error");}finally{state.submitting=false;submitButton.disabled=false;submitButton.textContent="保存评分/建议";}
  });
  var observer=new MutationObserver(installTargets);observer.observe(document.documentElement,{childList:true,subtree:true});window.addEventListener("hashchange",function(){setTimeout(installTargets,50);});installTargets();setInterval(installTargets,1500);
})();
