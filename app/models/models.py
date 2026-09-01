from ..extensions import db

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    #nombre del rol
    name = db.Column(db.String(50), unique=True, nullable=False)
    
    #relacion uno a muchos con usuarios
    users = db.relationship('User', backref='role', lazy=True) #un rol tiene muchos users

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    #identificador principal del usuario
    email = db.Column(db.String(120), unique=True, nullable=False)
    #almacenaje del hash, nunca la contrasena real
    password_hash = db.Column(db.String(128), nullable=False)
    #conexion obligatoria con la tabla de roles
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    

# tabla: roles              tabla: users
# ┌────┬───────────────┐    ┌────┬──────────────────────┬───────────────┬─────────┐
# │ id │ name          │    │ id │ email                │ password_hash │ role_id │
# ├────┼───────────────┤    ├────┼──────────────────────┼───────────────┼─────────┤
# │ 1  │ usuario       │    │ 1  │ ana@passport.com     │ $2b$12$...    │ 1       │
# │ 2  │ administrador │    │ 2  │ admin@passport.com   │ $2b$12$...    │ 2       │
# └────┴───────────────┘    └────┴──────────────────────┴───────────────┴─────────┘