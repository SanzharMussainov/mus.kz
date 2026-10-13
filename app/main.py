import os
import re
import secrets
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote
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
    return templates.TemplateResponse(request=request, name=name, context=dict(user=current_user(request,db), csrf=csrf(request), settings=db.get(Settings,1) or Settings(title='mus.kz'), specs=SPECS, now=now(), **context))


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
    if not obj:
        raise HTTPException(404,'Запись не найдена.')
    return obj


def localdate(value):
    if not value:
        return None
    d = datetime.fromisoformat(value)
    return d.replace(tzinfo=ZONE) if d.tzinfo is None else d


@app.get('/')
def home(request: Request, db=Depends(get_db)):
    return render(request, db, 'home.html', public_only=True, courses=db.scalars(select(Course).where(Course.public == True)).all(), groups=db.scalars(select(Group).where(Group.status == 'recruiting')).all(), events=db.scalars(select(Meeting).where(Meeting.is_event == True, Meeting.public == True, Meeting.status == 'scheduled', Meeting.starts_at > now()).order_by(Meeting.starts_at)).all())


@app.post('/apply')
async def apply(request: Request, db=Depends(get_db)):
    form = await request.form(); check_csrf(request,form)
    name, contact, message = [str(form.get(k,'')).strip() for k in ('name','contact','message')]
    if not name or not contact or len(name)>160 or len(contact)>200 or len(message)>3000:
        raise ValueError('Укажите имя и контакт. Сообщение — не более 3000 символов.')
    last = request.session.get('lead_at',0)
    if now().timestamp()-last < 60:
        raise ValueError('Заявка уже отправлена. Повторить можно через минуту.')
    db.add(Lead(name=name,contact=contact,message=message)); db.commit()
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
    return render(request,db,'dashboard.html', meetings=[m for m in meetings if m.status=='scheduled' and m.starts_at>=now() and participates(db,m,user.id)][:6], assignments=[a for a in db.scalars(select(Assignment).order_by(Assignment.deadline)) if accessible(db,a,user.id)], balance=balance(db,user.id))


