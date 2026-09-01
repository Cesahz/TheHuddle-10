from flask import Blueprint, request, jsonify, session, current_app
from ..extensions import db, bcrypt, limiter
from ..models.models import User, Role
import datetime
import jwt
from flask_wtf.csrf import generate_csrf
import re

#crear el blueprint para agrupar las rutas de autenticacion
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')  #===>  @auth_bp.route('/login') → /auth/login

#validacion de email
def is_valid_email(email: str) -> bool:
    #cualquier < > ( ) [ ] que use XSS queda bloqueado
    patron = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(patron, email))


@auth_bp.route('/register', methods=['POST'])
def register():
    #obtener los datos enviados en la peticion
    data = request.get_json()
    
    #evitar errores si no se envia json
    if not data:
        return jsonify({"error": "formato de datos invalido"}), 400
    
    #acceder a los valores
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    #validacion basica de campos vacios
    if not email or not password:
        return jsonify({"error": "email y contrasena son obligatorios"}), 400

    #validacion de email
    if not is_valid_email(email):
        return jsonify({"error": "formato de email invalido"}), 400

    #validar longitud de contrasena
    min_len = current_app.config['PASSWORD_MIN_LENGTH']
    max_len = current_app.config['PASSWORD_MAX_LENGTH']
    if len(password) < min_len:
        return jsonify({"error": f"la contrasena debe tener al menos {min_len} caracteres"}), 400
    if len(password) > max_len:
        return jsonify({"error": f"la contrasena no puede superar {max_len} caracteres"}), 400

    #verificar si el correo ya esta registrado para evitar duplicados
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "el usuario ya esta registrado"}), 409
        
    #asignar el rol basico por defecto
    user_role = Role.query.filter_by(name='usuario').first()
    
    #aplicar el hashing a la contrasena antes de guardarla
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8') #se guarda en str en vez de binario
    
    #instanciar el nuevo usuario
    new_user = User(
        email=email,
        password_hash=hashed_password,
        role_id=user_role.id
    )
    
    #ejecutar la transaccion en la base de datos
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"mensaje": "usuario creado con exito"}), 201


@auth_bp.route('/login/cookie', methods=['POST'])
@limiter.limit("5 per minute")
def login_cookie():
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "datos no proporcionados"}), 400
        
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    #buscar al usuario en la base de datos
    user = User.query.filter_by(email=email).first()
    
    #validar que el usuario exista y que la contrasena coincida con el hash
    if user and bcrypt.check_password_hash(user.password_hash, password):
        #limpiar cualquier sesion previa por seguridad
        session.clear()
        
        #inyectar los datos en la sesion de flask
        session['user_id'] = user.id            #ACA SE GUARDA LA COOKIEAEEE
        session['role']    = user.role.name     #ACA SE GUARDA LA COOKIEAEEE
        
        return jsonify({
            "mensaje": "inicio de sesion exitoso",
            "metodo": "cookie",
            "rol": user.role.name
        }), 200
        
    #respuesta generica para no dar pistas a los atacantes
    return jsonify({"error": "credenciales invalidas"}), 401
