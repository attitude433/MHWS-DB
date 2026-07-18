"""티카투카 — 다이애나와 겨루는 주사위 보드게임 (스탠드얼론 웹).

web.py 가 /tikatuka 라우트로 GAME_HTML 을 서빙. 룰 기반 AI, 서버 상태 없음(클라이언트 전용).
룰: 3줄×3칸, 같은 숫자 배율(×3/×5), 알까기(같은 줄 같은 눈 제거→실드 재굴림), 선공 랜덤 시작 실드, 2줄 선승.
"""

GAME_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>티카투카 — 다이애나와 주사위 대결</title>
<meta property="og:title" content="티카투카 — 다이애나와 주사위 대결">
<meta property="og:description" content="다이애나와 3줄 주사위 보드게임. 알까기로 상대 주사위를 날리고 3줄 중 2줄을 이겨라!">
<meta property="og:type" content="website">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3/dist/tabler-icons.min.css">
<style>
:root{
  --bg-accent:rgba(90,150,235,0.24); --text-accent:#a9cbf5;
  --bg-danger:rgba(232,92,90,0.24); --text-danger:#f3a6a4;
  --surface-1:rgba(255,255,255,0.06);
  --text-primary:#ece9f7; --text-secondary:#b7addb; --text-muted:#7d76a0;
  --border:rgba(255,255,255,0.12); --border-strong:rgba(255,255,255,0.24); --border-accent:#5a96eb;
  --text-success:#7fe0a3; --radius:8px;
  --font-sans:-apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic",sans-serif;
}
*{box-sizing:border-box;}
body{margin:0;min-height:100vh;background:linear-gradient(160deg,#241640,#160e2b 60%,#0f0a1f);color:var(--text-primary);font-family:var(--font-sans);padding:24px 16px;}
.wrap{max-width:560px;margin:0 auto;}
.brand{text-align:center;margin-bottom:16px;}
.brand h1{font-size:22px;font-weight:600;margin:0 0 4px;}
.brand p{font-size:13px;color:var(--text-secondary);margin:0;}
.card{background:rgba(255,255,255,0.05);border:1px solid var(--border);border-radius:16px;padding:18px;}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);}
#tk button{background:rgba(255,255,255,0.06);color:var(--text-primary);border:1px solid var(--border-strong);border-radius:var(--radius);padding:8px 14px;font-size:14px;cursor:pointer;font-family:var(--font-sans);transition:background .15s;}
#tk button:hover:not(:disabled){background:rgba(255,255,255,0.13);}
#tk button:active{transform:scale(0.98);}
#tk button:disabled{cursor:default;}
.tk-tip{max-width:560px;margin:16px auto 0;font-size:12.5px;color:var(--text-muted);line-height:1.7;}
@keyframes tkOut{0%{transform:translateY(0) rotate(0);opacity:1}60%{transform:translateY(-10px) rotate(14deg);opacity:1}100%{transform:translateY(-40px) rotate(32deg) scale(0.7);opacity:0}}
.tk-out{animation:tkOut 0.5s ease forwards;}
</style>
</head>
<body>
<div class="wrap">
  <div class="brand"><h1><i class="ti ti-dice-5" aria-hidden="true"></i> 티카투카</h1><p>다이애나와 3줄 주사위 대결 · 알까기로 상대 주사위를 날려라</p></div>
  <div class="card">
    <h2 class="sr-only">티카투카 — 다이애나와 3줄 주사위 보드게임.</h2>
    <div id="tk" style="position:relative;">
      <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
        <span style="font-size:14px; font-weight:500; color:var(--text-danger);"><i class="ti ti-robot" aria-hidden="true"></i> 다이애나 <span id="tk-dfirst" style="color:var(--text-secondary);font-weight:400;"></span></span>
        <span id="tk-dscore" style="font-size:13px; color:var(--text-secondary);"></span>
      </div>
      <div id="tk-diana"></div>
      <div style="display:flex; align-items:center; gap:12px; margin:12px 0;">
        <div id="tk-diebox" style="flex:none; width:48px; height:48px; border-radius:8px; background:var(--surface-1); display:flex; align-items:center; justify-content:center; font-size:22px; font-weight:500; transition:transform 0.08s ease;"></div>
        <div id="tk-status" style="flex:1; padding:8px 12px; background:var(--surface-1); border-radius:var(--radius); min-height:40px; font-size:14px; line-height:1.5;"></div>
      </div>
      <div id="tk-me"></div>
      <div style="display:flex; align-items:center; justify-content:space-between; margin-top:6px;">
        <span style="font-size:14px; font-weight:500; color:var(--text-accent);"><i class="ti ti-user" aria-hidden="true"></i> 나 <span id="tk-mfirst" style="color:var(--text-secondary);font-weight:400;"></span></span>
        <span id="tk-mscore" style="font-size:13px; color:var(--text-secondary);"></span>
      </div>
      <div style="display:flex; gap:8px; margin-top:14px; align-items:center;">
        <button id="tk-reroll" type="button"><i class="ti ti-refresh" aria-hidden="true"></i> 리롤</button>
        <button id="tk-new" type="button"><i class="ti ti-player-play" aria-hidden="true"></i> 새 게임</button>
      </div>
    </div>
  </div>
  <div class="tk-tip">같은 줄에 같은 숫자를 모으면 배율 (2개 ×3 · 3개 ×5). 상대와 같은 줄 같은 눈을 놓으면 <b>알까기</b>로 상대 주사위가 날아가고 실드를 다시 굴려 아무 줄에나 놓아요 (실드는 제거 면역). 선공은 랜덤, 시작 실드는 자기 보드에. 양쪽 보드가 다 차면 3줄 중 2줄 이긴 쪽 승리.</div>
