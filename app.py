# app.py
import calendar as cal_module
import os
from datetime import date, datetime, timedelta

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)

from models import (
    Assignment,
    ControlWork,
    Grade,
    HomeworkCompletion,
    Praise,
    Question,
    ScheduleItem,
    StudentAnswer,
    Subject,
    User,
    db,
    get_setting,
    set_setting,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'school-portal-secret-key-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'SCHOOL_PORTAL_DB', 'sqlite:///school.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему 🔑'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Вспомогательные функции ──────────────────────────────────────────────────

def get_current_date():
    custom = get_setting('current_date', '')
    if custom:
        try:
            return datetime.strptime(custom, '%Y-%m-%d').date()
        except ValueError:
            pass
    return date.today()


def get_current_period():
    return int(get_setting('current_period', '1'))


def get_period_type():
    return get_setting('period_type', 'quarter')


DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
DAY_NAMES_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
MONTH_NAMES = ['', 'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
               'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


def get_day_name(d):
    return DAY_NAMES[d.weekday()]


def get_day_name_short(d):
    return DAY_NAMES_SHORT[d.weekday()]


@app.context_processor
def inject_globals():
    today = get_current_date()
    return {
        'current_date': today,
        'current_period': get_current_period(),
        'period_type': get_period_type(),
        'get_day_name': get_day_name,
        'get_day_name_short': get_day_name_short,
        'day_names': DAY_NAMES,
        'day_names_short': DAY_NAMES_SHORT,
        'today': today,
        'tomorrow': today + timedelta(days=1),
    }


# ── Авторизация ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('teacher_dashboard')
                        if current_user.role == 'teacher'
                        else url_for('student_dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    users = User.query.order_by(User.role.desc(), User.last_name).all()
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        if user_id:
            user = db.session.get(User, int(user_id))
            if user:
                login_user(user)
                flash(f'Привет, {user.first_name}! {user.avatar_emoji}', 'success')
                return redirect(url_for('teacher_dashboard')
                                if user.role == 'teacher'
                                else url_for('student_dashboard'))
        flash('Пользователь не найден 😕', 'error')
    return render_template('login.html', users=users)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы 👋', 'info')
    return redirect(url_for('login'))


# ── Панель учителя — главная ─────────────────────────────────────────────────

@app.route('/teacher')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        flash('Доступ только для учителя! 🚫', 'error')
        return redirect(url_for('index'))

    today = get_current_date()
    students = User.query.filter_by(role='student').order_by(User.last_name).all()
    subjects = Subject.query.all()
    recent_grades = (Grade.query
                     .order_by(Grade.date.desc(), Grade.id.desc())
                     .limit(10).all())
    assignments = (Assignment.query
                   .filter(Assignment.date_due >= today)
                   .order_by(Assignment.date_due)
                   .limit(5).all())
    controls = (ControlWork.query
                .filter(ControlWork.date >= today)
                .order_by(ControlWork.date)
                .limit(5).all())
    praises_today = Praise.query.filter_by(date=today).all()

    return render_template('teacher/dashboard.html',
                           students=students, subjects=subjects,
                           recent_grades=recent_grades,
                           assignments=assignments,
                           controls=controls,
                           praises_today=praises_today,
                           total_students=len(students),
                           total_grades_today=Grade.query.filter_by(date=today).count())


# ── Журнал оценок ────────────────────────────────────────────────────────────

@app.route('/teacher/gradebook')
@login_required
def teacher_gradebook():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    subject_id = request.args.get('subject_id', type=int)
    subjects = Subject.query.order_by(Subject.name).all()
    students = User.query.filter_by(role='student').order_by(User.last_name).all()

    if not subject_id and subjects:
        subject_id = subjects[0].id

    current_subject = db.session.get(Subject, subject_id) if subject_id else None
    period = get_current_period()
    today = get_current_date()

    # 14 дней назад + сегодня
    dates = [today - timedelta(days=i) for i in range(13, -1, -1)]

    # Дни недели, когда предмет стоит в расписании
    schedule_days = set()
    if subject_id:
        for si in ScheduleItem.query.filter_by(subject_id=subject_id).all():
            schedule_days.add(si.day_of_week)

    # Оценки → словарь (student_id, date_iso) → [Grade]
    grades_map = {}
    averages = {}
    if subject_id:
        grades = Grade.query.filter_by(subject_id=subject_id, period=period).all()
        for g in grades:
            key = (g.student_id, g.date.isoformat())
            grades_map.setdefault(key, []).append(g)

        for student in students:
            sg = [g for g in grades if g.student_id == student.id]
            averages[student.id] = round(sum(g.value for g in sg) / len(sg), 1) if sg else None

    return render_template('teacher/gradebook.html',
                           subjects=subjects,
                           students=students,
                           current_subject=current_subject,
                           subject_id=subject_id,
                           dates=dates,
                           grades_map=grades_map,
                           averages=averages,
                           schedule_days=schedule_days,
                           period=period)


@app.route('/teacher/grade/add', methods=['POST'])
@login_required
def add_grade():
    if current_user.role != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    student_id = request.form.get('student_id', type=int)
    subject_id = request.form.get('subject_id', type=int)
    value = request.form.get('value', type=int)
    date_str = request.form.get('date', '')
    comment = request.form.get('comment', '')

    if not all([student_id, subject_id, value]) or not (1 <= value <= 5):
        flash('Ошибка в данных оценки ❌', 'error')
        return redirect(url_for('teacher_gradebook', subject_id=subject_id))

    try:
        grade_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        grade_date = get_current_date()

    grade = Grade(student_id=student_id, subject_id=subject_id,
                  value=value, date=grade_date,
                  comment=comment, period=get_current_period())
    db.session.add(grade)
    db.session.commit()

    flash(f'Оценка {value} поставлена! ✅', 'success')
    return redirect(url_for('teacher_gradebook', subject_id=subject_id))


@app.route('/teacher/grade/edit/<int:grade_id>', methods=['POST'])
@login_required
def edit_grade(grade_id):
    if current_user.role != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    grade = db.session.get(Grade, grade_id)
    if not grade:
        return jsonify({'error': 'not found'}), 404

    data = request.get_json(silent=True) or {}
    new_value = data.get('value') or request.form.get('value', type=int)

    try:
        new_value = int(new_value)
    except (TypeError, ValueError):
        new_value = None

    if new_value and 1 <= new_value <= 5:
        grade.value = new_value
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'value': grade.value})
        flash(f'Оценка изменена на {grade.value} ✅', 'success')
    else:
        flash('Неверное значение оценки ❌', 'error')

    return redirect(url_for('teacher_gradebook', subject_id=grade.subject_id))


@app.route('/teacher/grade/delete/<int:grade_id>', methods=['POST'])
@login_required
def delete_grade(grade_id):
    if current_user.role != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    grade = db.session.get(Grade, grade_id)
    if not grade:
        return jsonify({'error': 'not found'}), 404

    subject_id = grade.subject_id
    db.session.delete(grade)
    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True})
    flash('Оценка удалена 🗑️', 'info')
    return redirect(url_for('teacher_gradebook', subject_id=subject_id))


