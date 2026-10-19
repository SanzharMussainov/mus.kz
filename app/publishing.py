"""Trigger only an operator-configured Render deploy hook; never expose its key."""
import os
from urllib.parse import urlsplit
import httpx

async def trigger_public_deploy():
    hook=os.getenv('PUBLIC_DEPLOY_HOOK','').strip()
    url=urlsplit(hook)
    if (url.scheme!='https' or url.hostname!='api.render.com' or url.port not in (None,443)
        or url.username or url.password or not url.path.startswith('/deploy/srv-') or not url.query):
        raise ValueError('Публикация не настроена: добавьте Deploy Hook статического сайта в PUBLIC_DEPLOY_HOOK сервиса кабинета.')
    try:
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.post(hook)
        if not 200<=response.status_code<300:
            raise ValueError('Render не принял публикацию. Проверьте Deploy Hook и статус статического сайта в Render.')
    except httpx.RequestError:
        raise ValueError('Не удалось получить ответ Render. Проверьте Events статического сайта перед повторной публикацией.') from None
