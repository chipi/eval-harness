/* eval catalog: theme toggle, global search, table filter and sort. */
document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}});
(function(){const q=document.getElementById('q'),box=document.getElementById('hits'),up=document.body.dataset.up;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
if(!q||!window.CATALOG)return;
/* every search box on the page (the header's; the home page's large one) searches the same index */
const pairs=[...document.querySelectorAll('.search')].map(s=>[s.querySelector('input'),s.querySelector('.hits')]).filter(p=>p[0]&&p[1]);
function attach([q,box]){
function show(){const t=q.value.trim().toLowerCase();if(t.length<2){box.hidden=true;return;}
const words=t.split(/\s+/);
/* ranked: a word in the title counts more than one in the description; goals lead ties */
const score=x=>{const ti=x.t.toLowerCase();return words.reduce((n,w)=>n+(ti.startsWith(w)?4:ti.includes(w)?3:x.d.toLowerCase().includes(w)?1:0),0)+(x.k==='goal'?1:0);};
const hits=window.CATALOG.filter(x=>words.every(w=>x.s.includes(w))).map(x=>[score(x),x]).sort((a,b)=>b[0]-a[0]).slice(0,40).map(p=>p[1]);
box.innerHTML=hits.length?hits.map(x=>`<a href="${up}${x.u}"><span class="k">${x.k}</span>${esc(x.t)}<small>${esc(x.d)}</small></a>`).join(''):'<p>No match.</p>';box.hidden=false;}
q.addEventListener('input',show);q.addEventListener('focus',show);
/* arrow keys move through the results; Enter follows the focused one */
q.closest('.search').addEventListener('keydown',ev=>{if(box.hidden||!['ArrowDown','ArrowUp'].includes(ev.key))return;
const ls=[...box.querySelectorAll('a')];if(!ls.length)return;ev.preventDefault();
const i=ls.indexOf(document.activeElement);const n=ev.key==='ArrowDown'?Math.min(i+1,ls.length-1):i-1;
(n<0?q:ls[n]).focus();});}
pairs.forEach(attach);
/* "/" goes to the page's own large search where there is one, else the header's */
const big=document.getElementById('home-q');
document.addEventListener('keydown',ev=>{if(ev.key==='/'&&!pairs.some(p=>p[0]===document.activeElement)){ev.preventDefault();
if(big)big.focus();else{document.querySelector('.bar').classList.add('searching');q.focus();}}
if(ev.key==='Escape')pairs.forEach(([i,b])=>{b.hidden=true;i.blur();});});
document.addEventListener('click',ev=>{const s=ev.target.closest('.search');pairs.forEach(([i,b])=>{if(i.closest('.search')!==s)b.hidden=true;});});
/* phones: the search is a button in the bar; it opens the search row under it and focuses it */
const sb=document.querySelector('.search-btn'),bar=document.querySelector('.bar');
if(sb)sb.addEventListener('click',()=>{const on=bar.classList.toggle('searching');sb.setAttribute('aria-expanded',on);
if(on)q.focus();else{box.hidden=true;q.blur();}});})();
document.querySelectorAll('input[data-filter]').forEach(inp=>{const t=document.getElementById(inp.dataset.filter);
inp.addEventListener('input',()=>{const w=inp.value.toLowerCase().split(/\s+/).filter(Boolean);let n=0;
t.querySelectorAll('tbody tr').forEach(r=>{if(r.classList.contains('grouphead'))return;const ok=w.every(x=>r.textContent.toLowerCase().includes(x));const show=ok&&!r.classList.contains('pout')&&!r.classList.contains('fout');r.hidden=!show;n+=show;});
const c=document.querySelector(`[data-count="${inp.dataset.filter}"]`);if(c)c.textContent=n;});});
/* sort: a header holds a button (a column head keeps its meaning), and says how its column is sorted (aria-sort).
   A cell's value is its own data-v, else its first [data-v]'s; a blank (none, or —) sorts last both ways; a value
   with data-g (a measure's name) sorts among its own group's; group headings stay out (group.js regroups after). */
document.querySelectorAll('table.sortable th').forEach(th=>{th.setAttribute('aria-sort','none');
if(!th.querySelector('input,button')&&th.textContent.trim()){const b=document.createElement('button');b.type='button';b.className='sortbtn';
while(th.firstChild)b.appendChild(th.firstChild);th.appendChild(b);}
th.addEventListener('click',ev=>{if(ev.target.closest('input')||!th.querySelector('.sortbtn'))return;const tb=th.closest('table').tBodies[0],i=th.cellIndex;
const dir=th.dataset.dir==='asc'?'desc':'asc';th.closest('tr').querySelectorAll('th').forEach(x=>{delete x.dataset.dir;x.setAttribute('aria-sort','none');});th.dataset.dir=dir;th.setAttribute('aria-sort',dir==='asc'?'ascending':'descending');
const key=r=>{const c=r.cells[i];if(!c)return{blank:true,g:''};const s=c.dataset.v!=null?c:c.querySelector('[data-v]');
const raw=(s?s.dataset.v:c.textContent).trim(),g=(s&&s.dataset.g)||'';if(raw===''||/^—/.test(raw))return{blank:true,g};
const n=parseFloat(raw);return{g,v:isNaN(n)?raw.toLowerCase():n};};
const cmp=(x,y)=>x.blank||y.blank?(x.blank&&y.blank?0:x.blank?1:-1):x.g!==y.g?(x.g<y.g?-1:1):(x.v>y.v?1:x.v<y.v?-1:0)*(dir==='asc'?1:-1);
[...tb.rows].filter(r=>!r.classList.contains('grouphead')).sort((a,b)=>cmp(key(a),key(b))).forEach(r=>tb.appendChild(r));});});
/* paging: a long table shows 10 rows at a time, "show 10 more" and "show all" below it. It pages
   the rows the filter leaves (r.hidden), so filter and sort work over every row; a link to a row
   (#anchor) opens the table at it. window.paginate(table) for tables drawn later (the inspector). */