# API — быстрая оценка из журнала
@app.route('/api/grades/cell', methods=['POST'])
@login_required
def api_grade_cell():
    if current_user.role != 'teacher':
        return jsonify({'error': 'forbidden'}), 403

    data = request.get_json()
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')
    date_str = data.get('date')
    value = data.get('value')

    if not all([student_id, subject_id, date_str, value]):
        return jsonify({'error': 'missing data'}), 400

    try:
        value = int(value)
    except (TypeError, ValueError):
        return jsonify({'error': 'invalid value'}), 400
    if not 1 <= value <= 5:
        return jsonify({'error': 'invalid value'}), 400

    try:
        grade_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'invalid date'}), 400

    grade = Grade(student_id=student_id, subject_id=subject_id,
                  value=value, date=grade_date,
                  period=get_current_period())
    db.session.add(grade)
    db.session.commit()
    return jsonify({'success': True, 'grade_id': grade.id, 'value': value})


# ── Конструктор заданий ──────────────────────────────────────────────────────

@app.route('/teacher/assignments')
@login_required
def teacher_assignments():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    filter_subj = request.args.get('subject_id', type=int)
    subjects = Subject.query.order_by(Subject.name).all()
    today = get_current_date()

    q = Assignment.query
    if filter_subj:
        q = q.filter_by(subject_id=filter_subj)
    assignments = q.order_by(Assignment.date_due.desc()).all()

    return render_template('teacher/assignments.html',
                           subjects=subjects,
                           assignments=assignments,
                           today=today,
                           filter_subj=filter_subj)


