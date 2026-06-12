# ==============================================================================
# CEFR Mock Test Platform — app.py
# PythonAnywhere WSGI: point to this file, set 'application = app'
# See deploy_notes.txt for full deployment guide.
#
# WSGI snippet for PythonAnywhere /var/www/<username>_pythonanywhere_com_wsgi.py:
#   import sys, os
#   path = '/home/<username>/Sefr'
#   if path not in sys.path: sys.path.insert(0, path)
#   from app import app as application
#
# Set SECRET_KEY via environment variable for production security.
# ==============================================================================

import os
import json
from datetime import datetime, timedelta

from flask import (Flask, render_template, redirect, url_for,
                   request, flash, jsonify, abort)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
from sqlalchemy import func

from models import db, User, ReadingTest, ReadingQuestion, \
                   ListeningTest, ListeningQuestion, TestAttempt, CEFR_LEVELS

# --- ElevenLabs Integration ---
ELEVENLABS_API_KEY = os.environ.get('ELEVENLABS_API_KEY', 'sk_02c9a29b30c100216bcd9dba85da4292adc650be3f9804e0')

def generate_tts(text, filename):
    """Generates audio using ElevenLabs and saves to static/audio/."""
    try:
        from elevenlabs import generate, save, set_api_key
        set_api_key(ELEVENLABS_API_KEY)
        audio = generate(
            text=text,
            voice="Bella", # Default voice
            model="eleven_monolingual_v1"
        )
        save_path = os.path.join(app.static_folder, filename)
        save(audio, save_path)
        return True
    except Exception as e:
        print(f"TTS Error: {e}")
        return False

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production-12345')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cefr.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = "Iltimos, tizimga kiring."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ===========================================================================
# AUTH ROUTES
# ===========================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        if User.query.filter_by(username=username).first():
            flash('Bu username band. Boshqasini tanlang.', 'danger')
            return redirect(url_for('register'))
        if User.query.filter_by(email=email).first():
            flash('Bu email allaqachon ro\'yxatdan o\'tgan.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, email=email, full_name=full_name, cefr_level='A1')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Muvaffaqiyatli ro\'yxatdan o\'tdingiz!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            flash(f'Xush kelibsiz, {user.full_name or user.username}!', 'success')
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Username yoki parol noto\'g\'ri.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Tizimdan chiqdingiz.', 'info')
    return redirect(url_for('login'))


# ===========================================================================
# DASHBOARD
# ===========================================================================

@app.route('/')
@login_required
def dashboard():
    recent_attempts = TestAttempt.query\
        .filter_by(user_id=current_user.id)\
        .order_by(TestAttempt.taken_at.desc()).limit(5).all()

    reading_count = TestAttempt.query.filter_by(
        user_id=current_user.id, test_type='reading').count()
    listening_count = TestAttempt.query.filter_by(
        user_id=current_user.id, test_type='listening').count()

    # avg score
    all_att = TestAttempt.query.filter_by(user_id=current_user.id).all()
    avg_pct = (sum(a.percentage for a in all_att) / len(all_att)) if all_att else 0

    estimated = current_user.estimated_level()

    reading_tests_by_level = {}
    for lvl in CEFR_LEVELS:
        reading_tests_by_level[lvl] = ReadingTest.query.filter_by(level=lvl).count()
    listening_tests_by_level = {}
    for lvl in CEFR_LEVELS:
        listening_tests_by_level[lvl] = ListeningTest.query.filter_by(level=lvl).count()

    return render_template('dashboard.html',
                           recent_attempts=recent_attempts,
                           reading_count=reading_count,
                           listening_count=listening_count,
                           avg_pct=round(avg_pct, 1),
                           estimated=estimated,
                           cefr_levels=CEFR_LEVELS,
                           reading_tests_by_level=reading_tests_by_level,
                           listening_tests_by_level=listening_tests_by_level)


# ===========================================================================
# READING
# ===========================================================================

@app.route('/reading')
@login_required
def reading_list():
    level = request.args.get('level', '')
    if level and level in CEFR_LEVELS:
        tests = ReadingTest.query.filter_by(level=level).all()
    else:
        tests = ReadingTest.query.all()
    return render_template('reading_list.html', tests=tests,
                           levels=CEFR_LEVELS, selected=level)


@app.route('/reading/<int:test_id>', methods=['GET', 'POST'])
@login_required
def reading_test(test_id):
    test = ReadingTest.query.get_or_404(test_id)
    questions = ReadingQuestion.query.filter_by(test_id=test_id)\
        .order_by(ReadingQuestion.order).all()
    for q in questions:
        if q.options:
            try:
                q.options_list = json.loads(q.options)
            except Exception:
                q.options_list = []
        else:
            q.options_list = []

    if request.method == 'POST':
        score = 0
        total = len(questions)
        time_spent = int(request.form.get('time_spent', 0))
        for q in questions:
            user_ans = request.form.get(f'q_{q.id}', '').strip().lower()
            correct = q.correct_answer.strip().lower()
            if q.q_type == 'mcq' or q.q_type == 'tf':
                if user_ans == correct:
                    score += 1
            elif q.q_type == 'gap':
                if user_ans == correct:
                    score += 1
        pct = round((score / total * 100) if total else 0, 1)
        attempt = TestAttempt(
            user_id=current_user.id,
            test_type='reading',
            test_id=test.id,
            level=test.level,
            score=score,
            total=total,
            percentage=pct,
            time_spent=time_spent
        )
        db.session.add(attempt)
        db.session.commit()
        return redirect(url_for('results', attempt_id=attempt.id))

    return render_template('reading.html', test=test, questions=questions)


