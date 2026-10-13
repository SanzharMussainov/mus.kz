import os
import secrets
import hashlib
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import HTTPException
from .models import User

hasher = PasswordHasher()


def hash_password(password):
    if not 10 <= len(password) <= 200:
        raise ValueError('Пароль должен содержать от 10 до 200 символов.')
    return hasher.hash(password)


def verify(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def current_user(request, db):
    pk = request.session.get('user_id')
    user = db.get(User, pk) if pk else None
    valid = user and user.active and secrets.compare_digest(request.session.get('auth_stamp',''), auth_stamp(user))
    return user if valid else None


def auth_stamp(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:32]


def require_user(request, db, admin=False):
    user = current_user(request, db)
    if not user:
        raise HTTPException(303, headers={'Location':'/login'})
    if admin and user.role != 'admin':
        raise HTTPException(403, 'Доступ только преподавателю.')
    return user


def csrf(request):
    if 'csrf' not in request.session:
        request.session['csrf'] = secrets.token_urlsafe(32)
    return request.session['csrf']


def check_csrf(request, form):
    if not secrets.compare_digest(str(form.get('csrf','')), str(request.session.get('csrf','!'))):
        raise HTTPException(403, 'Форма устарела. Обновите страницу.')