@app.route('/teacher/assignment/create', methods=['POST'])
@login_required
def create_assignment():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    subject_id = request.form.get('subject_id', type=int)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    assignment_type = request.form.get('assignment_type', 'homework')
    date_due_str = request.form.get('date_due', '')

    if not title or not subject_id:
        flash('Заполните название и предмет! ❌', 'error')
        return redirect(url_for('teacher_assignments'))

    today = get_current_date()
    try:
        date_due = datetime.strptime(date_due_str, '%Y-%m-%d').date()
    except ValueError:
        date_due = today + timedelta(days=1)

    assignment = Assignment(subject_id=subject_id, title=title,
                            description=description,
                            assignment_type=assignment_type,
                            date_assigned=today, date_due=date_due)
    db.session.add(assignment)
    db.session.commit()

    # Собираем индексы вопросов из реальных ключей формы:
    # при удалении вопроса в конструкторе индексы идут с пропусками,
    # поэтому нельзя останавливаться на первом отсутствующем ключе.
    q_indices = sorted({
        int(key.rsplit('_', 1)[-1])
        for key in request.form
        if key.startswith('question_text_')
    })

    for q_index in q_indices:
        q_text = request.form.get(f'question_text_{q_index}', '')
        if q_text.strip():
            question = Question(
                assignment_id=assignment.id,
                text=q_text.strip(),
                question_type=request.form.get(f'question_type_{q_index}', 'text'),
                options=request.form.get(f'question_options_{q_index}', ''),
                correct_answer=request.form.get(f'question_correct_{q_index}', ''),
                order=q_index
            )
            db.session.add(question)

    db.session.commit()
    flash(f'Задание «{title}» создано! 📝', 'success')
    return redirect(url_for('teacher_assignments'))


@app.route('/teacher/assignment/<int:assignment_id>/delete', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    a = db.session.get(Assignment, assignment_id)
    if not a:
        flash('Задание не найдено', 'error')
        return redirect(url_for('teacher_assignments'))

    HomeworkCompletion.query.filter_by(assignment_id=assignment_id).delete()
    for q in a.questions:
        StudentAnswer.query.filter_by(question_id=q.id).delete()
    db.session.delete(a)
    db.session.commit()
    flash('Задание удалено 🗑️', 'info')
    return redirect(url_for('teacher_assignments'))


@app.route('/teacher/assignment/<int:assignment_id>/results')
@login_required
def assignment_results(assignment_id):
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('teacher_assignments'))

    students = User.query.filter_by(role='student').order_by(User.last_name).all()
    questions = (Question.query
                 .filter_by(assignment_id=assignment_id)
                 .order_by(Question.order).all())

    completions = {c.student_id: c
                   for c in HomeworkCompletion.query.filter_by(assignment_id=assignment_id).all()}

    answers_map = {}
    for ans in StudentAnswer.query.filter(
        StudentAnswer.question_id.in_([q.id for q in questions])
    ).all():
        answers_map[(ans.student_id, ans.question_id)] = ans

    return render_template('teacher/assignment_results.html',
                           assignment=assignment,
                           students=students,
                           questions=questions,
                           completions=completions,
                           answers_map=answers_map)


# ── Календарь контрольных ────────────────────────────────────────────────────

@app.route('/teacher/calendar')
@login_required
def teacher_calendar():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    today = get_current_date()
    year = request.args.get('year', type=int, default=today.year)
    month = request.args.get('month', type=int, default=today.month)

    # Навигация по месяцам
    if month < 1:
        month, year = 12, year - 1
    elif month > 12:
        month, year = 1, year + 1

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    subjects = Subject.query.order_by(Subject.name).all()
    controls = ControlWork.query.order_by(ControlWork.date).all()

    controls_by_date = {}
    for c in controls:
        key = c.date.isoformat()
        controls_by_date.setdefault(key, []).append(c)

    return render_template('teacher/calendar.html',
                           subjects=subjects,
                           controls=controls,
                           cal=cal_module.monthcalendar(year, month),
                           year=year, month=month,
                           month_name=MONTH_NAMES[month],
                           controls_by_date=controls_by_date,
                           prev_year=prev_year, prev_month=prev_month,
                           next_year=next_year, next_month=next_month,
                           date=date)


