from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

CEFR_LEVELS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2']

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120), default='')
    cefr_level = db.Column(db.String(4), default='A1')
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attempts = db.relationship('TestAttempt', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def estimated_level(self):
        """Return estimated CEFR level based on last 5 attempts."""
        last5 = TestAttempt.query.filter_by(user_id=self.id)\
            .order_by(TestAttempt.taken_at.desc()).limit(5).all()
        if not last5:
            return self.cefr_level
        avg_pct = sum(a.percentage for a in last5) / len(last5)
        level_idx = CEFR_LEVELS.index(self.cefr_level) if self.cefr_level in CEFR_LEVELS else 0
        if avg_pct >= 85:
            level_idx = min(level_idx + 1, 5)
        elif avg_pct < 50:
            level_idx = max(level_idx - 1, 0)
        return CEFR_LEVELS[level_idx]


class ReadingTest(db.Model):
    __tablename__ = 'reading_tests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    level = db.Column(db.String(4), nullable=False)       # A1, A2, …, C2
    passage = db.Column(db.Text, nullable=False)
    time_limit = db.Column(db.Integer, default=20)         # minutes
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('ReadingQuestion', backref='test', lazy=True,
                                cascade='all, delete-orphan')


class ReadingQuestion(db.Model):
    __tablename__ = 'reading_questions'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('reading_tests.id'), nullable=False)
    q_type = db.Column(db.String(20), nullable=False)      # 'mcq', 'tf', 'gap'
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, default='')               # JSON list for MCQ
    correct_answer = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, default=0)


class ListeningTest(db.Model):
    __tablename__ = 'listening_tests'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    level = db.Column(db.String(4), nullable=False)
    audio_file = db.Column(db.String(200), nullable=False)  # relative to static/
    transcript = db.Column(db.Text, default='')
    max_plays = db.Column(db.Integer, default=2)
    time_limit = db.Column(db.Integer, default=15)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    questions = db.relationship('ListeningQuestion', backref='test', lazy=True,
                                cascade='all, delete-orphan')


class ListeningQuestion(db.Model):
    __tablename__ = 'listening_questions'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('listening_tests.id'), nullable=False)
    q_type = db.Column(db.String(20), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, default='')
    correct_answer = db.Column(db.String(500), nullable=False)
    order = db.Column(db.Integer, default=0)


class TestAttempt(db.Model):
    __tablename__ = 'test_attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    test_type = db.Column(db.String(20), nullable=False)   # 'reading' or 'listening'
    test_id = db.Column(db.Integer, nullable=False)
    level = db.Column(db.String(4), nullable=False)
    score = db.Column(db.Integer, default=0)               # correct answers
    total = db.Column(db.Integer, default=0)               # total questions
    percentage = db.Column(db.Float, default=0.0)
    time_spent = db.Column(db.Integer, default=0)          # seconds
    taken_at = db.Column(db.DateTime, default=datetime.utcnow)
