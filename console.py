# console.py
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

console = Console(highlight=False)

from datetime import date, datetime, timedelta

from app import app, db, init_db
from models import (
    Assignment,
    Grade,
    HomeworkCompletion,
    Praise,
    ScheduleItem,
    Subject,
    User,
    get_setting,
    set_setting,
)

# ── Эмодзи для учеников ──────────────────────────────────────────────────────
STUDENT_EMOJIS = [
    '😊','😎','🤓','😺','🦊','🐻','🌟','🎈','🎯','🦄',
    '🐱','🐶','🐸','🐼','🦁','🐯','🦋','🌈','🎀','🎸',
    '⚽','🏀','🎨','🚀','🌺','🍀','🦅','🐬','🦔','🌻',
    '🍉','🎃','🐧','🦘','🌙','⭐','🔥','💎','🎵','🏆',
]

# ── Вспомогательное ──────────────────────────────────────────────────────────

def clr():
    os.system('cls' if os.name == 'nt' else 'clear')


def sep(label=''):
    if label:
        console.print(f"\n[dim]─── {label} ───[/dim]")
    else:
        console.print("[dim]" + "─" * 44 + "[/dim]")


def ok(msg):
    console.print(f"[bold green]✓[/bold green] {msg}")


def err(msg):
    console.print(f"[bold red]✗[/bold red] {msg}")


def warn(msg):
    console.print(f"[bold yellow]![/bold yellow] {msg}")


def info(msg):
    console.print(f"[cyan]i[/cyan] {msg}")


# ── КОМАНДЫ ──────────────────────────────────────────────────────────────────

def cmd_status():
    with app.app_context():
        current_date_val = get_setting('current_date', '')
        period = get_setting('current_period', '1')
        ptype = get_setting('period_type', 'quarter')
        teacher = User.query.filter_by(role='teacher').first()
        students = User.query.filter_by(role='student').count()
        subjects = Subject.query.count()
        grades = Grade.query.count()
        assignments = Assignment.query.count()

        sep('СТАТУС')
        console.print(f"  [cyan]Дата:[/cyan]      "
                      f"{current_date_val if current_date_val else '[dim]системная (' + date.today().isoformat() + ')[/dim]'}")
        p_label = 'Четверть' if ptype == 'quarter' else 'Триместр'
        console.print(f"  [cyan]Период:[/cyan]    {p_label} {period}")
        console.print(f"  [cyan]Учитель:[/cyan]   "
                      f"{teacher.get_full_name() + ' ' + teacher.avatar_emoji if teacher else '[red]НЕТ[/red]'}")
        console.print(f"  [cyan]Учеников:[/cyan]  {students}")
        console.print(f"  [cyan]Предметов:[/cyan] {subjects}")
        console.print(f"  [cyan]Оценок:[/cyan]    {grades}")
        console.print(f"  [cyan]Заданий:[/cyan]   {assignments}")
        console.print()


def cmd_users():
    with app.app_context():
        users = User.query.order_by(User.role.desc(), User.last_name).all()
        if not users:
            warn("Нет пользователей.")
            return

        sep('ПОЛЬЗОВАТЕЛИ')
        for u in users:
            role_tag = "[bold yellow]УЧИТЕЛЬ[/bold yellow]" if u.role == 'teacher' else "[blue]ученик[/blue]"
            console.print(f"  [dim]#{u.id:3d}[/dim]  {u.avatar_emoji}  {u.last_name} {u.first_name}  {role_tag}")
        console.print()


def cmd_add():
    with app.app_context():
        sep('ДОБАВИТЬ УЧЕНИКА')
        first = Prompt.ask("  Имя").strip()
        if not first:
            err("Имя не может быть пустым!")
            return

        last = Prompt.ask("  Фамилия").strip()
        if not last:
            err("Фамилия не может быть пустой!")
            return

        # Показ эмодзи
        console.print("\n  [cyan]Выбери эмодзи:[/cyan]")
        cols = 8
        for i, e in enumerate(STUDENT_EMOJIS):
            print(f"  {i+1:2d}.{e}", end="  ")
            if (i + 1) % cols == 0:
                print()
        print()

        idx = IntPrompt.ask("  Номер (или 0 = случайный)", default=0)
        if idx == 0 or not (1 <= idx <= len(STUDENT_EMOJIS)):
            avatar = random.choice(STUDENT_EMOJIS)
        else:
            avatar = STUDENT_EMOJIS[idx - 1]

        student = User(first_name=first, last_name=last,
                       role='student', avatar_emoji=avatar)
        db.session.add(student)
        db.session.commit()
        ok(f"Ученик {avatar} {last} {first} добавлен! (ID: {student.id})")
        console.print()


