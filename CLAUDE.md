# Core bancario

Core bancario mínimo en Flask + SQLAlchemy + PostgreSQL que registra cuentas y movimientos bajo partida doble, solo en MXN. La especificación completa está en `especificacion-core-bancario.md`: define **qué** se construye. Las secciones marcadas como **Pendiente** (§11) no se implementan por suposición.

Estado actual: el módulo `user` (usuarios, RBAC, login con JWT, altas de admin y operador, cambio de contraseña) está implementado. El módulo `account` solo tiene una ruta de prueba; el modelo contable (§4 a §6, §8.3 a §8.13, §10) está sin empezar.

## Comandos

```bash
docker compose up -d            # PostgreSQL 17 (se requiere 15+ por UNIQUE NULLS NOT DISTINCT)
venv/bin/python create_admin.py # DESTRUCTIVO: borra y recrea todas las tablas, siembra roles/permisos y el primer admin
venv/bin/python app.py          # servidor de desarrollo en http://localhost:8080
```

- `create_admin.py` hace `drop_all` + `create_all`. Es la única forma de crear el esquema hoy; no hay migraciones (`migrations/` está vacío, Alembic es un pendiente de §11).
- No hay pruebas todavía (`tests/` está vacío, la estrategia es un pendiente de §11). Para verificar una ruta se usa `app.test_client()`.
- Las dependencias están fijadas en `requirements.txt` y se instalan en `venv/`.

## Variables de entorno

Se cargan de `.env` con `python-dotenv`. `.env` no se versiona; se crea copiando `.env.example` y ajustando los valores.

| Variable | Uso |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Contenedor de `docker-compose.yml` |
| `DATABASE_URL` | Cadena de conexión de SQLAlchemy (`postgresql+psycopg://...`) |
| `JWT_SECRET` | Clave de firma HS256 |
| `JWT_EXPIRACION_MINUTOS` | Duración del access token, 20 por defecto |
| `BANCO_NOMBRE` | Definida, todavía no se usa en el código |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Primer admin que crea `create_admin.py` |

## Estructura

La especificación (§3) propone una carpeta por capa dentro de cada módulo. El código real usa **archivos planos por módulo**, y esa es la convención a seguir:

```
app.py                       # crea el contenedor, lo cablea, registra los blueprints
create_admin.py              # esquema + semilla RBAC + primer admin
src/
├── main/                    # compartido
│   ├── container.py         # DIContainer (dependency-injector)
│   ├── database.py          # Base declarativa de SQLAlchemy
│   ├── errors.py            # AuthenticationError (401), PermissionDenied (403)
│   ├── middleware.py        # decorador @authenticated
│   ├── routes.py            # GET / y manejadores de error globales
│   └── utils.py             # bcrypt, JWT, bearer_token(), json_body()
├── user/
│   ├── domain_model.py      # enums, modelos ORM y repositorios
│   ├── dto.py               # UserCreate, AuthenticatedUser
│   ├── application_service.py
│   └── routes.py
└── account/
    └── routes.py            # solo la ruta de prueba
```

- Los blueprints van en `src/<módulo>/routes.py`, no en una carpeta `api/`.
- `domain_model.py` reúne el modelo ORM y su repositorio en un solo archivo.

## Rutas

| Método | Ruta | Servicio de aplicación | Auth |
|---|---|---|---|
| GET | `/` | — | no |
| GET | `/user/` | — | no |
| POST | `/user/login` | `UserLogin` | no |
| POST | `/user/password` | `PasswordChanger` | `@authenticated(permitir_password_pendiente=True)` |
| POST | `/user/admin` | `UserSignup` (rol `ADMIN`, §8.1) | `@authenticated()` |
| POST | `/user/operador` | `UserSignup` (rol `OPERADOR`, §8.2) | `@authenticated()` |
| GET | `/account/` | — | no |

Las tres rutas `GET` son de prueba y responden `{"mensaje": "Hello, ...!"}`.

Cuerpos y respuestas:

