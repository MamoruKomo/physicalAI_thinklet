const $ = id => document.getElementById(id);
let latest = null, initialized = false, pending = false, pendingCount = 0, history = [], lastSample = 0;
let actionError = null;
const text = (id, value) => { $(id).textContent = value; };
const fmt = value => Number.isFinite(value) ? value.toFixed(1) : '—';
function notice(message, error=false) { text('notice', message); $('notice').classList.toggle('error', error); }
function fillSettings(s) {
  ['threshold','hysteresis','servo_pin','lower_angle','upper_angle','home_angle'].forEach(k => $(k.replaceAll('_','-')).value = s[k]);
  $('bright-raises').value = String(s.bright_raises);
  $('hardware-confirmed').checked = s.hardware_confirmed;
  text('threshold-output', `${s.threshold}%`);
}
function render(s) {
  latest = s;
  const c=s.camera, a=s.arm, ctl=s.control, fresh=c.fresh;
  if (!initialized) { fillSettings(s.settings); initialized=true; }
  text('connection', 'ボード接続中'); $('connection').className='pill good';
  text('camera-chip',fresh?'映像受信中':c.state==='PAUSED'?'一時停止':'映像待ち');
  text('decision-chip',fresh?({up:'上げる',down:'下げる',hold:'保持'}[ctl.decision]):'入力待ち');
  text('arm-chip',a.connected?(a.armed?'制御有効':'接続済み・停止'):'未接続');
  text('live',fresh?'● LIVE':'● OFFLINE'); $('live').className=`live ${fresh?'good':''}`;
  $('preview').hidden=!fresh; $('camera-placeholder').hidden=fresh;
  text('resolution',fresh?`${c.width} × ${c.height}`:'—');
  text('exposure',`露出：${fresh?(c.exposure_locked?'固定中':c.lock_supported?'調整中':'自動'):'映像待ち'}`);
  text('brightness',fresh?fmt(ctl.brightness):'—');
  text('raw-value',`入力 ${fresh?fmt(c.brightness)+'%':'—'}`);
  $('meter-fill').style.width=`${fresh?ctl.brightness:0}%`; $('threshold-mark').style.left=`${s.settings.threshold}%`;
  text('threshold-label',`しきい値 ${s.settings.threshold}%`);
  text('light-label',fresh?({bright:'明るい',dark:'暗い',unknown:'中間'}[ctl.light]):'待機中');
  text('decision',fresh?({up:'↑ アームを上げる',down:'↓ アームを下げる',hold:'↔ 現在の位置を保つ'}[ctl.decision]):'映像待ち');
  text('decision-note',s.mode==='auto'?'Arduinoへ指令を送っています':s.mode==='manual'?'手動操作中です':'判断を表示中。アーム制御は停止しています。');
  text('mode',({stopped:'停止中',manual:'手動',auto:'自動連動'}[s.mode]));
  $('mode').className=`pill ${a.armed?'good':''}`;
  $('angle').innerHTML=`${a.commanded_angle??'—'}<small>°</small>`;
  $('target').innerHTML=`${a.target_angle??'—'}<small>°</small>`;
  $('arm-svg').style.transform=`rotate(${a.commanded_angle===null?-35:a.commanded_angle-90}deg)`;
  $('arm-svg').style.transformOrigin='130px 98px';
  text('connect',a.connected?'Arduino切断':'Arduino接続');
  $('arm-enable').disabled=pending||!a.connected||a.armed||!fresh||!s.settings.hardware_confirmed;
  ['auto','up','down'].forEach(id=>$(id).disabled=pending||!a.armed||!fresh);
  text('auto',s.mode==='auto'?'☀ 自動連動中':'☀ 明るさに連動させる');
  $('save').disabled=pending||a.armed;
  $('exposure-reset').disabled=pending||!fresh;
  text('hardware-label',s.settings.hardware_confirmed?'確認済み':'未確認');
  if (!pending) {
    if (actionError) notice(actionError,true);
    else if (!fresh) notice('カメラ映像が届いていません。THINKLETのアプリとUSB接続を確認してください。',true);
    else if (!s.settings.hardware_confirmed) notice('実カメラの明るさを計測しています。アームの配線・可動範囲を確認すると連動できます。');
    else if (!a.connected) notice('カメラ計測中です。専用ファームウェアを書き込んだArduinoを接続してください。');
    else notice(s.mode==='auto'?'自動連動中です。明るさに合わせてアームが反応します。':'アーム制御は'+(a.armed?'手動操作中':'停止中')+'です。');
  }
  $('events').replaceChildren(...s.events.map(event=>{
    const li=document.createElement('li'), t=document.createElement('time'), message=document.createElement('span');
    t.textContent=new Date(event.at*1000).toLocaleTimeString('ja-JP',{hour12:false});message.textContent=event.message;
    li.append(t,message);return li;
  }));
  if (Date.now()-lastSample>=500) { lastSample=Date.now();history.push({at:lastSample,value:fresh?ctl.brightness:null}); }
  history=history.filter(point=>point.at>Date.now()-60000); drawChart();
}
async function poll() {
  try { const response=await fetch('/api/status',{signal:AbortSignal.timeout(2500)});if(!response.ok)throw Error('ボード接続が切れました');render(await response.json()); }
  catch(error) {text('connection','ボード未接続');$('connection').className='pill warn';notice('操作ボードとの通信が切れました。アームの状態は確認できません。',true);['arm-enable','auto','up','down','save'].forEach(id=>$(id).disabled=true);}
  finally {setTimeout(poll,300);}
}
async function action(action, settings) {
  const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action,settings}),signal:AbortSignal.timeout(6000)});
  const result=await response.json();if(!response.ok)throw Error(result.error);render(result);
}
async function operate(fn, urgent=false) {
  if (pending && !urgent) return;
  actionError=null;
  pendingCount++; pending=true;
  try {await fn();}
  catch(error) {actionError=error.message;notice(error.message,true);text('settings-message',error.message);}
  finally {pendingCount--;pending=pendingCount>0;if(latest)renderControls();}
}
function renderControls() {const a=latest.arm,c=latest.camera;$('arm-enable').disabled=pending||!a.connected||a.armed||!c.fresh||!latest.settings.hardware_confirmed;['auto','up','down'].forEach(id=>$(id).disabled=pending||!a.armed||!c.fresh);$('save').disabled=pending||a.armed;$('exposure-reset').disabled=pending||!c.fresh;}
['stop','arm-enable','auto','up','down'].forEach(id=>$(id).onclick=()=>operate(()=>action(id==='arm-enable'?'arm':id),id==='stop'));
$('connect').onclick=()=>operate(()=>action(latest?.arm.connected?'disconnect':'connect'));
$('exposure-reset').onclick=()=>operate(async()=>{const r=await fetch('/api/exposure-reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const s=await r.json();if(!r.ok)throw Error(s.error);render(s);});
$('threshold').oninput=()=>text('threshold-output',`${$('threshold').value}%`);
$('settings-form').onsubmit=event=>{event.preventDefault();operate(async()=>{
 const settings={threshold:Number($('threshold').value),hysteresis:Number($('hysteresis').value),bright_raises:$('bright-raises').value==='true',hardware_confirmed:$('hardware-confirmed').checked};
 ['servo_pin','lower_angle','upper_angle','home_angle'].forEach(k=>settings[k]=Number($(k.replaceAll('_','-')).value));
 await action('configure',settings);text('settings-message','保存しました');
});};
function drawChart(){const canvas=$('chart'),r=canvas.getBoundingClientRect(),scale=devicePixelRatio||1;canvas.width=r.width*scale;canvas.height=r.height*scale;const ctx=canvas.getContext('2d');ctx.scale(scale,scale);const w=r.width,h=r.height;ctx.strokeStyle='#edf1e8';ctx.lineWidth=1;[0,25,50,75,100].forEach(v=>{ctx.beginPath();ctx.moveTo(0,h-v*h/100);ctx.lineTo(w,h-v*h/100);ctx.stroke();});ctx.setLineDash([3,4]);ctx.strokeStyle='#bacbb4';const y=h-(latest?.settings.threshold??50)*h/100;ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();ctx.setLineDash([]);ctx.strokeStyle='#508567';ctx.lineWidth=2;ctx.beginPath();let gap=true;for(const p of history){if(p.value===null){gap=true;continue;}const x=w-(Date.now()-p.at)*w/60000,y=h-p.value*h/100;if(gap)ctx.moveTo(x,y);else ctx.lineTo(x,y);gap=false;}ctx.stroke();}
async function preview(){if(latest?.camera.fresh){const img=$('preview');await new Promise(resolve=>{img.onload=img.onerror=resolve;img.src='/api/frame.jpg?t='+Date.now();setTimeout(resolve,1500);});}setTimeout(preview,350);}
setInterval(()=>text('clock',new Date().toLocaleString('ja-JP',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})),1000);
window.addEventListener('resize',drawChart);poll();preview();
