import os
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote, urlparse
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from .db import get_db, now
from .models import *
from .security import *
from .services import *
from .admin import SPECS, LABELS
from .reports import weekly_report, week_start
from .messages import validate_template, message_context
from .deletion import DELETABLE, remove, restore
from .export_public import export as export_public
from .publishing import trigger_public_deploy

ROOT = Path(__file__).parent
ZONE = ZoneInfo('Asia/Qyzylorda')
SECRET = os.getenv('SECRET_KEY', '')
if len(SECRET) < 32 or SECRET.startswith('REPLACE_'):
    raise RuntimeError('Задайте SECRET_KEY: случайная строка минимум 32 символа.')
app = FastAPI(title='mus.kz', docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site='lax', https_only=os.getenv('COOKIE_SECURE','false').lower() == 'true', max_age=43200)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
templates = Jinja2Templates(directory=ROOT/'templates')
templates.env.filters['date'] = lambda d: d.astimezone(ZONE).strftime('%d.%m.%Y · %H:%M') if d else '—'
templates.env.filters['localinput'] = lambda d: d.astimezone(ZONE).strftime('%Y-%m-%dT%H:%M') if d else ''
templates.env.filters['minutes'] = lambda n: ('−' if n < 0 else '') + f'{abs(n)//60} ч {abs(n)%60:02d} мин'
templates.env.filters['label'] = lambda s: LABELS.get(s,s)
templates.env.filters['wa'] = lambda s: re.sub(r'\D','',s)
templates.env.filters['urlquote'] = lambda s: quote(s)
templates.env.globals['getattr'] = getattr


@app.middleware('http')
async def security_headers(request, call_next):
    if int(request.headers.get('content-length','0') or 0) > 11*1024*1024:
        return templates.TemplateResponse(request=request, name='error.html', context={'error':'Размер запроса превышает 11 МБ.'}, status_code=413)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


def render(request, db, name, **context):
    context['success_message'] = (request.session.get('success_message') if request.headers.get('X-Form-Submission') == 'fetch' else request.session.pop('success_message', None))
    return templates.TemplateResponse(request=request, name=name, context=dict(user=current_user(request,db), csrf=csrf(request), settings=db.get(Settings,1) or Settings(title='mus.kz'), specs=SPECS, deletable=DELETABLE, now=now(), **context))


def redirect(path):
    return RedirectResponse(path,303)


@app.exception_handler(ValueError)
async def value_error(request, error):
    return templates.TemplateResponse(request=request, name='error.html', context={'error':str(error)}, status_code=400)


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return templates.TemplateResponse(request=request, name='error.html', context={'error':'Такая запись уже существует или связанная запись не найдена. Проверьте данные.'}, status_code=409)


@app.exception_handler(HTTPException)
async def http_error(request, error):
    if error.status_code == 303:
        return redirect(error.headers['Location'])
    return templates.TemplateResponse(request=request, name='error.html', context={'error':error.detail}, status_code=error.status_code)


def get_or_404(db, model, pk):
    obj = db.get(model,pk)
    if not obj or getattr(obj,'deleted',False):
        raise HTTPException(404,'Запись не найдена.')
    return obj


def localdate(value):
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return d.replace(tzinfo=ZONE) if d.tzinfo is None else d


@app.get('/')
def home(request: Request, db=Depends(get_db)):
    return render(request, db, 'home.html', public_only=True, courses=db.scalars(select(Course).where(Course.public == True)).all(), groups=db.scalars(select(Group).where(Group.status == 'recruiting', Group.course_id.in_(select(Course.id).where(Course.public == True)))).all(), events=db.scalars(select(Meeting).where(Meeting.is_event == True, Meeting.public == True, Meeting.status == 'scheduled', Meeting.starts_at > now()).order_by(Meeting.starts_at)).all())


