(function(){const nodes=document.querySelectorAll('.method-aside .lc-node');
const io=new IntersectionObserver(es=>es.forEach(x=>{if(!x.isIntersecting)return;
const on=x.target.dataset.nodes.split(' ');nodes.forEach(n=>n.classList.toggle('on',on.includes(n.dataset.node)));}),{rootMargin:'-40% 0px -50% 0px'});
document.querySelectorAll('.chapter').forEach(c=>io.observe(c));})();