def cmd_qadd():
    with app.app_context():
        sep('БЫСТРОЕ ДОБАВЛЕНИЕ')
        info("Вводите «Имя Фамилия» по одному. Пустая строка = конец.")
        console.print()
        count = 0
        while True:
            raw = Prompt.ask(f"  [{count+1}]").strip()
            if not raw:
                break
            parts = raw.split(maxsplit=1)
            if len(parts) < 2:
                warn("Введите имя и фамилию через пробел!")
                continue
            first, last = parts[0], parts[1]
            avatar = random.choice(STUDENT_EMOJIS)
            s = User(first_name=first, last_name=last,
                     role='student', avatar_emoji=avatar)
            db.session.add(s)
            count += 1
            console.print(f"    [green]+[/green] {avatar} {last} {first}")

        if count:
            db.session.commit()
            ok(f"Добавлено учеников: {count}")
        else:
            info("Никого не добавлено.")
        console.print()


def cmd_del():
    with app.app_context():
        students = User.query.filter_by(role='student').order_by(User.last_name).all()
        if not students:
            warn("Нет учеников для удаления.")
            return

        sep('УДАЛИТЬ УЧЕНИКА')
        for s in students:
            console.print(f"  [dim]#{s.id}[/dim]  {s.avatar_emoji} {s.get_full_name()}")
        console.print()

        sid = IntPrompt.ask("  ID ученика для удаления")

        # Защита: нельзя удалить учителя
        target = db.session.get(User, sid)
        if not target:
            err(f"Пользователь #{sid} не найден!")
            return
        if target.role == 'teacher':
            err("НЕЛЬЗЯ удалить учителя — он как root!")
            return

        if Confirm.ask(f"  [red]Удалить {target.get_full_name()}?[/red]"):
            Grade.query.filter_by(student_id=sid).delete()
            HomeworkCompletion.query.filter_by(student_id=sid).delete()
            Praise.query.filter_by(student_id=sid).delete()
            # Ответы на тесты
            db.session.execute(
                db.text("DELETE FROM student_answers WHERE student_id = :s"),
                {'s': sid}
            )
            db.session.delete(target)
            db.session.commit()
            ok(f"Ученик #{sid} удалён.")
        else:
            info("Отменено.")
        console.print()


def cmd_emoji():
    """Изменить эмодзи ученика."""
    with app.app_context():
        students = User.query.filter_by(role='student').order_by(User.last_name).all()
        if not students:
            warn("Нет учеников.")
            return

        sep('ИЗМЕНИТЬ ЭМОДЗИ')
        for s in students:
            console.print(f"  [dim]#{s.id}[/dim]  {s.avatar_emoji} {s.get_full_name()}")
        console.print()

        sid = IntPrompt.ask("  ID ученика")
        target = db.session.get(User, sid)
        if not target or target.role == 'teacher':
            err("Ученик не найден.")
            return

        cols = 8
        for i, e in enumerate(STUDENT_EMOJIS):
            print(f"  {i+1:2d}.{e}", end="  ")
            if (i + 1) % cols == 0:
                print()
        print()

        idx = IntPrompt.ask("  Номер эмодзи (0 = случайный)", default=0)
        if idx == 0 or not (1 <= idx <= len(STUDENT_EMOJIS)):
            emoji = random.choice(STUDENT_EMOJIS)
        else:
            emoji = STUDENT_EMOJIS[idx - 1]

        target.avatar_emoji = emoji
        db.session.commit()
        ok(f"Эмодзи {target.get_full_name()} теперь {emoji}")
        console.print()


def cmd_teacher():
    with app.app_context():
        teacher = User.query.filter_by(role='teacher').first()
        if not teacher:
            err("Учитель не найден!")
            return

        sep('РЕДАКТИРОВАТЬ УЧИТЕЛЯ')
        console.print(f"  Текущий: {teacher.avatar_emoji} {teacher.get_full_name()}")

        first = Prompt.ask("  Имя", default=teacher.first_name)
        last  = Prompt.ask("  Фамилия", default=teacher.last_name)
        emoji = Prompt.ask("  Эмодзи", default=teacher.avatar_emoji)

        teacher.first_name = first
        teacher.last_name  = last
        teacher.avatar_emoji = emoji
        db.session.commit()
        ok(f"Учитель обновлён: {emoji} {last} {first}")
        console.print()


