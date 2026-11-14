# models.py
from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    avatar_emoji = db.Column(db.String(10), default='😊')
    created_at = db.Column(db.DateTime, default=datetime.now)

    grades = db.relationship('Grade', backref='student', lazy=True,
                             foreign_keys='Grade.student_id')
    homework_completions = db.relationship('HomeworkCompletion', backref='student', lazy=True)
    praises = db.relationship('Praise', backref='student', lazy=True,
                              foreign_keys='Praise.student_id')

    def get_full_name(self):
        return f"{self.last_name} {self.first_name}"

    def __repr__(self):
        return f"<User {self.id}: {self.get_full_name()} ({self.role})>"


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    emoji = db.Column(db.String(10), default='📚')
    color = db.Column(db.String(20), default='#4A90D9')

    grades = db.relationship('Grade', backref='subject', lazy=True)
    assignments = db.relationship('Assignment', backref='subject', lazy=True)
    schedule_items = db.relationship('ScheduleItem', backref='subject', lazy=True)

    def __repr__(self):
        return f"<Subject {self.name}>"


class Grade(db.Model):
    __tablename__ = 'grades'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    value = db.Column(db.Integer, nullable=False)
    date = db.Column(db.Date, nullable=False)
    comment = db.Column(db.String(200), default='')
    period = db.Column(db.Integer, default=1)

    def __repr__(self):
        return f"<Grade {self.value} student={self.student_id}>"


class Assignment(db.Model):
    __tablename__ = 'assignments'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    assignment_type = db.Column(db.String(20), default='homework')
    date_assigned = db.Column(db.Date, nullable=False)
    date_due = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    questions = db.relationship('Question', backref='assignment', lazy=True,
                                cascade='all, delete-orphan')
    completions = db.relationship('HomeworkCompletion', backref='assignment', lazy=True)

    def __repr__(self):
        return f"<Assignment {self.title}>"


class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)
    options = db.Column(db.Text, default='')
    correct_answer = db.Column(db.String(500), default='')
    order = db.Column(db.Integer, default=0)

    answers = db.relationship('StudentAnswer', backref='question', lazy=True,
                              cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Question {self.id}>"


class StudentAnswer(db.Model):
    __tablename__ = 'student_answers'
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    answer = db.Column(db.String(500), default='')
    is_correct = db.Column(db.Boolean, default=False)
    answered_at = db.Column(db.DateTime, default=datetime.now)


class HomeworkCompletion(db.Model):
    __tablename__ = 'homework_completions'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignments.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)


class Praise(db.Model):
    __tablename__ = 'praises'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    praise_type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(300), default='')
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def get_emoji(self):
        emojis = {
            'star': '⭐', 'diploma': '📜', 'medal': '🏅',
            'heart': '❤️', 'crown': '👑', 'fire': '🔥',
            'rocket': '🚀', 'rainbow': '🌈',
        }
        return emojis.get(self.praise_type, '🌟')


class ScheduleItem(db.Model):
    __tablename__ = 'schedule_items'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)
    lesson_number = db.Column(db.Integer, nullable=False)
    time_start = db.Column(db.String(10), default='')
    time_end = db.Column(db.String(10), default='')


class ControlWork(db.Model):
    __tablename__ = 'control_works'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, default='')
    color = db.Column(db.String(20), default='#FF6B6B')

    subject_rel = db.relationship('Subject', backref='control_works')


class AppSettings(db.Model):
    __tablename__ = 'app_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), default='')


def get_setting(key, default=''):
    s = AppSettings.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key, value):
    s = AppSettings.query.filter_by(key=key).first()
    if s:
        s.value = str(value)
    else:
        s = AppSettings(key=key, value=str(value))
        db.session.add(s)
    db.session.commit()