@app.get('/admin/{section}')
def admin_list(section:str, request:Request, db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    model,title,fields=SPECS[section]
    query=select(model).order_by(model.id.desc())
    if model==User: query=query.where(User.role=='student')
    return render(request,db,'admin_list.html',section=section,title=title,rows=db.scalars(query).all())


@app.get('/admin/{section}/{pk}')
def admin_form(section:str, pk:str, request:Request, db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    model,title,fields=SPECS[section]
    obj=get_or_404(db,model,int(pk)) if pk!='new' else None
    if isinstance(obj,User) and obj.role!='student': raise HTTPException(403,'Изменение администратора доступно через CLI.')
    choices={key:db.scalars(select(rel).where(User.role=='student') if rel==User else select(rel)).all() for key,label,kind,rel in fields if rel}
    return render(request,db,'admin_form.html',section=section,title=title,fields=fields,obj=obj,choices=choices,files=list(db.scalars(select(File).where(getattr(File, {'lessons':'lesson_id','tasks':'task_id','meetings':'meeting_id'}.get(section,'id'))==int(pk)))) if pk!='new' and section in ('lessons','tasks','meetings') else [])


@app.post('/admin/{section}/{pk}')
async def admin_save(section:str,pk:str,request:Request,db=Depends(get_db)):
    require_user(request,db,True)
    if section not in SPECS: raise HTTPException(404,'Раздел не найден')
    form=await request.form(); check_csrf(request,form)
    model,title,fields=SPECS[section]
    obj=get_or_404(db,model,int(pk)) if pk!='new' else model()
    if isinstance(obj,User) and obj.id and obj.role!='student': raise HTTPException(403,'Недоступно')
    old_snapshot=bool(getattr(obj,'snapshot',None))
    for key,label,kind,rel in fields:
        value=str(form.get(key,'')).strip()
        if key=='password':
            if value: obj.password_hash=hash_password(value)
            elif not obj.id: raise ValueError('Задайте пароль ученика.')
            continue
        if old_snapshot and key in ('group_id','template_id') and int(value)!=getattr(obj,key):
            raise ValueError('У опубликованной работы нельзя менять группу или шаблон. Создайте новую выдачу.')
        if isinstance(obj,Meeting) and obj.status in ('held','cancelled') and key in ('group_id','is_event','payment_mode'):
            continue
        if kind=='checkbox': value=key in form
        elif kind in ('number','select','optional-select'): value=int(value) if value else None
        elif kind=='datetime-local': value=localdate(value)
        elif '|' in kind and value not in kind.split('|'): raise ValueError('Недопустимое значение: '+label)
        if rel and value is not None:
            related=get_or_404(db,rel,value)
            if rel==User and related.role!='student': raise ValueError('Выберите ученика.')
        col=model.__table__.columns.get(key)
        if col is not None and not col.nullable and (value is None or value=='' and key in ('title','name','email','prompt','answer','direction','level','tolerance')):
            raise ValueError('Заполните поле: '+label)
        if isinstance(value,str) and len(value) > (getattr(col.type,'length',None) or 15000): raise ValueError('Слишком длинное поле: '+label)
        setattr(obj,key,value)
    if isinstance(obj,User):
        obj.email=obj.email.lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',obj.email): raise ValueError('Проверьте email.')
    if isinstance(obj,Task) and obj.status=='ready': check({c.name:getattr(obj,c.name) for c in Task.__table__.columns},obj.answer)
    if isinstance(obj,HomeworkTemplate):
        for task_id in ids(obj.task_ids): get_or_404(db,Task,task_id)
    if isinstance(obj,Assignment):
        if not obj.opens_at <= obj.deadline <= obj.solutions_at or not 1<=obj.max_attempts<=100: raise ValueError('Проверьте даты и количество попыток (1–100).')
        if obj.status=='published': publish(db,obj)
    if isinstance(obj,Group) and obj.starts_at and obj.ends_at and obj.starts_at>obj.ends_at: raise ValueError('Конец обучения раньше начала.')
    if isinstance(obj,Meeting):
        if not 1<=obj.duration<=1440: raise ValueError('Длительность: 1–1440 минут.')
        if obj.meet_url and not re.fullmatch(r'https://meet\.google\.com/[a-zA-Z0-9-]+',obj.meet_url): raise ValueError('Используйте ссылку https://meet.google.com/…')
        if obj.cancel_until and obj.cancel_until>obj.starts_at: raise ValueError('Срок отмены должен быть не позже начала.')
        for x in ids(obj.audience_groups): get_or_404(db,Group,x)
        for x in ids(obj.audience_users): get_or_404(db,User,x)
    if isinstance(obj,Settings):
        if obj.whatsapp and not re.fullmatch(r'\d{10,15}',obj.whatsapp): raise ValueError('WhatsApp: от 10 до 15 цифр.')
        obj.id=1
    db.add(obj); db.commit()
    return redirect(f'/admin/{section}/{obj.id}')


@app.post('/templates/{pk}/copy')
async def copy_template(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form)
    original=get_or_404(db,HomeworkTemplate,pk)
    obj=HomeworkTemplate(title=original.title+' — копия',task_ids=original.task_ids); db.add(obj); db.commit()
    return redirect(f'/admin/templates/{obj.id}')


@app.get('/courses')
def courses_page(request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    courses=db.scalars(select(Course) if user.role=='admin' else select(Course).where(Course.id.in_(course_ids(db,user.id)))).all()
    return render(request,db,'courses.html',courses=courses)


@app.get('/courses/{pk}')
def course_page(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); c=get_or_404(db,Course,pk)
    if user.role!='admin' and pk not in course_ids(db,user.id): raise HTTPException(403,'Курс недоступен.')
    topics=db.scalars(select(Topic).where(Topic.course_id==pk).order_by(Topic.position)).all()
    lessons={t.id:db.scalars(select(Lesson).where(Lesson.topic_id==t.id).order_by(Lesson.position)).all() for t in topics}
    files={l.id:db.scalars(select(File).where(File.lesson_id==l.id)).all() for ls in lessons.values() for l in ls}
    return render(request,db,'course.html',course=c,topics=topics,lessons=lessons,files=files)


@app.get('/homework')
def homework_page(request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    assignments=[a for a in db.scalars(select(Assignment).order_by(Assignment.deadline.desc())) if user.role=='admin' or accessible(db,a,user.id)]
    return render(request,db,'homework.html',assignments=assignments)


def attempt_correct(db, attempt):
    correction=db.scalar(select(GradeCorrection).where(GradeCorrection.attempt_id==attempt.id).order_by(GradeCorrection.id.desc()))
    return correction.correct if correction else attempt.correct


@app.get('/homework/{pk}')
def assignment_page(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); a=get_or_404(db,Assignment,pk)
    if user.role!='admin' and not accessible(db,a,user.id): raise HTTPException(403,'Работа недоступна.')
    attempts=db.scalars(select(Attempt).where(Attempt.assignment_id==pk,Attempt.user_id==user.id).order_by(Attempt.id)).all()
    tasks=[]; score=0
    for i,t in enumerate(a.snapshot):
        # Only explicitly permitted properties reach the template/browser.
        public={k:t.get(k) for k in ('title','prompt','kind','options','file_ids')}
        public['attempts']=[(x,attempt_correct(db,x)) for x in attempts if x.task_index==i]
        public['remaining']=a.max_attempts-len(public['attempts'])
        public['index']=i
        public['corrections']=[c for x,_ in public['attempts'] for c in db.scalars(select(GradeCorrection).where(GradeCorrection.attempt_id==x.id).order_by(GradeCorrection.id))]
        if any(correct for _,correct in public['attempts']): score+=1
        if now()>=a.solutions_at:
            public.update(answer=t['answer'],solution=t['solution'])
        tasks.append(public)
    return render(request,db,'assignment.html',assignment=a,tasks=tasks,score=score,files=db.scalars(select(File).where(File.assignment_id==pk,File.owner_id==user.id)).all())


@app.post('/homework/{pk}/answer/{index}')
async def answer(pk:int,index:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); form=await request.form(); check_csrf(request,form)
    value=';'.join(form.getlist('answer'))
    submit(db,pk,user.id,index,value); db.commit()
    return redirect(f'/homework/{pk}#task-{index}')


@app.get('/results')
def results(request:Request,group_id:str='',student_id:str='',assignment_id:str='',db=Depends(get_db)):
    user=require_user(request,db)
    group_id=int(group_id) if group_id else None
    student_id=int(student_id) if student_id else None
    assignment_id=int(assignment_id) if assignment_id else None
    query=select(Attempt).order_by(Attempt.created_at.desc())
    if user.role!='admin': query=query.where(Attempt.user_id==user.id)
    else:
        if group_id: query=query.where(Attempt.assignment_id.in_(select(Assignment.id).where(Assignment.group_id==group_id)))
        if student_id: query=query.where(Attempt.user_id==student_id)
    if assignment_id: query=query.where(Attempt.assignment_id==assignment_id)
    attempts=db.scalars(query).all()
    return render(request,db,'results.html',attempts=[(a,db.get(User,a.user_id),db.get(Assignment,a.assignment_id),attempt_correct(db,a)) for a in attempts],files=db.scalars(select(File).where(File.assignment_id!=None) if user.role=='admin' else select(File).where(File.assignment_id!=None,File.owner_id==user.id)).all())


@app.post('/results/{pk}/correct')
async def correct_grade(pk:int,request:Request,db=Depends(get_db)):
    require_user(request,db,True); form=await request.form(); check_csrf(request,form); get_or_404(db,Attempt,pk)
    reason=str(form.get('reason','')).strip()
    if not reason: raise ValueError('Укажите причину изменения оценки.')
    db.add(GradeCorrection(attempt_id=pk,correct=form.get('correct')=='true',reason=reason)); db.commit()
    return redirect('/results')


@app.get('/calendar')
def calendar(request:Request,db=Depends(get_db)):
    user=require_user(request,db)
    meetings=[m for m in db.scalars(select(Meeting).order_by(Meeting.starts_at)) if user.role=='admin' or meeting_access(db,m,user.id)]
    return render(request,db,'calendar.html',meetings=meetings,registrations={m.id:registration(db,m.id,user.id) for m in meetings})


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
    return render(request,db,'meeting.html',active_count=active_count,meeting=m,reg=registration(db,pk,user.id),joined=participates(db,m,user.id),balance=balance(db,user.id),participants=[db.get(User,x) for x in sorted(participants)] if is_admin else [],attendance=attendance if is_admin else {},history=db.scalars(select(RegistrationHistory).where(RegistrationHistory.meeting_id==pk).order_by(RegistrationHistory.id.desc())).all() if is_admin else [],students=db.scalars(select(User).where(User.role=='student')).all() if is_admin else [],registrations={x:registration(db,pk,x) for x in participants} if is_admin else {},files=db.scalars(select(File).where(File.meeting_id==pk)).all() if is_admin or participates(db,m,user.id) else [])


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
    return render(request,db,'billing.html',students=students,target=target,balance=balance(db,target.id) if target else 0,ledger=db.scalars(select(Ledger).where(Ledger.user_id==target.id).order_by(Ledger.id.desc())).all() if target else [])


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


@app.post('/files/upload')
async def upload(request:Request,db=Depends(get_db)):
    user=require_user(request,db); form=await request.form(); check_csrf(request,form)
    scope=str(form.get('scope','')); pk=int(form.get('target','0'))
    model={'lesson':Lesson,'assignment':Assignment,'task':Task,'meeting':Meeting}.get(scope)
    if not model: raise ValueError('Неизвестное назначение файла.')
    obj=get_or_404(db,model,pk)
    if user.role!='admin':
        if scope!='assignment' or not accessible(db,obj,user.id): raise HTTPException(403,'Загрузка недоступна.')
        if now()>=obj.solutions_at or now()>obj.deadline and not obj.allow_late: raise ValueError('Срок загрузки решения истёк.')
    file=form.get('file')
    if not file or not hasattr(file,'read'): raise ValueError('Выберите файл.')
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024: raise ValueError('Файл должен быть не больше 10 МБ.')
    mime='application/pdf' if data.startswith(b'%PDF-') else 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if data.startswith(b'\xff\xd8\xff') else None
    if not mime: raise ValueError('Допустимы только PDF, PNG и JPEG.')
    storage=Path(os.getenv('STORAGE_DIR','storage')); storage.mkdir(parents=True,exist_ok=True)
    filename=secrets.token_hex(24); path=storage/filename; path.write_bytes(data)
    obj=File(owner_id=user.id,name=Path(file.filename or 'file').name[:250],path=filename,mime=mime,size=len(data),**{scope+'_id':pk})
    try:
        db.add(obj); db.commit()
    except Exception:
        path.unlink(missing_ok=True); raise
    dest={'assignment':f'/homework/{pk}','lesson':f'/admin/lessons/{pk}','task':f'/admin/tasks/{pk}','meeting':f'/admin/meetings/{pk}'}
    return redirect(dest[scope])


@app.get('/files/{pk}')
def download(pk:int,request:Request,db=Depends(get_db)):
    user=require_user(request,db); f=get_or_404(db,File,pk); allowed=user.role=='admin'
    if f.assignment_id: allowed|=f.owner_id==user.id
    if f.lesson_id:
        lesson=db.get(Lesson,f.lesson_id); topic=db.get(Topic,lesson.topic_id); allowed|=topic.course_id in course_ids(db,user.id)
    if f.meeting_id:
        allowed|=participates(db,db.get(Meeting,f.meeting_id),user.id)
    if f.task_id:
        allowed|=any(accessible(db,a,user.id) and any(pk in t.get('file_ids',[]) for t in a.snapshot) for a in db.scalars(select(Assignment)))
    if not allowed: raise HTTPException(403,'Файл недоступен.')
    path=Path(os.getenv('STORAGE_DIR','storage'))/f.path
    if not path.is_file(): raise HTTPException(404,'Файл отсутствует в хранилище.')
    return FileResponse(path,filename=f.name,media_type=f.mime,headers={'Cache-Control':'private, no-store'})
