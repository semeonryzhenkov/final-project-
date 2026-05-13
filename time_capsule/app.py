import os
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_wtf import FlaskForm
from flask_sqlalchemy import SQLAlchemy
from flask_restful import Api, Resource
from wtforms import StringField, TextAreaField, DateTimeField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length
from datetime import datetime, timedelta
import json
import requests  # Для работы с внешними API
import uuid

# Инициализация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timecapsule.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
api = Api(app)

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
    category = db.Column(db.String(30), default='personal')
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
            'category': self.category,
            'days_left': (self.open_at - datetime.utcnow()).days if not self.is_opened else 0
        }


class Tag(db.Model):
    """Модель тегов для капсул"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    capsules = db.relationship('Capsule', secondary='capsule_tags', backref='tags')


capsule_tags = db.Table('capsule_tags',
    db.Column('capsule_id', db.Integer, db.ForeignKey('capsule.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)


# ==================== ФОРМЫ (WEB 2 - flask-wtf) ====================

class CapsuleForm(FlaskForm):
    """Форма создания капсулы"""
    title = StringField('Название капсулы', validators=[DataRequired(), Length(max=100)])
    content = TextAreaField('Содержимое', validators=[DataRequired()])
    author = StringField('Ваше имя', validators=[DataRequired(), Length(max=50)])
    open_date = DateTimeField('Когда открыть (YYYY-MM-DD HH:MM)', format='%Y-%m-%d %H:%M', validators=[DataRequired()])
    category = SelectField('Категория', choices=[
        ('personal', 'Личное'),
        ('memory', 'Воспоминание'),
        ('goal', 'Цель'),
        ('message', 'Послание будущему')
    ])
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
        capsule = Capsule(
            title=form.title.data,
            content=form.content.data,
            author=form.author.data,
            open_at=form.open_date.data,
            category=form.category.data,
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
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    
    query = Capsule.query
    if category != 'all':
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Capsule.title.contains(search))
    
    capsules = query.order_by(Capsule.open_at.asc()).all()
    return render_template('all.html', capsules=capsules, current_category=category, search=search)


# ==================== REST API (WEB 5, WEB 6 - Flask-RESTful) ====================

class CapsuleAPI(Resource):
    """REST API для работы с капсулами"""
    
    def get(self, capsule_id=None):
        """Получить капсулу(ы)"""
        if capsule_id:
            capsule = Capsule.query.get(capsule_id)
            if not capsule:
                return {'error': 'Капсула не найдена'}, 404
            return capsule.to_dict(), 200
        
        capsules = Capsule.query.all()
        return {'capsules': [c.to_dict() for c in capsules]}, 200
    
    def post(self):
        """Создать капсулу через API"""
        data = request.get_json()
        if not data:
            return {'error': 'Нет данных'}, 400
        
        try:
            open_at = datetime.fromisoformat(data['open_at'])
        except:
            return {'error': 'Неверный формат даты'}, 400
        
        capsule = Capsule(
            title=data['title'],
            content=data['content'],
            author=data.get('author', 'Аноним'),
            open_at=open_at,
            category=data.get('category', 'personal')
        )
        db.session.add(capsule)
        db.session.commit()
        
        return capsule.to_dict(), 201
    
    def put(self, capsule_id):
        """Обновить капсулу"""
        capsule = Capsule.query.get(capsule_id)
        if not capsule:
            return {'error': 'Капсула не найдена'}, 404
        
        data = request.get_json()
        if 'title' in data:
            capsule.title = data['title']
        if 'content' in data:
            capsule.content = data['content']
        if 'is_opened' in data:
            capsule.is_opened = data['is_opened']
        
        db.session.commit()
        return capsule.to_dict(), 200
    
    def delete(self, capsule_id):
        """Удалить капсулу"""
        capsule = Capsule.query.get(capsule_id)
        if not capsule:
            return {'error': 'Капсула не найдена'}, 404
        
        db.session.delete(capsule)
        db.session.commit()
        return {'message': 'Капсула удалена'}, 200


class WeatherEnhancedCapsule(Resource):
    """API с обогащением данными о погоде (внешний API)"""
    
    def get(self, city='Moscow'):
        """Получить погоду и предложить идею для капсулы"""
        # Используем бесплатный API Open-Meteo (не требует ключа)
        try:
            url = f"https://api.open-meteo.com/v1/forecast?latitude=55.75&longitude=37.61&current_weather=true"
            response = requests.get(url, timeout=5)
            weather_data = response.json()
            
            current = weather_data.get('current_weather', {})
            temp = current.get('temperature', 'N/A')
            windspeed = current.get('windspeed', 'N/A')
            
            idea = self._get_capsule_idea(temp)
            
            return {
                'city': city,
                'weather': {
                    'temperature': f"{temp}°C",
                    'windspeed': f"{windspeed} km/h"
                },
                'capsule_idea': idea,
                'source': 'Open-Meteo API (бесплатный, без ключа)'
            }, 200
        except Exception as e:
            return {
                'city': city,
                'weather': 'unavailable',
                'capsule_idea': self._get_capsule_idea('N/A'),
                'error': str(e)
            }, 200
    
    def _get_capsule_idea(self, temp):
        """Генерация идеи капсулы на основе погоды"""
        if isinstance(temp, (int, float)):
            if temp < 0:
                return "Зимняя капсула: опишите свои новогодние мечты или тёплые воспоминания о лете"
            elif temp < 15:
                return "Осенняя/весенняя капсула: запишите мысли о переменах в жизни"
            else:
                return "Летняя капсула: сохраните впечатления от приключений этого сезона"
        return "Универсальная капсула: напишите послание себе через год"


class QuoteAPI(Resource):
    """API цитат для вдохновения (внешний API)"""
    
    def get(self):
        """Получить случайную цитату для мотивации"""
        # Используем бесплатный API quotable.io
        try:
            url = "https://api.quotable.io/random?tags=inspire|wisdom"
            response = requests.get(url, timeout=5)
            quote_data = response.json()
            
            return {
                'quote': quote_data.get('content', 'No quote'),
                'author': quote_data.get('author', 'Unknown'),
                'source': 'Quotable API (бесплатный)'
            }, 200
        except:
            # Запасной вариант - локальные цитаты
            quotes = [
                {"quote": "Лучшее время чтобы посадить дерево было 20 лет назад. Следующее лучшее время — сегодня.", "author": "Китайская пословица"},
                {"quote": "Будущее принадлежит тем, кто верит в красоту своей мечты.", "author": "Элеонора Рузвельт"},
                {"quote": "Через год вы будете жалеть, что не начали сегодня.", "author": "Карен Лэмб"}
            ]
            import random
            quote = random.choice(quotes)
            return {
                **quote,
                'source': 'Локальная база (API недоступен)'
            }, 200


class AliceAI(Resource):
    """Интеграция с Алисой - WebHook сервер по правилам Яндекс Диалогов"""
    
    # Хранилище сессий (в памяти, для примера)
    sessionStorage = {}

    def post(self):
        """Обработка запроса от Алисы (WebHook) по протоколу Яндекс Диалогов"""
        req = request.get_json()
        
        if not req:
            return {'error': 'Нет данных'}, 400
        
        # Логирование запроса (как в уроке)
        app.logger.info(f'Alice Request: {req!r}')
        
        user_id = req['session']['user_id']
        
        # Формируем базовый ответ согласно документации
        response = {
            'session': req['session'],
            'version': req['version'],
            'response': {
                'end_session': False
            }
        }
        
        # Обработка диалога
        self.handle_dialog(req, response)
        
        app.logger.info(f'Alice Response: {response!r}')
        
        return response, 200
    
    def handle_dialog(self, req, res):
        """Логика диалога на основе урока"""
        user_id = req['session']['user_id']
        
        # Новая сессия?
        if req['session']['new']:
            # Инициализируем сессию с подсказками
            self.sessionStorage[user_id] = {
                'suggests': [
                    "Что такое WebHook?",
                    "Как работает логирование?",
                    "Что такое именованные сущности?"
                ]
            }
            res['response']['text'] = (
                "Привет! Я Алиса из урока по промышленному программированию. "
                "Я помогу вам разобраться с темой интеграции голосового помощника. "
                "Спросите меня про WebHook, логирование или именованные сущности!"
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            return
        
        # Получаем текст пользователя
        utterance = req['request']['original_utterance'].lower()
        
        # Ответы на основе учебного материала
        if any(word in utterance for word in ['webhook', 'вебхук', 'web-hook']):
            res['response']['text'] = (
                "WebHook — это способ интеграции, при котором Алиса сама обращается к вашему API. "
                "В отличие от классического API, где вы опрашиваете сервер, здесь сервер сам сообщает о событиях. "
                "Мы реализуем свой endpoint, который Алиса вызывает при каждом обращении пользователя."
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            
        elif any(word in utterance for word in ['логирова', 'лог', 'journal']):
            res['response']['text'] = (
                "Логирование — это запись событий программы в файл или консоль. "
                "В Python используется библиотека logging. Уровни: DEBUG (отладка), INFO (информация), "
                "WARNING (предупреждение), ERROR (ошибка), CRITICAL (критическая ошибка). "
                "В production логи пишут в файл с временными метками."
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            
        elif any(word in utterance for word in ['сущност', 'entity', 'nlu']):
            res['response']['text'] = (
                "Именованные сущности — это автоматически распознанные данные: имена, города, даты, числа. "
                "Алиса разбирает запрос пользователя и помещает их в раздел nlu.entities JSON запроса. "
                "Типы: YANDEX.GEO (география), YANDEX.FIO (имена), YANDEX.NUMBER (числа), YANDEX.DATETIME (даты)."
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            
        elif any(word in utterance for word in ['flask', 'фласк']):
            res['response']['text'] = (
                "Flask — это микро-фреймворк на Python для создания веб-приложений. "
                "Мы используем его для создания WebHook endpoint'а. Декоратор @app.route('/post', methods=['POST']) "
                "обрабатывает POST запросы от Алисы с JSON данными."
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            
        elif any(word in utterance for word in ['json', 'джсон']):
            res['response']['text'] = (
                "JSON — формат обмена данными. Алиса присылает JSON с полями: request (запрос пользователя), "
                "session (данные сессии), version. Мы возвращаем JSON с response (текст, кнопки, end_session) "
                "и session (копия из запроса)."
            )
            res['response']['buttons'] = self.get_suggests(user_id)
            
        elif any(word in utterance for word in ['пока', 'до свидани', 'законч', 'хватит']):
            res['response']['text'] = "Удачи в изучении промышленного программирования! Заходите ещё!"
            res['response']['end_session'] = True
            
        else:
            # Дефолтный ответ
            res['response']['text'] = (
                f"Вы сказали: '{req['request']['original_utterance']}'. "
                "Я могу рассказать про WebHook, логирование, именованные сущности, Flask или JSON. "
                "Что вас интересует?"
            )
            res['response']['buttons'] = self.get_suggests(user_id)
    
    def get_suggests(self, user_id):
        """Возвращает подсказки (кнопки) для пользователя"""
        session = self.sessionStorage.get(user_id)
        if not session or not session.get('suggests'):
            return []
        
        # Берем первые две подсказки
        suggests = [
            {'title': suggest, 'hide': True}
            for suggest in session['suggests'][:2]
        ]
        
        # Удаляем первую подсказку для разнообразия
        session['suggests'] = session['suggests'][1:]
        self.sessionStorage[user_id] = session
        
        # Если мало подсказок, добавляем завершающую
        if len(suggests) < 2:
            suggests.append({'title': "Рассказать про всё", 'hide': True})
        
        return suggests


class StatsAPI(Resource):
    """REST API для статистики"""
    
    def get(self):
        stats = {
            'total': Capsule.query.count(),
            'opened': Capsule.query.filter_by(is_opened=True).count(),
            'pending': Capsule.query.filter_by(is_opened=False).count(),
            'by_category': {}
        }
        
        for cat in ['personal', 'memory', 'goal', 'message']:
            stats['by_category'][cat] = Capsule.query.filter_by(category=cat).count()
        
        return stats, 200


# Регистрация API ресурсов
api.add_resource(CapsuleAPI, '/api/capsules', '/api/capsules/<int:capsule_id>')
api.add_resource(StatsAPI, '/api/stats')
api.add_resource(WeatherEnhancedCapsule, '/api/weather-idea')
api.add_resource(QuoteAPI, '/api/quote')
api.add_resource(AliceAI, '/api/alice')


# ==================== КОМАНДНАЯ СТРОКА (HTTP-API задание) ====================

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
