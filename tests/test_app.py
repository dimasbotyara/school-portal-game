# tests/test_app.py
"""Тесты школьного портала: авторизация, оценки, задания, настройки."""
import os
import tempfile

# Важно: временная БД ДО импорта app
_TMPDIR = tempfile.mkdtemp(prefix='school_test_')
os.environ['SCHOOL_PORTAL_DB'] = f'sqlite:///{_TMPDIR}/test.db'
os.environ['SECRET_KEY'] = 'test-secret-key'

import pytest  # noqa: E402

from app import app, db  # noqa: E402
from models import Assignment, Grade, Praise, Subject, User, get_setting, set_setting  # noqa: E402


@pytest.fixture()
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def _login(client, user_id):
    # Роут /login не пускает уже залогиненного — сбрасываем сессию
    client.get('/logout')
    return client.post('/login', data={'user_id': user_id})


@pytest.fixture(autouse=True)
def _ensure_student():
    """init_db() создаёт только учителя — добавим тестового ученика."""
    with app.app_context():
        if not User.query.filter_by(role='student').first():
            db.session.add(User(first_name='Ученик', last_name='Тестовый',
                                role='student', avatar_emoji='🤓'))
            db.session.commit()


@pytest.fixture()
def teacher_id():
    with app.app_context():
        return User.query.filter_by(role='teacher').first().id


@pytest.fixture()
def teacher_client(client, teacher_id):
    _login(client, teacher_id)
    return client


@pytest.fixture()
def student_client(client):
    with app.app_context():
        student = User.query.filter_by(role='student').first()
        sid = student.id
    _login(client, sid)
    return client


@pytest.fixture()
def subject_id():
    with app.app_context():
        return Subject.query.first().id


@pytest.fixture()
def student_id():
    with app.app_context():
        return User.query.filter_by(role='student').first().id


# ── Авторизация и доступ ─────────────────────────────────────────────────────

def test_login_page_lists_users(client):
    rv = client.get('/login')
    assert rv.status_code == 200
    assert 'Школьный портал'.encode() in rv.data


def test_login_redirects_by_role(client, teacher_id):
    rv = _login(client, teacher_id)
    assert rv.status_code == 302
    assert '/teacher' in rv.headers['Location']


def test_teacher_pages_require_teacher(client, student_client):
    # Ученик не может открыть панель учителя
    rv = student_client.get('/teacher')
    assert rv.status_code == 302


def test_student_pages_require_student(client, teacher_client):
    rv = teacher_client.get('/student')
    assert rv.status_code == 302


def test_anonymous_redirected_to_login(client):
    for path in ('/teacher', '/student', '/teacher/gradebook'):
        rv = client.get(path)
        assert rv.status_code == 302
        assert '/login' in rv.headers['Location']


def test_404_redirects(client, teacher_client):
    rv = teacher_client.get('/no/such/page')
    assert rv.status_code == 302


# ── Оценки ───────────────────────────────────────────────────────────────────

def test_add_grade_via_form(teacher_client, student_id, subject_id):
    rv = teacher_client.post('/teacher/grade/add', data={
        'student_id': student_id, 'subject_id': subject_id,
        'value': 5, 'date': '2026-11-10', 'comment': 'Молодец!',
    })
    assert rv.status_code == 302
    with app.app_context():
        g = Grade.query.filter_by(student_id=student_id,
                                  subject_id=subject_id, value=5).first()
        assert g is not None
        assert g.comment == 'Молодец!'


def test_add_grade_rejects_invalid_value(teacher_client, student_id, subject_id):
    before = Grade.query.count()
    rv = teacher_client.post('/teacher/grade/add', data={
        'student_id': student_id, 'subject_id': subject_id,
        'value': 9, 'date': '2026-11-10',
    })
    assert rv.status_code == 302
    assert Grade.query.count() == before


def test_api_grade_cell_valid_and_invalid(teacher_client, student_id, subject_id):
    # Валидная оценка
    rv = teacher_client.post('/api/grades/cell', json={
        'student_id': student_id, 'subject_id': subject_id,
        'date': '2026-11-10', 'value': 4,
    })
    assert rv.status_code == 200
    assert rv.get_json()['success'] is True

    # Оценка вне диапазона 1–5 больше не сохранится (раньше это был баг)
    rv = teacher_client.post('/api/grades/cell', json={
        'student_id': student_id, 'subject_id': subject_id,
        'date': '2026-11-10', 'value': 100,
    })
    assert rv.status_code == 400

    # Строка вместо числа
    rv = teacher_client.post('/api/grades/cell', json={
        'student_id': student_id, 'subject_id': subject_id,
        'date': '2026-11-10', 'value': 'five',
    })
    assert rv.status_code == 400


