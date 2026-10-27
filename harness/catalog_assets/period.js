/* The catalog's period, shared by every page that has one (#period): the chips, the line saying
   what trends compare with, the period in the link (page.html#p30d), and, on tables marked
   data-period-rows, the new badge, the in-period columns and the all / new / active chips.
   Periods are counted from today, the viewer's date; scripts/catalog_periods.py computes the
   same for evh. window.PERIOD (periods.js) holds the periods; window.PERIOD_ROWS each row's
   dated runs and spend. Without this script a page shows all time. */
(function(){const P=window.PERIOD,pick=document.getElementById('period');if(!P||!pick)return;
const DAY=864e5,iso=t=>new Date(t).toISOString().slice(0,10),at=s=>Date.parse(s+'T00:00:00Z');
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
const today=(()=>{const d=new Date();return Date.UTC(d.getFullYear(),d.getMonth(),d.getDate());})();
const mStart=(t,back)=>{const d=new Date(t);return Date.UTC(d.getUTCFullYear(),d.getUTCMonth()-(back||0),1);};
const mEnd=t=>mStart(t,-1)-DAY;
const sameDay=(first,day)=>Math.min(first+(day-1)*DAY,mEnd(first));
function bounds(key,t,first){const m=/^(\d+)d$/.exec(key);
if(m){const n=+m[1],s=t-(n-1)*DAY;return {since:iso(s),until:iso(t),prev:[iso(s-n*DAY),iso(s-DAY)]};}
const wd=(new Date(t).getUTCDay()+6)%7;
if(key==='week'){const s=t-wd*DAY;return {since:iso(s),until:iso(t),prev:[iso(s-7*DAY),iso(t-7*DAY)]};}
if(key==='lastweek'){const s=t-(wd+7)*DAY;return {since:iso(s),until:iso(s+6*DAY),prev:[iso(s-7*DAY),iso(s-DAY)]};}
if(key==='month'){const p=mStart(t,1);return {since:iso(mStart(t)),until:iso(t),prev:[iso(p),iso(sameDay(p,new Date(t).getUTCDate()))]};}
if(key==='lastmonth'){const s=mStart(t,1),p=mStart(t,2);return {since:iso(s),until:iso(mEnd(s)),prev:[iso(p),iso(mEnd(p))]};}
if(key==='year'){const d=new Date(t),y=d.getUTCFullYear(),mo=d.getUTCMonth(),da=d.getUTCDate();
const last=Date.UTC(y-1,mo,(mo===1&&da===29)?28:da);return {since:iso(Date.UTC(y,0,1)),until:iso(t),prev:[iso(Date.UTC(y-1,0,1)),iso(last)]};}
return {since:(first||iso(t)).slice(0,10),until:iso(t),prev:null};}
const within=(d,s)=>!!d&&s[0]<=d&&d<=s[1];
function trend(now,before){if(before===null)return '';if(!before)return now?'new: nothing in the previous period':'none in either period';
const pct=(now-before)/before*100;return (pct>0?'▲':pct<0?'▼':'=')+' '+Math.abs(pct).toFixed(0)+'%';}
/* short form for a badge: ▲ 12%, ▲ from 0 (nothing the period before), none */
const short=t=>/%$/.test(t)?t:t.startsWith('new')?'▲ from 0':t?'none':'';
const daysOf=(a,b)=>{const out=[];for(let t=at(a);t<=at(b);t+=DAY)out.push(iso(t));return out;};
const amount=(v,unit)=>unit==='tokens'?Math.round(v).toLocaleString('en-US')+' tokens':v<1?'$'+v.toFixed(4):'$'+v.toFixed(2);
const label=Object.fromEntries(P.periods.map(([k,l,c])=>[k,[l,c]]));
const keys=P.periods.map(p=>p[0]);
const listeners=[];let key=P.default;
const fromHash=()=>{const m=/^#p([a-z0-9]+)$/.exec(location.hash);return m&&keys.includes(m[1])?m[1]:null;};
/* rows: [data-key] rows of a table[data-period-rows], their runs [[day, arm]], spend [[day, usd]] and
   events [[day, html]] (the build writes that html, its names already escaped and linked) */
const R=window.PERIOD_ROWS||{};
const runsIn=(k,s)=>(R[k]&&R[k].runs||[]).filter(x=>within(x[0],s));
const evIn=(k,s)=>(R[k]&&R[k].events||[]).filter(x=>within(x[0],s)).sort((a,b)=>a[0]<b[0]?1:-1);
const usdIn=(k,s)=>(R[k]&&R[k].usd||[]).filter(x=>within(x[0],s)).reduce((a,x)=>a+x[1],0);
function cell(el,now,before,fmt){const t=before===null?'':short(trend(now,before));
el.dataset.v=now;el.innerHTML=esc(fmt(now))+(t&&t!=='none'?` <small class="trend">${esc(t)}</small>`:'');}
/* a row's runs per day over the period, in its table's colour; nothing when it had none */
function line(xs){if(xs.length<2||!xs.some(Boolean))return '';const top=Math.max(...xs),step=100/(xs.length-1);
const pts=xs.map((v,i)=>`${(i*step).toFixed(1)},${(17-15*v/top).toFixed(1)}`).join(' ');
return `<svg class="rowline" viewBox="0 0 100 18" preserveAspectRatio="none" aria-hidden="true"><polygon points="0,18 ${pts} 100,18" fill="var(--c)" fill-opacity="0.16"/><polyline points="${pts}" fill="none" stroke="var(--c)" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;}
let rowShow='all';
function rows(b){const s=[b.since,b.until];
document.querySelectorAll('table[data-period-rows]').forEach(t=>{let nNew=0,nAct=0;
[...t.tBodies[0].rows].forEach(r=>{const k=r.dataset.key,made=r.dataset.made||'',isNew=within(made,s);
const first=r.cells[0];first.querySelector('.new')?.remove();if(isNew)first.insertAdjacentHTML('beforeend',' <span class="new">new</span>');
const rs=runsIn(k,s),ev=evIn(k,s),act=rs.length>0||usdIn(k,s)>0||ev.length>0;nNew+=isNew;nAct+=act;r.classList.toggle('active',act);r.classList.toggle('isnew',isNew);
r.querySelectorAll('[data-flow]').forEach(c=>{const f=c.dataset.flow,pv=b.prev;
if(f==='runs')cell(c,rs.length,pv?runsIn(k,pv).length:null,v=>String(v));
else if(f==='arms')cell(c,new Set(rs.map(x=>x[1])).size,pv?new Set(runsIn(k,pv).map(x=>x[1])).size:null,v=>String(v));
else if(f==='usd')cell(c,usdIn(k,s),pv?usdIn(k,pv):null,v=>v?amount(v,'usd'):'—');
else if(f==='line')c.innerHTML=line(daysOf(b.since,b.until).map(d=>runsIn(k,[d,d]).length));
else if(f==='events')cell(c,ev.length,pv?evIn(k,pv).length:null,v=>String(v));});
r.classList.toggle('pout',rowShow==='new'?!isNew:rowShow==='active'?!act:false);});
const bar=document.querySelector(`.row-chips[data-for="${t.id}"]`);
if(bar){bar.querySelector('[data-rows="new"] b').textContent=nNew;bar.querySelector('[data-rows="active"] b').textContent=nAct;}
/* a filter that leaves nothing says so, in words, where the table was */
const box=t.closest('.scroll-x'),none=rowShow==='new'?!nNew:rowShow==='active'?!nAct:false;
let msg=box.nextElementSibling&&box.nextElementSibling.classList.contains('pempty')?box.nextElementSibling:null;
if(!msg){msg=document.createElement('p');msg.className='pempty muted';box.after(msg);}
msg.textContent=none?`Nothing ${rowShow==="new"?"new":"active"} in ${/^last \d/.test(label[key][0])?"the ":""}${label[key][0]}.`:'';msg.hidden=!none;box.hidden=none;
/* the text filter keeps its own rows hidden; a row out of the period's filter is hidden too */
const f=document.querySelector(`input[data-filter="${t.id}"]`);
if(f)f.dispatchEvent(new Event('input'));else{[...t.tBodies[0].rows].forEach(r=>{r.hidden=r.classList.contains('pout');});if(t._repage)t._repage();}});}
document.addEventListener('click',ev=>{const c=ev.target.closest('.row-chips button[data-rows]');if(!c)return;rowShow=c.dataset.rows;
document.querySelectorAll('.row-chips button[data-rows]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.rows===rowShow)));show(key,false);});
/* links to the other period pages carry the period */
/* a feed table (data-period-feed) keeps the rows of the period's days */
function feeds(b){const s=[b.since,b.until];document.querySelectorAll("table[data-period-feed]").forEach(t=>{let n=0;[...t.tBodies[0].rows].forEach(r=>{const ok=within(r.dataset.made||"",s);r.hidden=!ok;n+=ok;});const none=document.querySelector(`[data-feed-empty="${t.id}"]`);if(none)none.hidden=n>0;t.closest(".scroll-x").hidden=!n;if(t._repage)t._repage();});}
function links(){document.querySelectorAll('a[data-period-link]').forEach(a=>{a.href=a.getAttribute('href').replace(/#.*$/,'')+'#p'+key;});}
function show(k,push){key=k;const b=bounds(key,today,P.first);
pick.querySelectorAll('.chip').forEach(c=>c.setAttribute('aria-pressed',String(c.dataset.period===key)));
const sp=document.getElementById('period-span');if(sp){sp.textContent=b.prev?`▲▼ compared with ${label[key][1]}`:`since ${b.since}`;
sp.title=`${label[key][0]}: ${b.since} to ${b.until}`+(b.prev?`; compared with ${b.prev[0]} to ${b.prev[1]}`:'');}
if(push!==false&&history.replaceState)history.replaceState(null,'','#p'+key);
rows(b);feeds(b);links();listeners.forEach(fn=>fn(key,b));}
window.Period={DAY,iso,at,esc,today,bounds,within,trend,short,daysOf,amount,label,on:fn=>{listeners.push(fn);fn(key,bounds(key,today,P.first));},get key(){return key;}};
pick.hidden=false;pick.addEventListener('click',ev=>{const c=ev.target.closest('.chip');if(c)show(c.dataset.period);});
show(fromHash()||P.default,false);})();
