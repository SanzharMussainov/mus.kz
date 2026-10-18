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

document.addEventListener('click',e=>{const b=e.target.closest('[data-fill-from]');if(!b)return;const source=document.getElementById(b.dataset.fillFrom);const target=document.getElementById(b.dataset.fillTo);if(source&&target)target.value=source.value;});

// Keep the original form (including files and checkboxes) intact on failure.
document.addEventListener('submit', async event => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || form.method.toLowerCase() !== 'post' ||
      form.closest('[hx-post], [hx-get]') || event.defaultPrevented) return;
  const submitter = event.submitter;
  const destination = new URL(submitter?.hasAttribute('formaction') ? submitter.formAction : form.action, location.href);
  if (destination.origin !== location.origin) return;
  event.preventDefault();
  if (form.dataset.submitting) return;
  const data = new FormData(form);
  if (submitter?.name) data.append(submitter.name, submitter.value);
  form.dataset.submitting = 'true';
  const buttons = Array.from(form.querySelectorAll('button, input[type="submit"]'));
  const disabled = buttons.map(button => button.disabled);
  buttons.forEach(button => button.disabled = true);
  let notice = form.querySelector('.form-error');
  if (!notice) {
    notice = document.createElement('div');
    notice.className = 'notice form-error';
    notice.setAttribute('role', 'alert');
    notice.tabIndex = -1;
    const button = submitter || buttons[0];
    if (button) button.before(notice); else form.append(notice);
  }
  notice.hidden = true;
  const showError = message => {
    notice.textContent = message;
    notice.hidden = false;
    notice.focus();
  };
  try {
    const response = await fetch(destination, {method: 'POST', body: data, credentials: 'same-origin', headers: {'X-Form-Submission': 'fetch'}});
    if (!response.ok) {
      const html = new DOMParser().parseFromString(await response.text(), 'text/html');
      showError(html.querySelector('[role="alert"]')?.textContent?.trim() ||
        'Не удалось сохранить изменения. Введённые данные остались в форме.');
      return;
    }
    location.assign(response.redirected ? response.url : destination.href);
  } catch {
    showError('Не удалось получить ответ сервера. Введённые данные сохранены в форме. Проверьте соединение; перед повторной отправкой убедитесь, что действие не выполнено.');
  } finally {
    delete form.dataset.submitting;
    buttons.forEach((button, index) => button.disabled = disabled[index]);
  }
});

document.addEventListener('click',event=>{const button=event.target.closest('[data-dismiss-notice]');if(button)button.closest('.success-notice')?.remove();});