def test_edit_grade_safe_conversion(teacher_client, student_id, subject_id):
    with app.app_context():
        g = Grade(student_id=student_id, subject_id=subject_id,
                  value=3, date=__import__('datetime').date(2026, 11, 10))
        db.session.add(g)
        db.session.commit()
        gid = g.id

    # Нечисловое значение не должно ронять сервер (раньше был ValueError)
    rv = teacher_client.post(f'/teacher/grade/edit/{gid}',
                             json={'value': 'not-a-number'})
    assert rv.status_code == 302
    with app.app_context():
        assert db.session.get(Grade, gid).value == 3

    # Корректное изменение
    rv = teacher_client.post(f'/teacher/grade/edit/{gid}', json={'value': 5})
    assert rv.status_code == 302
    with app.app_context():
        assert db.session.get(Grade, gid).value == 5


def test_student_cannot_grade(student_client, student_id, subject_id):
    rv = student_client.post('/api/grades/cell', json={
        'student_id': student_id, 'subject_id': subject_id,
        'date': '2026-11-10', 'value': 5,
    })
    assert rv.status_code == 403


# ── Задания и тесты ──────────────────────────────────────────────────────────

def test_create_assignment_keeps_gap_questions(teacher_client, subject_id):
    """При удалении среднего вопроса в конструкторе индексы идут с
    пропусками — раньше все вопросы после пропуска терялись молча."""
    rv = teacher_client.post('/teacher/assignment/create', data={
        'subject_id': subject_id,
        'title': 'Тест с пропуском',
        'assignment_type': 'test',
        'date_due': '2026-12-01',
        'question_text_0': 'Вопрос первый',
        'question_type_0': 'text',
        'question_correct_0': 'ответ',
        # индекс 1 отсутствует — вопрос был удалён в форме
        'question_text_2': 'Вопрос третий',
        'question_type_2': 'text',
        'question_correct_2': 'ответ2',
    })
    assert rv.status_code == 302
    with app.app_context():
        a = Assignment.query.filter_by(title='Тест с пропуском').first()
        assert a is not None
        texts = {q.text for q in a.questions}
        assert texts == {'Вопрос первый', 'Вопрос третий'}


def test_student_test_flow(client, student_client, teacher_client, subject_id,
                           student_id):
    teacher_client.post('/teacher/assignment/create', data={
        'subject_id': subject_id,
        'title': 'Тест на 5',
        'assignment_type': 'test',
        'date_due': '2026-12-01',
        'question_text_0': '2+2?',
        'question_type_0': 'choice',
        'question_options_0': '3, 4, 5',
        'question_correct_0': '4',
    })
    with app.app_context():
        a = Assignment.query.filter_by(title='Тест на 5').first()
        aid = a.id
        qid = a.questions[0].id

    # teacher_client перелогинил общий client — возвращаемся к ученику
    _login(client, student_id)

    rv = client.get(f'/student/test/{aid}')
    assert rv.status_code == 200

    rv = client.post(f'/student/test/{aid}', data={f'answer_{qid}': '4'})
    assert rv.status_code == 302

    # Повторная сдача не принимается
    rv = client.post(f'/student/test/{aid}', data={f'answer_{qid}': '3'})
    assert rv.status_code == 200  # показываются результаты, ответы не меняются
    with app.app_context():
        from models import StudentAnswer
        answers = StudentAnswer.query.filter_by(student_id=student_id).all()
        assert len(answers) == 1
        assert answers[0].is_correct is True


# ── Предметы: каскадное удаление ─────────────────────────────────────────────

def test_delete_subject_cascades(teacher_client, student_id):
    with app.app_context():
        s = Subject(name='Временный предмет', emoji='🧪', color='#FF0000')
        db.session.add(s)
        db.session.flush()
        g = Grade(student_id=student_id, subject_id=s.id,
                  value=4, date=__import__('datetime').date(2026, 11, 10))
        a = Assignment(subject_id=s.id, title='ДЗ по временному',
                       assignment_type='homework',
                       date_assigned=__import__('datetime').date(2026, 11, 1),
                       date_due=__import__('datetime').date(2026, 12, 1))
        db.session.add_all([g, a])
        db.session.commit()
        sid, aid = s.id, a.id

    # Раньше здесь падал IntegrityError (500), т.к. оценки оставались висеть
    rv = teacher_client.post('/teacher/subjects', data={
        'action': 'delete', 'subject_id': sid,
    })
    assert rv.status_code == 302
    with app.app_context():
        assert db.session.get(Subject, sid) is None
        assert db.session.get(Assignment, aid) is None
        assert Grade.query.filter_by(subject_id=sid).count() == 0