# ===========================================================================
# LISTENING
# ===========================================================================

@app.route('/listening')
@login_required
def listening_list():
    level = request.args.get('level', '')
    if level and level in CEFR_LEVELS:
        tests = ListeningTest.query.filter_by(level=level).all()
    else:
        tests = ListeningTest.query.all()
    return render_template('listening_list.html', tests=tests,
                           levels=CEFR_LEVELS, selected=level)


@app.route('/listening/<int:test_id>', methods=['GET', 'POST'])
@login_required
def listening_test(test_id):
    test = ListeningTest.query.get_or_404(test_id)
    questions = ListeningQuestion.query.filter_by(test_id=test_id)\
        .order_by(ListeningQuestion.order).all()
    for q in questions:
        if q.options:
            try:
                q.options_list = json.loads(q.options)
            except Exception:
                q.options_list = []
        else:
            q.options_list = []

    if request.method == 'POST':
        score = 0
        total = len(questions)
        time_spent = int(request.form.get('time_spent', 0))
        for q in questions:
            user_ans = request.form.get(f'q_{q.id}', '').strip().lower()
            correct = q.correct_answer.strip().lower()
            if user_ans == correct:
                score += 1
        pct = round((score / total * 100) if total else 0, 1)
        attempt = TestAttempt(
            user_id=current_user.id,
            test_type='listening',
            test_id=test.id,
            level=test.level,
            score=score,
            total=total,
            percentage=pct,
            time_spent=time_spent
        )
        db.session.add(attempt)
        db.session.commit()
        return redirect(url_for('results', attempt_id=attempt.id))

    return render_template('listening.html', test=test, questions=questions)


# ===========================================================================
# RESULTS
# ===========================================================================