@app.route('/teacher/calendar/add', methods=['POST'])
@login_required
def add_control():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    subject_id = request.form.get('subject_id', type=int)
    title = request.form.get('title', '').strip()
    date_str = request.form.get('date', '')
    description = request.form.get('description', '')
    color = request.form.get('color', '#667eea')

    if not title or not subject_id or not date_str:
        flash('Заполните все поля! ❌', 'error')
        return redirect(url_for('teacher_calendar'))

    try:
        ctrl_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Неверная дата! ❌', 'error')
        return redirect(url_for('teacher_calendar'))

    ctrl = ControlWork(subject_id=subject_id, title=title,
                       date=ctrl_date, description=description, color=color)
    db.session.add(ctrl)
    db.session.commit()
    flash(f'Контрольная «{title}» запланирована! 📋', 'success')
    return redirect(url_for('teacher_calendar'))


@app.route('/teacher/calendar/delete/<int:ctrl_id>', methods=['POST'])
@login_required
def delete_control(ctrl_id):
    if current_user.role != 'teacher':
        return redirect(url_for('index'))
    ctrl = db.session.get(ControlWork, ctrl_id)
    if ctrl:
        db.session.delete(ctrl)
        db.session.commit()
        flash('Контрольная удалена 🗑️', 'info')
    return redirect(url_for('teacher_calendar'))


# ── Похвалить ────────────────────────────────────────────────────────────────

@app.route('/teacher/praise')
@login_required
def teacher_praise():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    students = User.query.filter_by(role='student').order_by(User.last_name).all()
    praises = Praise.query.order_by(Praise.date.desc()).limit(50).all()
    praise_types = [
        ('star', '⭐', 'Золотая звезда'),
        ('diploma', '📜', 'Грамота'),
        ('medal', '🏅', 'Медаль'),
        ('heart', '❤️', 'Сердечко'),
        ('crown', '👑', 'Корона'),
        ('fire', '🔥', 'Огонь'),
        ('rocket', '🚀', 'Ракета'),
        ('rainbow', '🌈', 'Радуга'),
    ]
    praise_counts = {s.id: Praise.query.filter_by(student_id=s.id).count()
                     for s in students}

    return render_template('teacher/praise.html',
                           students=students,
                           praises=praises,
                           praise_types=praise_types,
                           praise_counts=praise_counts)

@app.route('/teacher/praise/send', methods=['POST'])
@login_required
def send_praise():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    student_id = request.form.get('student_id', type=int)
    praise_type = request.form.get('praise_type', 'star')
    message = request.form.get('message', '').strip()

    if not student_id:
        flash('Выберите ученика! ❌', 'error')
        return redirect(url_for('teacher_praise'))

    student = db.session.get(User, student_id)
    if not student or student.role != 'student':
        flash('Ученик не найден 😕', 'error')
        return redirect(url_for('teacher_praise'))
    praise = Praise(student_id=student_id, praise_type=praise_type,
                    message=message, date=get_current_date())
    db.session.add(praise)
    db.session.commit()
    flash(f'Награда отправлена для {student.first_name}! 🎉', 'success')
    return redirect(url_for('teacher_praise'))


# ── Предметы ─────────────────────────────────────────────────────────────────

@app.route('/teacher/subjects', methods=['GET', 'POST'])
@login_required
def teacher_subjects():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            emoji = request.form.get('emoji', '📚').strip()
            color = request.form.get('color', '#4A90D9')
            if name:
                db.session.add(Subject(name=name, emoji=emoji, color=color))
                db.session.commit()
                flash(f'Предмет «{name}» добавлен! {emoji}', 'success')
        elif action == 'delete':
            subj_id = request.form.get('subject_id', type=int)
            subj = db.session.get(Subject, subj_id)
            if subj:
                # Каскадно чистим всё, что ссылается на предмет
                # (иначе FK-ограничение уронит запрос с 500-й ошибкой)
                assignment_ids = [a.id for a in
                                  Assignment.query.filter_by(subject_id=subj_id).all()]
                if assignment_ids:
                    question_ids = [q.id for q in Question.query.filter(
                        Question.assignment_id.in_(assignment_ids)).all()]
                    if question_ids:
                        StudentAnswer.query.filter(
                            StudentAnswer.question_id.in_(question_ids)).delete(
                            synchronize_session=False)
                    HomeworkCompletion.query.filter(
                        HomeworkCompletion.assignment_id.in_(assignment_ids)).delete(
                        synchronize_session=False)
                    Assignment.query.filter(
                        Assignment.id.in_(assignment_ids)).delete(
                        synchronize_session=False)
                Grade.query.filter_by(subject_id=subj_id).delete()
                ControlWork.query.filter_by(subject_id=subj_id).delete()
                ScheduleItem.query.filter_by(subject_id=subj_id).delete()
                db.session.delete(subj)
                db.session.commit()
                flash(f'Предмет «{subj.name}» удалён вместе с оценками и заданиями 🗑️', 'info')
        return redirect(url_for('teacher_subjects'))

    subjects = Subject.query.order_by(Subject.name).all()
    return render_template('teacher/subjects.html', subjects=subjects)


