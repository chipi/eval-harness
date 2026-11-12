/* The arms page (scripts/catalog_arms.py): pick arms on one dataset and open them in the inspector,
   and show one goal's trade-off charts at a time. Grouping and facets are group.js's, the period
   parts period.js's. */
(function(){const t=document.getElementById('arms');if(!t)return;const body=t.tBodies[0];
/* comparing: the inspector compares arms on one dataset, so a pick across datasets says why it cannot */
const bar=document.querySelector('.compare-bar'),link=bar&&bar.querySelector('[data-compare]');
function repick(){const ps=[...body.querySelectorAll('input.pick:checked')];if(!bar)return;bar.hidden=!ps.length;
const unseen=ps.filter(p=>!p.closest('tr').offsetParent).length;
bar.querySelector('[data-picked]').textContent=`${ps.length} picked`+(unseen?`, ${unseen} of them not shown here (the filter, the chips or a folded group)`:'');const ds=new Set(ps.map(p=>p.dataset.ds));
const ok=ps.length>0&&ds.size===1;link.classList.toggle('disabled',!ok);link.setAttribute('aria-disabled',String(!ok));if(ok)link.removeAttribute('tabindex');else link.tabIndex=-1;
link.href=ok?'inspect.html?runs='+ps.map(p=>encodeURIComponent(p.dataset.arm).replace(/%2F/g,'/')).join(','):'#';
bar.querySelector('[data-why]').textContent=ok?'':'the inspector compares arms on one dataset: pick arms of one';}
function keepPicks(){const q=new URLSearchParams(location.search),ps=[...body.querySelectorAll('input.pick:checked')].map(p=>p.dataset.arm);
if(ps.length)q.set('pick',ps.join(','));else q.delete('pick');const s=q.toString();try{history.replaceState(null,'',location.pathname+(s?'?'+s:'')+location.hash);}catch(e){}}
{const want=(new URLSearchParams(location.search).get('pick')||'').split(',').filter(Boolean);if(want.length){body.querySelectorAll('input.pick').forEach(p=>{if(want.includes(p.dataset.arm))p.checked=true;});setTimeout(repick,0);}}
body.addEventListener('change',ev=>{if(ev.target.matches('input.pick')){repick();keepPicks();}});
/* a pick the view stops showing is still picked: the bar says so, recounted when the view changes */
document.querySelector('input[data-filter="arms"]')?.addEventListener('input',()=>setTimeout(repick,0));
document.addEventListener('click',ev=>{if(ev.target.closest('.facet-chips,.group-chips,.row-chips,[data-gopen],[data-clearall]'))setTimeout(repick,0);});
bar&&bar.querySelector('[data-unpick]').addEventListener('click',()=>{body.querySelectorAll('input.pick:checked').forEach(p=>{p.checked=false;});repick();
document.querySelector('input[data-filter="arms"]')?.focus();keepPicks();});
/* the sort kept in the address too (column and direction); a shared link opens sorted */
t.tHead.addEventListener('click',()=>setTimeout(()=>{const th=t.tHead.querySelector('th[data-dir]');if(!th)return;const q=new URLSearchParams(location.search);
q.set('sort',`${th.cellIndex}:${th.dataset.dir}`);try{history.replaceState(null,'',location.pathname+'?'+q+location.hash);}catch(e){}},0));
{const m=/^(\d+):(asc|desc)$/.exec(new URLSearchParams(location.search).get('sort')||'');const th=m&&t.tHead.rows[0].cells[+m[1]];
if(th&&th.querySelector('.sortbtn')){th.dataset.dir=m[2]==='asc'?'desc':'asc';setTimeout(()=>th.click(),0);}}
/* the footer's command is the view's: grouping, one chip of a kind (the CLI takes one) and the period */
const term=document.querySelector('[data-elsewhere=term] code');
function viewCmd(){if(!term)return;const q=new URLSearchParams(location.search),a=['evh arms'];const g=q.get('group');
if(g&&g!=='set')a.push('--by '+(g==='scored'?'scored':g));
const only={};(q.get('only')||'').split(',').filter(Boolean).forEach(x=>{const i=x.indexOf(':');(only[x.slice(0,i)]=only[x.slice(0,i)]||[]).push(x.slice(i+1));});
const flag={where:'where',tier:'tier',weights:'weights',quality:'quality'},val={quality:{'a contender':'contender','below the leader':'below'}};
const dropped=[];Object.entries(only).forEach(([k,v])=>{if(flag[k]&&v.length===1)a.push(`--${flag[k]} ${(val[k]||{})[v[0]]||v[0]}`);else if(flag[k])dropped.push(k);});
const p=q.get('period')||(location.hash.match(/^#p([a-z0-9]+)$/)||[])[1];if(p&&p!=='14d')a.push('--period '+p);term.textContent=a.join(' ');
let note=term.parentElement.querySelector('[data-cmd-note]');if(!note){note=document.createElement('small');note.dataset.cmdNote='';note.className='muted';term.after(note);}
note.textContent=dropped.length?` (the terminal takes one chip of a kind: ${dropped.join(', ')} left out)`:'';}
viewCmd();window.addEventListener('hashchange',viewCmd);if(window.Period)Period.on(()=>setTimeout(viewCmd,0));document.addEventListener('click',()=>setTimeout(viewCmd,0));
link&&link.addEventListener('click',ev=>{if(link.getAttribute('aria-disabled')==='true')ev.preventDefault();});
/* on a phone the controls fold behind one line that says how many are on */
const tools=document.querySelector('details.arm-tools');
if(tools){const sum=tools.querySelector('summary');const count=()=>{const n=tools.querySelectorAll('.chip[aria-pressed=true]:not([data-group-by=""]):not([data-group-by="set"]):not([data-rows="all"])').length;
sum.textContent=n?`group, filter and key · ${n} on`:'group, filter and key';};
if(matchMedia('(max-width: 640px)').matches)tools.open=false;count();tools.addEventListener('click',()=>setTimeout(count,0));}
/* headers that stay in view: when the table fits its box it need not scroll sideways, so its head and each group's
   heading can stick under the bar */
function sticky(){const w=t.closest('.scroll-x'),bar=document.querySelector('.bar');if(!w)return;
const fits=w.scrollWidth<=w.clientWidth+1;w.classList.toggle('stickyhead',fits);
const b=bar?bar.offsetHeight:0,hd=t.tHead&&t.tHead.offsetParent?t.tHead.offsetHeight:0;
t.style.setProperty('--top0',b+'px');t.style.setProperty('--top1',(b+hd)+'px');
/* focus moved by the keyboard lands below the bar, the head and a group's heading, not under them (WCAG 2.4.11) */
const gh=fits?(t.querySelector('tr.grouphead')||{offsetHeight:0}).offsetHeight:0;document.documentElement.style.scrollPaddingTop=(b+(fits?hd+gh:0)+8)+'px';}
sticky();addEventListener('resize',sticky);document.addEventListener('click',()=>setTimeout(sticky,0));
/* one goal's trade-off charts at a time */
const sel=document.getElementById('tradeoff-goal');
sel&&sel.addEventListener('change',()=>document.querySelectorAll('[data-tradeoff]').forEach(d=>{d.hidden=d.dataset.tradeoff!==sel.value;}));})();
/* the phone's sort menu offers only the columns shown: the dataset column leaves while a heading names the dataset
   (catalog.js builds the menu after this script and before the grouping applies, so it is pruned when both are done) */
(function(){const t=document.getElementById('arms');if(!t)return;let all=null;
function prune(){const box=t.closest('.scroll-x')||t,sel=box.previousElementSibling;if(!sel||!sel.classList.contains('sortsel'))return;
if(!all)all=[...sel.options].map(o=>[o.value,o.textContent]);const cells=t.tHead.rows[0].cells;sel.innerHTML='';
all.forEach(([v,txt])=>{const i=v?+v.split(':')[0]:-1;if(i<0||getComputedStyle(cells[i]).display!=='none'){const o=document.createElement('option');o.value=v;o.textContent=txt;sel.appendChild(o);}});}
addEventListener('load',()=>setTimeout(prune,0));document.addEventListener('click',ev=>{if(ev.target.closest('.group-chips'))setTimeout(prune,0);});})();