@app.route('/results/<int:attempt_id>')
@login_required
def results(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    # CEFR band based on percentage
    pct = attempt.percentage
    if pct >= 90:
        band = 'C2'
    elif pct >= 78:
        band = 'C1'
    elif pct >= 65:
        band = 'B2'
    elif pct >= 52:
        band = 'B1'
    elif pct >= 38:
        band = 'A2'
    else:
        band = 'A1'

    # Retrieve test title
    if attempt.test_type == 'reading':
        test = ReadingTest.query.get(attempt.test_id)
    else:
        test = ListeningTest.query.get(attempt.test_id)

    return render_template('results.html', attempt=attempt, band=band, test=test)


# ===========================================================================
# PROGRESS
# ===========================================================================

@app.route('/progress')
@login_required
def progress():
    attempts = TestAttempt.query\
        .filter_by(user_id=current_user.id)\
        .order_by(TestAttempt.taken_at.asc()).all()

    # Chart data — line chart: date vs percentage
    chart_labels = [a.taken_at.strftime('%d %b') for a in attempts]
    chart_data = [a.percentage for a in attempts]

    # Bar chart: reading vs listening avg
    r_atts = [a for a in attempts if a.test_type == 'reading']
    l_atts = [a for a in attempts if a.test_type == 'listening']
    r_avg = round(sum(a.percentage for a in r_atts) / len(r_atts), 1) if r_atts else 0
    l_avg = round(sum(a.percentage for a in l_atts) / len(l_atts), 1) if l_atts else 0

    # Per-level stats
    level_stats = {}
    for lvl in CEFR_LEVELS:
        lvl_atts = [a for a in attempts if a.level == lvl]
        if lvl_atts:
            level_stats[lvl] = {
                'count': len(lvl_atts),
                'avg': round(sum(a.percentage for a in lvl_atts) / len(lvl_atts), 1)
            }
        else:
            level_stats[lvl] = {'count': 0, 'avg': 0}

    estimated = current_user.estimated_level()

    return render_template('progress.html',
                           attempts=attempts,
                           chart_labels=json.dumps(chart_labels),
                           chart_data=json.dumps(chart_data),
                           r_avg=r_avg,
                           l_avg=l_avg,
                           level_stats=level_stats,
                           estimated=estimated,
                           cefr_levels=CEFR_LEVELS)


# ===========================================================================
# ADMIN
# ===========================================================================

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    reading_tests = ReadingTest.query.order_by(ReadingTest.level, ReadingTest.id).all()
    listening_tests = ListeningTest.query.order_by(ListeningTest.level, ListeningTest.id).all()
    return render_template('admin.html',
                           reading_tests=reading_tests,
                           listening_tests=listening_tests,
                           levels=CEFR_LEVELS)


@app.route('/admin/reading/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_reading():
    if request.method == 'POST':
        test = ReadingTest(
            title=request.form['title'],
            level=request.form['level'],
            passage=request.form['passage'],
            time_limit=int(request.form.get('time_limit', 20))
        )
        db.session.add(test)
        db.session.flush()
        # parse questions
        q_texts = request.form.getlist('q_text[]')
        q_types = request.form.getlist('q_type[]')
        q_options = request.form.getlist('q_options[]')
        q_answers = request.form.getlist('q_answer[]')
        for i, qt in enumerate(q_texts):
            if qt.strip():
                opts = q_options[i] if i < len(q_options) else ''
                # store options as JSON if MCQ
                if q_types[i] == 'mcq' and opts:
                    opts_list = [o.strip() for o in opts.split('|') if o.strip()]
                    opts = json.dumps(opts_list)
                q = ReadingQuestion(
                    test_id=test.id,
                    q_type=q_types[i],
                    question_text=qt,
                    options=opts,
                    correct_answer=q_answers[i] if i < len(q_answers) else '',
                    order=i
                )
                db.session.add(q)
        db.session.commit()
        flash('Reading test qo\'shildi!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('admin_add_reading.html', levels=CEFR_LEVELS)


@app.route('/admin/listening/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_add_listening():
    if request.method == 'POST':
        use_tts = request.form.get('use_tts') == 'on'
        transcript = request.form.get('transcript', '')

        audio_filename = ''
        if use_tts and transcript:
            import uuid
            audio_filename = 'audio/tts_' + str(uuid.uuid4())[:8] + '.mp3'
            if not generate_tts(transcript, audio_filename):
                flash('TTS generatsiya qilishda xatolik yuz berdi.', 'danger')
                audio_filename = '' 
        else:
            audio_file = request.files.get('audio_file')
            if audio_file and audio_file.filename:
                import werkzeug.utils
                audio_filename = 'audio/' + werkzeug.utils.secure_filename(audio_file.filename)
                save_path = os.path.join(app.static_folder, audio_filename)
                audio_file.save(save_path)

        test = ListeningTest(
            title=request.form['title'],
            level=request.form['level'],
            audio_file=audio_filename,
            transcript=transcript,
            max_plays=int(request.form.get('max_plays', 2)),
            time_limit=int(request.form.get('time_limit', 15))
        )
        db.session.add(test)
        db.session.flush()
        q_texts = request.form.getlist('q_text[]')
        q_types = request.form.getlist('q_type[]')
        q_options = request.form.getlist('q_options[]')
        q_answers = request.form.getlist('q_answer[]')
        for i, qt in enumerate(q_texts):
            if qt.strip():
                opts = q_options[i] if i < len(q_options) else ''
                if q_types[i] == 'mcq' and opts:
                    opts_list = [o.strip() for o in opts.split('|') if o.strip()]
                    opts = json.dumps(opts_list)
                q = ListeningQuestion(
                    test_id=test.id,
                    q_type=q_types[i],
                    question_text=qt,
                    options=opts,
                    correct_answer=q_answers[i] if i < len(q_answers) else '',
                    order=i
                )
                db.session.add(q)
        db.session.commit()
        flash('Listening test qo\'shildi!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('admin_add_listening.html', levels=CEFR_LEVELS)


@app.route('/admin/reading/delete/<int:test_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_reading(test_id):
    test = ReadingTest.query.get_or_404(test_id)
    db.session.delete(test)
    db.session.commit()
    flash('Test o\'chirildi.', 'info')
    return redirect(url_for('admin_panel'))


@app.route('/admin/listening/delete/<int:test_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_listening(test_id):
    test = ListeningTest.query.get_or_404(test_id)
    db.session.delete(test)
    db.session.commit()
    flash('Test o\'chirildi.', 'info')
    return redirect(url_for('admin_panel'))


# ===========================================================================
# DATABASE INIT + SEED
# ===========================================================================

def seed_data():
    """Seed demo reading and listening tests for all CEFR levels."""
    if ReadingTest.query.count() > 0:
        return  # already seeded

    # --- READING TESTS ---
    reading_seeds = [
        {
            'title': 'My Daily Routine (A1)',
            'level': 'A1',
            'passage': (
                "My name is Sara. I wake up at 7 o'clock every morning. "
                "First, I wash my face and brush my teeth. Then I eat breakfast. "
                "I usually eat bread and drink tea. After breakfast, I go to school. "
                "School starts at 8:30. I study English, Maths, and Science. "
                "At 12 o'clock, I have lunch at school. In the afternoon, I play with my friends. "
                "I come home at 4 o'clock. I do my homework and watch TV. "
                "I go to bed at 9 o'clock. I love my daily routine!"
            ),
            'time_limit': 10,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What time does Sara wake up?',
                 'options': json.dumps(['6 o\'clock', '7 o\'clock', '8 o\'clock', '9 o\'clock']),
                 'correct_answer': '7 o\'clock', 'order': 0},
                {'q_type': 'tf', 'question_text': 'Sara eats bread and tea for breakfast.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'true', 'order': 1},
                {'q_type': 'mcq', 'question_text': 'What time does school start?',
                 'options': json.dumps(['7:30', '8:00', '8:30', '9:00']),
                 'correct_answer': '8:30', 'order': 2},
                {'q_type': 'tf', 'question_text': 'Sara goes home at 5 o\'clock.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 3},
                {'q_type': 'gap', 'question_text': 'Sara goes to _____ at 8:30.',
                 'options': '', 'correct_answer': 'school', 'order': 4},
            ]
        },
        {
            'title': 'The City Library (A2)',
            'level': 'A2',
            'passage': (
                "The city library is a great place to visit. It is open from Monday to Saturday, "
                "from 9 am to 7 pm. The library has three floors. On the first floor, there are "
                "children's books and magazines. On the second floor, you can find novels, history "
                "books, and science books. The third floor has computers and study rooms. "
                "Membership is free for all residents. You can borrow up to five books at a time "
                "for three weeks. The library also organizes free events every weekend, such as "
                "book clubs, storytelling for children, and language classes. The librarians are "
                "always happy to help you find a book."
            ),
            'time_limit': 12,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'The library is open on Sundays.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 0},
                {'q_type': 'mcq', 'question_text': 'Where are computers located?',
                 'options': json.dumps(['First floor', 'Second floor', 'Third floor', 'Ground floor']),
                 'correct_answer': 'third floor', 'order': 1},
                {'q_type': 'tf', 'question_text': 'Membership at the library costs money.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 2},
                {'q_type': 'gap', 'question_text': 'You can borrow up to _____ books at a time.',
                 'options': '', 'correct_answer': 'five', 'order': 3},
                {'q_type': 'mcq', 'question_text': 'How long can you keep borrowed books?',
                 'options': json.dumps(['One week', 'Two weeks', 'Three weeks', 'One month']),
                 'correct_answer': 'three weeks', 'order': 4},
            ]
        },
        {
            'title': 'Climate Change and Young People (B1)',
            'level': 'B1',
            'passage': (
                "Climate change is one of the most important issues facing the world today. "
                "Scientists have found that the Earth's temperature has risen by about 1.1 degrees "
                "Celsius since the industrial revolution. This warming is mainly caused by the "
                "burning of fossil fuels such as coal, oil, and gas. Young people around the world "
                "are becoming more aware of environmental problems. Many students have joined "
                "movements like Fridays for Future, started by Swedish activist Greta Thunberg. "
                "These young campaigners believe that governments need to act faster to reduce "
                "carbon emissions. Simple actions like recycling, using public transport, and "
                "reducing meat consumption can also make a difference. Experts say that if we do "
                "not change our habits now, the consequences could be devastating—more floods, "
                "droughts, and extreme weather events. The good news is that renewable energy "
                "sources like solar and wind power are becoming cheaper every year, giving hope "
                "for a cleaner future."
            ),
            'time_limit': 20,
            'questions': [
                {'q_type': 'mcq',
                 'question_text': 'By how much has the Earth\'s temperature risen since the industrial revolution?',
                 'options': json.dumps(['0.5°C', '1.1°C', '2.0°C', '3.5°C']),
                 'correct_answer': '1.1°c', 'order': 0},
                {'q_type': 'tf', 'question_text': 'Greta Thunberg started the Fridays for Future movement.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'true', 'order': 1},
                {'q_type': 'mcq', 'question_text': 'Which is NOT mentioned as a simple action to help?',
                 'options': json.dumps(['Recycling', 'Planting trees', 'Using public transport', 'Reducing meat']),
                 'correct_answer': 'planting trees', 'order': 2},
                {'q_type': 'gap', 'question_text': 'Climate change is mainly caused by burning _____ fuels.',
                 'options': '', 'correct_answer': 'fossil', 'order': 3},
                {'q_type': 'mcq', 'question_text': 'What gives hope for a cleaner future according to the text?',
                 'options': json.dumps(['Nuclear power', 'Renewable energy', 'Carbon taxes', 'Electric cars']),
                 'correct_answer': 'renewable energy', 'order': 4},
                {'q_type': 'tf', 'question_text': 'Renewable energy is becoming more expensive every year.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 5},
            ]
        },
        {
            'title': 'The Psychology of Decision-Making (B2)',
            'level': 'B2',
            'passage': (
                "Every day, humans make thousands of decisions, from trivial choices like what to "
                "have for breakfast to life-changing ones like choosing a career. Psychologists "
                "have long been fascinated by how people make decisions, and their research has "
                "revealed some surprising patterns. Daniel Kahneman, a Nobel Prize-winning "
                "psychologist, distinguished between two types of thinking: System 1, which is "
                "fast, intuitive, and emotional, and System 2, which is slow, deliberate, and "
                "logical. Most of our everyday decisions are made by System 1, which relies on "
                "mental shortcuts called heuristics. While these shortcuts are often useful, they "
                "can also lead to systematic biases. For example, the 'availability heuristic' "
                "causes people to overestimate the probability of events that come easily to mind, "
                "such as plane crashes, while underestimating more common but less dramatic risks. "
                "Another well-known bias is 'loss aversion'—the tendency to prefer avoiding losses "
                "over acquiring equivalent gains. Research shows that losing £50 typically feels "
                "about twice as painful as gaining £50 feels pleasant. Understanding these "
                "cognitive biases can help us make better decisions, both personally and in fields "
                "like economics, medicine, and public policy."
            ),
            'time_limit': 22,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What did Daniel Kahneman win?',
                 'options': json.dumps(['Pulitzer Prize', 'Nobel Prize', 'Booker Prize', 'Fields Medal']),
                 'correct_answer': 'nobel prize', 'order': 0},
                {'q_type': 'mcq', 'question_text': 'Which system is described as "fast and intuitive"?',
                 'options': json.dumps(['System 1', 'System 2', 'Both systems', 'Neither']),
                 'correct_answer': 'system 1', 'order': 1},
                {'q_type': 'tf',
                 'question_text': 'The availability heuristic helps people accurately assess all risks.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 2},
                {'q_type': 'gap',
                 'question_text': 'Mental shortcuts used in decision-making are called _____.',
                 'options': '', 'correct_answer': 'heuristics', 'order': 3},
                {'q_type': 'mcq',
                 'question_text': 'According to loss aversion, how does losing £50 compare to gaining £50?',
                 'options': json.dumps(['Equally painful/pleasant', 'Twice as painful', 'Half as painful', 'Three times as painful']),
                 'correct_answer': 'twice as painful', 'order': 4},
                {'q_type': 'tf',
                 'question_text': 'System 2 thinking is fast and relies on emotions.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 5},
            ]
        },
        {
            'title': 'The Paradox of Artificial Intelligence Ethics (C1)',
            'level': 'C1',
            'passage': (
                "The rapid advancement of artificial intelligence presents society with a "
                "fundamental paradox: the very systems designed to augment human capability may "
                "simultaneously undermine the values that define our humanity. As AI permeates "
                "domains from criminal justice to healthcare, questions of accountability, "
                "transparency, and fairness have become increasingly pressing. Algorithmic systems "
                "used in predictive policing have been shown to perpetuate and amplify existing "
                "racial biases embedded in historical crime data, raising profound questions about "
                "procedural justice. Similarly, AI-driven recruitment tools have demonstrated "
                "systematic discrimination against women, since they were trained on data "
                "reflecting decades of male-dominated hiring patterns. "
                "Proponents of AI ethics frameworks argue that with rigorous regulation and "
                "diverse development teams, these biases can be mitigated. Critics, however, "
                "contend that the opacity of large neural networks—often called the 'black box' "
                "problem—makes true accountability impossible. Even when AI systems are proven "
                "harmful, attributing legal or moral responsibility remains fraught: Is it the "
                "developer, the deploying organisation, or the algorithm itself? "
                "This philosophical quandary is not merely academic. As nations race to establish "
                "AI governance frameworks, the risk of regulatory fragmentation grows, potentially "
                "creating a patchwork of incompatible standards that multinational corporations "
                "can exploit to circumvent oversight."
            ),
            'time_limit': 25,
            'questions': [
                {'q_type': 'mcq',
                 'question_text': 'What does the author mean by the "paradox" of AI?',
                 'options': json.dumps([
                     'AI is too expensive to develop',
                     'AI may undermine human values while enhancing capability',
                     'AI cannot solve complex problems',
                     'AI development is too slow']),
                 'correct_answer': 'ai may undermine human values while enhancing capability', 'order': 0},
                {'q_type': 'tf',
                 'question_text': 'AI recruitment tools have shown bias against male candidates.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 1},
                {'q_type': 'mcq',
                 'question_text': 'What is the "black box" problem?',
                 'options': json.dumps([
                     'AI systems use too much electricity',
                     'AI systems are physically stored in black boxes',
                     'Large neural networks lack transparency',
                     'AI hardware is too expensive']),
                 'correct_answer': 'large neural networks lack transparency', 'order': 2},
                {'q_type': 'gap',
                 'question_text': 'Regulatory _____ could create incompatible standards exploited by corporations.',
                 'options': '', 'correct_answer': 'fragmentation', 'order': 3},
                {'q_type': 'mcq',
                 'question_text': 'According to critics, why is true AI accountability impossible?',
                 'options': json.dumps([
                     'Governments are too slow',
                     'AI systems are too cheap',
                     'Neural networks are opaque',
                     'Developers are dishonest']),
                 'correct_answer': 'neural networks are opaque', 'order': 4},
                {'q_type': 'tf',
                 'question_text': 'The author believes diverse development teams can completely eliminate AI bias.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 5},
            ]
        },
        {
            'title': 'Postcolonial Theory and Global Knowledge Systems (C2)',
            'level': 'C2',
            'passage': (
                "Postcolonial scholarship has fundamentally challenged the epistemological "
                "foundations upon which Western academic disciplines were constructed. Thinkers "
                "such as Frantz Fanon, Edward Said, and Gayatri Chakravorty Spivak have "
                "illuminated the ways in which colonial power relations did not merely subjugate "
                "peoples physically but systematically delegitimised non-Western knowledge "
                "traditions, rendering them epistemically invisible within hegemonic academic "
                "discourse. Said's concept of 'Orientalism' demonstrated how Western scholarship "
                "constructed the 'Orient' as a homogeneous, exotic Other—a projection serving "
                "colonial administrative purposes rather than reflecting any authentic social "
                "reality. Spivak's provocative question—'Can the Subaltern Speak?'—interrogates "
                "whether marginalised voices can articulate themselves within discursive frameworks "
                "that were themselves constructed to silence them. "
                "Contemporary decolonisation movements in universities have sought to 'decolonise "
                "the curriculum' by integrating non-Western epistemologies alongside canonical "
                "Western texts. Critics of this project argue that such efforts risk "
                "essentialising cultural difference, creating new hierarchies in place of old "
                "ones, or prioritising symbolic gestures over structural transformation. "
                "Proponents counter that without epistemological plurality, academic institutions "
                "perpetuate a form of 'epistemic injustice'—a term coined by Miranda Fricker—"
                "whereby certain communities are systematically disadvantaged as knowers. "
                "The challenge, then, lies not in replacing one hegemonic canon with another, "
                "but in dismantling the very mechanisms by which epistemic hierarchies are "
                "produced and reproduced."
            ),
            'time_limit': 30,
            'questions': [
                {'q_type': 'mcq',
                 'question_text': 'What is Said\'s concept of "Orientalism" primarily about?',
                 'options': json.dumps([
                     'A geographic study of the Orient',
                     'Western scholarly construction of the East as an exotic Other',
                     'Support for Eastern cultural traditions',
                     'A form of tourism studies']),
                 'correct_answer': "western scholarly construction of the east as an exotic other", 'order': 0},
                {'q_type': 'tf',
                 'question_text': 'Spivak argues that marginalised voices can easily articulate themselves within existing discourses.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 1},
                {'q_type': 'gap',
                 'question_text': 'The term "epistemic injustice" was coined by Miranda _____.',
                 'options': '', 'correct_answer': 'fricker', 'order': 2},
                {'q_type': 'mcq',
                 'question_text': 'What do critics of decolonisation efforts argue?',
                 'options': json.dumps([
                     'It goes too far in structural change',
                     'It may essentialize cultural difference',
                     'It is too expensive to implement',
                     'It ignores Western philosophy']),
                 'correct_answer': 'it may essentialize cultural difference', 'order': 3},
                {'q_type': 'mcq',
                 'question_text': 'What does the passage suggest is the ultimate challenge of decolonisation?',
                 'options': json.dumps([
                     'Replacing Western canon with Eastern canon',
                     'Dismantling mechanisms that produce epistemic hierarchies',
                     'Increasing university funding',
                     'Publishing more postcolonial texts']),
                 'correct_answer': 'dismantling mechanisms that produce epistemic hierarchies', 'order': 4},
                {'q_type': 'tf',
                 'question_text': 'Postcolonial scholarship only challenged physical forms of colonial subjugation.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 5},
            ]
        },
    ]

    for seed in reading_seeds:
        rt = ReadingTest(
            title=seed['title'],
            level=seed['level'],
            passage=seed['passage'],
            time_limit=seed['time_limit']
        )
        db.session.add(rt)
        db.session.flush()
        for qdata in seed['questions']:
            q = ReadingQuestion(test_id=rt.id, **qdata)
            db.session.add(q)

    # --- LISTENING TESTS (placeholder audio) ---
    listening_seeds = [
        {
            'title': 'At the Café (A1)',
            'level': 'A1',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "Customer: Hello! Can I have a coffee, please?\n"
                "Waiter: Of course! Big or small?\n"
                "Customer: Small, please. And a piece of chocolate cake.\n"
                "Waiter: Sure! That's £3.50 please.\n"
                "Customer: Here you are. Thank you!\n"
                "Waiter: Enjoy your coffee!"
            ),
            'max_plays': 2, 'time_limit': 10,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What does the customer order?',
                 'options': json.dumps(['Big coffee and cake', 'Small coffee and cake', 'Tea and cake', 'Just coffee']),
                 'correct_answer': 'small coffee and cake', 'order': 0},
                {'q_type': 'mcq', 'question_text': 'How much does the customer pay?',
                 'options': json.dumps(['£2.50', '£3.00', '£3.50', '£4.00']),
                 'correct_answer': '£3.50', 'order': 1},
                {'q_type': 'tf', 'question_text': 'The customer orders a large coffee.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 2},
            ]
        },
        {
            'title': 'A Weather Forecast (A2)',
            'level': 'A2',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "Good morning! Here is your weather forecast for today. "
                "In the north, it will be cold and cloudy with some rain in the afternoon. "
                "Temperatures will be around 8 degrees. In the south, the sun will shine in the "
                "morning, but clouds will arrive by midday. Temperatures will reach 15 degrees. "
                "Tomorrow, the whole country will have strong winds and heavy rain. "
                "Don't forget your umbrella!"
            ),
            'max_plays': 2, 'time_limit': 12,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What will the weather be like in the north afternoon?',
                 'options': json.dumps(['Sunny', 'Rainy', 'Snowy', 'Windy']),
                 'correct_answer': 'rainy', 'order': 0},
                {'q_type': 'gap', 'question_text': 'Southern temperatures will reach _____ degrees.',
                 'options': '', 'correct_answer': '15', 'order': 1},
                {'q_type': 'tf', 'question_text': 'Tomorrow will be sunny across the country.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 2},
            ]
        },
        {
            'title': 'A University Lecture on Urbanisation (B1)',
            'level': 'B1',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "Today we're going to talk about urbanisation—the process of people moving "
                "from rural areas to cities. Currently, more than half the world's population "
                "lives in urban areas, and this number is expected to reach 68% by 2050. "
                "Cities offer better job opportunities, healthcare, and education. However, "
                "rapid urbanisation also creates serious problems: housing shortages, traffic "
                "congestion, pollution, and increased inequality. Developing countries face the "
                "greatest challenges, as their cities often lack the infrastructure to support "
                "rapid population growth. Sustainable urban planning is therefore essential to "
                "ensure that cities can grow while maintaining quality of life for all residents."
            ),
            'max_plays': 2, 'time_limit': 18,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What percentage of people will live in cities by 2050?',
                 'options': json.dumps(['50%', '58%', '68%', '75%']),
                 'correct_answer': '68%', 'order': 0},
                {'q_type': 'tf', 'question_text': 'Rapid urbanisation only creates benefits, no problems.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 1},
                {'q_type': 'gap', 'question_text': 'Urbanisation is the process of people moving from _____ areas to cities.',
                 'options': '', 'correct_answer': 'rural', 'order': 2},
                {'q_type': 'mcq', 'question_text': 'Which countries face the greatest urbanisation challenges?',
                 'options': json.dumps(['Developed countries', 'Developing countries', 'Island nations', 'Cold climates']),
                 'correct_answer': 'developing countries', 'order': 3},
            ]
        },
        {
            'title': 'Interview: The Gig Economy (B2)',
            'level': 'B2',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "Host: Today we're discussing the gig economy with Dr. Chen, an economist at "
                "City University. Dr. Chen, what exactly is the gig economy?\n"
                "Dr. Chen: The gig economy refers to a labour market characterised by short-term, "
                "flexible, and freelance work rather than permanent jobs. Think of Uber drivers, "
                "Deliveroo couriers, or freelance designers working through platforms like Upwork.\n"
                "Host: What are the main advantages?\n"
                "Dr. Chen: Flexibility is the biggest draw. Workers can choose their hours and "
                "location. For businesses, it reduces overhead costs significantly. Consumers "
                "benefit from faster, cheaper services.\n"
                "Host: And the downsides?\n"
                "Dr. Chen: The lack of worker protections is the major concern. Gig workers often "
                "have no sick pay, no pension contributions, no job security. They bear all the "
                "financial risk while platforms take a substantial cut of earnings."
            ),
            'max_plays': 2, 'time_limit': 20,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'Where does Dr. Chen work?',
                 'options': json.dumps(['Oxford University', 'City University', 'London School of Economics', 'Cambridge']),
                 'correct_answer': 'city university', 'order': 0},
                {'q_type': 'tf', 'question_text': 'Gig workers typically have good job security.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 1},
                {'q_type': 'mcq', 'question_text': 'What does Dr. Chen say is the biggest advantage of gig work?',
                 'options': json.dumps(['High pay', 'Flexibility', 'Job security', 'Pension benefits']),
                 'correct_answer': 'flexibility', 'order': 2},
                {'q_type': 'gap', 'question_text': 'The gig economy is characterised by _____ and flexible work.',
                 'options': '', 'correct_answer': 'short-term', 'order': 3},
            ]
        },
        {
            'title': 'Lecture: Consciousness and Neuroscience (C1)',
            'level': 'C1',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "The so-called 'hard problem' of consciousness—a term coined by philosopher "
                "David Chalmers—asks why physical brain processes give rise to subjective "
                "experience at all. Why does stimulation of specific neurons produce the "
                "sensation of seeing red, rather than simply processing wavelength data without "
                "any accompanying experience? This qualia problem remains one of the deepest "
                "unsolved mysteries in both philosophy and neuroscience. "
                "Some neuroscientists, like Francis Crick and Christof Koch, have pursued the "
                "concept of 'neural correlates of consciousness'—seeking specific brain patterns "
                "associated with conscious experience. Others, like Daniel Dennett, dismiss the "
                "hard problem entirely, arguing that consciousness is simply what complex "
                "information processing looks like from the inside—an illusion generated by our "
                "own cognitive machinery."
            ),
            'max_plays': 2, 'time_limit': 25,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'Who coined the term "hard problem" of consciousness?',
                 'options': json.dumps(['Francis Crick', 'Daniel Dennett', 'David Chalmers', 'Christof Koch']),
                 'correct_answer': 'david chalmers', 'order': 0},
                {'q_type': 'tf',
                 'question_text': 'Daniel Dennett takes the hard problem of consciousness very seriously.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'false', 'order': 1},
                {'q_type': 'gap',
                 'question_text': 'Crick and Koch pursued _____ correlates of consciousness.',
                 'options': '', 'correct_answer': 'neural', 'order': 2},
                {'q_type': 'mcq',
                 'question_text': 'According to Dennett, consciousness is:',
                 'options': json.dumps([
                     'A spiritual phenomenon', 'An unsolvable mystery',
                     'An illusion from cognitive machinery', 'A quantum effect']),
                 'correct_answer': 'an illusion from cognitive machinery', 'order': 3},
            ]
        },
        {
            'title': 'Seminar: Post-Truth and Epistemic Crisis (C2)',
            'level': 'C2',
            'audio_file': 'audio/placeholder.mp3',
            'transcript': (
                "The ascendancy of what commentators have termed 'post-truth' politics represents "
                "not merely a pathological aberration but a structural feature of contemporary "
                "information ecosystems. The epistemological crisis we face is not simply about "
                "misinformation; it is about the erosion of shared epistemic norms—the agreed-upon "
                "standards by which claims are evaluated as true or false. Hannah Arendt, writing "
                "in the 1960s about totalitarian propaganda, observed that the goal was not to "
                "establish a credible lie but to destroy the very categories of truth and falsehood, "
                "leaving citizens unable to distinguish between fact and fiction. Digital media "
                "platforms, optimised for engagement rather than veracity, have industrialised this "
                "epistemological corrosion. Algorithmic amplification favours emotionally resonant "
                "content regardless of its factual accuracy, creating what researchers call 'filter "
                "bubbles'—information ecosystems in which users are systematically insulated from "
                "disconfirming evidence."
            ),
            'max_plays': 2, 'time_limit': 30,
            'questions': [
                {'q_type': 'mcq', 'question_text': 'What does the speaker say is the real epistemological crisis?',
                 'options': json.dumps([
                     'Lack of internet access', 'Erosion of shared epistemic norms',
                     'Too much information', 'Government censorship']),
                 'correct_answer': 'erosion of shared epistemic norms', 'order': 0},
                {'q_type': 'tf',
                 'question_text': 'Hannah Arendt wrote about totalitarian propaganda in the 1960s.',
                 'options': json.dumps(['True', 'False']),
                 'correct_answer': 'true', 'order': 1},
                {'q_type': 'gap',
                 'question_text': 'Algorithmic amplification favours emotionally _____ content.',
                 'options': '', 'correct_answer': 'resonant', 'order': 2},
                {'q_type': 'mcq', 'question_text': 'What are "filter bubbles"?',
                 'options': json.dumps([
                     'Spam email filters', 'Ecosystems insulating users from disconfirming evidence',
                     'Social media privacy settings', 'News aggregator tools']),
                 'correct_answer': 'ecosystems insulating users from disconfirming evidence', 'order': 3},
            ]
        },
    ]

    for seed in listening_seeds:
        lt = ListeningTest(
            title=seed['title'],
            level=seed['level'],
            audio_file=seed['audio_file'],
            transcript=seed['transcript'],
            max_plays=seed['max_plays'],
            time_limit=seed['time_limit']
        )
        db.session.add(lt)
        db.session.flush()
        for qdata in seed['questions']:
            q = ListeningQuestion(test_id=lt.id, **qdata)
            db.session.add(q)

    # admin user
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@cefr.uz',
                     full_name='Administrator', cefr_level='C2', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)

    db.session.commit()
    print("✅ Demo data seeded.")


# ===========================================================================
# CONTEXT PROCESSORS
# ===========================================================================

@app.context_processor
def inject_globals():
    return {'cefr_levels': CEFR_LEVELS, 'now': datetime.utcnow()}


# ===========================================================================
# ENTRY POINT
# ===========================================================================

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == '__main__':
    # For local development only.
    # On PythonAnywhere: do NOT use app.run() — the WSGI file handles serving.
    # Set host='0.0.0.0' and port=5000 only for local LAN testing.
    app.run(debug=True, host='127.0.0.1', port=5000)
