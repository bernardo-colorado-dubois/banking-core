# Core bancario

Core bancario mínimo en Flask + SQLAlchemy + PostgreSQL que registra cuentas y movimientos bajo partida doble, solo en MXN. La especificación completa está en `especificacion-core-bancario.md`: define **qué** se construye. Las secciones marcadas como **Pendiente** (§11) no se implementan por suposición.

Estado actual: el módulo `user` (usuarios, RBAC, login con JWT, altas de admin y operador, cambio de contraseña, perfil) está implementado. El módulo `account` tiene las tablas contables (§9), las aperturas de cuenta (§8.3, §8.4, §8.13) y las operaciones: fondeo, retiro, transferencia y consulta de saldo con historial de movimientos (§8.5 a §8.12), con las invariantes de §6 y el bloqueo de filas de §10, además de la lista de cuentas para operador y admin. No hay reversos ni idempotencia (pendientes de §11).

## Comandos

```bash
docker compose up -d            # PostgreSQL 17 (se requiere 15+ por UNIQUE NULLS NOT DISTINCT)
venv/bin/python create_admin.py # DESTRUCTIVO: borra y recrea todas las tablas, siembra roles/permisos y el primer admin
venv/bin/python app.py          # servidor de desarrollo en http://localhost:8080
```

- `create_admin.py` hace `drop_all` + `create_all`, que también borran y crean la vista `historial_cuentas`. Es la única forma de crear el esquema hoy; no hay migraciones (`migrations/` está vacío, Alembic es un pendiente de §11).
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
| `BANCO_NOMBRE` | Titular que se muestra en las cuentas NOSTRO (§7) |
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
│   ├── dto.py               # UserCreate, UserProfile, AuthenticatedUser
│   ├── application_service.py
│   └── routes.py
└── account/
    ├── domain_model.py      # enums, Account, Transaction (movimientos e invariantes), Movement, vista historial_cuentas y AccountRepository
    ├── dto.py               # AccountDetail, AccountBalance, AccountMovement, OperationResult
    ├── application_service.py
    └── routes.py
