"""Bounded parsing of numeric answers. No symbolic execution."""
import re
from fractions import Fraction


def number(value):
    value = str(value).strip().replace('−', '-').replace(',', '.')
    if len(value) > 100 or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:\s*/\s*[+-]?\d+)?', value):
        raise ValueError('Введите число или дробь, например −1,5 или 2/3.')
    try:
        parts = value.split('/')
        result = Fraction(parts[0].strip())
        if len(parts) == 2:
            result /= Fraction(parts[1].strip())
        return result
    except (ValueError, ZeroDivisionError):
        raise ValueError('Знаменатель дроби не может быть нулём.')


def check(task, value):
    value = value.strip()
    if not value or len(value) > 2000:
        raise ValueError('Введите ответ (не более 2000 символов).')
    answer, kind = task['answer'], task['kind']
    if kind in ('single', 'multiple'):
        options = task.get('options', '').splitlines()
        values = [x.strip() for x in value.split(';')]
        expected = [x.strip() for x in answer.split(';')]
        if any(x not in options for x in values) or (kind == 'single' and len(values) != 1):
            raise ValueError('Выберите допустимый вариант ответа.')
        return set(values) == set(expected)
    tolerance = number(task.get('tolerance', '0'))
    if tolerance < 0:
        raise ValueError('Погрешность не может быть отрицательной.')
    if kind in ('number', 'fraction'):
        equal = abs(number(value) - number(answer)) <= tolerance
        if kind == 'fraction' and task.get('exact_form'):
            return equal and re.sub(r'\s', '', value) == re.sub(r'\s', '', answer)
        return equal
    if kind == 'set':
        actual = [number(x) for x in value.split(';')]
        expected = [number(x) for x in answer.split(';')]
        if not task.get('ordered'):
            actual.sort()
            expected.sort()
        return len(actual) == len(expected) and all(abs(a-b) <= tolerance for a,b in zip(actual, expected))
    raise ValueError('Неизвестный тип задания.')