window.paginate=function(t,step){step=step||10;if(!t||!t.tBodies[0]||'nopage' in t.dataset||t._repage)return;
let shown=step;const bar=document.createElement('p');bar.className='pager small muted';
(t.closest('.scroll-x')||t).after(bar);
const id=decodeURIComponent(location.hash.slice(1));
if(id){const at=[...t.tBodies[0].rows].findIndex(r=>r.id===id);if(at>=step)shown=Infinity;}
/* a grouped table is not paged: each group folds its own rows (group.js), and a folded row is not on the page */
t._repage=function(){const lim='grouped' in t.dataset?Infinity:shown;
const live=[...t.tBodies[0].rows].filter(r=>!r.hidden&&!r.classList.contains('grouphead')&&!r.classList.contains('gfold'));
live.forEach((r,i)=>r.classList.toggle('paged-out',i>=lim));
[...t.tBodies[0].rows].filter(r=>r.hidden||r.classList.contains('gfold')).forEach(r=>r.classList.remove('paged-out'));
const n=live.length,vis=Math.min(n,lim);
if(n<=step||'grouped' in t.dataset){bar.hidden=true;return;}bar.hidden=false;
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
/* a selection's command (RFC-023): the boxes ticked in a .cmdpick give the command to copy; the page writes nothing */
document.querySelectorAll('.cmdpick').forEach(box=>{const out=box.querySelector('code.cmd'),btn=box.querySelector('button.copy');
const upd=()=>{const v=[...box.querySelectorAll('input.cmdsel:checked')].map(i=>box.dataset.flag+' '+i.value);
const c=v.length?box.dataset.prefix+' '+v.join(' '):box.dataset.empty;out.textContent=c;
if(btn){btn.dataset.copy=v.length?c:'';btn.hidden=!v.length;}};
const all=box.querySelector('input.cmdall');
if(all)all.addEventListener('change',()=>{box.querySelectorAll('input.cmdsel').forEach(i=>{const tr=i.closest('tr');
if(!tr||!tr.hidden&&tr.style.display!=='none')i.checked=all.checked;});upd();});
box.addEventListener('change',ev=>{if(ev.target.classList.contains('cmdsel'))upd();});upd();});
/* the data page's link (UXS-004): shown only when a local catalog-serve answers its API (never on a deployment or
   a page opened from disk) */
{const api=document.body.dataset.api||'/api/';
if(location.protocol.startsWith('http')&&document.querySelector('.local-only'))fetch(api+'data/store',{cache:'no-store'})
.then(r=>{if(r.ok||r.status===401)document.body.classList.add('local-data');}).catch(()=>{});}
/* phones (catalog.css, max 640 px): a table of four or more columns stacks, one card per row, its first cell the
   card's title and every other cell named by its column. The headers are hidden there, so a sortable table gets a
   "sort by" menu that clicks them. Tables drawn later (the inspector) are stacked as they appear; the label sheet
   stays a sheet: its item column stays put while it scrolls across the arms. */
(function(){const name=th=>{const c=th.cloneNode(true);c.querySelectorAll('small,input,select,button:not(.sortbtn)').forEach(x=>x.remove());return c.textContent.trim();};
const stack=t=>{const hr=t.tHead&&t.tHead.rows[t.tHead.rows.length-1];if(!hr||hr.cells.length<4)return;const hs=[...hr.cells].map(name);
t.classList.add('stack');
for(const b of t.tBodies)for(const r of b.rows){if('stacked' in r.dataset)continue;r.dataset.stacked='';let i=0;
for(const c of r.cells){if(c.colSpan===1&&hs[i])c.dataset.label=hs[i];i+=c.colSpan;}}
if(!t.classList.contains('sortable')||t._sortsel)return;
const sel=document.createElement('select');sel.className='sortsel';sel.setAttribute('aria-label','sort by');
const opt=(v,txt)=>{const o=document.createElement('option');o.value=v;o.textContent=txt;sel.appendChild(o);};
opt('','sort by …');hs.forEach((h,i)=>{if(h){opt(i+':asc',h+' ↑');opt(i+':desc',h+' ↓');}});
sel.addEventListener('change',()=>{if(!sel.value)return;const [i,d]=sel.value.split(':'),th=hr.cells[+i];th.dataset.dir=d==='asc'?'desc':'asc';th.click();});
(t.closest('.scroll-x')||t).before(sel);t._sortsel=sel;};
const all=()=>document.querySelectorAll('main table:not(.sheet)').forEach(stack);all();
let due=false;new MutationObserver(()=>{if(due)return;due=true;requestAnimationFrame(()=>{due=false;all();});}).observe(document.body,{childList:true,subtree:true});})();