# ── Расписание — только просмотр ─────────────────────────────────────────────

@app.route('/teacher/schedule')
@login_required
def teacher_schedule():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    schedule_map = {}
    for d in range(7):
        schedule_map[d] = (ScheduleItem.query
                           .filter_by(day_of_week=d)
                           .order_by(ScheduleItem.lesson_number)
                           .all())

    today_dow = get_current_date().weekday()

    return render_template('teacher/schedule.html',
                           schedule_map=schedule_map,
                           today_dow=today_dow)


# ── Настройки (веб вместо консоли) ───────────────────────────────────────────

STUDENT_EMOJIS = [
    '😊', '😎', '🤓', '😺', '🦊', '🐻', '🌟', '🎈', '🎯', '🦄',
    '🐱', '🐶', '🐸', '🐼', '🦁', '🐯', '🦋', '🌈', '🎀', '🎸',
    '⚽', '🏀', '🎨', '🚀', '🌺', '🍀', '🦅', '🐬', '🦔', '🌻',
    '🍉', '🎃', '🐧', '🦘', '🌙', '⭐', '🔥', '💎', '🎵', '🏆',
]


@app.route('/teacher/settings')
@login_required
def teacher_settings():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    students = User.query.filter_by(role='student').order_by(User.last_name).all()
    teacher = User.query.filter_by(role='teacher').first()

    return render_template('teacher/settings.html',
                           students=students,
                           teacher=teacher,
                           student_emojis=STUDENT_EMOJIS,
                           custom_date=get_setting('current_date', ''))


@app.route('/teacher/settings/student/add', methods=['POST'])
@login_required
def add_student():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    first = request.form.get('first_name', '').strip()
    last = request.form.get('last_name', '').strip()
    emoji = request.form.get('avatar_emoji', '😊').strip() or '😊'

    if not first or not last:
        flash('Заполните имя и фамилию! ❌', 'error')
        return redirect(url_for('teacher_settings'))

    student = User(first_name=first, last_name=last,
                   role='student', avatar_emoji=emoji[:4])
    db.session.add(student)
    db.session.commit()
    flash(f'Ученик {emoji} {last} {first} добавлен! 🎉', 'success')
    return redirect(url_for('teacher_settings'))