@app.post('/apply')
async def apply(request: Request, db=Depends(get_db)):
    form = await request.form(); check_csrf(request,form)
    name, contact, message = [str(form.get(k,'')).strip() for k in ('name','contact','message')]
    if not name or not contact or len(name)>160 or len(contact)>200 or len(message)>3000:
        raise ValueError('Укажите имя и контакт. Сообщение — не более 3000 символов.')
    last = request.session.get('lead_at',0)
    if now().timestamp()-last < 60:
        raise ValueError('Заявка уже отправлена. Повторить можно через минуту.')
    group_id=int(form['group_id']) if form.get('group_id') else None
    if group_id:
        group=get_or_404(db,Group,group_id)
        if group.status!='recruiting' or not db.get(Course,group.course_id).public:
            raise ValueError('Набор в эту группу закрыт.')
    db.add(Lead(name=name,contact=contact,message=message,group_id=group_id)); db.commit()
    request.session['lead_at'] = now().timestamp()
    return render(request,db,'thanks.html')


@app.get('/login')
def login_page(request: Request, db=Depends(get_db)):
    return render(request,db,'login.html')


@app.post('/login')
async def login(request: Request, db=Depends(get_db)):
    form=await request.form(); check_csrf(request,form)
    email=str(form.get('email','')).strip().lower()[:254]
    key=(request.client.host if request.client else 'unknown') + ':' + email
    failures=db.scalar(select(func.count()).select_from(LoginFailure).where(LoginFailure.key==key, LoginFailure.created_at > now()-timedelta(minutes=15)))
    if failures >= 8:
        raise HTTPException(429,'Слишком много попыток. Повторите через 15 минут.')
    user=db.scalar(select(User).where(User.email==email))
    if not user or not user.active or not verify(str(form.get('password',''))[:200],user.password_hash):
        db.add(LoginFailure(key=key)); db.commit()
        raise ValueError('Неверный email или пароль.')
    request.session.clear(); request.session['user_id']=user.id; request.session['auth_stamp']=auth_stamp(user)
    return redirect('/dashboard')


@app.post('/logout')
async def logout(request: Request):
    form=await request.form(); check_csrf(request,form); request.session.clear()
    return redirect('/')


@app.get('/dashboard')
def dashboard(request: Request, db=Depends(get_db)):
    user=require_user(request,db)
    meetings=db.scalars(select(Meeting).order_by(Meeting.starts_at)).all()
    if user.role=='admin':
        students=db.scalars(select(User).where(User.role=='student',User.active==True)).all()
        notices=[(u,payment_notice(db,u.id)) for u in students]; notices=[(u,n) for u,n in notices if n]
        return render(request,db,'dashboard.html', meetings=[m for m in meetings if m.status=='scheduled' and m.starts_at>=now()][:6], pending=[m for m in meetings if m.status=='scheduled' and m.starts_at<now()], notices=notices, leads=db.scalars(select(Lead).where(Lead.status=='new')).all(), student_count=len(students))
    return render(request,db,'dashboard.html', meetings=[m for m in meetings if m.status=='scheduled' and m.starts_at>=now() and participates(db,m,user.id)][:6], report=weekly_report(db,user.id), courses=db.scalars(select(Course).where(Course.id.in_(course_ids(db,user.id)))).all(), balance=balance(db,user.id))


