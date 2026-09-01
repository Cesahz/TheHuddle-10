from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_session import Session
import os

#instancia de la base de datos independiente de la app principal
db = SQLAlchemy() #ORM
#instancia para el hasheo seguro de contrasenas
bcrypt = Bcrypt()

#instanciar la herramienta para poner timer a las peticiones
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

#instanciar la proteccion csrf
csrf = CSRFProtect() if os.getenv('CSRF_ENABLED', 'True') == 'True' else None

#instancia de flask-session para manejar sesiones del lado del servidor
server_session = Session() #reemplaza la cookie firmada