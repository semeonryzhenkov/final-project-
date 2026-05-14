import os
import uuid
from flask import Flask, render_template, redirect, url_for, flash, request, send_file
from flask_wtf import FlaskForm
from flask_sqlalchemy import SQLAlchemy
from wtforms import StringField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length
from datetime import datetime, timedelta
import json

# Инициализация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timecapsule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимум 16MB

# Создаём папку для загрузок если не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# ==================== МОДЕЛИ БАЗЫ ДАННЫХ (WEB 3, WEB 4) ====================

class Capsule(db.Model):
    """Модель капсулы времени"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    open_at = db.Column(db.DateTime, nullable=False)
    is_opened = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(100))
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'author': self.author,
            'created_at': self.created_at.isoformat(),
            'open_at': self.open_at.isoformat(),
            'is_opened': self.is_opened,
            'days_left': (self.open_at - datetime.utcnow()).days if not self.is_opened else 0
        }


class CapsuleFile(db.Model):
    """Модель файлов в капсуле"""
    id = db.Column(db.Integer, primary_key=True)
    capsule_id = db.Column(db.Integer, db.ForeignKey('capsule.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    capsule = db.relationship('Capsule', backref=db.backref('files', lazy=True))


# ==================== ФОРМЫ (WEB 2 - flask-wtf) ====================

class CapsuleForm(FlaskForm):
    """Форма создания капсулы"""
    title = StringField('Название капсулы', validators=[DataRequired(), Length(max=100)])
    content = TextAreaField('Содержимое', validators=[DataRequired()])
    author = StringField('Ваше имя', validators=[DataRequired(), Length(max=50)])
    open_period = SelectField('Когда открыть', choices=[
        ('1', 'Через 1 минуту'),
        ('day', 'Через 1 день'),
        ('month', 'Через 1 месяц'),
        ('year', 'Через 1 год'),
        ('2years', 'Через 2 года'),
        ('5years', 'Через 5 лет'),
        ('10years', 'Через 10 лет'),
        ('50years', 'Через 50 лет'),
        ('100years', 'Через 100 лет')
    ], validators=[DataRequired()])
    email = StringField('Email для уведомления (опционально)')
    submit = SubmitField('Создать капсулу')


class OpenForm(FlaskForm):
    """Форма открытия капсулы"""
    capsule_id = StringField('ID капсулы', validators=[DataRequired()])
    submit = SubmitField('Открыть')


# ==================== ШАБЛОНЫ (WEB 2) ====================

@app.route('/')
def index():
    """Главная страница (WEB 1, WEB 2)"""
    form = CapsuleForm()
    capsules = Capsule.query.order_by(Capsule.created_at.desc()).limit(10).all()
    stats = {
        'total': Capsule.query.count(),
        'opened': Capsule.query.filter_by(is_opened=True).count(),
        'pending': Capsule.query.filter_by(is_opened=False).count()
    }
    return render_template('index.html', form=form, capsules=capsules, stats=stats)


@app.route('/create', methods=['GET', 'POST'])
def create_capsule():
    """Создание капсулы (WEB 1 - обработка форм)"""
    form = CapsuleForm()
    if form.validate_on_submit():
        # Вычисляем дату открытия на основе выбранного периода
        now = datetime.utcnow()
        period = form.open_period.data
        
        if period == '1':
            open_at = now + timedelta(minutes=1)
        elif period == 'day':
            open_at = now + timedelta(days=1)
        elif period == 'month':
            open_at = now + timedelta(days=30)
        elif period == 'year':
            open_at = now.replace(year=now.year + 1)
        elif period == '2years':
            open_at = now.replace(year=now.year + 2)
        elif period == '5years':
            open_at = now.replace(year=now.year + 5)
        elif period == '10years':
            open_at = now.replace(year=now.year + 10)
        elif period == '50years':
            open_at = now.replace(year=now.year + 50)
        elif period == '100years':
            open_at = now.replace(year=now.year + 100)
        else:
            open_at = now + timedelta(days=365)  # По умолчанию 1 год
        
        capsule = Capsule(
            title=form.title.data,
            content=form.content.data,
            author=form.author.data,
            open_at=open_at,
            email=form.email.data
        )
        db.session.add(capsule)
        db.session.commit()
        flash(f'Капсула "{capsule.title}" создана! ID: {capsule.id}', 'success')
        return redirect(url_for('view_capsule', capsule_id=capsule.id))
    return render_template('create.html', form=form)


@app.route('/capsule/<int:capsule_id>')
def view_capsule(capsule_id):
    """Просмотр капсулы"""
    capsule = Capsule.query.get_or_404(capsule_id)
    can_open = datetime.utcnow() >= capsule.open_at
    return render_template('view.html', capsule=capsule, can_open=can_open, now=datetime.utcnow)


@app.route('/open/<int:capsule_id>', methods=['GET', 'POST'])
def open_capsule(capsule_id):
    """Открытие капсулы (WEB 1 - обработка форм)"""
    capsule = Capsule.query.get_or_404(capsule_id)
    form = OpenForm()
    
    if datetime.utcnow() < capsule.open_at and not form.validate_on_submit():
        flash('Ещё рано открывать эту капсулу!', 'warning')
        return redirect(url_for('view_capsule', capsule_id=capsule_id))
    
    if form.validate_on_submit():
        capsule.is_opened = True
        db.session.commit()
        flash('Капсула открыта!', 'success')
        return redirect(url_for('view_capsule', capsule_id=capsule_id))
    
    return render_template('open.html', capsule=capsule, form=form)


@app.route('/all')
def all_capsules():
    """Все капсулы с фильтрацией"""
    search = request.args.get('search', '')
    
    query = Capsule.query
    if search:
        query = query.filter(Capsule.title.contains(search) | Capsule.author.contains(search))
    
    capsules = query.order_by(Capsule.open_at.asc()).all()
    now = datetime.utcnow()
    return render_template('all.html', capsules=capsules, search=search, now=now)


@app.route('/today')
def today_capsules():
    """Капсулы, открывшиеся сегодня"""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    
    capsules = Capsule.query.filter(
        Capsule.open_at >= today_start,
        Capsule.open_at < today_end
    ).all()
    
    return render_template('today.html', capsules=capsules, today=today_start)


@app.route('/upload/<int:capsule_id>', methods=['POST'])
def upload_files(capsule_id):
    """Загрузка файлов в капсулу"""
    capsule = Capsule.query.get_or_404(capsule_id)
    
    if 'files' in request.files:
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                # Генерируем уникальное имя файла
                ext = os.path.splitext(file.filename)[1]
                unique_filename = f"{uuid.uuid4().hex}{ext}"
                
                # Сохраняем файл
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(file_path)
                
                # Сохраняем информацию о файле в БД
                capsule_file = CapsuleFile(
                    capsule_id=capsule.id,
                    filename=unique_filename,
                    original_filename=file.filename
                )
                db.session.add(capsule_file)
        
        db.session.commit()
        flash('Файлы успешно загружены!', 'success')
    
    return redirect(url_for('view_capsule', capsule_id=capsule_id))


@app.route('/download/<int:file_id>')
def download_file(file_id):
    """Скачивание файла"""
    capsule_file = CapsuleFile.query.get_or_404(file_id)
    capsule = Capsule.query.get(capsule_file.capsule_id)
    
    # Проверяем, можно ли открыть капсулу
    if datetime.utcnow() < capsule.open_at and not capsule.is_opened:
        flash('Файлы недоступны до открытия капсулы!', 'warning')
        return redirect(url_for('view_capsule', capsule_id=capsule.id))
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], capsule_file.filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True, download_name=capsule_file.original_filename)
    else:
        flash('Файл не найден!', 'error')
        return redirect(url_for('view_capsule', capsule_id=capsule.id))


# ==================== КОМАНДНАЯ СТРОКА ====================

@app.cli.command('init-db')
def init_db():
    """Инициализация базы данных"""
    db.create_all()
    print('База данных инициализирована!')


@app.cli.command('check-capsules')
def check_capsules():
    """Проверка капсул, готовых к открытию"""
    now = datetime.utcnow()
    ready = Capsule.query.filter(
        Capsule.open_at <= now,
        Capsule.is_opened == False
    ).all()

    print(f'Капсул готово к открытию: {len(ready)}')
    for c in ready:
        print(f'  - {c.title} (ID: {c.id})')


# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
