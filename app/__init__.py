from flask import Flask
from .config import Config
from .extensions import db, bcrypt, limiter, csrf, server_session
from .models.models import User, Role #importar modelo para que sqlalchemy reconozca al crear tabla
import os

def create_app(config_class=Config):
    #inicializa la aplicacion flask
    app = Flask(__name__)
    app.config.from_object(config_class) #lee todos los atributos de la clase

    #crear el directorio de sesiones si no existe
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)

    #vincula las extensiones
    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    if csrf:
        csrf.init_app(app)
    server_session.init_app(app)

    #contexto de la app para operaciones de base de datos iniciales
    with app.app_context():
        #crea el archivo sqlite y las tablas si no existen
        db.create_all()
        
        #creacion automatica de roles base si la tabla esta vacia
        if not Role.query.first():
            rol_usuario = Role(name='usuario')
            rol_admin = Role(name='administrador')
            db.session.add_all([rol_usuario, rol_admin]) #session es como el cursor
            db.session.commit()

    #ruta de prueba
    @app.route('/ping')
    def ping():
        return {"mensaje": "servidor passport inc activo"}
    
    #registro de blueprints
    from .controller.auth import auth_bp
    from .controller.protected import protected_bp
    
    app.register_blueprint(auth_bp) #monta todas las rutas de auth_bp en /auth/
    app.register_blueprint(protected_bp) #lo mismo pero con protected_bp en /api

    return app