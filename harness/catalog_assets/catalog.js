/* eval catalog: theme toggle, global search, table filter and sort. */
document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}});
(function(){const q=document.getElementById('q'),box=document.getElementById('hits'),up=document.body.dataset.up;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
if(!q||!window.CATALOG)return;
function show(){const t=q.value.trim().toLowerCase();if(t.length<2){box.hidden=true;return;}
const words=t.split(/\s+/);
/* ranked: a word in the title counts more than one in the description; goals lead ties */
const score=x=>{const ti=x.t.toLowerCase();return words.reduce((n,w)=>n+(ti.startsWith(w)?4:ti.includes(w)?3:x.d.toLowerCase().includes(w)?1:0),0)+(x.k==='goal'?1:0);};
const hits=window.CATALOG.filter(x=>words.every(w=>x.s.includes(w))).map(x=>[score(x),x]).sort((a,b)=>b[0]-a[0]).slice(0,40).map(p=>p[1]);
box.innerHTML=hits.length?hits.map(x=>`<a href="${up}${x.u}"><span class="k">${x.k}</span>${esc(x.t)}<small>${esc(x.d)}</small></a>`).join(''):'<p>No match.</p>';box.hidden=false;}
q.addEventListener('input',show);q.addEventListener('focus',show);
/* arrow keys move through the results; Enter follows the focused one */
document.addEventListener('keydown',ev=>{if(box.hidden||!['ArrowDown','ArrowUp'].includes(ev.key))return;
const ls=[...box.querySelectorAll('a')];if(!ls.length)return;ev.preventDefault();
const i=ls.indexOf(document.activeElement);const n=ev.key==='ArrowDown'?Math.min(i+1,ls.length-1):i-1;
(n<0?q:ls[n]).focus();});
document.addEventListener('keydown',ev=>{if(ev.key==='/'&&document.activeElement!==q){ev.preventDefault();document.querySelector('.bar').classList.add('searching');q.focus();}if(ev.key==='Escape'){box.hidden=true;q.blur();}});
document.addEventListener('click',ev=>{if(!ev.target.closest('.search'))box.hidden=true;});
/* phones: the search is a button in the bar; it opens the search row under it and focuses it */
const sb=document.querySelector('.search-btn'),bar=document.querySelector('.bar');
if(sb)sb.addEventListener('click',()=>{const on=bar.classList.toggle('searching');sb.setAttribute('aria-expanded',on);
if(on)q.focus();else{box.hidden=true;q.blur();}});})();
document.querySelectorAll('input[data-filter]').forEach(inp=>{const t=document.getElementById(inp.dataset.filter);
inp.addEventListener('input',()=>{const w=inp.value.toLowerCase().split(/\s+/).filter(Boolean);let n=0;
t.querySelectorAll('tbody tr').forEach(r=>{if(r.classList.contains('grouphead'))return;const ok=w.every(x=>r.textContent.toLowerCase().includes(x));const show=ok&&!r.classList.contains('pout')&&!r.classList.contains('fout');r.hidden=!show;n+=show;});
const c=document.querySelector(`[data-count="${inp.dataset.filter}"]`);if(c)c.textContent=n;});});
/* sort: a header is a button (click, or Enter/Space from the keyboard), and says how its column is sorted (aria-sort) */
document.querySelectorAll('table.sortable th').forEach((th,i)=>{th.tabIndex=0;th.setAttribute('role','button');th.setAttribute('aria-sort','none');
th.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();th.click();}});
th.addEventListener('click',()=>{const tb=th.closest('table').tBodies[0];
const dir=th.dataset.dir==='asc'?'desc':'asc';th.closest('tr').querySelectorAll('th').forEach(x=>{delete x.dataset.dir;x.setAttribute('aria-sort','none');});th.dataset.dir=dir;th.setAttribute('aria-sort',dir==='asc'?'ascending':'descending');
const key=r=>{const c=r.cells[i];const v=c.dataset.v??c.textContent.trim();const n=parseFloat(v);return isNaN(n)?v.toLowerCase():n;};
[...tb.rows].sort((a,b)=>{const x=key(a),y=key(b);return (x>y?1:x<y?-1:0)*(dir==='asc'?1:-1);}).forEach(r=>tb.appendChild(r));});});
/* paging: a long table shows 10 rows at a time, "show 10 more" and "show all" below it. It pages
   the rows the filter leaves (r.hidden), so filter and sort work over every row; a link to a row
   (#anchor) opens the table at it. window.paginate(table) for tables drawn later (the inspector). */
window.paginate=function(t,step){step=step||10;if(!t||!t.tBodies[0]||'nopage' in t.dataset||t._repage)return;
let shown=step;const bar=document.createElement('p');bar.className='pager small muted';
(t.closest('.scroll-x')||t).after(bar);
const id=decodeURIComponent(location.hash.slice(1));
if(id){const at=[...t.tBodies[0].rows].findIndex(r=>r.id===id);if(at>=step)shown=Infinity;}
t._repage=function(){const live=[...t.tBodies[0].rows].filter(r=>!r.hidden&&!r.classList.contains('grouphead'));
live.forEach((r,i)=>r.classList.toggle('paged-out',i>=shown));
[...t.tBodies[0].rows].filter(r=>r.hidden).forEach(r=>r.classList.remove('paged-out'));
const n=live.length,vis=Math.min(n,shown);
if(n<=step){bar.hidden=true;return;}bar.hidden=false;
bar.innerHTML=`Showing ${vis} of ${n}`+(vis<n?` <button type="button" class="btn small" data-more>show ${Math.min(step,n-vis)} more</button><button type="button" class="btn small" data-all>show all</button>`:` <button type="button" class="btn small" data-less>show ${step}</button>`);};
bar.addEventListener('click',ev=>{const b=ev.target.closest('button');if(!b)return;
shown='more' in b.dataset?shown+step:'all' in b.dataset?Infinity:step;t._repage();});
t._repage();};
document.querySelectorAll('table.data').forEach(t=>window.paginate(t));
document.querySelectorAll('input[data-filter]').forEach(inp=>{const t=document.getElementById(inp.dataset.filter);
inp.addEventListener('input',()=>{if(t&&t._repage)t._repage();});});
/* ?q=<text> opens a page's first table filtered by it (a model's arms: arms.html?q=<model id>) */
{const pre=new URLSearchParams(location.search).get('q'),f=document.querySelector('input[data-filter]');
if(pre&&f){f.value=pre;f.dispatchEvent(new Event('input'));}}
document.querySelectorAll('table.sortable th').forEach(th=>th.addEventListener('click',()=>{const t=th.closest('table');if(t._repage)t._repage();}));
/* a suggested command's copy button: the clipboard where the browser allows it, else select it */
document.addEventListener('click',ev=>{const b=ev.target.closest('button.copy');if(!b)return;
const done=()=>{b.textContent='copied';setTimeout(()=>{b.textContent='copy';},1500);};
const pick=()=>{const c=b.previousElementSibling;if(!c)return;const r=document.createRange();r.selectNodeContents(c);
const sel=getSelection();sel.removeAllRanges();sel.addRange(r);b.textContent='selected';};
try{navigator.clipboard.writeText(b.dataset.copy).then(done,pick);}catch(e){pick();}});
/* the menu's groups: one open at a time, and a click elsewhere closes it */
document.addEventListener('click',ev=>{document.querySelectorAll('details.navgroup[open]').forEach(d=>{if(!d.contains(ev.target))d.open=false;});});
