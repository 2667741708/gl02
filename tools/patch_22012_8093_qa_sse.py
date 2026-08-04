from pathlib import Path

path = Path(r"F:\高炉炼铁项目-real-sensor-v2_V4_8093_PREVIEW\高炉前端数据\frontend_dashboard_v3.server.html")
text = path.read_text(encoding="utf-8")
marker = "/* OPS-8093-QA-SSE-ROBUST-V1: QA text uses SSE; the 8768 WebSocket is data-only. */"
if marker in text:
    print("already_present")
    raise SystemExit(0)
needle = "setTimeout(qaMountMarkdownObserver,0);"
idx = text.find(needle)
if idx < 0:
    raise SystemExit("qa markdown observer anchor not found")
block = r'''/* OPS-8093-QA-SSE-ROBUST-V1: QA text uses SSE; the 8768 WebSocket is data-only. */
async function qaServerChatStream(payload,{onStart,onDelta,onFinal}={}){
  if(typeof ReadableStream==='undefined'){const data=await qaServerJson('/api/qa/chat',{method:'POST',body:JSON.stringify({...payload,stream:false})});onFinal?.(data);return data}
  const res=await fetch('/api/qa/chat',{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream'},body:JSON.stringify({...payload,stream:true})});
  const contentType=(res.headers.get('content-type')||'').toLowerCase();
  if(!res.ok)throw new Error(`接口 HTTP ${res.status}`);
  if(!res.body||!contentType.includes('text/event-stream')){let data=null;try{data=await res.json()}catch(e){}if(!data||data.ok===false)throw new Error(data?.error||'接口未返回流式内容');onFinal?.(data);return data}
  const reader=res.body.getReader(),decoder=new TextDecoder('utf-8');let buffer='',eventName='message',dataLines=[],finalData=null,errorData=null;
  const dispatch=()=>{if(!dataLines.length)return;const raw=dataLines.join('\n');let obj;try{obj=JSON.parse(raw)}catch(e){obj={raw}}if(eventName==='start')onStart?.(obj);else if(eventName==='delta')onDelta?.(obj);else if(eventName==='final'){finalData=obj;onFinal?.(obj)}else if(eventName==='error')errorData=obj;eventName='message';dataLines=[]};
  while(true){const part=await reader.read();if(part.done)break;buffer+=decoder.decode(part.value,{stream:true});const lines=buffer.split(/\r?\n/);buffer=lines.pop()||'';for(const line of lines){if(line===''){dispatch();continue}if(line.startsWith('event:'))eventName=line.slice(6).trim()||'message';else if(line.startsWith('data:'))dataLines.push(line.slice(5).trimStart())}}
  if(buffer.trim()){if(buffer.startsWith('data:'))dataLines.push(buffer.slice(5).trimStart());else dataLines.push(buffer.trim())}dispatch();if(errorData)throw new Error(errorData.error||'问答流式接口失败');return finalData||{}
}'''
text = text[:idx + len(needle)] + "\n" + block + text[idx + len(needle):]
path.write_text(text, encoding="utf-8")
print("patched", path)
