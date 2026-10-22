(function(){const panels=[...document.querySelectorAll('.lc-panel')],nodes=[...document.querySelectorAll('.lc-map .lc-node')];
if(!panels.length)return;document.querySelector('.lc-explorer').classList.add('live');
function show(id){panels.forEach(p=>p.classList.toggle('on',p.dataset.node===id));nodes.forEach(n=>n.classList.toggle('on',n.dataset.node===id));}
nodes.forEach(n=>{n.addEventListener('click',ev=>{ev.preventDefault();show(n.dataset.node);if(innerWidth<=900){const p=panels.find(p=>p.dataset.node===n.dataset.node);if(p)p.scrollIntoView({block:'nearest',behavior:'smooth'});}});n.addEventListener('mouseenter',()=>show(n.dataset.node));n.addEventListener('focus',()=>show(n.dataset.node));});
show('dataset');})();