def cmd_date():
    with app.app_context():
        current_val = get_setting('current_date', '')
        today_real = date.today()

        sep('УПРАВЛЕНИЕ ДАТОЙ')
        console.print(f"  Портальная: [bold]{current_val if current_val else 'системная (' + today_real.isoformat() + ')'}[/bold]")
        console.print(f"  Реальная:   [dim]{today_real.isoformat()}[/dim]")
        console.print()
        console.print("  [dim]1[/dim]  Установить дату (ГГГГ-ММ-ДД)")
        console.print("  [dim]2[/dim]  Сбросить на системную")
        console.print("  [dim]3[/dim]  +1 день")
        console.print("  [dim]4[/dim]  -1 день")
        console.print("  [dim]5[/dim]  +7 дней (следующая неделя)")
        console.print("  [dim]6[/dim]  -7 дней")
        console.print("  [dim]7[/dim]  Перейти на конкретный день недели")
        console.print()

        c = Prompt.ask("  Выбор", choices=[str(i) for i in range(1, 8)], default='1')

        # Вычисляем текущую «портальную» дату как базу
        if current_val:
            try:
                base = datetime.strptime(current_val, '%Y-%m-%d').date()
            except ValueError:
                base = today_real
        else:
            base = today_real

        if c == '1':
            raw = Prompt.ask("  Дата (ГГГГ-ММ-ДД)")
            try:
                d = datetime.strptime(raw, '%Y-%m-%d').date()
                set_setting('current_date', d.isoformat())
                ok(f"Дата установлена: {d.isoformat()}")
            except ValueError:
                err("Неверный формат! Нужно ГГГГ-ММ-ДД")
        elif c == '2':
            set_setting('current_date', '')
            ok("Дата сброшена на системную.")
        elif c == '3':
            new = base + timedelta(days=1)
            set_setting('current_date', new.isoformat())
            ok(f"Дата: {new.isoformat()} (+1 день, {_dow(new)})")
        elif c == '4':
            new = base - timedelta(days=1)
            set_setting('current_date', new.isoformat())
            ok(f"Дата: {new.isoformat()} (-1 день, {_dow(new)})")
        elif c == '5':
            new = base + timedelta(days=7)
            set_setting('current_date', new.isoformat())
            ok(f"Дата: {new.isoformat()} (+7 дней, {_dow(new)})")
        elif c == '6':
            new = base - timedelta(days=7)
            set_setting('current_date', new.isoformat())
            ok(f"Дата: {new.isoformat()} (-7 дней, {_dow(new)})")
        elif c == '7':
            days = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
            for i, d in enumerate(days):
                console.print(f"  {i} — {d}")
            target_dow = IntPrompt.ask("  День недели (0=Пн … 6=Вс)", default=0)
            if 0 <= target_dow <= 6:
                diff = (target_dow - base.weekday()) % 7
                new = base + timedelta(days=diff)
                set_setting('current_date', new.isoformat())
                ok(f"Дата: {new.isoformat()} ({days[target_dow]})")
            else:
                err("Неверный день!")
        console.print()


def _dow(d):
    return ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'][d.weekday()]


def cmd_period():
    with app.app_context():
        period = get_setting('current_period', '1')
        ptype  = get_setting('period_type', 'quarter')

        sep('ПЕРИОДЫ')
        p_label = 'Четверти' if ptype == 'quarter' else 'Триместры'
        console.print(f"  Тип:    {p_label}")
        console.print(f"  Номер:  {period}")
        console.print()
        console.print("  [dim]1[/dim]  Переключить Четверти / Триместры")
        console.print("  [dim]2[/dim]  Установить номер периода")
        console.print("  [dim]3[/dim]  Начать следующий период")
        console.print()

        c = Prompt.ask("  Выбор", choices=['1','2','3'], default='1')

        if c == '1':
            new = 'trimester' if ptype == 'quarter' else 'quarter'
            set_setting('period_type', new)
            ok(f"Переключено на: {'Четверти' if new == 'quarter' else 'Триместры'}")
        elif c == '2':
            max_p = 4 if ptype == 'quarter' else 3
            new_p = IntPrompt.ask(f"  Номер (1–{max_p})", default=int(period))
            if 1 <= new_p <= max_p:
                set_setting('current_period', str(new_p))
                ok(f"Период установлен: {new_p}")
            else:
                err(f"Номер должен быть от 1 до {max_p}!")
        elif c == '3':
            max_p = 4 if ptype == 'quarter' else 3
            new_p = int(period) + 1
            if new_p > max_p:
                new_p = 1
            p_label2 = 'Четверть' if ptype == 'quarter' else 'Триместр'
            if Confirm.ask(f"  Начать {p_label2} {new_p}? Оценки останутся в архиве."):
                set_setting('current_period', str(new_p))
                ok(f"Начат(а) {p_label2} {new_p}!")
            else:
                info("Отменено.")
        console.print()


