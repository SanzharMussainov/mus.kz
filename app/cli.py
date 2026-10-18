import argparse
import getpass
from datetime import timedelta
from sqlalchemy import select
from .db import Session, now
from .models import *
from .security import hash_password
from .services import payment


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
        db.add(Meeting(title='Алгебра: разбираем уравнения · демо',group_id=group.id,starts_at=now()+timedelta(days=1),duration=60))
        db.add(Meeting(title='Подготовка к СОР · демо',description='Разбираем задания по алгебре, 7 класс. Демонстрационное событие.',is_event=True,public=True,audience='all',starts_at=now()+timedelta(days=2),duration=90,payment_mode='free'))
        db.add(Meeting(title='Прошедшее занятие · демо',group_id=group.id,starts_at=now()-timedelta(days=1),duration=60))
        payment(db,student.id,30,0,'Демонстрационное начисление, не реальная оплата'); db.commit()
        print('ДЕМО: teacher@example.test / Teacher-demo-2026')
        print('ДЕМО: student@example.test / Student-demo-2026')
        print('Не используйте эти аккаунты на публичном сервере.')


if __name__=='__main__': main()