@app.route('/teacher/settings/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    target = db.session.get(User, student_id)
    if not target:
        flash('Ученик не найден 😕', 'error')
        return redirect(url_for('teacher_settings'))
    if target.role == 'teacher':
        flash('Учителя удалить нельзя! 🚫', 'error')
        return redirect(url_for('teacher_settings'))

    # Каскадно удаляем все данные ученика
    Grade.query.filter_by(student_id=student_id).delete()
    HomeworkCompletion.query.filter_by(student_id=student_id).delete()
    Praise.query.filter_by(student_id=student_id).delete()
    StudentAnswer.query.filter_by(student_id=student_id).delete()
    db.session.delete(target)
    db.session.commit()
    flash(f'Ученик {target.get_full_name()} удалён 🗑️', 'info')
    return redirect(url_for('teacher_settings'))


@app.route('/teacher/settings/student/<int:student_id>/emoji', methods=['POST'])
@login_required
def set_student_emoji(student_id):
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    target = db.session.get(User, student_id)
    if not target or target.role == 'teacher':
        flash('Ученик не найден 😕', 'error')
        return redirect(url_for('teacher_settings'))

    emoji = request.form.get('avatar_emoji', '').strip()
    if emoji:
        target.avatar_emoji = emoji[:4]
        db.session.commit()
        flash(f'Эмодзи {target.first_name} обновлён {emoji} ✅', 'success')
    return redirect(url_for('teacher_settings'))


@app.route('/teacher/settings/teacher', methods=['POST'])
@login_required
def update_teacher():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    teacher = User.query.filter_by(role='teacher').first()
    if not teacher:
        flash('Учитель не найден 😕', 'error')
        return redirect(url_for('teacher_settings'))

    first = request.form.get('first_name', '').strip()
    last = request.form.get('last_name', '').strip()
    emoji = request.form.get('avatar_emoji', '').strip()

    if first:
        teacher.first_name = first
    if last:
        teacher.last_name = last
    if emoji:
        teacher.avatar_emoji = emoji[:4]
    db.session.commit()
    flash('Данные учителя обновлены ✅', 'success')
    return redirect(url_for('teacher_settings'))


@app.route('/teacher/settings/date', methods=['POST'])
@login_required
def set_portal_date():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    action = request.form.get('action', 'set')
    raw = request.form.get('date', '')
    custom = get_setting('current_date', '')
    base = get_current_date()

    if action == 'set':
        try:
            base = datetime.strptime(raw, '%Y-%m-%d').date()
            set_setting('current_date', base.isoformat())
            flash(f'Дата портала: {base.strftime("%d.%m.%Y")} 📅', 'success')
        except ValueError:
            flash('Неверный формат даты ❌', 'error')
        return redirect(url_for('teacher_settings'))

    if action == 'reset':
        set_setting('current_date', '')
        base = date.today()
    else:
        shifts = {'plus1': 1, 'minus1': -1, 'plus7': 7, 'minus7': -7}
        if custom:
            try:
                base = datetime.strptime(custom, '%Y-%m-%d').date()
            except ValueError:
                base = date.today()
        base = base + timedelta(days=shifts.get(action, 0))
        set_setting('current_date', base.isoformat())

    flash(f'Дата портала: {base.strftime("%d.%m.%Y")} 📅', 'success')
    return redirect(url_for('teacher_settings'))


@app.route('/teacher/settings/period', methods=['POST'])
@login_required
def set_period():
    if current_user.role != 'teacher':
        return redirect(url_for('index'))

    action = request.form.get('action', 'number')

    if action == 'toggle':
        new_type = 'trimester' if get_period_type() == 'quarter' else 'quarter'
        set_setting('period_type', new_type)
        flash(f'Переключено на: {"четверти" if new_type == "quarter" else "триместры"} ✅',
              'success')
        return redirect(url_for('teacher_settings'))

    ptype = get_period_type()
    max_p = 4 if ptype == 'quarter' else 3
    label = 'Четверть' if ptype == 'quarter' else 'Триместр'

    if action == 'next':
        new_p = get_current_period() % max_p + 1
    else:
        new_p = request.form.get('period', type=int, default=1)

    if 1 <= new_p <= max_p:
        set_setting('current_period', str(new_p))
        flash(f'Начинается {label.lower()} {new_p} ✅', 'success')
    else:
        flash(f'Номер периода должен быть от 1 до {max_p} ❌', 'error')
    return redirect(url_for('teacher_settings'))


# ── Кабинет ученика ──────────────────────────────────────────────────────────

@app.route('/student')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Этот раздел для учеников! 📚', 'error')
        return redirect(url_for('index'))

    today = get_current_date()
    day_of_week = today.weekday()

    schedule = (ScheduleItem.query
                .filter_by(day_of_week=day_of_week)
                .order_by(ScheduleItem.lesson_number).all())

    assignments = (Assignment.query
                   .filter(Assignment.date_due >= today)
                   .order_by(Assignment.date_due).all())

    completions = {c.assignment_id: c
                   for c in HomeworkCompletion.query.filter_by(student_id=current_user.id).all()}

    recent_grades = (Grade.query
                     .filter_by(student_id=current_user.id)
                     .order_by(Grade.date.desc(), Grade.id.desc())
                     .limit(10).all())

    praises = (Praise.query
               .filter_by(student_id=current_user.id)
               .order_by(Praise.date.desc())
               .limit(10).all())

    controls = (ControlWork.query
                .filter(ControlWork.date >= today)
                .order_by(ControlWork.date)
                .limit(3).all())

    period = get_current_period()
    all_grades = Grade.query.filter_by(student_id=current_user.id, period=period).all()
    my_avg = (round(sum(g.value for g in all_grades) / len(all_grades), 1)
              if all_grades else None)

    return render_template('student/dashboard.html',
                           today=today,
                           day_of_week=day_of_week,
                           schedule=schedule,
                           assignments=assignments,
                           completions=completions,
                           recent_grades=recent_grades,
                           praises=praises,
                           controls=controls,
                           my_avg=my_avg)


@app.route('/student/diary')
@login_required
def student_diary():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    today = get_current_date()
    start_of_week = today - timedelta(days=today.weekday())
    week_days = [start_of_week + timedelta(days=i) for i in range(7)]

    schedule_map = {}
    for item in ScheduleItem.query.all():
        schedule_map.setdefault(item.day_of_week, []).append(item)

    assignments = (Assignment.query
                   .filter(Assignment.date_due >= start_of_week,
                           Assignment.date_due <= start_of_week + timedelta(days=6))
                   .order_by(Assignment.date_due).all())

    completions = {c.assignment_id: c
                   for c in HomeworkCompletion.query.filter_by(student_id=current_user.id).all()}

    # Оценки за неделю — ключ (date_iso, subject_id)
    grades = (Grade.query
              .filter(Grade.student_id == current_user.id,
                      Grade.date >= start_of_week,
                      Grade.date <= start_of_week + timedelta(days=6))
              .all())

    grades_by_date_subj = {}
    for g in grades:
        key = (g.date.isoformat(), g.subject_id)
        grades_by_date_subj.setdefault(key, []).append(g)

    return render_template('student/diary.html',
                           today=today,
                           week_days=week_days,
                           schedule_map=schedule_map,
                           assignments=assignments,
                           completions=completions,
                           grades_by_date_subj=grades_by_date_subj)


@app.route('/student/complete_homework/<int:assignment_id>', methods=['POST'])
@login_required
def complete_homework(assignment_id):
    if current_user.role != 'student':
        return jsonify({'error': 'forbidden'}), 403

    comp = HomeworkCompletion.query.filter_by(
        student_id=current_user.id, assignment_id=assignment_id).first()

    if comp:
        comp.completed = not comp.completed
        comp.completed_at = datetime.now() if comp.completed else None
    else:
        comp = HomeworkCompletion(student_id=current_user.id,
                                  assignment_id=assignment_id,
                                  completed=True,
                                  completed_at=datetime.now())
        db.session.add(comp)

    db.session.commit()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'completed': comp.completed})
    return redirect(url_for('student_diary'))