@app.get('/admin/{section}')
def admin_list(section:str, request:Request, trash:bool=False, db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    if section=='memberships': return membership_page(request,db)
    model,title,fields=SPECS[section]
    query=select(model).order_by(model.id.desc())
    if model==User: query=query.where(User.role=='student')
    if trash and section in DELETABLE: query=query.execution_options(include_deleted=True).where(model.deleted==True)
    return render(request,db,'admin_list.html',section=section,title=title,rows=db.scalars(query).all(),trash=trash and section in DELETABLE)


@app.get('/admin/{section}/{pk}')
def admin_form(section:str, pk:str, request:Request, db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    model,title,fields=SPECS[section]
    obj=get_or_404(db,model,int(pk)) if pk!='new' else None
    if isinstance(obj,User) and obj.role!='student': raise HTTPException(403,'Изменение администратора доступно через CLI.')
    choices={key:db.scalars(select(rel).where(User.role=='student') if rel==User else select(rel)).all() for key,label,kind,rel in fields if rel}
    return render(request,db,'admin_form.html',section=section,title=title,fields=fields,obj=obj,choices=choices,files=[])


@app.post('/admin/{section}/{pk}')
async def admin_save(section:str,pk:str,request:Request,db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    form=await request.form(); check_csrf(request,form)
    model,title,fields=SPECS[section]
    obj=get_or_404(db,model,int(pk)) if pk!='new' else model()
    if isinstance(obj,User) and obj.id and obj.role!='student': raise HTTPException(403,'Недоступно')
    for key,label,kind,rel in fields:
        value=str(form.get(key,'')).strip()
        if key=='password':
            if value: obj.password_hash=hash_password(value)
            elif not obj.id: raise ValueError('Задайте пароль ученика.')
            continue
        if isinstance(obj,Meeting) and obj.status in ('held','cancelled') and key in ('group_id','is_event','payment_mode'):
            continue
        if kind=='checkbox': value=key in form
        elif kind in ('number','select','optional-select'): value=int(value) if value else None
        elif kind=='datetime-local': value=localdate(value)
        elif '|' in kind and value not in kind.split('|'): raise ValueError('Недопустимое значение: '+label)
        if rel and value is not None:
            related=db.get(rel,value)
            if related is None or getattr(related,"deleted",False):
                raise ValueError(f'Поле «{label}»: запись #{value} не найдена или удалена. Выберите существующую запись.')
            if rel==User and (related.role!='student' or related.deleted): raise ValueError('Выберите ученика.')
        col=model.__table__.columns.get(key)
        if col is not None and not col.nullable and (value is None or value=='' and key in ('title','name','email','prompt','answer','direction','level','tolerance')):
            raise ValueError('Заполните поле: '+label)
        if isinstance(value,str) and len(value) > (getattr(col.type,'length',None) or 15000): raise ValueError('Слишком длинное поле: '+label)
        setattr(obj,key,value)
    if isinstance(obj,User):
        obj.email=obj.email.lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',obj.email): raise ValueError('Проверьте email.')
    if isinstance(obj,Group) and obj.starts_at and obj.ends_at and obj.starts_at>obj.ends_at: raise ValueError('Конец обучения раньше начала.')
    if isinstance(obj,Group):
        if obj.hourly_price is not None and obj.hourly_price < 0: raise ValueError('Стоимость не может быть отрицательной.')
        if any(n is not None and n < 1 for n in (obj.min_students,obj.max_students)): raise ValueError('Размер группы должен быть положительным.')
        if obj.min_students and obj.max_students and obj.min_students > obj.max_students: raise ValueError('Минимум учеников больше максимума.')
        if obj.meet_url and not re.fullmatch(r'https://meet\.google\.com/[a-zA-Z0-9-]+',obj.meet_url): raise ValueError('Уберите из ссылки Google Meet знак ? и всё после него, например ?pli=1&authuser=2. Эти параметры относятся к выбору Google-аккаунта, а не к самой встрече. Вставьте ссылку в таком виде: https://meet.google.com/wna-axgf-xuj')
    if isinstance(obj,Meeting):
        if obj.group_id and not obj.is_event and not obj.meet_url:
            obj.meet_url=db.get(Group,obj.group_id).meet_url or ''
        if not 1<=obj.duration<=1440: raise ValueError('Длительность: 1–1440 минут.')
        if obj.meet_url and not re.fullmatch(r'https://meet\.google\.com/[a-zA-Z0-9-]+',obj.meet_url): raise ValueError('Уберите из ссылки Google Meet знак ? и всё после него, например ?pli=1&authuser=2. Эти параметры относятся к выбору Google-аккаунта, а не к самой встрече. Вставьте ссылку в таком виде: https://meet.google.com/wna-axgf-xuj')
        if obj.cancel_until and obj.cancel_until>obj.starts_at: raise ValueError('Срок отмены должен быть не позже начала.')
        if obj.is_event and obj.audience=='selected':
            for raw, related_model, label in (
                (obj.audience_groups,Group,'Номера групп аудитории'),
                (obj.audience_users,User,'Номера учеников аудитории'),
            ):
                for x in ids(raw):
                    related=db.get(related_model,x)
                    if related is None or getattr(related,'deleted',False):
                        raise ValueError(f'Поле «{label}»: запись #{x} не найдена или удалена. Укажите существующий номер из списка групп или учеников.')
                    if related_model==User and related.role!='student':
                        raise ValueError(f'Поле «{label}»: #{x} не является учеником.')
    if isinstance(obj,Course) and obj.stepik_url:
        url=urlparse(obj.stepik_url)
        if url.scheme!='https' or url.netloc not in ('stepik.org','www.stepik.org'):
            raise ValueError('Укажите HTTPS-ссылку на stepik.org.')
    if isinstance(obj,MessageTemplate): validate_template(obj.body)
    if isinstance(obj,Settings):
        if obj.whatsapp and not re.fullmatch(r'\d{10,15}',obj.whatsapp): raise ValueError('WhatsApp: от 10 до 15 цифр.')
        obj.id=1
    db.add(obj); db.flush()
    db.commit()
    created_messages = {
        'students': 'Ученик успешно создан.', 'courses': 'Курс успешно создан.',
        'groups': 'Группа успешно создана.', 'memberships': 'Ученик успешно добавлен в группу.',
        'meetings': 'Событие успешно создано.' if getattr(obj,'is_event',False) else 'Занятие успешно создано.',
        'leads': 'Заявка успешно создана.', 'messages': 'Шаблон сообщения успешно создан.',
        'settings': 'Настройки успешно сохранены.',
    }
    request.session['success_message'] = created_messages.get(section,'Запись успешно создана.') if pk=='new' else 'Изменения успешно сохранены.'
    return redirect(f'/admin/{section}/{obj.id}')


@app.get('/courses')
def courses_page(request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    courses=db.scalars(select(Course) if user.role=='admin' else select(Course).where(Course.id.in_(course_ids(db,user.id)))).all()
    return render(request,db,'courses.html',courses=courses)


@app.get('/admin/{section}/{pk}/delete')
def delete_page(section:str,pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True)
    if section not in DELETABLE: raise HTTPException(404,'Удаление недоступно.')
    obj=get_or_404(db,DELETABLE[section],pk)
    if isinstance(obj,User) and obj.role!='student': raise HTTPException(403,'Нельзя удалить преподавателя.')
    return render(request,db,'delete.html',section=section,obj=obj,title=SPECS[section][1])


@app.post('/admin/{section}/{pk}/delete')
async def delete_record(section:str,pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True);form=await request.form();check_csrf(request,form)
    if section not in DELETABLE: raise HTTPException(404,'Удаление недоступно.')
    if form.get('confirm')!='yes': raise ValueError('Подтвердите удаление на странице записи.')
    obj=db.scalar(select(DELETABLE[section]).where(DELETABLE[section].id==pk).with_for_update().execution_options(include_deleted=True))
    if not obj: raise HTTPException(404,'Запись не найдена.')
    remove(db,obj);db.commit()
    request.session['success_message'] = {
        'students': 'Ученик успешно удалён.',
        'courses': 'Курс успешно удалён.',
        'groups': 'Группа успешно удалена.',
        'meetings': 'Событие успешно удалено.' if getattr(obj,'is_event',False) else 'Занятие успешно удалено.',
        'leads': 'Заявка успешно удалена.',
        'messages': 'Шаблон сообщения успешно удалён.',
    }.get(section,'Запись успешно удалена.') + ' Восстановить запись можно в корзине.'
    return redirect(f'/admin/{section}')


@app.post('/admin/{section}/{pk}/restore')
async def restore_record(section:str,pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True);form=await request.form();check_csrf(request,form)
    if section not in DELETABLE: raise HTTPException(404,'Восстановление недоступно.')
    obj=db.scalar(select(DELETABLE[section]).where(DELETABLE[section].id==pk).with_for_update().execution_options(include_deleted=True))
    if not obj: raise HTTPException(404,'Запись не найдена.')
    if isinstance(obj,User) and obj.role!='student': raise HTTPException(403,'Недоступно.')
    restore(db,obj);db.commit()
    return redirect(f'/admin/{section}/{pk}')


def membership_page(request,db):
    groups=db.scalars(select(Group).order_by(Group.title)).all()
    students=db.scalars(select(User).where(User.role=='student',User.active==True).order_by(User.name)).all()
    members={g.id:db.scalars(select(User).join(Membership,Membership.user_id==User.id).where(Membership.group_id==g.id,Membership.active==True).order_by(User.name)).all() for g in groups}
    return render(request,db,'memberships.html',groups=groups,students=students,members=members)


@app.post('/groups/{pk}/members')
async def add_members(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True);form=await request.form();check_csrf(request,form)
    group=lock(db,Group,pk)
    if group.status=='archived': raise ValueError('Сначала активируйте группу.')
    selected=set(int(x) for x in form.getlist('students'))
    if not selected: raise ValueError('Выберите хотя бы одного ученика.')
    current=set(db.scalars(select(Membership.user_id).where(Membership.group_id==pk,Membership.active==True)))
    if group.max_students and len(current|selected)>group.max_students: raise ValueError('Выбрано больше учеников, чем мест в группе.')
    for uid in sorted(selected):
        student=lock(db,User,uid)
        if student.deleted or not student.active or student.role!='student': raise ValueError('Выберите активного ученика.')
        member=db.scalar(select(Membership).where(Membership.group_id==pk,Membership.user_id==uid))
        if member: member.active=True
        else: db.add(Membership(group_id=pk,user_id=uid))
    db.commit()
    return redirect('/admin/memberships')


@app.post('/groups/{pk}/members/{uid}/remove')
async def remove_member(pk:int,uid:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True);form=await request.form();check_csrf(request,form)
    lock(db,Group,pk)
    member=db.scalar(select(Membership).where(Membership.group_id==pk,Membership.user_id==uid))
    if member: member.active=False
    db.commit()
    return redirect('/admin/memberships')
















@app.get('/courses/{pk}')
def course_page(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    if user.role!='admin' and pk not in course_ids(db,user.id): raise HTTPException(403,'Курс недоступен.')
    get_or_404(db,Course,pk)
    return redirect('/courses')


@app.get('/calendar')
def calendar(request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    meetings=[m for m in db.scalars(select(Meeting).order_by(Meeting.starts_at)) if user.role=='admin' or meeting_access(db,m,user.id)]
    return render(request,db,'calendar.html',meetings=meetings,registrations={m.id:registration(db,m.id,user.id) for m in meetings})


def report_target(request, db, student):
    user=require_user(request,db)
    students=db.scalars(select(User).where(User.role=='student').order_by(User.name)).all() if user.role=='admin' else [user]
    if student is not None and user.role!='admin' and student!=user.id:
        raise HTTPException(403,'Можно просматривать только свои отчёты.')
    target=next((u for u in students if u.id==student),None) if student is not None else (students[0] if students else None)
    if student is not None and target is None: raise HTTPException(404,'Ученик не найден.')
    return students,target


@app.get('/reports')
def reports_page(request:Request,student:int|None=None,week:str|None=None,db=Depends(get_db)):
    students,target=report_target(request,db,student)
    return render(request,db,'reports.html',students=students,target=target,report=weekly_report(db,target.id,week) if target else None)


@app.get('/messages')
def messages_page(request:Request,student:int|None=None,week:str|None=None,db=Depends(get_db)):
    require_user(request,db,True)
    students,target=report_target(request,db,student)
    context=message_context(db,target,week) if target else None
    rows=[]
    for template in db.scalars(select(MessageTemplate).order_by(MessageTemplate.id)):
        validate_template(template.body)
        rows.append((template,template.body.format_map(context) if context else ''))
    return render(request,db,'messages.html',students=students,target=target,messages=rows,week=week_start(week).isoformat())


@app.post('/meetings/{pk}/topics')
async def meeting_topics(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    meeting=lock(db,Meeting,pk)
    for field in ('planned_topics','covered_topics'):
        value=str(form.get(field,'')).strip()
        if len(value)>15000: raise ValueError('Список тем слишком длинный.')
        setattr(meeting,field,value)
    db.commit()
    return redirect(f'/meetings/{pk}')


@app.get('/meetings/{pk}')
def meeting_page(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); m=get_or_404(db,Meeting,pk)
    if user.role!='admin' and not meeting_access(db,m,user.id): raise HTTPException(403,'Событие недоступно.')
    participants=set(db.scalars(select(Registration.user_id).where(Registration.meeting_id==pk,Registration.active==True)))
    if not m.is_event and m.group_id: participants|=set(db.scalars(select(Membership.user_id).where(Membership.group_id==m.group_id,Membership.active==True)))
    active_count=len(participants)
    participants|=set(db.scalars(select(Attendance.user_id).where(Attendance.meeting_id==pk)))
    attendance={r.user_id:r for r in db.scalars(select(Attendance).where(Attendance.meeting_id==pk))}
    is_admin=user.role=='admin'
    return render(request,db,'meeting.html',active_count=active_count,meeting=m,reg=registration(db,pk,user.id),joined=participates(db,m,user.id),balance=balance(db,user.id),participants=db.scalars(select(User).where(User.id.in_(participants)).order_by(User.id).execution_options(include_deleted=True)).all() if is_admin else [],attendance=attendance if is_admin else {},history=db.scalars(select(RegistrationHistory).where(RegistrationHistory.meeting_id==pk).order_by(RegistrationHistory.id.desc())).all() if is_admin else [],students=db.scalars(select(User).where(User.role=='student')).all() if is_admin else [],registrations={x:registration(db,pk,x) for x in participants} if is_admin else {},files=db.scalars(select(File).where(File.meeting_id==pk)).all() if is_admin or participates(db,m,user.id) else [])


@app.post('/meetings/{pk}/register')
async def register_route(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); form=await request.form(); check_csrf(request,form)
    admin=user.role=='admin'; user_id=int(form.get('user_id',user.id)) if admin else user.id
    student=get_or_404(db,User,user_id)
    if student.role!='student': raise ValueError('Выберите ученика.')
    register(db,pk,user_id,form.get('action')!='cancel',admin); db.commit()
    return redirect(f'/meetings/{pk}')


@app.post('/meetings/{pk}/confirm')
async def confirm_route(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    statuses={int(k[7:]):str(v) for k,v in form.items() if k.startswith('status_')}
    m=lock(db,Meeting,pk)
    topics=str(form.get('covered_topics',m.covered_topics)).strip()
    if len(topics)>15000: raise ValueError('Список тем слишком длинный.')
    if form.get('action')!='cancel' and any(v in ('present','trial') for v in statuses.values()) and not topics:
        raise ValueError('Укажите фактически пройденные темы для недельного отчёта.')
    m.covered_topics=topics
    confirm_meeting(db,pk,int(form.get('duration','0')),statuses,form.get('action')=='cancel',str(form.get('reason','')).strip() or 'Подтверждение занятия'); db.commit()
    return redirect(f'/meetings/{pk}')


@app.post('/meetings/{pk}/paid/{user_id}')
async def mark_paid(pk:int,user_id:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    m=get_or_404(db,Meeting,pk); r=registration(db,pk,user_id)
    if not r or m.payment_mode!='separate': raise ValueError('Отдельная оплата не предусмотрена.')
    paid=form.get('paid','1')=='1'
    if r.paid != paid:
        r.paid=paid
        db.add(RegistrationHistory(meeting_id=pk,user_id=user_id,action='paid' if r.paid else 'payment_revoked'))
    db.commit()
    return redirect(f'/meetings/{pk}')


@app.get('/billing')
def billing(request:Request,student:int|None=None,db=Depends(get_db)):
    user=require_user(request,db)
    students=db.scalars(select(User).where(User.role=='student').order_by(User.name)).all() if user.role=='admin' else [user]
    target=next((u for u in students if u.id==student),students[0] if students else None)
    return render(request,db,'billing.html',students=students,target=target,balance=balance(db,target.id) if target else 0,deleted_meetings=set(db.scalars(select(Meeting.id).where(Meeting.deleted==True).execution_options(include_deleted=True))),ledger=db.scalars(select(Ledger).where(Ledger.user_id==target.id).order_by(Ledger.id.desc())).all() if target else [])


@app.post('/billing/payment')
async def payment_route(request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    user_id=int(form['user_id']); get_or_404(db,User,user_id)
    payment(db,user_id,int(form['minutes']),int(form['amount']),str(form['reason']),localdate(form.get('created_at')),form.get('kind')=='adjustment'); db.commit()
    return redirect(f'/billing?student={user_id}')


@app.post('/billing/refund/{pk}')
async def refund_route(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    original=get_or_404(db,Ledger,pk); refund(db,pk,int(form['minutes']),str(form['reason'])); db.commit()
    return redirect(f'/billing?student={original.user_id}')


@app.post('/billing/request/{pk}')
async def payment_requested(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    u=lock(db,User,pk); u.payment_requested=bool(payment_notice(db,pk)); db.commit()
    return redirect('/dashboard')


@app.get('/profile')
def profile(request:Request,db=Depends(get_db)):
    require_user(request,db); return render(request,db,'profile.html')


@app.post('/profile')
async def profile_save(request:Request,db=Depends(get_db)):
    user=require_user(request,db); form=await request.form(); check_csrf(request,form)
    user.phone=str(form.get('phone',''))[:40]; user.parent_contact=str(form.get('parent_contact',''))[:300]
    if form.get('password'):
        if not verify(str(form.get('old_password','')),user.password_hash): raise ValueError('Текущий пароль неверен.')
        user.password_hash=hash_password(str(form['password']))
    db.commit(); return redirect('/profile')


@app.get('/files/{pk}')
def download(pk:int,request:Request,inline:bool=False,db=Depends(get_db)):
    user=require_user(request,db); f=get_or_404(db,File,pk); allowed=user.role=='admin'
    if f.meeting_id:
        meeting=db.get(Meeting,f.meeting_id)
        allowed |= bool(meeting and participates(db,meeting,user.id))
    if not allowed: raise HTTPException(403,'Файл недоступен.')
    path=Path(os.getenv('STORAGE_DIR','storage'))/f.path
    if not path.is_file(): raise HTTPException(404,'Файл отсутствует в хранилище.')
    return FileResponse(path,filename=f.name,media_type=f.mime,content_disposition_type='inline' if inline and f.mime in ('image/png','image/jpeg') else 'attachment',headers={'Cache-Control':'private, no-store'})


@app.get('/public-content.json')
def public_content(db=Depends(get_db)):
    return export_public(db)


@app.post('/admin/publish-public')
async def publish_public(request:Request,db=Depends(get_db)):
    require_user(request,db,True)
    form=await request.form();check_csrf(request,form)
    last=request.session.get('public_publish_at',0)
    if now().timestamp()-last<60:
        raise ValueError('Публикация уже запрошена. Подождите минуту перед повторным запуском.')
    await trigger_public_deploy()
    request.session['public_publish_at']=now().timestamp()
    request.session['success_message']='Публикация запущена. Главная обновится после успешной сборки Render. Обычно это занимает несколько минут; статус смотрите в Render → Events.'
    return redirect('/dashboard')
