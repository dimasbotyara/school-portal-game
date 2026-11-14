# migrate.py
"""
Запусти один раз: python migrate.py
Безопасно добавляет новые данные не трогая существующие.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import DEFAULT_SCHEDULE, DEFAULT_SUBJECTS, app, db
from models import Grade, ScheduleItem, Subject, User, get_setting, set_setting


def migrate():
    with app.app_context():
        print("🔄 Запуск миграции...")

        # 1. Создаём таблицы которых нет (существующие НЕ трогает)
        db.create_all()
        print("  ✅ Таблицы проверены / созданы")

        # 2. Учитель — если вдруг нет
        teacher = User.query.filter_by(role='teacher').first()
        if not teacher:
            teacher = User(
                first_name='Учитель',
                last_name='Главный',
                role='teacher',
                avatar_emoji='👩‍🏫'
            )
            db.session.add(teacher)
            db.session.commit()
            print("  ✅ Учитель создан")
        else:
            print(f"  ✅ Учитель уже есть: {teacher.get_full_name()}")

        # 3. Добавляем предметы которых нет по имени
        added_subjects = 0
        for name, emoji, color in DEFAULT_SUBJECTS:
            exists = Subject.query.filter_by(name=name).first()
            if not exists:
                db.session.add(Subject(name=name, emoji=emoji, color=color))
                added_subjects += 1
                print(f"  ➕ Предмет добавлен: {emoji} {name}")
        if added_subjects:
            db.session.commit()
        else:
            print("  ✅ Все предметы уже есть")

        # 4. Расписание — добавляем только если его совсем нет
        schedule_count = ScheduleItem.query.count()
        if schedule_count == 0:
            print("  🔄 Расписание пустое, заполняю стандартным...")
            for subj_name, day, lesson_num in DEFAULT_SCHEDULE:
                subj = Subject.query.filter_by(name=subj_name).first()
                if subj:
                    db.session.add(ScheduleItem(
                        subject_id=subj.id,
                        day_of_week=day,
                        lesson_number=lesson_num
                    ))
            db.session.commit()
            print("  ✅ Расписание создано")
        else:
            print(f"  ✅ Расписание уже есть ({schedule_count} уроков)")

        # 5. Настройки по умолчанию если нет
        if not get_setting('current_period'):
            set_setting('current_period', '1')
        if not get_setting('period_type'):
            set_setting('period_type', 'quarter')
        print("  ✅ Настройки проверены")

        # 6. Статистика
        print()
        print("📊 Итог:")
        print(f"  👨‍🎓 Учеников:  {User.query.filter_by(role='student').count()}")
        print(f"  📚 Предметов: {Subject.query.count()}")
        print(f"  📅 Уроков:    {ScheduleItem.query.count()}")
        print(f"  📝 Оценок:    {Grade.query.count()}")
        print()
        print("🎉 Готово! Запускай python app.py")

if __name__ == '__main__':
    migrate()