```

- Los blueprints van en `src/<módulo>/routes.py`, no en una carpeta `api/`.
- `domain_model.py` reúne el modelo ORM y su repositorio en un solo archivo.

## Rutas

| Método | Ruta | Servicio de aplicación | Auth |
|---|---|---|---|
| GET | `/` | — | no |
| GET | `/user/` | `UserProfileReader` | `@authenticated(permitir_password_pendiente=True)` |
| POST | `/user/login` | `UserLogin` | no |
| POST | `/user/password` | `PasswordChanger` | `@authenticated(permitir_password_pendiente=True)` |
| POST | `/user/admin` | `UserSignup` (rol `ADMIN`, §8.1) | `@authenticated()` |
| POST | `/user/operador` | `UserSignup` (rol `OPERADOR`, §8.2) | `@authenticated()` |
| GET | `/account/` | `AccountLister` | `@authenticated()` |
| POST | `/account/cliente` | `ClientSignup` (§8.3) | `@authenticated()` |
| POST | `/account/vostro` | `VostroAccountOpener` (§8.4) | `@authenticated()` |
| POST | `/account/nostro` | `NostroAccountOpener` (§8.13) | `@authenticated()` |
| POST | `/account/<cuenta_id>/fondeo` | `AccountFunder` (§8.5, §8.10) | `@authenticated()` |
| POST | `/account/<cuenta_id>/retiro` | `AccountWithdrawer` (§8.6, §8.11) | `@authenticated()` |
| POST | `/account/<cuenta_id>/transferencia` | `AccountTransfer` (§8.7, §8.12) | `@authenticated()` |
| GET | `/account/<cuenta_id>/saldo` | `AccountBalanceReader` (§8.8, §8.9) | `@authenticated()` |

`GET /` es de prueba y responde `{"mensaje": "Hello, World!"}`.

Cuerpos y respuestas:

- `GET /user/`: perfil del usuario autenticado. Devuelve `id`, `email`, `nombre`, `rol`, `activo`, `debe_cambiar_password`, `creado_en` (ISO 8601); nunca el hash de la contraseña.
- `POST /user/login`: recibe `email`, `password`. Devuelve `token`, `debe_cambiar_password`.
- `POST /user/password`: recibe `password_actual`, `password_nueva`. Devuelve `debe_cambiar_password: false`.
- `POST /user/admin` y `/user/operador`: reciben `email`, `password`. Devuelven 201 con `id`, `email`, `rol`, `activo`, `debe_cambiar_password`.
- `POST /account/cliente`: recibe `email`, `password`, `nombre`, `alias`. Crea el usuario `CLIENTE` y su primera cuenta VOSTRO.
- `POST /account/vostro`: recibe `email` del cliente existente y `alias`.
- `POST /account/nostro`: recibe `alias`.
- Las tres aperturas devuelven 201 con `id`, `clase`, `alias`, `titular`, `titular_id`, `creada_en`. `titular` es el nombre del cliente o, en NOSTRO, `BANCO_NOMBRE` (con `titular_id` nulo).
- `GET /account/`: devuelve `cuentas`, la lista completa de cuentas NOSTRO y VOSTRO de la más antigua a la más reciente, cada una con los mismos campos que una apertura. Sin paginación.
- `POST /account/<cuenta_id>/fondeo` y `/retiro`: reciben `monto`.
- `POST /account/<cuenta_id>/transferencia`: la cuenta de la ruta es el origen; recibe `cuenta_destino_id`, `monto`.
- Las tres operaciones devuelven 201 con `transaccion_id`, `tipo`, `monto`, `cuenta_id`, `cuenta_destino_id` (nulo salvo en transferencias), `saldo` (el de `cuenta_id` después de la operación) y `creada_en`.
- `GET /account/<cuenta_id>/saldo`: devuelve `cuenta_id`, `clase`, `alias` y `movimientos`, la lista completa del más antiguo al más reciente. Cada movimiento trae `movimiento_id`, `transaccion_id`, `tipo`, `naturaleza`, `monto`, `saldo` (el de la cuenta después de ese movimiento) y `creado_en`. No hay saldo global en la cabecera: el saldo actual es el del último movimiento, y una cuenta sin movimientos devuelve la lista vacía.
- `monto` se acepta como texto o número JSON, mayor que cero y con máximo 2 decimales. Los montos y saldos se devuelven como texto con 2 decimales (`"100.50"`), nunca como float.

## Servicios de aplicación

Están en `src/<módulo>/application_service.py` y exponen un único método `invoque(...)`.

Módulo `user`:

| Servicio | Qué hace |
|---|---|
| `UserCreator` | Valida email único y rol existente, guarda el usuario con el hash de la contraseña. Lo usan `UserSignup` y `create_admin.py`. |
| `UserSignup` | Exige el permiso `GESTIONAR_USUARIOS` y solo acepta los roles `ADMIN` y `OPERADOR`; delega en `UserCreator`. Los clientes se dan de alta con su cuenta (§8.3). |
| `UserLogin` | Verifica credenciales y usuario activo, emite el JWT. Devuelve el mismo error en todos los fallos para no revelar qué emails existen. |
| `UserAuthenticator` | Traduce el token a un `AuthenticatedUser`. Consulta al usuario en cada solicitud, así una desactivación o cambio de rol surte efecto de inmediato. Lo usa `@authenticated`. |
| `UserProfileReader` | Devuelve el `UserProfile` del usuario autenticado, armado antes de cerrar la sesión. |
| `PasswordChanger` | Cambia la contraseña y apaga `debe_cambiar_password`. |

Módulo `account`:

| Servicio | Qué hace |
|---|---|
| `ClientSignup` | Exige `ABRIR_CUENTA:VOSTRO`. Crea el usuario `CLIENTE` y su cuenta en un solo commit: la cuenta se guarda con el titular nuevo en cascada. No pasa por `UserCreator`, que hace su propio commit. |
| `VostroAccountOpener` | Exige `ABRIR_CUENTA:VOSTRO`. Rechaza email inexistente, usuario que no es `CLIENTE` o inactivo, y alias repetido para ese cliente. |
| `NostroAccountOpener` | Exige `ABRIR_CUENTA:NOSTRO`. Rechaza alias repetido entre las cuentas del banco. |
| `AccountLister` | Exige `VER` sobre `VOSTRO` y sobre `NOSTRO` a la vez, porque la lista trae ambas clases; por la semilla solo lo cumplen operador y admin. Devuelve todas las cuentas con su titular. No bloquea ni modifica nada. |
| `AccountFunder`, `AccountWithdrawer` | Bloquean la cuenta, exigen `FONDEAR` o `RETIRAR` sobre su alcance, arman la transacción, validan §6 y la guardan. |
| `AccountTransfer` | Bloquea ambas cuentas en orden de id. Exige `TRANSFERIR` solo sobre el origen; el destino solo debe existir. |
| `AccountBalanceReader` | Exige `VER` sobre el alcance de la cuenta. Devuelve el historial de la vista `historial_cuentas`, con el saldo en cada movimiento. No bloquea ni modifica nada. |

Cómo se arma una operación:

- Hay **un servicio por operación**, no uno por rol. `autorizar(actor, accion, account)` calcula el alcance con `account.alcance_para(actor.id)` (`PROPIAS`, `VOSTRO` o `NOSTRO`) y exige el permiso `(accion, alcance)`. Por eso el admin, que tiene los permisos sobre `VOSTRO`, también opera cuentas de clientes.
- `parse_monto` valida el monto antes de abrir la transacción de BD.
- `Transaction.fondeo`, `.retiro` y `.transferencia` arman los movimientos de §5. `transaction.validar(saldos)` aplica las invariantes de §6 y se llama siempre antes de `save_transaction`.
- `find_by_ids_for_update` bloquea las cuentas (`SELECT ... FOR UPDATE`, ordenado por id) y `balance` se calcula después, en la misma sesión. El bloqueo se libera con el commit de `save_transaction` o con `close`.
- Cuenta inexistente, monto inválido y fondos insuficientes son `ValueError` (400); la falta de permiso es `PermissionDenied` (403).

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

Tablas: `usuarios`, `roles`, `permisos`, `rol_permisos`, `cuentas`, `transacciones`, `movimientos`. Las claves primarias son UUID.

Vista `historial_cuentas` (`CREAR_HISTORIAL` en `src/account/domain_model.py`): una fila por movimiento del lado `PRINCIPAL`, con el tipo de su transacción y el saldo acumulado de la cuenta, calculado en SQL con una función de ventana ordenada por `creado_en`. Por eso `movimientos.creado_en` toma `clock_timestamp()` y no `now()`: se asigna después de obtener el bloqueo de la cuenta, así que el orden por fecha es el orden en que se aplicaron los movimientos. Se lee con la tabla `historial_cuentas`, declarada en un `MetaData` aparte para que `create_all` no la cree como tabla.

Decisiones que cierran pendientes de §11:

- Toda cuenta lleva un `alias` obligatorio, NOSTRO y VOSTRO. Es único por titular (`UNIQUE NULLS NOT DISTINCT (titular_id, alias)`), así que también es único entre las NOSTRO.
- `usuarios.nombre` es el dato del cliente que se pide en el alta (§8.3). Es nulo en admins y operadores.
- El admin sí opera cuentas VOSTRO, por los permisos de la semilla; no hay un servicio aparte para eso.
- La consulta de saldo devuelve el historial de movimientos con el saldo tras cada uno, sin saldo global; no hay un servicio aparte ni paginación.

## Convenciones

- Indentación de 2 espacios. Comentarios, mensajes de error, claves JSON y mensajes de commit en español; los comentarios citan la sección de la especificación (`§7`, `§8.1`).
- Errores como JSON `{"error": "..."}`:
  - 400: la ruta valida los campos obligatorios y convierte en 400 los `ValueError` de los servicios.
  - 401 y 403: los servicios lanzan `AuthenticationError` o `PermissionDenied`, y los manejadores globales de `src/main/routes.py` los convierten.
- Las rutas leen el cuerpo con `json_body()`, que devuelve `{}` si no es un objeto JSON.
- Inyección de dependencias: cada servicio nuevo se registra como `Factory` en `DIContainer` y se recibe en la ruta con `Provide[DIContainer.<nombre>]` bajo `@inject`. Un módulo de rutas nuevo se agrega a `container.wire(...)` y a `register_blueprint` en `app.py`.
- Sesiones de BD: `session` es un `Factory`, cada repositorio recibe la suya. `save` y `update` hacen commit y cierran; los servicios que solo leen cierran el repositorio en un `finally` para devolver la conexión al pool.
- El repo no tiene remoto y los commits van directo a `main`.
