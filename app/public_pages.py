"""Shared selection of public courses and groups for subject pages."""
def matches(direction, subject):
    value = (direction or '').casefold()
    words = ('русск', 'литератур', 'начальн', 'подготовка к школе', 'памят', 'чтен') if subject == 'russian' else ('математ', 'программ', 'python', 'java', 'информат', 'алгебр', 'геометр')
    return any(word in value for word in words)


def page_data(data, subject):
    return dict(courses=[c for c in data['courses'] if matches(c['direction'], subject)],
                groups=[g for g in data['groups'] if matches(g.get('direction', ''), subject)],
                events=[], subject=subject)