@app.route('/student/test/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def student_test(assignment_id):
    if current_user.role != 'student':
        return redirect(url_for('index'))

    assignment = db.session.get(Assignment, assignment_id)
    if not assignment:
        flash('Задание не найдено', 'error')
        return redirect(url_for('student_dashboard'))

    questions = (Question.query
                 .filter_by(assignment_id=assignment_id)
                 .order_by(Question.order).all())

    existing = StudentAnswer.query.filter(
        StudentAnswer.student_id == current_user.id,
        StudentAnswer.question_id.in_([q.id for q in questions])
    ).all()
    already_submitted = len(existing) > 0

    if request.method == 'POST' and not already_submitted:
        correct = 0
        for q in questions:
            answer = request.form.get(f'answer_{q.id}', '').strip()
            is_correct = answer.lower() == q.correct_answer.lower().strip()
            if is_correct:
                correct += 1
            db.session.add(StudentAnswer(
                question_id=q.id,
                student_id=current_user.id,
                answer=answer,
                is_correct=is_correct
            ))

        comp = HomeworkCompletion.query.filter_by(
            student_id=current_user.id, assignment_id=assignment_id).first()
        if comp:
            comp.completed = True
            comp.completed_at = datetime.now()
        else:
            db.session.add(HomeworkCompletion(
                student_id=current_user.id, assignment_id=assignment_id,
                completed=True, completed_at=datetime.now()))

        db.session.commit()
        flash(f'Тест сдан! Результат: {correct}/{len(questions)} ✅', 'success')
        return redirect(url_for('student_test', assignment_id=assignment_id))

    answers_map = {a.question_id: a for a in existing}
    correct_count = sum(1 for a in existing if a.is_correct)

    return render_template('student/test.html',
                           assignment=assignment,
                           questions=questions,
                           already_submitted=already_submitted,
                           answers_map=answers_map,
                           correct_count=correct_count)


@app.route('/student/progress')
@login_required
def student_progress():
    if current_user.role != 'student':
        return redirect(url_for('index'))

    today = get_current_date()
    period = get_current_period()
    subjects = Subject.query.order_by(Subject.name).all()

    subject_data = {}
    for subj in subjects:
        grades = Grade.query.filter_by(
            student_id=current_user.id, subject_id=subj.id, period=period).all()
        if grades:
            avg = round(sum(g.value for g in grades) / len(grades), 1)
            subject_data[subj.id] = {'average': avg, 'grades': grades}

    week_data = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        grades = Grade.query.filter_by(student_id=current_user.id, date=d).all()
        avg = round(sum(g.value for g in grades) / len(grades), 1) if grades else None
        week_data.append({'date': d, 'day': get_day_name_short(d),
                          'average': avg, 'count': len(grades)})

    praises = (Praise.query
               .filter_by(student_id=current_user.id)
               .order_by(Praise.date.desc()).all())

    return render_template('student/progress.html',
                           subjects=subjects,
                           subject_data=subject_data,
                           week_data=week_data,
                           praises=praises,
                           period=period)


# ── Инициализация БД ─────────────────────────────────────────────────────────

DEFAULT_SUBJECTS = [
    ('Математика',          '🔢', '#4A90D9'),
    ('Русский язык',        '📖', '#E74C3C'),
    ('Чтение',              '📚', '#2ECC71'),
    ('Окружающий мир',      '🌍', '#F39C12'),
    ('Рисование',           '🎨', '#9B59B6'),
    ('Физкультура',         '⚽', '#1ABC9C'),
    ('Музыка',              '🎵', '#E91E63'),
    ('Технология',          '✂️', '#795548'),
    ('Английский язык',     '🇬🇧', '#3498DB'),
    ('Разговоры о важном',  '💬', '#FF7675'),
]

# Расписание: (название_предмета, день_недели 0=Пн, номер_урока)
DEFAULT_SCHEDULE = [
    # Понедельник
    ('Рисование',           0, 1),
    ('Чтение',              0, 2),
    ('Русский язык',        0, 3),
    # Вторник
    ('Окружающий мир',      1, 1),
    ('Разговоры о важном',  1, 2),
    ('Технология',          1, 3),
    ('Английский язык',     1, 4),
    # Среда
    ('Физкультура',         2, 1),
    ('Музыка',              2, 2),
    ('Математика',          2, 3),
    ('Русский язык',        2, 4),
    # Четверг
    ('Чтение',              3, 1),
    ('Русский язык',        3, 2),
    ('Окружающий мир',      3, 3),
    # Пятница
    ('Математика',          4, 1),
    ('Физкультура',         4, 2),
    ('Английский язык',     4, 3),
]


def init_db():
    with app.app_context():
        db.create_all()

        # Учитель
        if not User.query.filter_by(role='teacher').first():
            db.session.add(User(first_name='Учитель', last_name='Главный',
                                role='teacher', avatar_emoji='👩‍🏫'))
            db.session.commit()

        # Предметы
        if not Subject.query.first():
            for name, emoji, color in DEFAULT_SUBJECTS:
                db.session.add(Subject(name=name, emoji=emoji, color=color))
            db.session.commit()

        # Расписание
        if not ScheduleItem.query.first():
            for subj_name, day, lesson_num in DEFAULT_SCHEDULE:
                subj = Subject.query.filter_by(name=subj_name).first()
                if subj:
                    db.session.add(ScheduleItem(
                        subject_id=subj.id,
                        day_of_week=day,
                        lesson_number=lesson_num
                    ))
            db.session.commit()

        # Настройки
        if not get_setting('current_period'):
            set_setting('current_period', '1')
        if not get_setting('period_type'):
            set_setting('period_type', 'quarter')


init_db()


@app.errorhandler(404)
def page_not_found(e):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(host=os.environ.get('HOST', '0.0.0.0'),
            port=int(os.environ.get('PORT', '9000')),
            debug=os.environ.get('DEBUG', '1') != '0')
