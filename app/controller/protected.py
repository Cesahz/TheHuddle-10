from flask import Blueprint, jsonify
from ..decorators import login_required, admin_required, get_user_identity
from ..models.models import User

#blueprint para agrupar todas las rutas que requieren autorizacion
protected_bp = Blueprint('protected', __name__, url_prefix='/api')

@protected_bp.route('/perfil', methods=['GET'])
@login_required
def perfil():
    identity = get_user_identity()
    return jsonify({
        "mensaje": "acceso concedido",
        "usuario": identity['user_id'],
        "rol": identity['role'],
        "datos": "aqui estaran tus pasaportes e identificaciones digitales"
    }), 200

@protected_bp.route('/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    identity = get_user_identity()
    total_usuarios = User.query.count()
    return jsonify({
        "mensaje": "panel de administracion",
        "admin_id": identity['user_id'],
        "total_usuarios_registrados": total_usuarios
    }), 200