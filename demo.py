# demo.py
"""
Заполняет базу ДЕМО-данными: вымышленные ученики, оценки, задания,
контрольные и награды — чтобы сразу посмотреть, как выглядит портал.

Запуск:  python demo.py
Использует ту же базу, что и приложение (или SCHOOL_PORTAL_DB).
Чтобы демо попало в отдельный файл, а не в рабочую базу:
    SCHOOL_PORTAL_DB=sqlite:///demo.db python demo.py
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta

from app import app, db, init_db
from models import (
    Assignment,
    ControlWork,
    Grade,
    HomeworkCompletion,
    Praise,
    Question,
    ScheduleItem,
    Subject,
    User,
    get_setting,
)

DEMO_STUDENTS = [
    ('Алиса',     'Колокольчикова', '🦊'),
    ('Борис',     'Медведев',       '🐻'),
    ('Вика',      'Ромашкова',      '🦄'),
    ('Гоша',      'Зайцев',         '😺'),
    ('Даша',      'Ёлкина',         '🌟'),
    ('Егор',      'Белкин',         '🐶'),
]

DEMO_ASSIGNMENTS = [
    # (предмет, тип, название, описание, дней_до_сдачи, вопросы)
    ('Математика', 'homework', 'Стр. 42, упр. 7',
     'Решить задачки на сложение в столбик', 2, []),
    ('Русский язык', 'homework', 'Упражнение 15',
     'Списать текст, подчеркнуть главные члены предложения', 3, []),
    ('Математика', 'test', 'Тест: таблица умножения на 7',
     'Проверим знание таблицы умножения', 4, [
        ('Сколько будет 7 × 8?', 'choice', '49, 54, 56, 63', '56'),
        ('Сколько будет 7 × 6?', 'choice', '36, 42, 48, 40', '42'),
        ('Сколько будет 7 × 9?', 'text', '', '63'),
    ]),
    ('Окружающий мир', 'test', 'Тест: планеты Солнечной системы',
     'Мини-викторина про космос', 5, [
        ('Какая планета ближе всего к Солнцу?', 'choice',
         'Венера, Меркурий, Марс, Земля', 'Меркурий'),
        ('Какая планета самая большая?', 'choice',
         'Сатурн, Юпитер, Нептун, Уран', 'Юпитер'),
    ]),
]

DEMO_CONTROLS = [
    ('Математика', 'Контрольная: умножение и деление', 5,
     'Таблица умножения, деление, задачи в два действия', '#E74C3C'),
    ('Русский язык', 'Диктант «Зимние узоры»', 8,
     'Повторить словарные слова', '#3498DB'),
]

DEMO_PRAISES = [
    ('star',   'Отлично решила задачу у доски! ⭐'),
    ('heart',  'Помогла соседу по парте ❤️'),
    ('crown',  'Лучшая работа в классе! 👑'),
    ('fire',   'Быстро справилась с тестом 🔥'),
    ('medal',  'Победитель в конкурсе загадок 🏅'),
    ('rocket', 'Огромный прогресс в чтении 🚀'),
]


def seed_demo():
    with app.app_context():
        init_db()

        students = User.query.filter_by(role='student').all()
        if any(s.last_name in ('Колокольчикова', 'Медведев') for s in students):
            print('ℹ️  Демо-данные уже есть в базе, ничего не делаю.')
            return

        print('🌱 Создаю демо-данные...')

        # ── Ученики ──
        students = []
        for first, last, emoji in DEMO_STUDENTS:
            s = User(first_name=first, last_name=last, role='student',
                     avatar_emoji=emoji)
            db.session.add(s)
            students.append(s)
        db.session.commit()
        print(f'  👨‍🎓 Ученики: {len(students)}')

        # ── Оценки за последние 2 недели (в основном хорошие — всё-таки игра!) ──
        today = date.today()
        subjects = Subject.query.all()
        subjects_by_name = {s.name: s for s in subjects}
        grades_added = 0
        random.seed(42)

        # В какие дни у какого предмета уроки (из стандартного расписания)
        for s in students:
            for offset in range(13, -1, -1):
                d = today - timedelta(days=offset)
                if d.weekday() >= 5:
                    continue  # выходные
                items = ScheduleItem.query.filter_by(day_of_week=d.weekday()).all()
                for item in items:
                    if random.random() < 0.75:
                        # 5-ки и 4-ки чаще, чем 2-ки
                        value = random.choices([5, 4, 3, 2], weights=[55, 30, 10, 5])[0]
                        db.session.add(Grade(
                            student_id=s.id, subject_id=item.subject_id,
                            value=value, date=d,
                            period=int(get_setting('current_period', '1'))))
                        grades_added += 1
        db.session.commit()
        print(f'  📝 Оценки: {grades_added}')

        # ── Задания и тесты ──
        for subj_name, a_type, title, descr, due_in, questions in DEMO_ASSIGNMENTS:
            subj = subjects_by_name.get(subj_name)
            if not subj:
                continue
            a = Assignment(subject_id=subj.id, title=title,
                           description=descr, assignment_type=a_type,
                           date_assigned=today - timedelta(days=1),
                           date_due=today + timedelta(days=due_in))
            db.session.add(a)
            db.session.flush()
            for i, (q_text, q_type, options, correct) in enumerate(questions):
                db.session.add(Question(assignment_id=a.id, text=q_text,
                                        question_type=q_type, options=options,
                                        correct_answer=correct, order=i))
            # Пара учеников «сдала» ДЗ
            for s in random.sample(students, k=random.randint(2, 4)):
                db.session.add(HomeworkCompletion(
                    student_id=s.id, assignment_id=a.id,
                    completed=True, completed_at=None))
        db.session.commit()
        print(f'  📚 Задания: {len(DEMO_ASSIGNMENTS)} (с тестами и вопросами)')

        # ── Контрольные ──
        for subj_name, title, due_in, descr, color in DEMO_CONTROLS:
            subj = subjects_by_name.get(subj_name)
            if not subj:
                continue
            db.session.add(ControlWork(
                subject_id=subj.id, title=title,
                date=today + timedelta(days=due_in),
                description=descr, color=color))
        db.session.commit()
        print(f'  🗓️ Контрольные: {len(DEMO_CONTROLS)}')

        # ── Награды ──
        for s, (ptype, msg) in zip(students, DEMO_PRAISES):
            db.session.add(Praise(student_id=s.id, praise_type=ptype,
                                  message=msg, date=today - timedelta(days=1)))
        db.session.commit()
        print(f'  🏆 Награды: {len(DEMO_PRAISES)}')

        print()
        print('🎉 Готово! Запускай python app.py и заходи на http://127.0.0.1:9000')
        print('   Учитель — первый в списке, ученики — за ним.')


if __name__ == '__main__':
    seed_demo()
