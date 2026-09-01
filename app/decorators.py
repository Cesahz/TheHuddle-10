from functools import wraps
from flask import request, jsonify, session, current_app
import jwt

def get_user_identity():
    #intentar obtener la identidad mediante token jwt en el header (bearer token)
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
            return {"user_id": payload['user_id'], "role": payload['role']}
        except jwt.ExpiredSignatureError:
            return {"error": "el token ha expirado"}
        except jwt.InvalidTokenError:
            return {"error": "token invalido o modificado"}
            
    #si no hay token valido, intentar obtener la identidad mediante la cookie de sesion
    if 'user_id' in session:
        return {"user_id": session.get('user_id'), "role": session.get('role')}
        
    return None


def login_required(f):
    #decorador para rutas que exigen que el usuario este logueado
    @wraps(f)
    def decorated_function(*args, **kwargs):
        identity = get_user_identity()
        
        if not identity:
            return jsonify({"error": "autenticacion requerida. inicie sesion o provea un token"}), 401
            
        if "error" in identity:
            return jsonify({"error": identity["error"]}), 401
            
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    #decorador para rutas exclusivas del rol administrador
    @wraps(f)
    def decorated_function(*args, **kwargs):
        identity = get_user_identity()
        
        if not identity or "error" in identity:
            return jsonify({"error": "autenticacion requerida"}), 401
            
        if identity.get("role") != "administrador":
            return jsonify({"error": "acceso denegado. requiere rol de administrador"}), 403
            
        return f(*args, **kwargs)
    return decorated_function