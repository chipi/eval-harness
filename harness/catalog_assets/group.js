/* Grouping and facets for a table of rows (the arms, datasets and metrics pages). A table opts in
   with chips that name it: `.group-chips[data-for=<table id>]` buttons carry data-group-by (a row
   attribute, data-<key>), `.facet-chips[data-for=<table id>]` buttons carry data-facet and
   data-value. A group is the rows sorted by that attribute (stable, so a column's sort holds
   inside it) under a heading naming it and counting its rows; `?group=<key>` opens a page grouped.
   Facets: within one kind any value picked keeps a row; across kinds all must. */
(function(){const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
document.querySelectorAll('table.data').forEach(t=>{const gc=document.querySelector(`.group-chips[data-for="${t.id}"]`),
fc=document.querySelector(`.facet-chips[data-for="${t.id}"]`);if(!gc&&!fc)return;
const body=t.tBodies[0],cols=t.tHead.rows[0].cells.length,noun=t.dataset.noun||'row';
const chips=gc?[...gc.querySelectorAll('button[data-group-by]')]:[];
let by=new URLSearchParams(location.search).get('group')||'';
if(!chips.some(b=>b.dataset.groupBy===by))by='';
function regroup(){body.querySelectorAll('tr.grouphead').forEach(r=>r.remove());
chips.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.groupBy===by)));
if(!by){if(t._repage)t._repage();return;}
const label=(chips.find(b=>b.dataset.groupBy===by)||{}).dataset.label||by;
const rows=[...body.rows];const key=r=>r.dataset[by]||'';
rows.sort((a,b)=>key(a)<key(b)?-1:key(a)>key(b)?1:0).forEach(r=>body.appendChild(r));
let last=null;[...body.rows].forEach(r=>{const k=key(r);if(k===last)return;last=k;
const n=rows.filter(x=>key(x)===k).length,h=document.createElement('tr');h.className='grouphead';
h.innerHTML=`<td colspan="${cols}"><span class="muted small">${esc(label)}</span> <b>${esc(k)}</b> <small class="muted">${n} ${esc(noun)}${n===1?'':'s'}</small></td>`;
r.before(h);});if(t._repage)t._repage();}
gc&&gc.addEventListener('click',ev=>{const b=ev.target.closest('button[data-group-by]');if(!b)return;by=b.dataset.groupBy;regroup();});
t.tHead.addEventListener('click',()=>{if(by)setTimeout(regroup,0);});
const picked={};
function refacet(){[...body.rows].forEach(r=>{if(r.classList.contains('grouphead'))return;
const out=Object.entries(picked).some(([f,vals])=>vals.size&&!vals.has(r.dataset[f]));r.classList.toggle('fout',out);});
const f=document.querySelector(`input[data-filter="${t.id}"]`);if(f)f.dispatchEvent(new Event('input'));else if(t._repage)t._repage();}
fc&&fc.addEventListener('click',ev=>{const b=ev.target.closest('button[data-facet]');if(!b)return;
const s=picked[b.dataset.facet]||(picked[b.dataset.facet]=new Set());const on=b.getAttribute('aria-pressed')!=='true';
b.setAttribute('aria-pressed',String(on));if(on)s.add(b.dataset.value);else s.delete(b.dataset.value);refacet();});
/* a group whose rows are all filtered or paged out loses its heading too (paging counts rows only) */
function heads(){let h=null,any=false;const end=()=>{if(h)h.hidden=!any;};
[...body.rows].forEach(r=>{if(r.classList.contains('grouphead')){end();h=r;any=false;}else if(!r.hidden&&!r.classList.contains('paged-out'))any=true;});end();}
const repage=t._repage;if(repage)t._repage=function(){repage();heads();};
document.querySelector(`input[data-filter="${t.id}"]`)?.addEventListener('input',()=>setTimeout(heads,0));
if(by)regroup();});})();
