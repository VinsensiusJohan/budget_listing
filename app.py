from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')

app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:12345678@34.121.77.122:3306/db-budget-listing'
app.config['JWT_SECRET_KEY'] = 'supersecretkey'
CORS(app, origins=["https://vinsensiusjohan.github.io"])

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ---------------------
# Database Models
# ---------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)  # income/expense
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ---------------------
# Auth Endpoints
# ---------------------

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user = User(name=data['name'], email=data['email'], password_hash=hashed_pw)
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify(message='User registered successfully', token=token), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()
    if user and bcrypt.check_password_hash(user.password_hash, data['password']):
        token = create_access_token(identity=str(user.id))
        return jsonify(message='Login successful', token=token)
    return jsonify(message='Invalid credentials'), 401

@app.route('/api/me', methods=['GET'])
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    return jsonify(id=user.id, name=user.name, email=user.email)

# ---------------------
# Transaction Endpoints
# ---------------------

@app.route('/api/transactions', methods=['GET'])
@jwt_required()
def get_transactions():
    user_id = get_jwt_identity()
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    result = [
        {
            'id': t.id,
            'type': t.type,
            'amount': t.amount,
            'category': t.category,
            'note': t.note,
            'date': t.date.strftime('%Y-%m-%d')
        } for t in transactions
    ]
    return jsonify(transactions=result)

@app.route('/api/transactions', methods=['POST'])
@jwt_required()
def add_transaction():
    user_id = get_jwt_identity()
    data = request.json
    t = Transaction(
        user_id=user_id,
        type=data['type'],
        amount=data['amount'],
        category=data['category'],
        note=data.get('note', ''),
        date=datetime.strptime(data['date'], '%Y-%m-%d').date()
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(message='Transaction added successfully'), 201

@app.route('/api/transactions/<int:id>', methods=['PUT'])
@jwt_required()
def update_transaction(id):
    user_id = get_jwt_identity()
    t = Transaction.query.filter_by(id=id, user_id=user_id).first_or_404()
    data = request.json
    t.type = data['type']
    t.amount = data['amount']
    t.category = data['category']
    t.note = data.get('note', '')
    t.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    db.session.commit()
    return jsonify(message='Transaction updated')

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_transaction(id):
    user_id = get_jwt_identity()
    t = Transaction.query.filter_by(id=id, user_id=user_id).first_or_404()
    db.session.delete(t)
    db.session.commit()
    return jsonify(message='Transaction deleted')

@app.route('/api/transactions/summary', methods=['GET'])
@jwt_required()
def summary():
    user_id = get_jwt_identity()
    month = int(request.args.get('month', datetime.today().month))
    year = int(request.args.get('year', datetime.today().year))
    transactions = Transaction.query.filter_by(user_id=user_id).filter(
        db.extract('month', Transaction.date) == month,
        db.extract('year', Transaction.date) == year
    ).all()
    income_total = sum(t.amount for t in transactions if t.type == 'income')
    expense_total = sum(t.amount for t in transactions if t.type == 'expense')
    return jsonify(
        income_total=income_total,
        expense_total=expense_total,
        balance=income_total - expense_total
    )

# ---------------------
# Init DB (Auto Create Table)
# ---------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
