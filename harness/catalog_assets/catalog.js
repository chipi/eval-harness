/* eval catalog: theme toggle, global search, table filter and sort. */
document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}});
(function(){const q=document.getElementById('q'),box=document.getElementById('hits'),up=document.body.dataset.up;
if(!q||!window.CATALOG)return;
function show(){const t=q.value.trim().toLowerCase();if(t.length<2){box.hidden=true;return;}
const words=t.split(/\s+/);
/* ranked: a word in the title counts more than one in the description; goals lead ties */
const score=x=>{const ti=x.t.toLowerCase();return words.reduce((n,w)=>n+(ti.startsWith(w)?4:ti.includes(w)?3:x.d.toLowerCase().includes(w)?1:0),0)+(x.k==='goal'?1:0);};
const hits=window.CATALOG.filter(x=>words.every(w=>x.s.includes(w))).map(x=>[score(x),x]).sort((a,b)=>b[0]-a[0]).slice(0,40).map(p=>p[1]);
box.innerHTML=hits.length?hits.map(x=>`<a href="${up}${x.u}"><span class="k">${x.k}</span>${x.t.replace(/[<>&]/g,'')}<small>${x.d.replace(/[<>&]/g,'')}</small></a>`).join(''):'<p>No match.</p>';box.hidden=false;}
q.addEventListener('input',show);q.addEventListener('focus',show);
/* arrow keys move through the results; Enter follows the focused one */
document.addEventListener('keydown',ev=>{if(box.hidden||!['ArrowDown','ArrowUp'].includes(ev.key))return;
const ls=[...box.querySelectorAll('a')];if(!ls.length)return;ev.preventDefault();
const i=ls.indexOf(document.activeElement);const n=ev.key==='ArrowDown'?Math.min(i+1,ls.length-1):i-1;
(n<0?q:ls[n]).focus();});
document.addEventListener('keydown',ev=>{if(ev.key==='/'&&document.activeElement!==q){ev.preventDefault();q.focus();}if(ev.key==='Escape'){box.hidden=true;q.blur();}});
document.addEventListener('click',ev=>{if(!ev.target.closest('.search'))box.hidden=true;});})();
document.querySelectorAll('input[data-filter]').forEach(inp=>{const t=document.getElementById(inp.dataset.filter);
inp.addEventListener('input',()=>{const w=inp.value.toLowerCase().split(/\s+/).filter(Boolean);let n=0;
t.querySelectorAll('tbody tr').forEach(r=>{const ok=w.every(x=>r.textContent.toLowerCase().includes(x));r.hidden=!ok;n+=ok;});
const c=document.querySelector(`[data-count="${inp.dataset.filter}"]`);if(c)c.textContent=n;});});
document.querySelectorAll('table.sortable th').forEach((th,i)=>th.addEventListener('click',()=>{const tb=th.closest('table').tBodies[0];
const dir=th.dataset.dir==='asc'?'desc':'asc';th.closest('tr').querySelectorAll('th').forEach(x=>delete x.dataset.dir);th.dataset.dir=dir;
const key=r=>{const c=r.cells[i];const v=c.dataset.v??c.textContent.trim();const n=parseFloat(v);return isNaN(n)?v.toLowerCase():n;};
[...tb.rows].sort((a,b)=>{const x=key(a),y=key(b);return (x>y?1:x<y?-1:0)*(dir==='asc'?1:-1);}).forEach(r=>tb.appendChild(r));}));