- `POST /user/login`: recibe `email`, `password`. Devuelve `token`, `debe_cambiar_password`.
- `POST /user/password`: recibe `password_actual`, `password_nueva`. Devuelve `debe_cambiar_password: false`.
- `POST /user/admin` y `/user/operador`: reciben `email`, `password`. Devuelven 201 con `id`, `email`, `rol`, `activo`, `debe_cambiar_password`.

## Servicios de aplicación

Todos están en `src/user/application_service.py` y exponen un único método `invoque(...)`.

| Servicio | Qué hace |
|---|---|
| `UserCreator` | Valida email único y rol existente, guarda el usuario con el hash de la contraseña. Lo usan `UserSignup` y `create_admin.py`. |
| `UserSignup` | Exige el permiso `GESTIONAR_USUARIOS` y solo acepta los roles `ADMIN` y `OPERADOR`; delega en `UserCreator`. Los clientes se dan de alta con su cuenta (§8.3). |
| `UserLogin` | Verifica credenciales y usuario activo, emite el JWT. Devuelve el mismo error en todos los fallos para no revelar qué emails existen. |
| `UserAuthenticator` | Traduce el token a un `AuthenticatedUser`. Consulta al usuario en cada solicitud, así una desactivación o cambio de rol surte efecto de inmediato. Lo usa `@authenticated`. |
| `PasswordChanger` | Cambia la contraseña y apaga `debe_cambiar_password`. |

## Autenticación y autorización

- JWT HS256 con un solo access token, sin refresh ni lista de revocación. Claims: `sub` (id del usuario), `rol`, `iat`, `exp`. Se envía como `Authorization: Bearer <token>`.
- `@authenticated()` valida el token y pasa el usuario a la vista como argumento `actor: AuthenticatedUser`. Va **encima** de `@inject`.
- Mientras `debe_cambiar_password` sea true, el usuario solo puede entrar a rutas marcadas con `permitir_password_pendiente=True`; en las demás recibe 403.
- La autorización se hace por **permisos, nunca por rol**: `actor.tiene_permiso(Accion.X, Alcance.Y)`. Un permiso es el par `(Accion, Alcance)`; `GESTIONAR_USUARIOS` va sin alcance.
- Las contraseñas se guardan con bcrypt, que admite como máximo 72 bytes (`MAX_PASSWORD_BYTES`); se valida al crear el usuario y al cambiar la contraseña.

Semilla fija de roles (`create_admin.py`, §9):

| Rol | Permisos |
|---|---|
| `CLIENTE` | VER, FONDEAR, RETIRAR, TRANSFERIR sobre `PROPIAS` |
| `OPERADOR` | VER, FONDEAR, RETIRAR, TRANSFERIR, ABRIR_CUENTA sobre `NOSTRO`; VER y ABRIR_CUENTA sobre `VOSTRO` |
| `ADMIN` | VER, FONDEAR, RETIRAR, TRANSFERIR, ABRIR_CUENTA sobre `VOSTRO` y `NOSTRO`; `GESTIONAR_USUARIOS` |

Tablas: `usuarios`, `roles`, `permisos`, `rol_permisos`. Las claves primarias son UUID.

## Convenciones

- Indentación de 2 espacios. Comentarios, mensajes de error, claves JSON y mensajes de commit en español; los comentarios citan la sección de la especificación (`§7`, `§8.1`).
- Errores como JSON `{"error": "..."}`:
  - 400: la ruta valida los campos obligatorios y convierte en 400 los `ValueError` de los servicios.
  - 401 y 403: los servicios lanzan `AuthenticationError` o `PermissionDenied`, y los manejadores globales de `src/main/routes.py` los convierten.
- Las rutas leen el cuerpo con `json_body()`, que devuelve `{}` si no es un objeto JSON.
- Inyección de dependencias: cada servicio nuevo se registra como `Factory` en `DIContainer` y se recibe en la ruta con `Provide[DIContainer.<nombre>]` bajo `@inject`. Un módulo de rutas nuevo se agrega a `container.wire(...)` y a `register_blueprint` en `app.py`.
- Sesiones de BD: `session` es un `Factory`, cada repositorio recibe la suya. `save` y `update` hacen commit y cierran; los servicios que solo leen cierran el repositorio en un `finally` para devolver la conexión al pool.
- El repo no tiene remoto y los commits van directo a `main`.
