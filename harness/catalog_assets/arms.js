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
body.addEventListener('change',ev=>{if(ev.target.matches('input.pick'))repick();});
/* a pick the view stops showing is still picked: the bar says so, recounted when the view changes */
document.querySelector('input[data-filter="arms"]')?.addEventListener('input',()=>setTimeout(repick,0));
document.addEventListener('click',ev=>{if(ev.target.closest('.facet-chips,.group-chips,.row-chips,[data-gopen],[data-clearall]'))setTimeout(repick,0);});
bar&&bar.querySelector('[data-unpick]').addEventListener('click',()=>{body.querySelectorAll('input.pick:checked').forEach(p=>{p.checked=false;});repick();
document.querySelector('input[data-filter="arms"]')?.focus();});
/* the footer's command is the view's: grouping, one chip of a kind (the CLI takes one) and the period */
const term=document.querySelector('[data-elsewhere=term] code');
function viewCmd(){if(!term)return;const q=new URLSearchParams(location.search),a=['evh arms'];const g=q.get('group');
if(g&&g!=='set')a.push('--by '+(g==='scored'?'scored':g));
const only={};(q.get('only')||'').split(',').filter(Boolean).forEach(x=>{const i=x.indexOf(':');(only[x.slice(0,i)]=only[x.slice(0,i)]||[]).push(x.slice(i+1));});
const flag={where:'where',tier:'tier',weights:'weights',quality:'quality'},val={quality:{'a contender':'contender','below the leader':'below'}};
Object.entries(only).forEach(([k,v])=>{if(flag[k]&&v.length===1)a.push(`--${flag[k]} ${(val[k]||{})[v[0]]||v[0]}`);});
const p=q.get('period')||(location.hash.match(/^#p([a-z0-9]+)$/)||[])[1];if(p&&p!=='14d')a.push('--period '+p);term.textContent=a.join(' ');}
viewCmd();window.addEventListener('hashchange',viewCmd);document.addEventListener('click',()=>setTimeout(viewCmd,0));
link&&link.addEventListener('click',ev=>{if(link.getAttribute('aria-disabled')==='true')ev.preventDefault();});
/* on a phone the controls fold behind one line that says how many are on */
const tools=document.querySelector('details.arm-tools');
if(tools){const sum=tools.querySelector('summary');const count=()=>{const n=tools.querySelectorAll('.chip[aria-pressed=true]:not([data-group-by=""])').length;
sum.textContent=n?`group, filter and key · ${n} on`:'group, filter and key';};
if(matchMedia('(max-width: 640px)').matches)tools.open=false;count();tools.addEventListener('click',()=>setTimeout(count,0));}
/* headers that stay in view: when the table fits its box it need not scroll sideways, so its head and each group's
   heading can stick under the bar */
function sticky(){const w=t.closest('.scroll-x'),bar=document.querySelector('.bar');if(!w)return;
const fits=w.scrollWidth<=w.clientWidth+1;w.classList.toggle('stickyhead',fits);
const b=bar?bar.offsetHeight:0,hd=t.tHead&&t.tHead.offsetParent?t.tHead.offsetHeight:0;
t.style.setProperty('--top0',b+'px');t.style.setProperty('--top1',(b+hd)+'px');}
sticky();addEventListener('resize',sticky);document.addEventListener('click',()=>setTimeout(sticky,0));
/* one goal's trade-off charts at a time */
const sel=document.getElementById('tradeoff-goal');
sel&&sel.addEventListener('change',()=>document.querySelectorAll('[data-tradeoff]').forEach(d=>{d.hidden=d.dataset.tradeoff!==sel.value;}));})();
