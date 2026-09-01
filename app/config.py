import os
from dotenv import load_dotenv

#cargar las variables de entorno
load_dotenv()

class Config:
    #clave secreta para firmar cookies y tokens CSRF y la session
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    #configuracion de la base de datos sqlite
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'passport.db')

    #desactivar el rastreo de modificaciones para ahorrar memoria
    SQLALCHEMY_TRACK_MODIFICATIONS = False