def cmd_grades():
    with app.app_context():
        students = User.query.filter_by(role='student').order_by(User.last_name).all()
        subjects = Subject.query.order_by(Subject.name).all()
        period   = int(get_setting('current_period', '1'))

        if not students:
            warn("Нет учеников.")
            return

        sep(f'ОЦЕНКИ — ПЕРИОД {period}')

        for subj in subjects:
            grades = Grade.query.filter_by(subject_id=subj.id, period=period).all()
            if not grades:
                continue

            console.print(f"\n  [bold]{subj.emoji} {subj.name}[/bold]")
            for student in students:
                sg = [g for g in grades if g.student_id == student.id]
                if not sg:
                    continue
                g_parts = []
                for g in sg:
                    if g.value >= 5:
                        g_parts.append(f"[green]{g.value}[/green]")
                    elif g.value >= 4:
                        g_parts.append(f"[blue]{g.value}[/blue]")
                    elif g.value >= 3:
                        g_parts.append(f"[yellow]{g.value}[/yellow]")
                    else:
                        g_parts.append(f"[red]{g.value}[/red]")

                avg = sum(g.value for g in sg) / len(sg)
                avg_col = 'green' if avg >= 4.5 else 'blue' if avg >= 3.5 else 'yellow' if avg >= 2.5 else 'red'
                gs = " ".join(g_parts)
                console.print(f"    {student.avatar_emoji} {student.get_full_name():22s}  {gs}  "
                              f"[dim]ср:[/dim] [{avg_col}]{avg:.1f}[/{avg_col}]")
        console.print()


def cmd_schedule():
    with app.app_context():
        days = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']
        subjects = Subject.query.order_by(Subject.name).all()

        while True:
            sep('РАСПИСАНИЕ')
            console.print("  [dim]s[/dim]  Показать расписание")
            console.print("  [dim]a[/dim]  Добавить урок")
            console.print("  [dim]d[/dim]  Удалить урок")
            console.print("  [dim]r[/dim]  Сбросить на стандартное")
            console.print("  [dim]q[/dim]  Назад")
            console.print()

            c = Prompt.ask("  Выбор").strip().lower()

            if c == 'q':
                break

            elif c == 's':
                for dow in range(7):
                    items = (ScheduleItem.query
                             .filter_by(day_of_week=dow)
                             .order_by(ScheduleItem.lesson_number).all())
                    if not items:
                        continue
                    console.print(f"\n  [bold]{days[dow]}[/bold]")
                    for it in items:
                        t = f" {it.time_start}" if it.time_start else ""
                        console.print(f"    [dim]#{it.id:3d}[/dim]  {it.lesson_number}. {it.subject.emoji} {it.subject.name}{t}")
                console.print()

            elif c == 'a':
                console.print("\n  Предметы:")
                for s in subjects:
                    console.print(f"    [dim]{s.id}[/dim]  {s.emoji} {s.name}")

                sid = IntPrompt.ask("  ID предмета")
                subj = db.session.get(Subject, sid)
                if not subj:
                    err("Предмет не найден!")
                    continue

                for i, d in enumerate(days[:6]):
                    console.print(f"  {i} — {d}")
                dow = IntPrompt.ask("  День (0=Пн … 5=Пт)", default=0)
                if not (0 <= dow <= 6):
                    err("Неверный день!")
                    continue

                num = IntPrompt.ask("  Номер урока", default=1)
                t_start = Prompt.ask("  Начало (пусто = нет)", default="")
                t_end   = Prompt.ask("  Конец  (пусто = нет)", default="")

                db.session.add(ScheduleItem(
                    subject_id=sid, day_of_week=dow,
                    lesson_number=num,
                    time_start=t_start, time_end=t_end
                ))
                db.session.commit()
                ok(f"Урок добавлен: {days[dow]}, урок {num} — {subj.emoji} {subj.name}")

            elif c == 'd':
                # Показать все с ID
                items = ScheduleItem.query.order_by(
                    ScheduleItem.day_of_week, ScheduleItem.lesson_number).all()
                if not items:
                    warn("Расписание пустое.")
                    continue
                for it in items:
                    console.print(f"  [dim]#{it.id}[/dim]  {days[it.day_of_week]:12s}  "
                                  f"{it.lesson_number}. {it.subject.emoji} {it.subject.name}")
                console.print()
                item_id = IntPrompt.ask("  ID урока для удаления")
                it = db.session.get(ScheduleItem, item_id)
                if it:
                    db.session.delete(it)
                    db.session.commit()
                    ok("Урок удалён из расписания.")
                else:
                    err("Урок не найден!")

            elif c == 'r':
                if Confirm.ask("  Сбросить расписание на стандартное?"):
                    ScheduleItem.query.delete()
                    db.session.commit()

                    from app import DEFAULT_SCHEDULE
                    for subj_name, day, lesson_num in DEFAULT_SCHEDULE:
                        subj = Subject.query.filter_by(name=subj_name).first()
                        if subj:
                            db.session.add(ScheduleItem(
                                subject_id=subj.id,
                                day_of_week=day,
                                lesson_number=lesson_num
                            ))
                    db.session.commit()
                    ok("Расписание сброшено на стандартное!")
                else:
                    info("Отменено.")