</div>
<script>
(function(){
  const MULT={1:1,2:3,3:5}, TD=850;
  let P,D,turn,die,phase,pending,choice,rerollLeft,firstDie,first,over,busy,animCell;

  function lineScore(line){ const g={}; line.forEach(d=>g[d.v]=(g[d.v]||0)+1); let s=0; for(const v in g) s+=Number(v)*MULT[g[v]]; return s; }
  function roll(){ return 1+Math.floor(Math.random()*6); }
  function full(b){ return b.every(l=>l.length>=3); }
  function noSlot(){ return full(P)&&full(D); }
  function bd(bn){ return bn==='P'?P:D; }

  function reset(){
    P=[[],[],[]]; D=[[],[],[]]; die=null; phase='normal'; pending=null; choice=null; animCell=null;
    rerollLeft={P:1,D:1}; over=false; busy=false;
    first=Math.random()<0.5?'P':'D'; turn=first; firstDie={P:first==='P',D:first==='D'};
    render();
    say('선공은 <b>'+(first==='P'?'당신':'다이애나')+'</b>! '+(first==='P'?'시작 실드를 놓을 줄을 고르세요.':'다이애나가 먼저 시작 실드를 놓습니다…'));
    startTurn();
  }

  function cell(d,owner,bn,line,idx){
    if(!d) return '<div style="width:40px;height:40px;border:1px dashed var(--border-strong);border-radius:6px;"></div>';
    const blue=d.by==='P';
    const bg=blue?'var(--bg-accent)':'var(--bg-danger)', fg=blue?'var(--text-accent)':'var(--text-danger)';
    const ring=d.shield?'box-shadow:0 0 0 2px '+fg+' inset;':'';
    const sh=d.shield?'<i class="ti ti-shield" style="position:absolute;top:1px;right:2px;font-size:10px;" aria-hidden="true"></i>':'';
    const hide=(animCell&&animCell.bn===bn&&animCell.line===line&&animCell.idx===idx)?'visibility:hidden;':'';
    const cls=d._removing?'tk-out':'';
    return '<div class="'+cls+'" style="position:relative;width:40px;height:40px;border-radius:6px;background:'+bg+';color:'+fg+';display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:500;'+ring+hide+'">'+d.v+sh+'</div>';
  }
  function canClick(owner,len){
    if(over||busy||turn!=='P'||choice) return false;
    if(phase==='normal') return owner==='me' && die!=null && len<3;
    if(phase==='shield') return pending!=null && len<3;
    return false;
  }
  function boardHTML(b,owner){
    const bn=owner==='me'?'P':'D'; let cols='';
    for(let i=0;i<3;i++){
      let slots=''; for(let s=0;s<3;s++) slots+=cell(b[i][s],owner,bn,i,s);
      const click=canClick(owner,b[i].length);
      const border=click?'1px solid var(--border-accent)':'0.5px solid var(--border)';
      const opp=(owner==='me'?D:P); const sc=lineScore(b[i]); const win=sc>lineScore(opp[i]);
      cols+='<div data-line="'+i+'" data-owner="'+owner+'" class="'+(click?'tk-click':'')+'" style="display:flex;flex-direction:column;gap:5px;align-items:center;padding:6px;border:'+border+';border-radius:8px;cursor:'+(click?'pointer':'default')+';">'+slots+'<div style="font-size:12px;font-weight:500;color:'+(win?'var(--text-success)':'var(--text-muted)')+';margin-top:2px;">'+sc+'</div></div>';
    }
    return '<div style="display:flex;gap:8px;justify-content:center;">'+cols+'</div>';
  }
  function render(){
    document.getElementById('tk-diana').innerHTML=boardHTML(D,'diana');
    document.getElementById('tk-me').innerHTML=boardHTML(P,'me');
    document.getElementById('tk-mfirst').textContent=first==='P'?'· 선공':'';
    document.getElementById('tk-dfirst').textContent=first==='D'?'· 선공':'';
    const pt=P.reduce((a,l)=>a+lineScore(l),0), dt=D.reduce((a,l)=>a+lineScore(l),0);
    const pw=[0,1,2].filter(i=>lineScore(P[i])>lineScore(D[i])).length;
    const dw=[0,1,2].filter(i=>lineScore(D[i])>lineScore(P[i])).length;
    document.getElementById('tk-mscore').textContent='줄 '+pw+'승 · 총 '+pt;
    document.getElementById('tk-dscore').textContent='줄 '+dw+'승 · 총 '+dt;
    const rb=document.getElementById('tk-reroll');
    rb.disabled=!(turn==='P'&&phase==='normal'&&die!=null&&!choice&&rerollLeft.P>0&&!over&&!busy);
    rb.style.opacity=rb.disabled?0.4:1;
    document.querySelectorAll('.tk-click').forEach(el=>{ el.addEventListener('mouseenter',()=>el.style.background='var(--bg-accent)'); el.addEventListener('mouseleave',()=>el.style.background='transparent'); });
  }
  function say(h){ document.getElementById('tk-status').innerHTML=h; }
  function cbtn(v){ return '<span class="tk-choice" data-cv="'+v+'" style="display:inline-flex;width:34px;height:34px;border-radius:6px;background:var(--bg-accent);color:var(--text-accent);align-items:center;justify-content:center;font-size:16px;font-weight:500;cursor:pointer;margin:0 4px;vertical-align:middle;">'+v+'</span>'; }

  function animateRoll(finalV,who,done){
    busy=true; render();
    const box=document.getElementById('tk-diebox'), blue=who==='P';
    box.style.background=blue?'var(--bg-accent)':'var(--bg-danger)';
    box.style.color=blue?'var(--text-accent)':'var(--text-danger)';
    let t=0;
    const iv=setInterval(()=>{
      box.textContent=1+Math.floor(Math.random()*6);
      box.style.transform='rotate('+(Math.random()*54-27)+'deg) scale(0.9)';
      if(++t>=13){ clearInterval(iv); box.textContent=finalV; box.style.transform='rotate(0deg) scale(1.14)'; setTimeout(()=>box.style.transform='rotate(0deg) scale(1)',130); busy=false; setTimeout(done,260); }
    },58);
  }

  function fly(bn,line,idx,value,byWho,done){
    const tk=document.getElementById('tk'), base=tk.getBoundingClientRect();
    const src=document.getElementById('tk-diebox').getBoundingClientRect();
    const board=document.getElementById(bn==='D'?'tk-diana':'tk-me');
    const col=board.querySelector('[data-line="'+line+'"]'), slot=col.children[idx], dst=slot.getBoundingClientRect();
    const blue=byWho==='P';
    const el=document.createElement('div'); el.textContent=value;
    el.style.cssText='position:absolute;width:40px;height:40px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:17px;font-weight:500;z-index:5;transition:left 0.42s cubic-bezier(.2,.75,.3,1),top 0.42s cubic-bezier(.2,.75,.3,1),transform 0.42s;background:'+(blue?'var(--bg-accent)':'var(--bg-danger)')+';color:'+(blue?'var(--text-accent)':'var(--text-danger)')+';';
    el.style.left=(src.left-base.left)+'px'; el.style.top=(src.top-base.top)+'px'; el.style.transform='scale(1.15)';
    tk.appendChild(el); el.getBoundingClientRect();
    el.style.left=(dst.left-base.left)+'px'; el.style.top=(dst.top-base.top)+'px'; el.style.transform='scale(1)';
    setTimeout(()=>{ el.remove(); done(); }, 460);
  }
  function doPlace(bn,line,obj,cb){
    const b=bd(bn); b[line].push(obj); const idx=b[line].length-1;
    animCell={bn:bn,line:line,idx:idx}; busy=true; render();
    fly(bn,line,idx,obj.v,obj.by,()=>{ animCell=null; busy=false; render(); cb&&cb(); });
  }
  function doRemove(bn,line,value,cb){
    const b=bd(bn); let cnt=0; b[line].forEach(d=>{ if(!d.shield&&d.v===value){ d._removing=true; cnt++; } });
    if(!cnt){ cb&&cb(0); return; }
    busy=true; render();
    setTimeout(()=>{ if(bn==='P') P[line]=P[line].filter(d=>!d._removing); else D[line]=D[line].filter(d=>!d._removing); busy=false; render(); cb&&cb(cnt); }, 540);
  }
  function alkFore(bn,line,value){ return bd(bn)[line].some(d=>!d.shield&&d.v===value); }
  function remDmg(line,value){ return lineScore(line)-lineScore(line.filter(d=>d.shield||d.v!==value)); }

  function startTurn(){
    if(noSlot()) return end();
    if(turn==='P'&&full(P)&&phase==='normal'){ turn='D'; return startTurn(); }
    if(turn==='D'&&full(D)){ turn='P'; return startTurn(); }
    const v=roll();
    animateRoll(v,turn,()=>{ die=v; if(turn==='P'){ say('당신 차례 — <b>'+die+'</b> 을(를) 놓을 줄을 고르세요.'+(firstDie.P?' <span style="color:var(--text-secondary)">(선공 시작 실드!)</span>':'')); render(); } else dianaTurn(); });
  }

  function dBest(v){ let bv=-1e9; for(let i=0;i<3;i++){ if(D[i].length>=3) continue; if(alkFore('P',i,v)) bv=Math.max(bv,remDmg(P[i],v)+3.5); else bv=Math.max(bv,lineScore(D[i].concat([{v:v}]))-lineScore(D[i])); } return bv; }
  function dOwnBest(w){ let si=-1,sg=-1e9; for(let i=0;i<3;i++){ if(D[i].length>=3) continue; const g=lineScore(D[i].concat([{v:w}]))-lineScore(D[i]); if(g>sg){sg=g;si=i;} } return si; }
  function dOppBlock(){ let bi=-1,be=-1; for(let i=0;i<3;i++){ const e=3-P[i].length; if(e>0&&e>be){be=e;bi=i;} } return bi; }
  function dShieldDecide(w){ if(w<=3){ let bi=dOppBlock(); if(bi>=0) return {b:'P',i:bi}; let si=dOwnBest(w); if(si>=0) return {b:'D',i:si}; } else { let si=dOwnBest(w); if(si>=0) return {b:'D',i:si}; let bi=dOppBlock(); if(bi>=0) return {b:'P',i:bi}; } return {b:'D',i:0}; }

  function dianaTurn(){
    const v=die;
    if(firstDie.D){ firstDie.D=false; const i=Math.floor(Math.random()*3); say('다이애나가 시작 실드 <b>'+v+'</b> 배치…'); doPlace('D',i,{v:v,shield:true,by:'D'},()=>{ die=null; turn='P'; say('다이애나가 '+(i+1)+'번 줄에 시작 실드 <b>'+v+'</b> 배치.'); setTimeout(startTurn,TD); }); return; }
    if(rerollLeft.D>0 && v<=2 && dBest(v)<6){ rerollLeft.D--; const v2=roll(); say('다이애나 리롤…'); render(); return animateRoll(v2,'D',()=>{ die=(dBest(v2)>dBest(v)?v2:v); dianaAct(die); }); }
    dianaAct(v);
  }
  function dianaAct(v){
    let best=-1,bv=-1e9,alk=false;
    for(let i=0;i<3;i++){ if(D[i].length>=3) continue;
      if(alkFore('P',i,v)){ const val=remDmg(P[i],v)+3.5+Math.random()*0.4; if(val>bv){bv=val;best=i;alk=true;} }
      else { const g=lineScore(D[i].concat([{v:v}]))-lineScore(D[i]); const val=g+Math.random()*0.4; if(val>bv){bv=val;best=i;alk=false;} }
    }
    if(best<0){ die=null; turn='P'; render(); return setTimeout(startTurn,300); }
    if(alk){
      say('다이애나 <b>알까기!</b> '+(best+1)+'번 줄 당신 주사위 날리는 중…');
      doRemove('P',best,v,(cnt)=>{
        const w=roll(); say('다이애나 알까기! (당신 '+v+' '+cnt+'개 제거) 실드 굴리는 중…'); render();
        animateRoll(w,'D',()=>{ const dec=dShieldDecide(w); say('다이애나 실드 <b>'+w+'</b> 배치…'); doPlace(dec.b,dec.i,{v:w,shield:true,by:'D'},()=>{ die=null; turn='P'; say('다이애나 실드 <b>'+w+'</b> → '+(dec.b==='P'?'당신':'자기')+' '+(dec.i+1)+'번 줄. <span style="color:var(--text-danger)">(당신 '+v+' '+cnt+'개 제거됨)</span>'); setTimeout(startTurn,TD); }); });
      });
    } else { say('다이애나 배치…'); doPlace('D',best,{v:v,shield:false,by:'D'},()=>{ die=null; turn='P'; say('다이애나가 '+(best+1)+'번 줄에 <b>'+v+'</b> 배치.'); setTimeout(startTurn,TD); }); }
  }

  function end(){
    over=true; die=null; phase='normal'; choice=null;
    const pt=P.reduce((a,l)=>a+lineScore(l),0), dt=D.reduce((a,l)=>a+lineScore(l),0);
    const pw=[0,1,2].filter(i=>lineScore(P[i])>lineScore(D[i])).length;
    const dw=[0,1,2].filter(i=>lineScore(D[i])>lineScore(P[i])).length;
    let res; if(pw>dw) res='<b style="color:var(--text-success)">당신 승리!</b>'; else if(dw>pw) res='<b style="color:var(--text-danger)">다이애나 승리…</b>'; else res=pt>dt?'<b style="color:var(--text-success)">동률→총점 당신 승리!</b>':(dt>pt?'<b style="color:var(--text-danger)">동률→총점 다이애나 승리…</b>':'<b>완전 무승부!</b>');
    say('게임 종료 — '+res+' <span style="color:var(--text-secondary)">(줄 '+pw+':'+dw+' · 총점 '+pt+':'+dt+')</span>'); render();
  }

  document.getElementById('tk').addEventListener('click',function(e){
    const ch=e.target.closest('.tk-choice');
    if(ch){ if(!choice) return; die=+ch.dataset.cv; choice=null; document.getElementById('tk-diebox').textContent=die; say('<b>'+die+'</b> 선택 — 놓을 줄을 고르세요.'); render(); return; }
    const col=e.target.closest('.tk-click'); if(!col) return;
    if(turn!=='P'||over||busy||choice) return;
    const i=+col.dataset.line, owner=col.dataset.owner;
    if(phase==='normal'){
      if(owner!=='me'||die==null||P[i].length>=3) return;
      const v=die;
      if(firstDie.P){ firstDie.P=false; die=null; doPlace('P',i,{v:v,shield:true,by:'P'},()=>{ turn='D'; say('당신이 '+(i+1)+'번 줄에 시작 실드 <b>'+v+'</b> 배치.'); setTimeout(startTurn,TD); }); return; }
      if(alkFore('D',i,v)){
        die=null; say('<b style="color:var(--text-accent)">알까기!</b> '+(i+1)+'번 줄 다이애나 주사위 날리는 중…');
        doRemove('D',i,v,(cnt)=>{ phase='shield'; pending=roll(); say('<b style="color:var(--text-accent)">알까기!</b> (다이애나 '+v+' '+cnt+'개 제거) 실드 굴리는 중…'); render(); animateRoll(pending,'P',()=>{ say('실드 <b>'+pending+'</b> — 놓을 줄을 고르세요 <span style="color:var(--text-secondary)">(내/다이애나 보드 아무 데나)</span>'); render(); }); });
      } else { die=null; doPlace('P',i,{v:v,shield:false,by:'P'},()=>{ turn='D'; say('당신이 '+(i+1)+'번 줄에 <b>'+v+'</b> 배치.'); setTimeout(startTurn,TD); }); }
    } else if(phase==='shield'){
      if(pending==null) return; const bn=owner==='me'?'P':'D'; if(bd(bn)[i].length>=3) return;
      const w=pending; pending=null; phase='normal';
      doPlace(bn,i,{v:w,shield:true,by:'P'},()=>{ die=null; turn='D'; say('실드 <b>'+w+'</b> → '+(owner==='me'?'내':'다이애나')+' '+(i+1)+'번 줄.'); setTimeout(startTurn,TD); });
    }
  });
  document.getElementById('tk-reroll').addEventListener('click',function(){
    if(turn!=='P'||phase!=='normal'||die==null||choice||rerollLeft.P<=0||over||busy) return;
    rerollLeft.P--; const v1=die, v2=roll();
    animateRoll(v2,'P',()=>{ choice={a:v1,b:v2}; die=null; say('리롤! 둘 중 선택 — 기존 '+cbtn(v1)+' vs 새 '+cbtn(v2)); render(); });
  });
  document.getElementById('tk-new').addEventListener('click',reset);
  reset();
})();
</script>
</body>
</html>"""
