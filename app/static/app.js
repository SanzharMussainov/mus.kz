function initMath() {
  if (window.renderMathInElement) renderMathInElement(document.body, {delimiters:[{left:'\\(',right:'\\)',display:false},{left:'\\[',right:'\\]',display:true}],throwOnError:false,trust:false,maxExpand:1000});
  document.querySelectorAll('.sidebar a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')===location.pathname));
}
document.addEventListener('DOMContentLoaded',initMath);
document.addEventListener('htmx:afterSwap',initMath);
document.addEventListener('htmx:responseError',e=>{const p=document.createElement('p');p.className='notice';p.setAttribute('role','alert');const doc=new DOMParser().parseFromString(e.detail.xhr.responseText,'text/html');p.textContent=doc.querySelector('[role="alert"]')?.textContent||'Не удалось сохранить ответ. Обновите страницу и повторите.';e.detail.elt.querySelector('[role="alert"]')?.remove();e.detail.elt.append(p);});
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-copy]');if(!b)return;
  const text=document.getElementById(b.dataset.copy);
  try {await navigator.clipboard.writeText(text.value);b.textContent='Скопировано ✓';}
  catch {text.select();b.textContent='Выделено — нажмите Ctrl+C';}
});