# ── Награды ──────────────────────────────────────────────────────────────────

def test_send_praise(teacher_client, student_id):
    rv = teacher_client.post('/teacher/praise/send', data={
        'student_id': student_id, 'praise_type': 'star', 'message': 'Отлично!',
    })
    assert rv.status_code == 302
    with app.app_context():
        p = Praise.query.filter_by(student_id=student_id,
                                   praise_type='star').first()
        assert p is not None and p.message == 'Отлично!'


def test_send_praise_missing_student_no_crash(teacher_client):
    # Раньше student.first_name падал с AttributeError
    rv = teacher_client.post('/teacher/praise/send', data={
        'student_id': 99999, 'praise_type': 'star',
    })
    assert rv.status_code == 302


# ── Настройки ────────────────────────────────────────────────────────────────

def test_add_and_delete_student(teacher_client):
    rv = teacher_client.post('/teacher/settings/student/add', data={
        'first_name': 'Тестик', 'last_name': 'Тестов', 'avatar_emoji': '🤖',
    })
    assert rv.status_code == 302
    with app.app_context():
        s = User.query.filter_by(last_name='Тестов').first()
        assert s is not None and s.avatar_emoji == '🤖'
        sid = s.id

    # Оценка, чтобы проверить каскад при удалении ученика
    with app.app_context():
        subj = Subject.query.first()
        db.session.add(Grade(student_id=sid, subject_id=subj.id,
                             value=5,
                             date=__import__('datetime').date(2026, 11, 10)))
        db.session.commit()

    rv = teacher_client.post(f'/teacher/settings/student/{sid}/delete')
    assert rv.status_code == 302
    with app.app_context():
        assert db.session.get(User, sid) is None
        assert Grade.query.filter_by(student_id=sid).count() == 0


def test_settings_date_and_period(teacher_client):
    rv = teacher_client.post('/teacher/settings/date',
                             data={'action': 'set', 'date': '2026-11-20'})
    assert rv.status_code == 302
    with app.app_context():
        assert get_setting('current_date') == '2026-11-20'

    rv = teacher_client.post('/teacher/settings/date', data={'action': 'reset'})
    assert rv.status_code == 302
    with app.app_context():
        assert get_setting('current_date') == ''

    rv = teacher_client.post('/teacher/settings/period',
                             data={'action': 'number', 'period': 2})
    assert rv.status_code == 302
    with app.app_context():
        assert get_setting('current_period') == '2'
        set_setting('current_period', '1')


def test_settings_reject_bad_date(teacher_client):
    rv = teacher_client.post('/teacher/settings/date',
                             data={'action': 'set', 'date': 'мусор'})
    assert rv.status_code == 302


# ── Ученические страницы ─────────────────────────────────────────────────────

def test_student_dashboard(student_client):
    rv = student_client.get('/student')
    assert rv.status_code == 200
    assert 'Привет'.encode() in rv.data


def test_student_diary_and_progress(student_client):
    assert student_client.get('/student/diary').status_code == 200
    assert student_client.get('/student/progress').status_code == 200


def test_homework_toggle(client, student_id, teacher_client, subject_id):
    teacher_client.post('/teacher/assignment/create', data={
        'subject_id': subject_id,
        'title': 'ДЗ для галочки', 'assignment_type': 'homework',
        'date_due': '2026-12-01',
    })
    with app.app_context():
        aid = Assignment.query.filter_by(title='ДЗ для галочки').first().id

    # teacher_client перелогинил общий client — возвращаемся к ученику
    _login(client, student_id)

    rv = client.post(f'/student/complete_homework/{aid}',
                     headers={'X-Requested-With': 'XMLHttpRequest'})
    assert rv.status_code == 200
    assert rv.get_json()['completed'] is True

    # Повторный клик снимает отметку
    rv = client.post(f'/student/complete_homework/{aid}',
                     headers={'X-Requested-With': 'XMLHttpRequest'})
    assert rv.get_json()['completed'] is False
