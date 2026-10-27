/* The arms page (scripts/catalog_arms.py): pick arms on one dataset and open them in the inspector,
   and show one goal's trade-off charts at a time. Grouping and facets are group.js's, the period
   parts period.js's. */
(function(){const t=document.getElementById('arms');if(!t)return;const body=t.tBodies[0];
/* comparing: the inspector compares arms on one dataset, so a pick across datasets says why it cannot */
const bar=document.querySelector('.compare-bar'),link=bar&&bar.querySelector('[data-compare]');
function repick(){const ps=[...body.querySelectorAll('input.pick:checked')];if(!bar)return;bar.hidden=!ps.length;
bar.querySelector('[data-picked]').textContent=`${ps.length} picked`;const ds=new Set(ps.map(p=>p.dataset.ds));
const ok=ps.length>0&&ds.size===1;link.classList.toggle('disabled',!ok);link.setAttribute('aria-disabled',String(!ok));
link.href=ok?'inspect.html?runs='+ps.map(p=>encodeURIComponent(p.dataset.arm).replace(/%2F/g,'/')).join(','):'#';
bar.querySelector('[data-why]').textContent=ok?'':'the inspector compares arms on one dataset: pick arms of one';}
body.addEventListener('change',ev=>{if(ev.target.matches('input.pick'))repick();});
bar&&bar.querySelector('[data-unpick]').addEventListener('click',()=>{body.querySelectorAll('input.pick:checked').forEach(p=>{p.checked=false;});repick();});
link&&link.addEventListener('click',ev=>{if(link.getAttribute('aria-disabled')==='true')ev.preventDefault();});
/* one goal's trade-off charts at a time */
const sel=document.getElementById('tradeoff-goal');
sel&&sel.addEventListener('change',()=>document.querySelectorAll('[data-tradeoff]').forEach(d=>{d.hidden=d.dataset.tradeoff!==sel.value;}));})();
