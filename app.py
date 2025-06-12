from flask import Flask, Blueprint, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from flask_cors import CORS
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=10)
CORS(app)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# ---------------------
# Database Models
# ---------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')

class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=True, unique=True)  
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    transactions = db.relationship('Transaction', backref='location', lazy=True)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    note = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False)
    currency_code = db.Column(db.String(10), default='IDR')
    currency_rate = db.Column(db.Float, default=1.0)
    time_zone = db.Column(db.String(50), default='Asia/Jakarta')
    location_id = db.Column(db.String(150), db.ForeignKey('location.name'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ---------------------
# Auth Endpoints
# ---------------------

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if not data.get('name') or not data.get('email') or not data.get('password'):
        return jsonify(message='Semua field wajib diisi'), 400
    if User.query.filter_by(email=data['email']).first():
        return jsonify(message='Email sudah terdaftar'), 409

    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    user = User(name=data['name'], email=data['email'], password_hash=hashed_pw)
    db.session.add(user)
    db.session.commit()
    token = create_access_token(identity=str(user.id))
    return jsonify(message='User registered successfully', token=token), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if not data.get('email') or not data.get('password'):
        return jsonify(message='Email dan password wajib diisi'), 400
    user = User.query.filter_by(email=data['email']).first()
    if user and bcrypt.check_password_hash(user.password_hash, data['password']):
        token = create_access_token(identity=str(user.id))
        return jsonify(message='Login successful', token=token), 200
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
            'date': t.date.strftime('%Y-%m-%d'),
            'currency_code': t.currency_code,
            'currency_rate': t.currency_rate,
            'time_zone': t.time_zone,
            'location': {
                'id': t.location.id,
                'name': t.location.name,
                'latitude': t.location.latitude,
                'longitude': t.location.longitude
            } if t.location else None,
            'created_at': t.created_at.isoformat(),
            'updated_at': t.updated_at.isoformat()
        } for t in transactions
    ]
    return jsonify(transactions=result)

@app.route('/api/transactions/<int:id>', methods=['GET'])
@jwt_required()
def get_transaction_by_id(id):
    user_id = get_jwt_identity()
    # Cari transaksi berdasarkan id dan user_id untuk melindungi data user
    transaction = Transaction.query.filter_by(id=id, user_id=user_id).first()

    if not transaction:
        # Jika transaksi tidak ditemukan, kembalikan 404 Not Found
        abort(404, description=f"Transaction with id {id} not found")

    result = {
        'id': transaction.id,
        'type': transaction.type,
        'amount': transaction.amount,
        'category': transaction.category,
        'note': transaction.note,
        'date': transaction.date.strftime('%Y-%m-%d'),
        'currency_code': transaction.currency_code,
        'currency_rate': transaction.currency_rate,
        'time_zone': transaction.time_zone,
        'location_name':transaction.location_id,
        'location': {
            'id': transaction.location.id,
            'name': transaction.location.name,
            'latitude': transaction.location.latitude,
            'longitude': transaction.location.longitude
        } if transaction.location else None,
        'created_at': transaction.created_at.isoformat(),
        'updated_at': transaction.updated_at.isoformat()
    }

    return jsonify(transaction=result)

@app.route('/api/transactions', methods=['POST'])
@jwt_required()
def add_transaction():
    user_id = get_jwt_identity()
    data = request.json

    location_name = data.get('location_id')
    location = None
    if location_name:
        location = Location.query.filter_by(name=location_name).first()
        if not location:
            return jsonify(message='Invalid location name'), 400

    t = Transaction(
        user_id=user_id,
        type=data['type'],
        amount=data['amount'],
        category=data['category'],
        note=data.get('note', ''),
        date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        currency_code=data.get('currency_code', 'IDR'),
        currency_rate=data.get('currency_rate', 1.0),
        time_zone=data.get('time_zone', 'Asia/Jakarta'),
        location_id=data.get('location_id')
    )
    try:
        db.session.add(t)
        db.session.commit()
        return jsonify(message='Transaction added successfully'), 201
    except Exception as e:
        db.session.rollback()
        return jsonify(message='Failed to add transaction', error=str(e)), 500


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
    t.currency_code = data.get('currency_code', 'IDR')
    t.currency_rate = data.get('currency_rate', 1.0)
    t.time_zone = data.get('time_zone', 'Asia/Jakarta')
    t.location_id=data.get('location_id')
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

location_bp = Blueprint('location', __name__)

@location_bp.route('/api/locations', methods=['POST'])
@jwt_required()
def add_location():
    user_id = get_jwt_identity()
    data = request.get_json()

    name = data.get('name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    # Validasi input
    if not name or latitude is None or longitude is None:
        return jsonify({'error': 'Nama, latitude, dan longitude harus diisi'}), 400
    existing_location = Location.query.filter_by(name=name).first()
    if existing_location:
        return jsonify({'error': f'Lokasi dengan nama "{name}" sudah digunakan'}), 409

    try:
        new_location = Location(
            name=name,
            latitude=float(latitude),
            longitude=float(longitude)
        )
        db.session.add(new_location)
        db.session.commit()

        return jsonify({
            'message': 'Lokasi berhasil ditambahkan',
            'location': {
                'id': new_location.id,
                'name': new_location.name,
                'latitude': new_location.latitude,
                'longitude': new_location.longitude
            }
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Terjadi kesalahan: {str(e)}'}), 500


@app.route('/api/locations', methods=['GET'])
@jwt_required()
def get_all_locations():
    locations = Location.query.all()
    results = [
        {
            'id': loc.id,
            'name': loc.name,
            'latitude': loc.latitude,
            'longitude': loc.longitude,
        }
        for loc in locations
    ]
    return jsonify(locations=results), 200


@app.route('/api/locations/search', methods=['GET'])
@jwt_required()
def search_locations_by_query():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'locations': []})

    locations = Location.query.filter(Location.name.ilike(f'%{query}%')).all()
    results = [
        {
            'id': loc.id,
            'name': loc.name,
            'latitude': loc.latitude,
            'longitude': loc.longitude,
        }
        for loc in locations
    ]
    return jsonify({'locations': results})

@app.route('/api/locations/<int:id>', methods=['PUT'])
@jwt_required()
def update_location(id):
    location = Location.query.get_or_404(id)
    data = request.get_json()
    name = data.get('name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if not name or latitude is None or longitude is None:
        return jsonify({'error': 'Semua data wajib diisi'}), 400

    # Cek jika nama baru sudah dipakai oleh lokasi lain
    existing = Location.query.filter(Location.name == name, Location.id != id).first()
    if existing:
        return jsonify({'error': 'Nama lokasi sudah dipakai'}), 409

    location.name = name
    location.latitude = latitude
    location.longitude = longitude
    db.session.commit()

    return jsonify({'message': 'Lokasi berhasil diperbarui'})

@app.route('/api/locations/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_location(id):
    location = Location.query.get_or_404(id)

    # Cek apakah lokasi dipakai di transaksi
    if location.transactions and len(location.transactions) > 0:
        return jsonify({'error': 'Lokasi tidak bisa dihapus karena sedang digunakan'}), 400

    db.session.delete(location)
    db.session.commit()
    return jsonify({'message': 'Lokasi berhasil dihapus'})



app.register_blueprint(location_bp)
# ---------------------
# Init DB (Auto Create Table)
# ---------------------
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
