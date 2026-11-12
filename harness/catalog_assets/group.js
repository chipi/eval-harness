/* Grouping and facets for a table of rows (the arms, datasets and metrics pages). A table opts in
   with chips that name it: `.group-chips[data-for=<table id>]` buttons carry data-group-by (a row
   attribute, data-<key>), `.facet-chips[data-for=<table id>]` buttons carry data-facet and
   data-value. A group is the rows sorted by that attribute (stable, so a column's sort holds
   inside it) under a heading naming it and counting the rows the filter and facets leave; `?group=<key>` opens a
   page grouped and `?only=<facet>:<value>,…` with those facets picked; both follow the chips, so the address shares
   the view. A table's data-default-group opens it grouped (`?group=none` then means no grouping), and its data-fold
   shows the first N rows of each group, the rest behind its heading's "show N more" (the page's own order puts what
   to read first). When nothing is left, one row says so, with a button that clears the filter and the facets.
   Facets: within one kind any value picked keeps a row; across kinds all must. */
(function(){const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
document.querySelectorAll('table.data').forEach(t=>{const gc=document.querySelector(`.group-chips[data-for="${t.id}"]`),
fc=document.querySelector(`.facet-chips[data-for="${t.id}"]`);if(!gc&&!fc)return;
const body=t.tBodies[0],cols=t.tHead.rows[0].cells.length,noun=t.dataset.noun||'row',fold=+(t.dataset.fold||0);
const filt=document.querySelector(`input[data-filter="${t.id}"]`),dflt=t.dataset.defaultGroup||'';
const chips=gc?[...gc.querySelectorAll('button[data-group-by]')]:[];
let by=new URLSearchParams(location.search).get('group');by=by==null?dflt:by==='none'?'':by;
if(!chips.some(b=>b.dataset.groupBy===by))by='';
const open=new Set(),plural=n=>`${n} ${esc(noun)}${n===1?'':'s'}`;
const isRow=r=>!r.classList.contains('grouphead');
const shown=r=>!r.hidden&&!r.classList.contains('fout')&&!r.classList.contains('pout');
function regroup(){body.querySelectorAll('tr.grouphead').forEach(r=>r.remove());
chips.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.groupBy===by)));
if(by){t.dataset.grouped='';t.dataset.groupedBy=by;}else{delete t.dataset.grouped;delete t.dataset.groupedBy;}
if(!by){if(t._repage)t._repage();return;}
const label=(chips.find(b=>b.dataset.groupBy===by)||{}).dataset.label||by;
const rows=[...body.rows];const key=r=>r.dataset[by]||'';
rows.sort((a,b)=>key(a)<key(b)?-1:key(a)>key(b)?1:0).forEach(r=>body.appendChild(r));
let last=null;[...body.rows].forEach(r=>{const k=key(r);if(k===last)return;last=k;
const h=document.createElement('tr');h.className='grouphead';h.dataset.gkey=k;
h.innerHTML=`<th colspan="${cols}" scope="rowgroup"><span class="muted small">${esc(label)}</span> <b>${esc(k)}</b> <small class="muted" data-n></small> <span data-gfold></span></th>`;
r.before(h);});if(t._repage)t._repage();}
gc&&gc.addEventListener('click',ev=>{const b=ev.target.closest('button[data-group-by]');if(!b)return;by=b.dataset.groupBy;open.clear();regroup();remember();});
t.tHead.addEventListener('click',()=>{if(by)setTimeout(regroup,0);});
const picked={};
function remember(){const q=new URLSearchParams(location.search);if(by)q.set('group',by);else if(dflt)q.set('group','none');else q.delete('group');
const only=Object.entries(picked).flatMap(([f,vals])=>[...vals].map(v=>`${f}:${v}`));
if(only.length)q.set('only',only.join(','));else q.delete('only');const qs=q.toString();
try{history.replaceState(null,'',location.pathname+(qs?'?'+qs:'')+location.hash);}catch(e){}}
function refacet(){[...body.rows].forEach(r=>{if(!isRow(r))return;
const out=Object.entries(picked).some(([f,vals])=>vals.size&&!vals.has(r.dataset[f]));r.classList.toggle('fout',out);});
if(filt)filt.dispatchEvent(new Event('input'));else if(t._repage)t._repage();}
fc&&fc.addEventListener('click',ev=>{const b=ev.target.closest('button[data-facet]');if(!b)return;
const s=picked[b.dataset.facet]||(picked[b.dataset.facet]=new Set());const on=b.getAttribute('aria-pressed')!=='true';
b.setAttribute('aria-pressed',String(on));if(on)s.add(b.dataset.value);else s.delete(b.dataset.value);refacet();remember();});
(new URLSearchParams(location.search).get('only')||'').split(',').filter(Boolean).forEach(x=>{const i=x.indexOf(':');
const b=fc&&[...fc.querySelectorAll('button[data-facet]')].find(c=>c.dataset.facet===x.slice(0,i)&&c.dataset.value===x.slice(i+1));
if(!b)return;(picked[b.dataset.facet]||(picked[b.dataset.facet]=new Set())).add(b.dataset.value);b.setAttribute('aria-pressed','true');});
/* each group shows its first `fold` rows the filter leaves; the rest wait behind its heading */
function folds(){let h=null,seen=0;[...body.rows].forEach(r=>{if(!isRow(r)){if(r.dataset.gkey!=null){h=r;seen=0;}return;}
const on=by&&fold&&h&&!open.has(h.dataset.gkey)&&shown(r)&&seen++>=fold;r.classList.toggle('gfold',!!on);});}
/* a heading counts what is left in its group and offers the rest; a group with nothing left loses its heading;
   a table with nothing left says so */
function heads(){let h=null,n=0,more=0;const end=()=>{if(!h)return;h.hidden=!n;const c=h.querySelector('[data-n]');if(c)c.textContent=plural(n);
const g=h.querySelector('[data-gfold]');if(g)g.innerHTML=more?`<button type="button" class="btn small" data-gopen="${esc(h.dataset.gkey)}" aria-expanded="false">show ${more} more</button>`
:open.has(h.dataset.gkey)&&n>fold?`<button type="button" class="btn small" data-gopen="${esc(h.dataset.gkey)}" aria-expanded="true">show ${fold}</button>`:'';};
let total=0;[...body.rows].forEach(r=>{if(!isRow(r)){if(r.dataset.gkey!=null){end();h=r;n=0;more=0;}return;}
if(shown(r)){n++;total++;if(r.classList.contains('gfold'))more++;}});end();
let empty=body.querySelector('tr.emptyrow');
if(total){if(empty)empty.remove();return;}
if(!empty){empty=document.createElement('tr');empty.className='grouphead emptyrow';body.prepend(empty);}
const what=filt&&filt.value.trim()?` matches “${esc(filt.value.trim())}”`:' is left';
const only=Object.values(picked).some(s=>s.size)?` with only: ${esc(Object.values(picked).flatMap(s=>[...s]).join(', '))}`:'';
empty.innerHTML=`<td colspan="${cols}">No ${esc(noun)}${what}${only}. <button type="button" class="btn small" data-clearall>Clear the filter and the chips</button></td>`;}
body.addEventListener('click',ev=>{const g=ev.target.closest('button[data-gopen]');
if(g){const k=g.dataset.gopen;if(open.has(k))open.delete(k);else open.add(k);if(t._repage)t._repage();
const again=body.querySelector(`button[data-gopen="${CSS.escape(k)}"]`);if(again)again.focus();return;}
if(ev.target.closest('button[data-clearall]')){Object.keys(picked).forEach(f=>delete picked[f]);
fc&&fc.querySelectorAll('button[data-facet]').forEach(b=>b.setAttribute('aria-pressed','false'));
if(filt)filt.value='';refacet();remember();if(filt)filt.focus();}});
const repage=t._repage;if(repage)t._repage=function(){folds();repage();heads();};
filt?.addEventListener('input',()=>setTimeout(()=>{if(t._repage)t._repage();},0));
if(by)regroup();else if(t._repage)t._repage();if(Object.keys(picked).length)refacet();});})();
