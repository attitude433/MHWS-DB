"""1대1 승부 웹 페이지 (/duel/<id>). commands.web 의 Flask app 에 라우트 등록."""
from __future__ import annotations
from flask import jsonify, request

from commands import duel
from commands.web import app


@app.route('/duel/<mid>')
def duel_page(mid):
    return PAGE.replace('__MID__', mid)


@app.route('/api/duel/<mid>')
def duel_state(mid):
    s = duel.state(mid, request.args.get('t', ''))
    return jsonify(s) if s else (jsonify({'error': '없는 승부예요'}), 404)


@app.route('/api/duel/<mid>/join', methods=['POST'])
def duel_join(mid):
    return jsonify(duel.join(mid, (request.json or {}).get('nick', '')))


@app.route('/api/duel/<mid>/act', methods=['POST'])
def duel_act(mid):
    body = request.json or {}
    return jsonify(duel.act(mid, body.get('t', ''), body.get('hand', '')))


PAGE = r"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>⚔️ 다이애나 승부</title>
<meta property="og:title" content="⚔️ 1대1 승부">
<meta property="og:description" content="참가자는 닉네임 입력, 나머지는 관전!">
<style>
:root{--bg:#120b1f;--card:rgba(255,255,255,.06);--line:rgba(255,255,255,.12);--txt:#f1eaff;--sub:#a99bc4;--gold:#ffd166;--win:#4ade80;--lose:#f87171;--pri:#8b5cf6}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(circle at 50% 0,#3b1f66,var(--bg) 70%);color:var(--txt);font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;display:flex;justify-content:center;padding:24px 16px}
.wrap{width:100%;max-width:480px}
h1{font-size:20px;text-align:center;margin:0 0 4px}
.meta{text-align:center;color:var(--sub);font-size:14px;margin-bottom:18px}
.meta b{color:var(--gold)}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:14px}
.vs{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;text-align:center}
.name{font-weight:700;font-size:15px;word-break:break-all}
.st{font-size:12px;color:var(--sub);margin-top:4px;min-height:16px}
.big{font-size:56px;height:72px;line-height:72px;margin-top:8px}
.vsx{color:var(--sub);font-weight:700}
.me .name{color:var(--gold)}
.msg{text-align:center;font-size:18px;font-weight:700;min-height:26px;margin:4px 0 0}
.btns{display:flex;gap:10px;justify-content:center}
button{font:inherit;border:0;border-radius:12px;padding:14px 18px;background:var(--pri);color:#fff;font-weight:700;cursor:pointer;font-size:16px}
button:disabled{opacity:.35;cursor:default}
.hand{font-size:34px;padding:12px 18px;background:rgba(255,255,255,.1)}
input{font:inherit;width:100%;padding:12px;border-radius:10px;border:1px solid var(--line);background:rgba(0,0,0,.25);color:var(--txt);margin-bottom:10px}
.ghost{background:transparent;border:1px solid var(--line);color:var(--sub)}
.hist{font-size:13px;color:var(--sub);text-align:center;line-height:1.8}
.win{color:var(--win)}.lose{color:var(--lose)}
.shake{animation:sh .25s infinite}
@keyframes sh{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
.pop{animation:pp .35s}
@keyframes pp{0%{transform:scale(.4);opacity:0}100%{transform:scale(1);opacity:1}}
.hide{display:none}
</style></head><body><div class="wrap">
<h1>⚔️ 1대1 승부</h1>
<div class="meta" id="meta">불러오는 중…</div>

<div class="card hide" id="joinBox">
  <div style="margin-bottom:10px">참가자는 카톡 닉네임을 입력해주세요</div>
  <input id="nick" placeholder="카톡 닉네임" maxlength="40">
  <div class="btns"><button id="joinBtn">입장</button><button class="ghost" id="watchBtn">관전하기</button></div>
  <div class="st" id="joinErr" style="text-align:center"></div>
</div>

<div class="hide" id="game">
  <div class="card">
    <div class="vs">
      <div id="pa"><div class="name" id="na"></div><div class="st" id="sa"></div><div class="big" id="ba"></div></div>
      <div class="vsx">VS</div>
      <div id="pb"><div class="name" id="nb"></div><div class="st" id="sb"></div><div class="big" id="bb"></div></div>
    </div>
    <div class="msg" id="msg"></div>
  </div>
  <div class="card hide" id="ctrl"><div class="btns" id="btns"></div></div>
  <div class="hist" id="hist"></div>
</div>
</div>
<script>
const MID='__MID__', KEY='duel_'+MID, E={'가위':'✌️','바위':'✊','보':'✋'};
const DICE=['','⚀','⚁','⚂','⚃','⚄','⚅'];
const $=id=>document.getElementById(id);
const esc=t=>String(t).replace(/[&<>"']/g,c=>'&#'+c.charCodeAt(0)+';');
const ls=(k,v)=>{try{return v===undefined?localStorage.getItem(k):localStorage.setItem(k,v)}catch(e){return null}};
let token=ls(KEY)||'', watching=!!token||!!ls(KEY+'_w');
let S=null, shownHist=0, shownPick={a:null,b:null}, anim=false;

const face=(g,v)=>g==='rps'?E[v]:DICE[v];
function spin(el,g,v,done){
  anim=true;el.classList.remove('pop');
  if(g==='rps'){el.textContent='✊';el.classList.add('shake')}
  let i=0;const t=setInterval(()=>{if(g==='dice')el.textContent=DICE[1+Math.floor(Math.random()*6)];
    if(++i>=10){clearInterval(t);el.classList.remove('shake');el.textContent=face(g,v);el.classList.add('pop');anim=false;done&&done()}},90);
}
async function api(p,b){const r=await fetch('/api/duel/'+MID+p,b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{});return r.json()}

$('joinBtn').onclick=async()=>{
  const n=$('nick').value.trim(); if(!n)return;
  const r=await api('/join',{nick:n});
  if(r.error){$('joinErr').textContent=r.error;return}
  if(r.token){token=r.token;ls(KEY,token)}
  else{alertBox('참가자가 아니라서 관전으로 들어가요')}
  enter();
};
$('watchBtn').onclick=()=>{ls(KEY+'_w','1');enter()};
function alertBox(t){$('joinErr').textContent=t}
function enter(){watching=true;$('joinBox').classList.add('hide');$('game').classList.remove('hide');tick()}

async function act(hand){$('btns').querySelectorAll('button').forEach(b=>b.disabled=true);await api('/act',{t:token,hand});tick()}

function render(){
  const s=S,g=s.game;
  const left=s.status==='playing'?` · ${Math.floor(s.left/60)}:${String(s.left%60).padStart(2,'0')}`:'';
  $('meta').innerHTML=`${s.game_kr} · <b>${s.amount.toLocaleString()}제니</b>${left}`;
  $('na').textContent=s.nick.a;$('nb').textContent=s.nick.b;
  $('pa').className=s.me==='a'?'me':'';$('pb').className=s.me==='b'?'me':'';

  // 새 판 결과 연출
  if(s.history.length>shownHist&&!anim){
    const h=s.history[s.history.length-1];shownHist=s.history.length;shownPick={a:null,b:null};
    $('msg').textContent=g==='rps'?'가위바위보!':'';
    let n=0;const fin=()=>{if(++n<2)return;
      $('msg').innerHTML=h.w===null?'비겼어요! 다시 한 번':(`<span class="win">🏆 ${esc(s.nick[h.w])} 승리!</span>`);
      renderHist();setTimeout(()=>{if(S.status==='playing'){$('ba').textContent='';$('bb').textContent=''}render()},h.w===null?1500:0)};
    spin($('ba'),g,h.a,fin);spin($('bb'),g,h.b,fin);return;
  }
  if(anim)return;

  for(const r of ['a','b']){
    const v=s.picks[r],el=$('b'+r),st=$('s'+r);
    if(!s.joined[r])st.textContent='입장 대기';
    else if(v===null||v===undefined)st.textContent=g==='rps'?'고르는 중…':'굴리는 중…';
    else st.textContent=g==='rps'?'냈어요':'굴렸어요';
    if(s.status!=='playing')st.textContent='';
    if(g==='dice'&&typeof v==='number'&&shownPick[r]!==v){shownPick[r]=v;spin(el,g,v)}
    else if(g==='rps'&&r===s.me&&typeof v==='string'&&shownPick[r]!==v){shownPick[r]=v;el.textContent=E[v]}
    else if(g==='rps'&&v===true&&!el.textContent)el.textContent='❔';
  }

  if(s.status==='done'){$('msg').innerHTML=`<span class="win">🏆 ${esc(s.nick[s.winner])} 승리! +${s.amount.toLocaleString()}제니</span>`}
  else if(s.status==='void'){$('msg').innerHTML=`<span class="lose">승부 무효 (${esc(s.reason)})</span>`}
  else if(!s.history.length||s.history[s.history.length-1].w!==null)$('msg').textContent=s.me?'':'관전 중';

  const mine=s.me&&s.status==='playing'&&(s.picks[s.me]===null||s.picks[s.me]===undefined);
  $('ctrl').classList.toggle('hide',!(s.me&&s.status==='playing'));
  const want=g==='rps'?'rps':'dice';
  if($('btns').dataset.k!==want){
    $('btns').dataset.k=want;
    $('btns').innerHTML=g==='rps'?['가위','바위','보'].map(h=>`<button class="hand" data-h="${h}">${E[h]}</button>`).join(''):'<button data-h="">🎲 굴리기</button>';
    $('btns').querySelectorAll('button').forEach(b=>b.onclick=()=>act(b.dataset.h));
  }
  $('btns').querySelectorAll('button').forEach(b=>b.disabled=!mine);
  renderHist();
}
function renderHist(){
  const s=S;$('hist').innerHTML=s.history.map((h,i)=>`${i+1}판 · ${s.nick.a} ${face(s.game,h.a)} vs ${face(s.game,h.b)} ${s.nick.b} · ${h.w===null?'비김':s.nick[h.w]+' 승'}`)
    .map(esc).join('<br>');
}
async function tick(){
  try{const r=await fetch('/api/duel/'+MID+'?t='+encodeURIComponent(token));
    if(!r.ok){$('meta').textContent='없거나 끝난 승부예요';return}
    S=await r.json();render();
    if(S.status==='playing'||anim)setTimeout(tick,1000);
  }catch(e){setTimeout(tick,2000)}
}
(async()=>{
  const r=await fetch('/api/duel/'+MID);
  if(!r.ok){$('meta').textContent='없거나 끝난 승부예요';return}
  S=await r.json();
  if(watching||S.status!=='playing')enter();
  else{$('meta').textContent=`${S.game_kr} · ${S.amount.toLocaleString()}제니`;$('joinBox').classList.remove('hide')}
})();
</script></body></html>"""
