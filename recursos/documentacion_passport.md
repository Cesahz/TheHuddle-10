# PassPort Inc. — Documentación Técnica del Sistema de Autenticación

> Documentación adaptada al código real del proyecto. Cada sección explica el *qué*, el *por qué* y el *cómo* de cada decisión técnica, siguiendo el flujo exacto de los archivos.

---

## Índice

- [Stack y dependencias](#stack-y-dependencias)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Flujo de arranque — `__init__.py`](#flujo-de-arranque--__init__py)
- [Extensiones — `extensions.py`](#extensiones--extensionspy)
- [Configuración — `config.py`](#configuración--configpy)
- [Modelos — `models.py`](#modelos--modelspy)
- [Autenticación — `auth.py`](#autenticación--authpy)
  - [Validación de email con regex](#validación-de-email-con-regex)
  - [Registro de usuario](#registro-de-usuario)
  - [Login con Cookie](#login-con-cookie)
  - [Logout con Cookie](#logout-con-cookie)
  - [Login con JWT](#login-con-jwt)
  - [CSRF Token](#csrf-token)
- [Decoradores — `decorators.py`](#decoradores--decoratorspy)
  - [get_user_identity](#get_user_identity)
  - [login_required](#login_required)
  - [admin_required](#admin_required)
- [Rutas protegidas — `protected.py`](#rutas-protegidas--protectedpy)
- [Flujos completos end-to-end](#flujos-completos-end-to-end)
  - [Flujo Cookie](#flujo-cookie)
  - [Flujo JWT](#flujo-jwt)
- [Mapa de todas las rutas](#mapa-de-todas-las-rutas)
- [Decisiones de seguridad y por qué](#decisiones-de-seguridad-y-por-qué)

---

## Stack y dependencias

```
Python 3.10+
Flask 3.x                  — framework web
Flask-SQLAlchemy           — ORM para la base de datos
Flask-Bcrypt               — hashing seguro de contraseñas
Flask-Limiter              — rate limiting (protección fuerza bruta)
Flask-WTF                  — protección CSRF
Flask-Session              — sesiones del lado del servidor
PyJWT                      — generación y verificación de tokens JWT
python-dotenv              — carga de variables de entorno desde .env
SQLite                     — base de datos (archivo local passport.db)
```

```bash
# Instalar todo de una vez
pip install flask flask-sqlalchemy flask-bcrypt flask-limiter \
            flask-wtf flask-session pyjwt python-dotenv
```

El archivo `.env` mínimo para que arranque:

```
SECRET_KEY=una-clave-larga-y-aleatoria-minimo-32-caracteres
SESSION_COOKIE_SECURE=False    # True solo en produccion con HTTPS
```

---

## Estructura del proyecto

```
passport_inc/
│
├── __init__.py       ← fábrica de la app (create_app), arranque y registro de blueprints
├── config.py         ← todas las variables de configuración centralizadas
├── extensions.py     ← instancias de las librerías (db, bcrypt, limiter, etc.)
├── models.py         ← definición de tablas: User y Role
├── auth.py           ← rutas de autenticación (/auth/...)
├── decorators.py     ← lógica de protección reutilizable (login_required, admin_required)
├── protected.py      ← rutas que requieren autenticación (/api/...)
│
├── passport.db       ← archivo SQLite (se genera automáticamente)
├── flask_sessions/   ← archivos de sesión del servidor (se genera automáticamente)
└── .env              ← variables de entorno (nunca subir a git)
```

**Por qué esta estructura:** cada archivo tiene una única responsabilidad. `extensions.py` existe específicamente para romper dependencias circulares — si cada archivo importara Flask directamente, Python entraría en un loop de importaciones.

---

## Flujo de arranque — `__init__.py`

Este es el punto de entrada de toda la aplicación. Usa el patrón **Application Factory** (`create_app`), que permite crear instancias de la app con distintas configuraciones (producción, testing, desarrollo).

```python
from flask import Flask
from .config import Config
from .extensions import db, bcrypt, limiter, csrf, server_session
from .models import User, Role
import os

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    # app.config.from_object() lee todos los atributos de la clase Config
    # y los carga en el diccionario de configuración de Flask (app.config).
    # Accesibles luego como: current_app.config['SECRET_KEY']

    # Crear el directorio de sesiones si no existe.
    # Flask-Session con SESSION_TYPE='filesystem' escribe un archivo
    # por cada sesión activa. Si el directorio no existe, lanza un error.
    os.makedirs(app.config['SESSION_FILE_DIR'], exist_ok=True)
    # exist_ok=True evita el error si el directorio ya existe.

    # Vincular extensiones a esta instancia de la app.
    # init_app() es el patrón de Flask para extensiones que fueron
    # instanciadas sin app (en extensions.py). Las conecta en este momento.
    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    server_session.init_app(app)

    with app.app_context():
        # app_context() es necesario para cualquier operación que requiera
        # acceder a la base de datos o a current_app fuera de un request.
        db.create_all()
        # create_all() lee los modelos importados arriba (User, Role)
        # y crea las tablas en SQLite si no existen. Si ya existen, no hace nada.

        # Seed de roles: poblar la tabla de roles si está vacía.
        # Esto garantiza que siempre existan los roles base sin intervención manual.
        if not Role.query.first():
            db.session.add_all([Role(name='usuario'), Role(name='administrador')])
            db.session.commit()

    # Registro de blueprints.
    # Los imports están aquí adentro (no al inicio del archivo) para evitar
    # importaciones circulares: auth.py importa de extensions.py, que ya
    # fue importado arriba. Si se importara al inicio, el ciclo se rompería.
    from .auth import auth_bp
    from .protected import protected_bp

    app.register_blueprint(auth_bp)      # monta todas las rutas de auth_bp en /auth
    app.register_blueprint(protected_bp) # monta todas las rutas de protected_bp en /api

    return app
```

---

## Extensiones — `extensions.py`

```python
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_session import Session

# Todas las extensiones se instancian SIN pasar la app.
# Esto es el patrón "init_app" de Flask: separar la creación
# de la extensión de su vinculación con la app.
# Ventaja: este archivo puede ser importado desde cualquier otro
# sin necesitar la instancia de Flask todavía.

db             = SQLAlchemy()   # ORM — maneja todas las operaciones con la DB
bcrypt         = Bcrypt()       # hashing de contraseñas con bcrypt
csrf           = CSRFProtect()  # protección automática contra CSRF en formularios POST
server_session = Session()      # sesiones del lado del servidor (reemplaza la cookie firmada)

limiter = Limiter(
    key_func=get_remote_address,
    # get_remote_address usa la IP del cliente como clave para el contador.
    # Cada IP tiene su propio límite independiente.

    default_limits=["200 per day", "50 per hour"]
    # Límites globales para TODAS las rutas.
    # Rutas específicas pueden tener límites más estrictos con @limiter.limit().
)
```

---

## Configuración — `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()
# load_dotenv() lee el archivo .env del directorio actual
# y carga cada línea como variable de entorno del proceso.
# Después de esto, os.environ.get('SECRET_KEY') funciona.

class Config:

    SECRET_KEY = os.environ.get('SECRET_KEY')
    # Flask usa SECRET_KEY para firmar cookies, tokens CSRF y la sesión.
    # Si esta clave se filtra, un atacante puede falsificar cualquier dato
    # firmado por Flask. Debe ser larga (mínimo 32 chars), aleatoria,
    # y vivir SOLO en el .env, nunca en el código.

    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'passport.db')
    # __file__ es la ruta del archivo config.py.
    # abspath + dirname nos da el directorio donde vive config.py.
    # Resultado: la DB se crea en el mismo directorio que el proyecto.

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Desactiva un sistema de eventos de SQLAlchemy que consume memoria
    # y no se usa en este proyecto.

    # ── Sesiones del lado del servidor ───────────────────────────────
    SESSION_TYPE = 'filesystem'
    # Sin SESSION_TYPE, Flask usa su sesión por defecto: guarda todo el
    # contenido de session{} firmado DENTRO de la cookie del cliente.
    # Consecuencia: session.clear() en el logout solo borra el cliente,
    # no existe nada en el servidor que invalidar realmente.
    # Con 'filesystem', Flask escribe un archivo por sesión en el servidor.
    # La cookie solo transporta el ID — el contenido queda en el servidor.
    # Para producción con múltiples workers: reemplazar por 'redis'.

    SESSION_FILE_DIR = os.path.join(basedir, 'flask_sessions')
    # Directorio donde Flask-Session escribirá los archivos de sesión.
    # Se crea automáticamente en __init__.py con os.makedirs().

    SESSION_PERMANENT = False
    # False: la sesión expira cuando el usuario cierra el navegador.
    # True: la sesión dura PERMANENT_SESSION_LIFETIME segundos.

    # ── Flags de seguridad de la cookie ──────────────────────────────
    SESSION_COOKIE_HTTPONLY = True
    # Impide que JavaScript lea la cookie desde el cliente.
    # Sin esto: document.cookie expone el session ID — robo trivial con XSS.
    # Con esto: aunque haya XSS, el script no puede leer la cookie.

    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE') == 'True'
    # True: el navegador solo envía la cookie por HTTPS, nunca por HTTP.
    # Previene que alguien en la misma red WiFi intercepte la cookie
    # con un sniffer (ataque Man-in-the-Middle).
    # Se lee del .env para poder ser False en desarrollo (HTTP local).

    SESSION_COOKIE_SAMESITE = 'Strict'
    # Controla cuándo el navegador envía la cookie en requests cross-site.
    # 'Strict': NUNCA se envía si el request viene de otro dominio.
    #           Ni siquiera al hacer clic en un link externo.
    # 'Lax':    No se envía en POST cross-site, pero SÍ en GET de navegación.
    # 'None':   Se envía siempre (requiere Secure=True).
    # Para PassPort que custodia documentos de identidad: Strict es obligatorio.

    # ── Límites de contraseña ─────────────────────────────────────────
    PASSWORD_MIN_LENGTH = 8
    # Contraseñas de menos de 8 caracteres son triviales de romper
    # por fuerza bruta incluso con bcrypt.

    PASSWORD_MAX_LENGTH = 128
    # bcrypt internamente procesa hasta 72 bytes y descarta el resto.
    # Una contraseña de 10.000 caracteres obliga a bcrypt a hacer
    # trabajo costoso antes de truncar igual a 72 bytes.
    # Esto es un vector de DoS barato: el atacante manda contraseñas
    # enormes para saturar el CPU del servidor.
```

---

## Modelos — `models.py`

```python
from .extensions import db
# Importar la instancia de SQLAlchemy desde extensions.py.
# NO se importa desde flask_sqlalchemy directamente para mantener
# una única instancia compartida en toda la app.

class Role(db.Model):
    __tablename__ = 'roles'
    # __tablename__ define el nombre exacto de la tabla en SQLite.
    # Sin esto, SQLAlchemy usaría el nombre de la clase en minúsculas.

    id   = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    # unique=True: no pueden existir dos roles con el mismo nombre.
    # nullable=False: toda fila debe tener nombre, no puede ser NULL.

    users = db.relationship('User', backref='role', lazy=True)
    # Relación uno a muchos: un Role tiene muchos Users.
    # backref='role' agrega automáticamente el atributo .role a cada
    # instancia de User. Ej: usuario.role.name devuelve "administrador".
    # lazy=True: los usuarios NO se cargan de la DB hasta que se acceda
    # a role.users explícitamente (carga diferida — más eficiente).


class User(db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    # NUNCA se almacena la contraseña en texto plano.
    # Solo el hash generado por bcrypt. bcrypt produce hashes de
    # longitud fija (~60 chars), pero String(128) da margen.

    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    # Clave foránea que conecta cada User con exactamente un Role.
    # nullable=False: todo usuario debe tener rol asignado.
    # db.ForeignKey('roles.id') usa el nombre de tabla, no la clase.
```

**Cómo se ven las tablas en SQLite:**

```
tabla: roles              tabla: users
┌────┬───────────────┐    ┌────┬──────────────────────┬───────────────┬─────────┐
│ id │ name          │    │ id │ email                │ password_hash │ role_id │
├────┼───────────────┤    ├────┼──────────────────────┼───────────────┼─────────┤
│ 1  │ usuario       │    │ 1  │ ana@passport.com     │ $2b$12$...    │ 1       │
│ 2  │ administrador │    │ 2  │ admin@passport.com   │ $2b$12$...    │ 2       │
└────┴───────────────┘    └────┴──────────────────────┴───────────────┴─────────┘
```

---

## Autenticación — `auth.py`

Blueprint que agrupa todas las rutas públicas de autenticación bajo el prefijo `/auth`.

```python
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
# Blueprint: una forma de organizar rutas en grupos reutilizables.
# url_prefix='/auth' significa que TODAS las rutas de este blueprint
# tendrán /auth como prefijo. Ej: @auth_bp.route('/login') → /auth/login
```

### Validación de email con regex

```python
import re

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
# re.compile() compila el patrón una sola vez al cargar el módulo.
# Es más eficiente que re.match() en cada request porque no recompila.

def is_valid_email(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))
```

Lectura del patrón carácter por carácter:

```
^                        debe EMPEZAR acá (nada antes)
[a-zA-Z0-9._%+\-]+       lado izquierdo del @:
                           letras (mayus/minus), números, y los símbolos . _ % + -
                           el + significa "uno o más de estos"
@                        el arroba literal — obligatorio, exactamente uno
[a-zA-Z0-9.\-]+          el dominio: letras, números, puntos, guiones
\.                       un punto LITERAL (la \ escapa el punto, que en regex
                         normalmente significa "cualquier carácter")
[a-zA-Z]{2,}             la extensión (.com, .net, .org):
                           solo letras, mínimo 2 caracteres
$                        debe TERMINAR acá (nada después)
```

**Por qué esto en lugar de `bleach.clean()`:** `bleach` sanitiza HTML. Un email no contiene HTML — `bleach.clean("usuario@ejemplo.com")` devuelve exactamente lo mismo que recibió. No aportaba ninguna protección real, solo daba una falsa sensación de seguridad. El regex rechaza cualquier carácter que no pertenezca al formato de email válido, incluyendo `< > ( )` que son la base de cualquier payload XSS.

---

### Registro de usuario

```python
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    # get_json() parsea el body del request como JSON.
    # Devuelve None si el Content-Type no es application/json
    # o si el body no es JSON válido.

    if not data:
        return jsonify({"error": "formato de datos invalido"}), 400

    email    = data.get('email', '').strip().lower()
    # .strip() elimina espacios al inicio y al final.
    # .lower() normaliza a minúsculas para evitar duplicados:
    # "Ana@Passport.com" y "ana@passport.com" son el mismo email.
    password = data.get('password', '')
    # data.get('campo', '') devuelve '' si el campo no existe,
    # en lugar de None — evita errores en las validaciones siguientes.

    if not email or not password:
        return jsonify({"error": "email y contrasena son obligatorios"}), 400

    if not is_valid_email(email):
        return jsonify({"error": "formato de email invalido"}), 400
        # Input con <script>, espacios, o formato inválido → rechazado acá.
        # Nunca llega a la base de datos.

    min_len = current_app.config['PASSWORD_MIN_LENGTH']   # 8
    max_len = current_app.config['PASSWORD_MAX_LENGTH']   # 128
    if len(password) < min_len:
        return jsonify({"error": f"la contrasena debe tener al menos {min_len} caracteres"}), 400
    if len(password) > max_len:
        return jsonify({"error": f"la contrasena no puede superar {max_len} caracteres"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "el usuario ya esta registrado"}), 409
        # filter_by() genera: SELECT * FROM users WHERE email = ? LIMIT 1
        # .first() devuelve el primer resultado o None.
        # 409 Conflict: el recurso ya existe.

    user_role = Role.query.filter_by(name='usuario').first()
    # Todo usuario registrado via API pública recibe el rol básico.
    # El rol 'administrador' solo se asigna manualmente (via DB o ruta protegida).

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    # bcrypt.generate_password_hash() aplica el algoritmo bcrypt con un salt
    # aleatorio incorporado. Cada llamada produce un hash diferente incluso
    # para la misma contraseña — esto previene rainbow tables.
    # El resultado es bytes (b'$2b$12$...'), .decode() lo convierte a str
    # para poder guardarlo en la columna String de SQLAlchemy.

    new_user = User(email=email, password_hash=hashed_password, role_id=user_role.id)
    db.session.add(new_user)
    db.session.commit()
    # db.session.add() registra el objeto para ser insertado.
    # db.session.commit() ejecuta el INSERT y confirma la transacción.
    # Si commit() falla, SQLAlchemy hace rollback automático.

    return jsonify({"mensaje": "usuario creado con exito"}), 201
    # 201 Created: el recurso fue creado exitosamente.
```

---

### Login con Cookie

```python
@auth_bp.route('/login/cookie', methods=['POST'])
@limiter.limit("5 per minute")
# Este decorador aplica un límite específico de 5 requests por minuto
# POR IP a esta ruta. Supera ese límite → 429 Too Many Requests.
# Protege contra ataques de fuerza bruta: máximo 5 intentos por minuto.
def login_cookie():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):
        # bcrypt.check_password_hash() extrae el salt del hash almacenado,
        # aplica bcrypt a la contraseña recibida con ese mismo salt,
        # y compara. Nunca se "descifra" el hash — se rehashea y compara.

        session.clear()
        # CRÍTICO: limpiar la sesión ANTES de escribir datos del usuario.
        # Previene Session Fixation: si un atacante logró fijar un session ID
        # conocido por él antes del login, session.clear() descarta ese ID
        # y genera uno nuevo. El atacante pierde el acceso.

        session['user_id'] = user.id
        session['role']    = user.role.name
        # Con Flask-Session (filesystem), estos datos se escriben en un
        # archivo del servidor. La cookie del cliente solo contiene el ID
        # que apunta a ese archivo — nunca el contenido.

        return jsonify({"mensaje": "inicio de sesion exitoso", "metodo": "cookie", "rol": user.role.name}), 200

    return jsonify({"error": "credenciales invalidas"}), 401
    # Respuesta genérica: no decimos "el email no existe" ni "la contraseña
    # es incorrecta". Dar pistas específicas facilita ataques de enumeración
    # de usuarios (el atacante sabe qué emails están registrados).
```

---

### Logout con Cookie

```python
@auth_bp.route('/logout/cookie', methods=['POST'])
# Sin @limiter.limit — limitar el logout sería un vector de DoS:
# un atacante podría hacer 5 requests al endpoint y bloquear al
# usuario legítimo durante un minuto, impidiéndole cerrar su sesión.
def logout_cookie():
    session.clear()
    # Con Flask-Session en filesystem: elimina el archivo de sesión
    # del servidor Y instruye al navegador a borrar la cookie.
    # El session ID queda huérfano e inútil — logout real y completo.
    return jsonify({"mensaje": "sesion cerrada correctamente"}), 200
```

---

### Login con JWT

```python
@auth_bp.route('/login/jwt', methods=['POST'])
@limiter.limit("5 per minute")
def login_jwt():
    data     = request.get_json()
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '')

    user = User.query.filter_by(email=email).first()

    if user and bcrypt.check_password_hash(user.password_hash, password):

        now = datetime.datetime.now(datetime.timezone.utc)
        # datetime.now(timezone.utc) devuelve un datetime "aware":
        # sabe que está en UTC. Es el reemplazo de utcnow() que está
        # deprecado desde Python 3.12 porque devolvía un datetime "naive"
        # (sin información de zona horaria), causando bugs sutiles.

        payload = {
            'user_id': user.id,
            'role':    user.role.name,
            'iat':     now,
            # iat = issued at: timestamp de cuándo se creó el token.
            # Útil para auditoría y para invalidar tokens emitidos antes
            # de un evento de seguridad (ej: cambio de contraseña).

            'exp': now + datetime.timedelta(hours=1),
            # exp = expiration: el token deja de ser válido 1 hora después.
            # PyJWT verifica esto automáticamente en jwt.decode().
            # Sin expiración, un token robado sería válido para siempre.
        }

        token = jwt.encode(payload, current_app.config['SECRET_KEY'], algorithm='HS256')
        # jwt.encode() construye el JWT:
        # 1. Serializa header y payload a JSON y los codifica en Base64URL
        # 2. Calcula HMAC-SHA256(base64(header) + "." + base64(payload), SECRET_KEY)
        # 3. Concatena las tres partes con puntos: header.payload.signature
        #
        # ⚠️  El payload NO está cifrado — cualquiera puede decodificarlo con Base64.
        #     La firma solo garantiza INTEGRIDAD (que no fue modificado),
        #     no CONFIDENCIALIDAD. Nunca poner contraseñas o datos sensibles aquí.

        return jsonify({"mensaje": "inicio de sesion exitoso", "metodo": "jwt", "token": token}), 200

    return jsonify({"error": "credenciales invalidas"}), 401
```

---

### CSRF Token

```python
@auth_bp.route('/csrf-token', methods=['GET'])
def get_csrf_token():
    token = generate_csrf()
    # generate_csrf() de Flask-WTF genera un token aleatorio,
    # lo almacena en la sesión actual, y lo devuelve.
    # El cliente debe incluirlo en requests mutantes (POST/PUT/DELETE)
    # como header X-CSRFToken o en el body.
    # Flask-WTF lo compara con el de la sesión antes de procesar.
    return jsonify({"csrf_token": token}), 200
```

**Cómo funciona la protección CSRF completa:**

```
1. Cliente pide GET /auth/csrf-token  →  servidor genera token y lo guarda en sesión
2. Cliente guarda el token
3. Cliente hace POST /api/alguna-ruta con header X-CSRFToken: <token>
4. Flask-WTF compara el token del header con el de la sesión
5. Coinciden → request procesado
   No coinciden → 400 Bad Request

Un atacante desde evil.com no puede leer el token (Same-Origin Policy),
por lo tanto no puede incluirlo en sus requests maliciosos.
```

---

## Decoradores — `decorators.py`

Los decoradores son funciones que envuelven a otras funciones para agregar comportamiento antes o después de ejecutarlas. Aquí se usan para proteger rutas sin repetir código de validación.

### get_user_identity

```python
def get_user_identity():
    # Esta función implementa un sistema dual de autenticación:
    # acepta tanto JWT (para clientes API) como Cookie (para browsers).
    # Primero verifica JWT, luego Cookie. El primero que sea válido gana.

    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        # El header tiene formato: "Bearer eyJhbGci..."
        # split(' ')[1] toma la segunda parte (el token en sí).

        try:
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
                # algorithms debe ser una lista EXPLÍCITA.
                # Sin esto, versiones antiguas de PyJWT aceptaban
                # alg: "none" en el header, permitiendo tokens sin firma.
            )
            return {"user_id": payload['user_id'], "role": payload['role']}

        except jwt.ExpiredSignatureError:
            return {"error": "el token ha expirado"}
            # El token existía y era válido, pero su 'exp' ya pasó.
            # El cliente debe obtener un nuevo token haciendo login.

        except jwt.InvalidTokenError:
            return {"error": "token invalido o modificado"}
            # Captura cualquier otro error: firma inválida, formato
            # incorrecto, algoritmo incorrecto, etc.
            # InvalidTokenError es la clase base de todos los errores de PyJWT.

    if 'user_id' in session:
        return {"user_id": session.get('user_id'), "role": session.get('role')}
        # Si no hay JWT válido, buscar en la sesión de cookie.
        # Con Flask-Session, esto consulta el archivo/Redis del servidor.

    return None
    # None significa: no hay ninguna forma válida de identificar al usuario.
```

### login_required

```python
def login_required(f):
    @wraps(f)
    # @wraps(f) preserva el nombre y docstring de la función original.
    # Sin esto, todas las rutas decoradas se llamarían "decorated_function"
    # internamente, causando conflictos en Flask al registrar las rutas.
    def decorated_function(*args, **kwargs):
        identity = get_user_identity()

        if not identity:
            return jsonify({"error": "autenticacion requerida"}), 401

        if "error" in identity:
            return jsonify({"error": identity["error"]}), 401
            # get_user_identity() devuelve {"error": "..."} cuando el token
            # existe pero es inválido (expirado, modificado). Distinguir esto
            # de None (sin token) permite dar mensajes de error más precisos.

        return f(*args, **kwargs)
        # Si llegamos acá, la identidad es válida. Ejecutar la vista original.
    return decorated_function
```

### admin_required

```python
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        identity = get_user_identity()

        if not identity or "error" in identity:
            return jsonify({"error": "autenticacion requerida"}), 401

        if identity.get("role") != "administrador":
            return jsonify({"error": "acceso denegado. requiere rol de administrador"}), 403
            # 403 Forbidden: el usuario está autenticado pero no autorizado.
            # Diferencia importante con 401 (no autenticado):
            # 401 = "no sé quién sos"
            # 403 = "sé quién sos, pero no tenés permiso"

        return f(*args, **kwargs)
    return decorated_function
```

**Cómo se usan los decoradores (orden de ejecución):**

```python
@protected_bp.route('/admin/dashboard', methods=['GET'])
@admin_required       # ← se ejecuta segundo (más cercano a la función)
def admin_dashboard():
    ...

# Cuando llega un request, el orden real es:
# 1. Flask verifica la ruta y el método HTTP
# 2. admin_required() llama a get_user_identity()
# 3. Si es admin → ejecuta admin_dashboard()
# 4. admin_dashboard() retorna la respuesta
```

---

## Rutas protegidas — `protected.py`

```python
protected_bp = Blueprint('protected', __name__, url_prefix='/api')

@protected_bp.route('/perfil', methods=['GET'])
@login_required
def perfil():
    identity = get_user_identity()
    # get_user_identity() se llama de nuevo aunque ya fue llamada en
    # @login_required. Esto es porque el decorador no pasa la identidad
    # a la vista — una mejora futura sería usar flask.g para compartirla.
    return jsonify({
        "mensaje":  "acceso concedido",
        "usuario":  identity['user_id'],
        "rol":      identity['role'],
        "datos":    "aqui estaran tus pasaportes e identificaciones digitales"
    }), 200


@protected_bp.route('/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    identity      = get_user_identity()
    total_usuarios = User.query.count()
    # User.query.count() genera: SELECT COUNT(*) FROM users
    # Más eficiente que User.query.all() + len() porque no trae
    # todos los objetos a memoria, solo el número.
    return jsonify({
        "mensaje":                   "panel de administracion",
        "admin_id":                  identity['user_id'],
        "total_usuarios_registrados": total_usuarios
    }), 200
```

---

## Flujos completos end-to-end

### Flujo Cookie

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. REGISTRO                                                         │
│                                                                      │
│  POST /auth/register  { email, password }                            │
│    → is_valid_email()         — valida formato                       │
│    → len(password)            — valida longitud                      │
│    → User.query.filter_by()   — verifica que no exista               │
│    → bcrypt.generate_hash()   — hashea la contraseña                 │
│    → db.session.commit()      — persiste en SQLite                   │
│  ← 201 { mensaje: "usuario creado" }                                 │
│                                                                      │
│  2. LOGIN                                                            │
│                                                                      │
│  POST /auth/login/cookie  { email, password }                        │
│    → User.query.filter_by()          — busca el usuario              │
│    → bcrypt.check_password_hash()    — verifica contraseña           │
│    → session.clear()                 — previene session fixation      │
│    → session['user_id'] = user.id    — guarda en servidor            │
│  ← 200 + Set-Cookie: session=<ID>; HttpOnly; Secure; SameSite=Strict│
│                                                                      │
│  3. REQUEST AUTENTICADO                                              │
│                                                                      │
│  GET /api/perfil  Cookie: session=<ID>  (enviada automáticamente)   │
│    → @login_required                                                 │
│    → get_user_identity()      — busca 'user_id' en session           │
│    → Flask-Session lee el archivo del servidor con ese ID            │
│  ← 200 { usuario, rol, datos }                                       │
│                                                                      │
│  4. LOGOUT                                                           │
│                                                                      │
│  POST /auth/logout/cookie                                            │
│    → session.clear()   — elimina el archivo del servidor             │
│  ← 200  + el navegador borra la cookie                               │
│                                                                      │
│  5. REQUEST POST-LOGOUT                                              │
│                                                                      │
│  GET /api/perfil  (sin cookie o con cookie ya inválida)              │
│    → get_user_identity() devuelve None                               │
│  ← 401 { error: "autenticacion requerida" }                          │
└──────────────────────────────────────────────────────────────────────┘
```

### Flujo JWT

```
┌──────────────────────────────────────────────────────────────────────┐
│  1. LOGIN                                                            │
│                                                                      │
│  POST /auth/login/jwt  { email, password }                           │
│    → bcrypt.check_password_hash()                                    │
│    → jwt.encode({ user_id, role, iat, exp }, SECRET_KEY, HS256)      │
│  ← 200 { token: "eyJhbGci..." }                                      │
│       El servidor NO guarda nada — sin estado                        │
│                                                                      │
│  2. REQUEST AUTENTICADO                                              │
│                                                                      │
│  GET /api/perfil                                                     │
│  Authorization: Bearer eyJhbGci...                                   │
│    → @login_required                                                 │
│    → get_user_identity()                                             │
│    → jwt.decode(token, SECRET_KEY, algorithms=['HS256'])             │
│         verifica firma + verifica exp                                │
│  ← 200 { usuario, rol, datos }                                       │
│                                                                      │
│  3. TOKEN EXPIRADO                                                   │
│                                                                      │
│  GET /api/perfil  Authorization: Bearer <token expirado>             │
│    → jwt.decode() lanza ExpiredSignatureError                        │
│    → get_user_identity() retorna { error: "el token ha expirado" }   │
│  ← 401 { error: "el token ha expirado" }                             │
│                                                                      │
│  4. TOKEN MODIFICADO                                                 │
│                                                                      │
│  GET /api/perfil  Authorization: Bearer <token alterado>             │
│    → jwt.decode() lanza InvalidTokenError (firma no coincide)        │
│  ← 401 { error: "token invalido o modificado" }                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Mapa de todas las rutas

| Método | Ruta | Protección | Descripción |
|--------|------|------------|-------------|
| GET | `/ping` | Ninguna | Health check del servidor |
| GET | `/auth/csrf-token` | Ninguna | Obtener token CSRF |
| POST | `/auth/register` | Ninguna | Crear cuenta nueva |
| POST | `/auth/login/cookie` | Rate limit 5/min | Login con sesión |
| POST | `/auth/logout/cookie` | Ninguna | Cerrar sesión |
| POST | `/auth/login/jwt` | Rate limit 5/min | Login con JWT |
| GET | `/api/perfil` | `@login_required` | Datos del usuario |
| GET | `/api/admin/dashboard` | `@admin_required` | Panel de administración |

---

## Decisiones de seguridad y por qué

| Decisión | Alternativa descartada | Motivo |
|----------|------------------------|--------|
| `SESSION_TYPE='filesystem'` | Sesión firmada en cookie (default Flask) | Con la default, `session.clear()` no invalida nada en el servidor |
| `SameSite=Strict` | `SameSite=Lax` | PassPort custodia documentos de identidad — no hay justificación para aceptar cookies en navegación cross-site |
| `SESSION_COOKIE_HTTPONLY=True` | `False` | Sin esto JavaScript puede leer el session ID — robo trivial vía XSS |
| Regex para email | `bleach.clean()` | `bleach` sanitiza HTML, no emails. Rechazar input inválido es más correcto que "limpiarlo" |
| Límite de contraseña 8-128 chars | Sin límite | Sin mínimo: fuerza bruta trivial. Sin máximo: DoS contra bcrypt |
| `datetime.now(timezone.utc)` | `datetime.utcnow()` | `utcnow()` deprecado en Python 3.12 — produce datetime sin zona horaria |
| Sin `@limiter` en logout | Con `@limiter` | Limitar el logout es un DoS contra el propio usuario |
| Respuesta genérica en login fallido | Mensajes específicos | Mensajes específicos permiten enumerar usuarios registrados |
| `algorithms=['HS256']` explícito | Sin especificar | Sin lista explícita, versiones viejas de PyJWT aceptaban `alg: none` |

---

*Documentación generada sobre el código real de PassPort Inc. — Python 3.10+ · Flask 3.x · PyJWT 2.x · Flask-Session 0.8+*