def cmd_url():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"

    sep('АДРЕС ПОРТАЛА')
    console.print("  [cyan]Локально:[/cyan]  http://127.0.0.1:9000")
    console.print(f"  [cyan]В сети:[/cyan]    http://{ip}:9000")
    console.print("  [dim]Запустите сервер: python app.py[/dim]")
    console.print()


def cmd_reset():
    with app.app_context():
        sep('ПОЛНАЯ ОЧИСТКА')
        warn("Это удалит ВСЕХ учеников, оценки, задания, похвалы!")
        warn("Учитель и предметы будут пересозданы.")

        if Confirm.ask("  [red]Продолжить?[/red]"):
            if Confirm.ask("  [bold red]Подтвердите ещё раз[/bold red]"):
                db.drop_all()
                db.create_all()
                init_db()
                ok("Все данные очищены. База пересоздана.")
            else:
                info("Отменено.")
        else:
            info("Отменено.")
        console.print()


def cmd_help():
    sep('КОМАНДЫ')
    cmds = [
        ('status',   'Статус портала'),
        ('users',    'Список пользователей'),
        ('add',      'Добавить ученика'),
        ('qadd',     'Быстрое добавление нескольких'),
        ('del',      'Удалить ученика'),
        ('emoji',    'Изменить эмодзи ученика'),
        ('teacher',  'Редактировать учителя'),
        ('',         ''),
        ('date',     'Управление датой портала'),
        ('period',   'Управление четвертями/триместрами'),
        ('schedule', 'Редактировать расписание'),
        ('grades',   'Просмотр оценок'),
        ('',         ''),
        ('url',      'Показать адрес портала'),
        ('reset',    'Полная очистка данных'),
        ('clear',    'Очистить экран'),
        ('exit',     'Выход'),
    ]
    for cmd, desc in cmds:
        if not cmd:
            console.print()
        else:
            console.print(f"  [bold cyan]{cmd:<12}[/bold cyan] {desc}")
    console.print()


# ── Главный цикл ─────────────────────────────────────────────────────────────

COMMANDS = {
    'status':   cmd_status,
    'users':    cmd_users,
    'add':      cmd_add,
    'qadd':     cmd_qadd,
    'del':      cmd_del,
    'emoji':    cmd_emoji,
    'teacher':  cmd_teacher,
    'date':     cmd_date,
    'period':   cmd_period,
    'schedule': cmd_schedule,
    'grades':   cmd_grades,
    'url':      cmd_url,
    'reset':    cmd_reset,
    'help':     cmd_help,
    'clear':    lambda: (clr(), print()),
}


def main():
    with app.app_context():
        init_db()

    clr()
    console.print()
    console.print("[bold cyan]ШКОЛЬНЫЙ ПОРТАЛ[/bold cyan]  [bold yellow]// КОНСОЛЬ v2[/bold yellow]")
    sep()
    console.print("  Введите [cyan]help[/cyan] для справки по командам.")
    console.print()

    while True:
        try:
            cmd = Prompt.ask("[bold yellow]school[/bold yellow]").strip().lower()

            if not cmd:
                continue
            elif cmd in ('exit', 'quit', 'q'):
                console.print("[bold cyan]До свидания! 👋[/bold cyan]")
                break
            elif cmd in COMMANDS:
                COMMANDS[cmd]()
            else:
                err(f"Неизвестная команда: «{cmd}». Введите [cyan]help[/cyan].")

        except KeyboardInterrupt:
            console.print("\n[bold cyan]До свидания! 👋[/bold cyan]")
            break
        except EOFError:
            break
        except Exception as e:
            err(f"Ошибка: {e}")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")


if __name__ == '__main__':
    main()
