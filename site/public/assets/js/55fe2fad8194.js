document.getElementById('theme').addEventListener('click',()=>{const r=document.documentElement;
const dark=r.dataset.theme?r.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
r.dataset.theme=dark?'light':'dark';try{localStorage.setItem('theme',r.dataset.theme);}catch(e){}});
/* the on-this-page line: the section in view marked, its link kept in sight on a narrow screen */
(()=>{const links=[...document.querySelectorAll('.onpage a')];if(!links.length)return;
const secs=links.map(a=>[a,document.getElementById(decodeURIComponent(a.hash.slice(1)))]).filter(x=>x[1]);
let cur=null,queued=false;
/* the last section whose top has passed under the header */
const mark=()=>{queued=false;let on=null;for(const[a,s]of secs){if(s.getBoundingClientRect().top<=120)on=a;}
if(on===cur)return;if(cur)cur.removeAttribute('aria-current');cur=on;
if(on){on.setAttribute('aria-current','true');const n=on.parentElement;n.scrollLeft=Math.max(0,on.offsetLeft-n.clientWidth/3);}};
addEventListener('scroll',()=>{if(!queued){queued=true;requestAnimationFrame(mark);}},{passive:true});mark();})();
const tip=document.getElementById('tip');
function place(x,y){const w=tip.offsetWidth,h=tip.offsetHeight;tip.style.left=Math.max(8,Math.min(x+14,innerWidth-w-8))+'px';tip.style.top=(y+14+h>innerHeight?y-h-14:y+14)+'px';}
document.addEventListener('pointerover',ev=>{if(ev.pointerType==='touch')return;const t=ev.target.closest('[data-tip]');if(!t)return;tip.textContent=t.dataset.tip;tip.classList.add('on');place(ev.clientX,ev.clientY);});
document.addEventListener('pointermove',ev=>{if(ev.pointerType==='touch'||!tip.classList.contains('on'))return;place(ev.clientX,ev.clientY);});
document.addEventListener('pointerout',ev=>{if(ev.pointerType!=='touch'&&ev.target.closest('[data-tip]'))tip.classList.remove('on');});
// Touch: a tap shows the tip where the finger is; the next tap elsewhere, or a scroll, hides it.
document.addEventListener('pointerdown',ev=>{if(ev.pointerType!=='touch')return;const t=ev.target.closest('[data-tip]');if(!t){tip.classList.remove('on');return;}tip.textContent=t.dataset.tip;tip.classList.add('on');place(ev.clientX,ev.clientY);});
addEventListener('scroll',()=>tip.classList.remove('on'),{passive:true});
const io=new IntersectionObserver(es=>es.forEach(x=>{if(x.isIntersecting){x.target.classList.add('in');io.unobserve(x.target);}}),{rootMargin:'0px 0px -8% 0px'});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));
setTimeout(()=>document.querySelectorAll('.reveal').forEach(el=>el.classList.add('in')),2500);
/* the phone menu closes on Escape (focus back on its button) and on a tap outside it */
document.addEventListener('keydown',ev=>{if(ev.key!=='Escape')return;document.querySelectorAll('details.menu[open]').forEach(d=>{d.open=false;d.querySelector('summary').focus();});});
document.addEventListener('click',ev=>{document.querySelectorAll('details.menu[open]').forEach(d=>{if(!d.contains(ev.target))d.open=false;});});
