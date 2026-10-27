/* The home page's period: tiles with trends, the activity and spend charts and the feed, for the
   period picked, measured from today (the viewer's date). window.HOME is written by the build
   (home.js); scripts/catalog_periods.py computes the same for `evh overview --period`, and the
   charts are drawn as scripts/catalog_charts.py draws them. Without this script the page shows
   all time. */
(function(){const H=window.HOME,Pd=window.Period;if(!H||!Pd)return;
const {DAY,iso,at,esc,within,trend,daysOf,amount,label}=Pd;
function flow(what,s){if(what==='measured runs')return Object.entries(H.runs).filter(([d])=>within(d,s)).reduce((n,[,p])=>n+Object.values(p).reduce((a,b)=>a+b,0),0);
const i=what==='billed'?0:1;return Object.entries(H.spend).filter(([d])=>within(d,s)).reduce((n,[,p])=>n+Object.values(p).reduce((a,x)=>a+(x[i]||0),0),0);}
function tileValue(s){s=String(s);const dg=s.replace(/,/g,'');if(s.length<=7||!/^\d+$/.test(dg))return esc(s);const v=+dg;
const [d,u]=[[1e9,'B'],[1e6,'M'],[1e3,'k']].find(([d])=>v>=d);return `<span class="full">${esc(s)}</span><span class="short">${(v/d).toFixed(1).replace(/\.0$/,'')}${u}</span>`;}
/* a tile's line in its own colour (--c, catalog.css), with a faint area under it */
function spark(xs){if(xs.length<2)return '';const top=Math.max(...xs)||1,step=100/(xs.length-1);
const pts=xs.map((v,i)=>`${(i*step).toFixed(1)},${(22-20*v/top).toFixed(1)}`).join(' ');
return `<svg class="spark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true"><polygon points="0,24 ${pts} 100,24" fill="var(--c)" fill-opacity="0.14"/><polyline points="${pts}" fill="none" stroke="var(--c)" stroke-width="1.75" vector-effect="non-scaling-stroke"/></svg>`;}
/* the charts, as catalog_charts.py draws them */
const SLOTS=8,LEFT=84,RIGHT=16,TOP=12,BOTTOM=28,HALF=560,Hh=200;
/* the drawing's width: half a page beside another chart, or data-width on a chart that has the row */
let CW=HALF;
const colour=i=>i<SLOTS?`var(--s${i+1})`:'var(--muted)',swatch=i=>i<SLOTS?`sw${i+1}`:'swm';
function num(v){if(v===Math.trunc(v)&&Math.abs(v)>=1)return String(v);if(Math.abs(v)>=10)return v.toFixed(1);
if(Math.abs(v)>=0.01||v===0)return v?v.toFixed(3).replace(/0+$/,'').replace(/\.$/,''):'0';return v.toPrecision(2);}
function nice(top){if(top<=0)return 1;const mag=10**Math.floor(Math.log10(top));for(const m of [1,2,2.5,5,10])if(m*mag>=top)return m*mag;return 10*mag;}
const axis=(top,fmt,w)=>[0,.5,1].map(f=>{const y=TOP+(Hh-TOP-BOTTOM)*(1-f);return `<line x1="${LEFT}" x2="${w-RIGHT}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="var(--axis)" stroke-width="${f===0?1:0.5}"/><text x="${LEFT-6}" y="${(y+4).toFixed(1)}" text-anchor="end" class="tick">${esc(fmt(top*f))}</text>`;}).join('');
function dayLabels(days,x){const p=[...new Set([0,days.length-1].concat(days.length>6?[Math.floor(days.length/2)]:[]))].sort((a,b)=>a-b);
return p.map(i=>`<text x="${x(i).toFixed(1)}" y="${Hh-8}" text-anchor="middle" class="tick">${esc(days[i].slice(5))}</text>`).join('');}
const legend=names=>'<p class="legend">'+names.map((n,i)=>`<span><i class="${swatch(i)}"></i>${esc(n)}</span>`).join('')+'</p>';
const fig=(label,inner,names)=>`<figure class="chart"><svg viewBox="0 0 ${CW} ${Hh}" role="img" aria-label="${esc(label)}">${inner}</svg>${legend(names)}</figure>`;
function bars(days,series,label,unit){const names=Object.keys(series),tot=days.map((_,i)=>names.reduce((a,n)=>a+series[n][i],0));
const top=nice(Math.max(0,...tot)),bw=(CW-LEFT-RIGHT)/Math.max(days.length,1),x=i=>LEFT+bw*(i+.5),y=v=>TOP+(Hh-TOP-BOTTOM)*(1-v/top);
let out='';days.forEach((d,i)=>{let base=0;names.forEach((n,k)=>{const v=series[n][i];if(!v)return;const y0=y(base),y1=y(base+v),w=Math.min(Math.max(bw*.76,1),48);
out+=`<rect x="${(x(i)-w/2).toFixed(1)}" y="${y1.toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(y0-y1,.5).toFixed(1)}" fill="${colour(k)}"><title>${esc(d)} · ${esc(n)}: ${esc(num(v))}${esc(unit)}</title></rect>`;base+=v;});});
return fig(label,axis(top,num,CW)+out+dayLabels(days,x),names);}
function cumulative(days,series,label,fmt){const names=Object.keys(series),runs={};names.forEach(n=>{let s=0;runs[n]=series[n].map(v=>s+=v);});
const top=nice(Math.max(0,...names.map(n=>runs[n].at(-1)||0))),pw=CW-LEFT-RIGHT,step=pw/Math.max(days.length-1,1);
const x=i=>days.length>1?LEFT+step*i:LEFT+pw/2,y=v=>TOP+(Hh-TOP-BOTTOM)*(1-v/top);
const lines=names.map((n,k)=>`<polyline points="${runs[n].map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}" fill="none" stroke="${colour(k)}" stroke-width="2"><title>${esc(n)}: ${esc(fmt(runs[n].at(-1)||0))} by ${esc(days.at(-1)||'')}</title></polyline>`
+runs[n].map((v,i)=>series[n][i]?`<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.5" fill="${colour(k)}"><title>${esc(days[i])} · ${esc(n)}: ${esc(fmt(v))} so far</title></circle>`:'').join('')).join('');
return fig(label,axis(top,fmt,CW)+lines+(days.length?dayLabels(days,x):''),names);}
function activity(s){const days=daysOf(s[0],s[1]),series={};
H.datasets.forEach(ds=>{const xs=days.map(d=>(H.runs[d]||{})[ds]||0);if(xs.some(Boolean))series[ds]=xs;});
const total=Object.values(series).reduce((a,xs)=>a+xs.reduce((p,q)=>p+q,0),0);
if(!total)return '<p class="muted">No measured run in this period.</p>';
return `<p class="small muted">${total} measured runs (repeats counted one by one), by day and dataset.</p>`+bars(days,series,'measured runs per day, by dataset',' runs');}
let unit='usd';
function spendChart(s,u){const i=H.units.indexOf(u),days=daysOf(s[0],s[1]),series={};
H.kinds.forEach(k=>{const xs=days.map(d=>(((H.spend[d]||{})[k])||[])[i]);if(xs.some(v=>typeof v==='number'))series[k]=xs.map(v=>v||0);});
const names=Object.keys(series);if(!names.length)return `<p class="muted">No ${u==='usd'?'cost':'token count'} recorded in this period.</p>`;
const tot=Object.fromEntries(names.map(n=>[n,series[n].reduce((a,b)=>a+b,0)])),sum=Object.values(tot).reduce((a,b)=>a+b,0);
return `<p class="small">${names.map(n=>`${esc(n)} <b>${esc(amount(tot[n],u))}</b>`).join(' · ')} · total <b>${esc(amount(sum,u))}</b></p>`
+cumulative(days,series,u==='usd'?'cumulative spend in USD':'cumulative tokens (in plus out)',v=>amount(v,u).replace(' tokens',''));}
function spend(s){return '<p class="unit-switch" role="group" aria-label="unit">'+H.units.map(u=>`<button type="button" class="btn small" data-unit-show="${u}" aria-pressed="${u===unit}">${u==='usd'?'USD':'tokens'}</button>`).join('')+'</p>'
+H.units.map(u=>`<div data-unit="${u}"${u===unit?'':' hidden'}>${spendChart(s,u)}</div>`).join('');}
function show(key,b){const s=[b.since,b.until],days=daysOf(b.since,b.until);
document.querySelectorAll('.tile[data-tile]').forEach(el=>{const [what,,kind]=H.tiles[+el.dataset.tile],tr=el.querySelector('.trend');
/* the tile says it short (▲ 12%, new); its title says it in full */
let v,line='',full='';el.querySelector('.spark')?.remove();
if(kind==='stock'){const ds=H.dates[what];v=ds.length;const n=ds.filter(d=>within(d,s)).length;line=full=n?`+${n} new`:'none new';
el.insertAdjacentHTML('beforeend',spark(days.map(d=>ds.filter(x=>x&&x<=d).length)));}
else{v=flow(what,s);if(b.prev){full=trend(v,flow(what,b.prev));line=Pd.short(full);
if(/%$/.test(full))full+=` vs ${label[key][1]}`;}
el.insertAdjacentHTML('beforeend',spark(days.map(d=>flow(what,[d,d]))));
v=what==='billed'?amount(v,'usd'):Math.round(v).toLocaleString('en-US');}
el.querySelector('b').innerHTML=tileValue(v);el.title=`${v} ${what}`+(full?` · ${full}`:'');if(tr)tr.textContent=line;});
const a=document.querySelector('[data-chart="activity"]');if(a&&H.first){CW=+(a.dataset.width||HALF);a.innerHTML=activity(s);}
const p=document.querySelector('[data-chart="spend"]');if(p&&Object.keys(H.spend).length){CW=+(p.dataset.width||HALF);p.innerHTML=spend(s);}
const feed=document.getElementById('feeda');if(feed){let n=0;[...feed.tBodies[0].rows].forEach(r=>{const ok=within((r.cells[0].dataset.v||'').slice(0,10),s);r.hidden=!ok;n+=ok;});
const none=document.querySelector('[data-feed-empty]');if(none)none.hidden=n>0;feed.closest('.scroll-x').hidden=!n;if(feed._repage)feed._repage();}}
document.addEventListener('click',ev=>{const btn=ev.target.closest('.unit-switch button[data-unit-show]');if(!btn)return;unit=btn.dataset.unitShow;
const box=btn.closest('[data-chart]')||document;box.querySelectorAll('.unit-switch button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.unitShow===unit)));
box.querySelectorAll('[data-unit]').forEach(x=>{x.hidden=x.dataset.unit!==unit;});});
Pd.on(show);})();
