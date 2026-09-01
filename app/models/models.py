from ..extensions import db

class Role(db.Model):
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    #nombre del rol
    name = db.Column(db.String(50), unique=True, nullable=False)
    
    #relacion uno a muchos con usuarios
    users = db.relationship('User', backref='role', lazy=True) #un rol tiene muchos users
