import argparse
import getpass
from datetime import timedelta
from sqlalchemy import select
from .db import Session, now
from .models import *
from .security import hash_password
from .services import publish, payment


def main():
    parser=argparse.ArgumentParser(description='Управление mus.kz')
    parser.add_argument('command', choices=['create-admin','reset-password','seed-demo'])
    parser.add_argument('--email')
    parser.add_argument('--name',default='Преподаватель')
    args=parser.parse_args()
    with Session() as db:
        if args.command in ('create-admin','reset-password'):
            email=(args.email or input('Email: ')).strip().lower()
            password=getpass.getpass('Пароль (от 10 символов): ')
            if password!=getpass.getpass('Повторите пароль: '): raise SystemExit('Пароли не совпадают')
            user=db.scalar(select(User).where(User.email==email))
            if args.command=='create-admin':
                if user: raise SystemExit('Пользователь уже существует')
                user=User(name=args.name,email=email,role='admin',password_hash=hash_password(password)); db.add(user)
            else:
                if not user: raise SystemExit('Пользователь не найден')
                user.password_hash=hash_password(password)
            if not db.get(Settings,1): db.add(Settings(id=1))
            db.commit(); print('Готово'); return
        if db.scalar(select(User).where(User.email=='student@example.test')):
            print('Демонстрационные данные уже загружены.'); return
        student=User(name='Демо · Алия',email='student@example.test',role='student',password_hash=hash_password('Student-demo-2026'))
        admin=db.scalar(select(User).where(User.email=='teacher@example.test'))
        if not admin:
            admin=User(name='Демо · Преподаватель',email='teacher@example.test',role='admin',password_hash=hash_password('Teacher-demo-2026')); db.add(admin)
        db.add(student)
        if not db.get(Settings,1): db.add(Settings(id=1))
        courses=[]
        for grade,description in [(5,'Дроби, проценты и первые уравнения. Строим прочную основу.'),(6,'Отрицательные числа, пропорции и задачи на логику.'),(7,'Алгебра и геометрия: от выражений к доказательствам.')]:
            course=Course(title=f'Математика, {grade} класс · демо',description=description,direction='Школьная математика',grade=grade,level='Базовый',public=True); db.add(course); courses.append(course)
        db.flush()
        group=Group(title='Демо · 7 класс, вторник и четверг',course_id=courses[-1].id,schedule='Вторник и четверг, 18:00 · демонстрационное расписание',status='recruiting',starts_at=now(),ends_at=now()+timedelta(days=120)); db.add(group); db.flush()
        db.add(Membership(group_id=group.id,user_id=student.id))
        topic=Topic(course_id=courses[-1].id,title='Дроби и уравнения',position=1); db.add(topic); db.flush()
        db.add(Lesson(topic_id=topic.id,title='Равные дроби',content='Демо-урок. Умножение числителя и знаменателя на одно число сохраняет значение дроби: \\(\\frac{2}{3}=\\frac{4}{6}\\).',position=1))
        tasks=[]
        examples=[('Дроби','Сократите дробь \\(4/6\\).','fraction','2/3','','Разделите числитель и знаменатель на 2.'),('Линейное уравнение','Решите \\(2x+3=10\\).','number','3.5','','Вычтите 3 и разделите на 2.'),('Корни','Решите \\(x^2=4\\).','set','-2;2','','Оба числа при возведении в квадрат дают 4.'),('Простое число','Выберите простое число.','single','7','4\n7\n9','У числа 7 ровно два натуральных делителя.'),('Чётные числа','Выберите все чётные числа.','multiple','2;4','2\n3\n4','Чётные числа делятся на 2.')]
        for title,prompt,kind,answer,options,solution in examples:
            task=Task(title=title+' · демо',prompt=prompt,kind=kind,answer=answer,options=options,solution=solution,tolerance='0',status='ready',grade=7,topic='Основы'); db.add(task); tasks.append(task)
        db.flush(); template=HomeworkTemplate(title='Практика №1 · демо',task_ids=','.join(str(t.id) for t in tasks)); db.add(template); db.flush()
        assignment=Assignment(group_id=group.id,template_id=template.id,title='Дроби и уравнения · демо',opens_at=now()-timedelta(days=1),deadline=now()+timedelta(days=3),solutions_at=now()+timedelta(days=4),max_attempts=3,allow_late=True)
        publish(db,assignment); db.add(assignment)
        db.add(Meeting(title='Алгебра: разбираем уравнения · демо',group_id=group.id,starts_at=now()+timedelta(days=1),duration=60))
        db.add(Meeting(title='Подготовка к СОР · демо',description='Разбираем задания по алгебре, 7 класс. Демонстрационное событие.',is_event=True,public=True,audience='all',starts_at=now()+timedelta(days=2),duration=90,payment_mode='free'))
        db.add(Meeting(title='Прошедшее занятие · демо',group_id=group.id,starts_at=now()-timedelta(days=1),duration=60))
        payment(db,student.id,30,0,'Демонстрационное начисление, не реальная оплата'); db.commit()
        print('ДЕМО: teacher@example.test / Teacher-demo-2026')
        print('ДЕМО: student@example.test / Student-demo-2026')
        print('Не используйте эти аккаунты на публичном сервере.')


if __name__=='__main__': main()
