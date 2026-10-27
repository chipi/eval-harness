/* The arms page (scripts/catalog_arms.py): group the table of arms, keep only some (local or
   hosted, a price tier), pick arms on one dataset and open them in the inspector, and show one
   goal's trade-off charts at a time. The period parts are period.js's. */
(function(){const t=document.getElementById('arms');if(!t)return;const body=t.tBodies[0];
const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
const cols=t.tHead.rows[0].cells.length;let by=new URLSearchParams(location.search).get('group')||'';
const label={dataset:'dataset',config:'config',model:'model',provider:'provider',scored:'scored against'};
/* grouping: the rows sorted by the group's value (stable, so a column's sort holds inside a group),
   a heading row before each group naming it and counting its arms */
function regroup(){body.querySelectorAll('tr.grouphead').forEach(r=>r.remove());
document.querySelectorAll('.group-chips button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.groupBy===by)));
if(!by){if(t._repage)t._repage();return;}
const rows=[...body.rows];const key=r=>r.dataset[by]||'';
rows.sort((a,b)=>key(a)<key(b)?-1:key(a)>key(b)?1:0).forEach(r=>body.appendChild(r));
let last=null;[...body.rows].forEach(r=>{const k=key(r);if(k===last)return;last=k;
const n=rows.filter(x=>key(x)===k).length,h=document.createElement('tr');h.className='grouphead';
h.innerHTML=`<td colspan="${cols}"><span class="muted small">${esc(label[by])}</span> <b>${esc(k)}</b> <small class="muted">${n} arm${n===1?'':'s'}</small></td>`;
r.before(h);});if(t._repage)t._repage();}
document.querySelector('.group-chips')?.addEventListener('click',ev=>{const b=ev.target.closest('button[data-group-by]');if(!b)return;by=b.dataset.groupBy;regroup();});
t.tHead.addEventListener('click',()=>{if(by)setTimeout(regroup,0);});
/* facets: within one kind any value picked keeps a row (local or hosted); across kinds all must */
const picked={};
function refacet(){[...body.rows].forEach(r=>{if(r.classList.contains('grouphead'))return;
const out=Object.entries(picked).some(([f,vals])=>vals.size&&!vals.has(r.dataset[f]));r.classList.toggle('fout',out);});
const f=document.querySelector('input[data-filter="arms"]');if(f)f.dispatchEvent(new Event('input'));}
document.querySelector('.facet-chips')?.addEventListener('click',ev=>{const b=ev.target.closest('button[data-facet]');if(!b)return;
const s=picked[b.dataset.facet]||(picked[b.dataset.facet]=new Set());const on=b.getAttribute('aria-pressed')!=='true';
b.setAttribute('aria-pressed',String(on));if(on)s.add(b.dataset.value);else s.delete(b.dataset.value);refacet();});
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
sel&&sel.addEventListener('change',()=>document.querySelectorAll('[data-tradeoff]').forEach(d=>{d.hidden=d.dataset.tradeoff!==sel.value;}));
/* a group whose arms are all filtered out loses its heading too */
function heads(){let h=null,any=false;const end=()=>{if(h)h.hidden=!any;};
[...body.rows].forEach(r=>{if(r.classList.contains('grouphead')){end();h=r;any=false;}else if(!r.hidden)any=true;});end();}
document.querySelector('input[data-filter="arms"]')?.addEventListener('input',()=>setTimeout(heads,0));
if(by)regroup();})();
