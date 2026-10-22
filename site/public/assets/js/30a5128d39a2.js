(function(){var p=new URLSearchParams(location.search),t=p.get('theme');
try{t=t||localStorage.getItem('theme');}catch(e){}
if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;
if(!p.has('static'))document.documentElement.classList.add('js');})();
