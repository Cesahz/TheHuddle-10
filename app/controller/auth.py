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
