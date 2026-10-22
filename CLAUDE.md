# Core bancario

Core bancario mínimo en Flask + SQLAlchemy + PostgreSQL que registra cuentas y movimientos bajo partida doble, solo en MXN. La especificación completa está en `banking-core-specification.md`: define **qué** se construye. Las secciones marcadas como **Pendiente** (§11) no se implementan por suposición.

La especificación y el código están en inglés y usan los mismos nombres: rutas, claves JSON, modelo, esquema de BD, valores de los enums, servicios, comentarios y mensajes de error.

Estado actual: el módulo `user` (usuarios, RBAC, login con JWT, altas de admin y operador, desactivación, cambio de contraseña, lista de usuarios y perfil) está implementado. El módulo `account` tiene las tablas contables (§9), las aperturas de cuenta (§8.3, §8.4, §8.13) y las operaciones: depósito (fondeo), retiro, transferencia y consulta de saldo con historial de movimientos (§8.5 a §8.12), con las invariantes de §6 y el bloqueo de filas de §10, además de la lista de cuentas para operador y admin y el reverso de transacciones (§8.15).

## Comandos

```bash
make up            # construye y levanta la app (Dockerfile) y PostgreSQL 17 en http://localhost:8080 (o el puerto de PORT)
                   # y el frontend en http://localhost:5173 (o el puerto de FRONTEND_PORT)
make create-admin  # DESTRUCTIVO: borra y recrea todas las tablas, siembra roles/permisos y el primer admin (pide confirmación)
make help          # lista los demás: down, build, restart, logs, front-logs, ps, shell, psql
```

- Todo corre en `docker-compose.yml`: el servicio `app` (servidor de desarrollo de Flask con `--debug`) y `postgres` (se requiere 15+ por UNIQUE NULLS NOT DISTINCT). El directorio del proyecto se monta en `/app`, así que el servidor recarga al guardar; tras cambiar `requirements.txt` hay que reconstruir con `make build`.
- Dentro de Compose, `DATABASE_URL` se sobrescribe con el host `postgres`; `load_dotenv` no pisa variables ya definidas. El `DATABASE_URL` de `.env` (con `localhost`) solo sirve para correr fuera del contenedor.
- `create_admin.py` hace `drop_all` + `create_all`, que también borran y crean la vista `ledger_history`. Es la única forma de crear el esquema. `drop_all` solo borra las tablas del modelo actual: si se renombra una tabla o la vista, la anterior hay que borrarla a mano (con `CASCADE` si otra tabla la referencia).
- Para verificar una ruta se usa `app.test_client()`.
- Las dependencias están fijadas en `requirements.txt` y se instalan en la imagen.
- El servicio `frontend` (node:22-alpine) monta `frontend/`, corre `npm ci` y el servidor de Vite. Su `node_modules` vive en un volumen anónimo del contenedor.

## Variables de entorno

Se cargan de `.env` con `python-dotenv`. `.env` no se versiona; se crea copiando `.env.example` y ajustando los valores.

| Variable | Uso |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Contenedor de `docker-compose.yml` |
| `DATABASE_URL` | Cadena de conexión de SQLAlchemy (`postgresql+psycopg://...`) |
| `JWT_SECRET` | Clave de firma HS256 |
| `JWT_EXPIRATION_MINUTES` | Duración del access token, 20 por defecto |
| `PORT` | Puerto del host donde se publica la app, 8080 por defecto |
| `FRONTEND_PORT` | Puerto del host donde se publica el frontend, 5173 por defecto |
| `BANK_NAME` | Titular que se muestra en las cuentas NOSTRO (§7) |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Primer admin que crea `create_admin.py` |

## Estructura

La especificación (§3) propone una carpeta por capa dentro de cada módulo. El código real usa **archivos planos por módulo**, y esa es la convención a seguir:

```
Dockerfile, docker-compose.yml, Makefile
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
    ├── domain_model.py      # enums, Ledger, Account, Transaction (movimientos e invariantes), Movement, vista ledger_history y LedgerRepository
    ├── dto.py               # AccountDetail, AccountSummary, AccountBalance, AccountMovement, OperationResult, ReversalResult
    ├── application_service.py
    └── routes.py
```

- Los blueprints van en `src/<módulo>/routes.py`, no en una carpeta `api/`.
- `domain_model.py` reúne el modelo ORM y su repositorio en un solo archivo.

## Frontend

`frontend/` es un proyecto aparte de Vite + Vue 3 + Vue Router, sin librerías de UI ni de estado (versiones fijadas en `package.json`). No toca el backend: lo consume por HTTP.

```
frontend/
├── vite.config.js           # proxy /api → API_URL (http://app:8080 en compose, localhost:8080 fuera)
├── public/favicon.svg       # el logo con los colores de acento fijos, porque no lee las variables de CSS
└── src/
    ├── api.js               # fetch con el Bearer; un 401 cierra la sesión y manda al login
    ├── session.js           # token en sessionStorage; sub y role se leen de sus claims
    ├── format.js            # montos como texto, nunca Number; fechas en es-MX
    ├── router.js            # guardas: sin token → login, must_change_password → /password
    ├── App.vue, style.css   # barra superior y tokens de color claro/oscuro
    ├── components/
    │   ├── BankLogo.vue        # logo SVG de banco en currentColor, con prop size; en la barra y el login
    │   ├── TabSwitch.vue       # pestañas con v-model (prop options: valor → etiqueta)
    │   ├── LoginForm.vue       # tarjeta con logo y login (prop expired; emite logged-in)
    │   ├── PasswordForm.vue    # tarjeta de cambio de contraseña (emite changed)
    │   ├── OpenAccountForm.vue # tarjeta de alta de cliente, VOSTRO o NOSTRO (emite opened con la cuenta)
    │   ├── AccountsTable.vue   # tabla de cuentas (prop accounts)
    │   ├── MovementsTable.vue  # tabla de movimientos (props movements, canReverse; emite reverse)
    │   └── OperationPanel.vue  # depósito, retiro y transferencia (props accountId, destinations; emite applied)
    └── views/               # Login, Password, Accounts, Account (historial y operaciones), OpenAccount
```

Reparto de responsabilidades:

- Las **vistas** son las únicas que conocen la ruta: cargan los datos de la página con `api`, arman el layout (tarjetas, encabezados `h2`) y muestran los estados de carga, error y vacío.
- Los **componentes** reciben datos por props y avisan por eventos; no leen la ruta ni dibujan tarjetas, salvo los `*Form`, que son la página entera y traen su propia tarjeta con su `h1`. Las tablas y `TabSwitch` no llaman a la API. Un formulario sí aplica su propia operación (`OperationPanel` y los `*Form` llaman a `api`, validan y muestran sus mensajes) y emite el resultado para que la vista recargue o navegue; las acciones de una tabla (el reverso) las resuelve la vista.
- `style.css` guarda las clases visuales compartidas (`card`, `tabs`, tablas, `alert`, `badge`, `back`); el `<style scoped>` de cada archivo solo ajusta lo propio.

- El navegador solo habla con el origen de Vite, así que Flask no necesita CORS.
- La UI muestra todas las acciones y deja que la API responda 403, salvo el botón de reverso, que solo ve el admin (`session.role`): el token trae el rol y no los permisos. La API sigue exigiendo `REVERSE`.
- Un cliente recibe de `GET /account/` solo sus cuentas: la lista las muestra como "Your accounts" y, si tiene una sola, lo manda directo a `/account/{id}`.
- En una transferencia el destino se elige de la lista de cuentas o se escribe su id, porque un cliente solo lista las suyas.

## Rutas

| Método | Ruta | Servicio de aplicación | Auth |
|---|---|---|---|
| GET | `/` | — | no |
| GET | `/user/` | `UserLister` | `@authenticated()` |
| GET | `/user/<user_id>` | `UserProfileReader` | `@authenticated(allow_pending_password=True)` |
| POST | `/user/login` | `UserLogin` | no |
| POST | `/user/password` | `PasswordChanger` | `@authenticated(allow_pending_password=True)` |
| POST | `/user/admin` | `UserSignup` (rol `ADMIN`, §8.1) | `@authenticated()` |
| POST | `/user/operator` | `UserSignup` (rol `OPERATOR`, §8.2) | `@authenticated()` |
| POST | `/user/deactivate` | `UserDeactivator` (§8.14) | `@authenticated()` |
| GET | `/account/` | `AccountLister` | `@authenticated()` |
| POST | `/account/client` | `ClientSignup` (§8.3) | `@authenticated()` |
| POST | `/account/vostro` | `VostroAccountOpener` (§8.4) | `@authenticated()` |
| POST | `/account/nostro` | `NostroAccountOpener` (§8.13) | `@authenticated()` |
| POST | `/account/<account_id>/deposit` | `AccountFunder` (§8.5, §8.10) | `@authenticated()` |
| POST | `/account/<account_id>/withdrawal` | `AccountWithdrawer` (§8.6, §8.11) | `@authenticated()` |
| POST | `/account/<account_id>/transfer` | `AccountTransfer` (§8.7, §8.12) | `@authenticated()` |
| GET | `/account/<account_id>/balance` | `AccountBalanceReader` (§8.8, §8.9) | `@authenticated()` |
| POST | `/account/transaction/<transaction_id>/reversal` | `TransactionReverser` (§8.15) | `@authenticated()` |

`GET /` es de prueba y responde `{"message": "Hello, World!"}`.

Cuerpos y respuestas:

- `GET /user/`: devuelve `users`, la lista completa de usuarios del más antiguo al más reciente, cada uno con los campos del perfil.
- `GET /user/<user_id>`: perfil de un usuario. Devuelve `id`, `email`, `name`, `role`, `active`, `must_change_password`, `created_at` (ISO 8601); nunca el hash de la contraseña.
- `POST /user/login`: recibe `email`, `password`. Devuelve `token`, `must_change_password`.
- `POST /user/password`: recibe `current_password`, `new_password`. Devuelve `must_change_password: false`.
- `POST /user/admin` y `/user/operator`: reciben `email`, `password`. Devuelven 201 con `id`, `email`, `role`, `active`, `must_change_password`.
- `POST /user/deactivate`: recibe `email` del usuario a desactivar. Devuelve 200 con `id`, `email`, `role`, `active` (false), `must_change_password`.
- `POST /account/client`: recibe `email`, `password`, `name`, `alias`. Crea el usuario `CLIENT` y su primera cuenta VOSTRO.
- `POST /account/vostro`: recibe `email` del cliente existente y `alias`.
- `POST /account/nostro`: recibe `alias`.
- Las tres aperturas crean el ledger con sus dos cuentas (§4.2) y devuelven 201 con `id` (el del ledger), `account_class`, `alias`, `holder`, `holder_id`, `created_at`. `holder` es el nombre del cliente o, en NOSTRO, `BANK_NAME` (con `holder_id` nulo).
- `GET /account/`: devuelve `accounts`, la lista completa de cuentas NOSTRO y VOSTRO (o, para un cliente, solo las suyas) de la más antigua a la más reciente, cada una con los mismos campos que una apertura más `balance`, su saldo actual (`"0.00"` si no tiene movimientos).
- `POST /account/<account_id>/deposit` y `/withdrawal`: reciben `amount`.
- `POST /account/<account_id>/transfer`: la cuenta de la ruta es el origen; recibe `destination_account_id`, `amount`.
- Las tres operaciones devuelven 201 con `transaction_id`, `type`, `amount`, `account_id`, `destination_account_id` (nulo salvo en transferencias), `balance` (el de `account_id` después de la operación) y `created_at`.
- `GET /account/<account_id>/balance`: devuelve `account_id`, `account_class`, `alias` y `movements`, la lista completa del más antiguo al más reciente. Cada movimiento trae `movement_id`, `transaction_id`, `type`, `entry_type`, `amount`, `balance` (el de la cuenta después de ese movimiento) y `created_at`. No hay saldo global en la cabecera: el saldo actual es el del último movimiento, y una cuenta sin movimientos devuelve la lista vacía.
- `POST /account/transaction/<transaction_id>/reversal`: sin cuerpo. Devuelve 201 con `transaction_id` (la del reverso), `type` (`REVERSAL`), `original_transaction_id`, `original_type`, `amount`, `accounts` (una entrada `account_id`, `balance` por cada cuenta de la original, con su saldo después del reverso) y `created_at`.
- `amount` se acepta como texto o número JSON, mayor que cero y con máximo 2 decimales. Los montos y saldos se devuelven como texto con 2 decimales (`"100.50"`), nunca como float.

## Servicios de aplicación

Están en `src/<módulo>/application_service.py` y exponen un único método `invoke(...)`.

Módulo `user`:

| Servicio | Qué hace |
|---|---|
| `UserCreator` | Valida email único y rol existente, guarda el usuario con el hash de la contraseña. Lo usan `UserSignup` y `create_admin.py`. |
| `UserSignup` | Exige el permiso `MANAGE_USERS` y solo acepta los roles `ADMIN` y `OPERATOR`; delega en `UserCreator`. Los clientes se dan de alta con su cuenta (§8.3). |
| `UserLogin` | Verifica credenciales y usuario activo, emite el JWT. Devuelve el mismo error en todos los fallos para no revelar qué emails existen. |
| `UserAuthenticator` | Traduce el token a un `AuthenticatedUser`. Consulta al usuario en cada solicitud, así una desactivación o cambio de rol surte efecto de inmediato. Lo usa `@authenticated`. |
| `UserLister` | Exige `MANAGE_USERS`. Devuelve el `UserProfile` de todos los usuarios; `find_all` carga el rol en la misma consulta. |
| `UserProfileReader` | Devuelve el `UserProfile` de un usuario, armado con `UserProfile.of` antes de cerrar la sesión. El propio se puede ver siempre, aun con contraseña pendiente; el de otro exige `MANAGE_USERS` y la contraseña ya cambiada (`actor.must_change_password`). Rechaza id inexistente (400) solo a quien puede ver otros usuarios: a los demás les responde 403 sin buscarlo. |
| `PasswordChanger` | Cambia la contraseña y apaga `must_change_password`. |
| `UserDeactivator` | Exige `MANAGE_USERS`. Bloquea a los admins activos (`find_active_admins_for_update`) y luego al usuario, y pone `active` en false. Rechaza email inexistente, usuario ya inactivo y al único admin activo (§7). |

Módulo `account`:

| Servicio | Qué hace |
|---|---|
| `ClientSignup` | Exige `OPEN_ACCOUNT:VOSTRO`. Crea el usuario `CLIENT` y su ledger con sus dos cuentas en un solo commit: el ledger se guarda con el titular nuevo y sus cuentas en cascada. No pasa por `UserCreator`, que hace su propio commit. |
| `VostroAccountOpener` | Exige `OPEN_ACCOUNT:VOSTRO`. Rechaza email inexistente, usuario que no es `CLIENT` o inactivo, y alias repetido para ese cliente. |
| `NostroAccountOpener` | Exige `OPEN_ACCOUNT:NOSTRO`. Rechaza alias repetido entre las cuentas del banco. |
| `AccountLister` | Con `VIEW` sobre `VOSTRO` y sobre `NOSTRO` a la vez (operador y admin) devuelve todas las cuentas; con solo `VIEW` sobre `OWN` (cliente), las suyas (`find_by_holder`); sin ninguno, 403. Cada cuenta va con su titular y su saldo actual; los saldos salen de una sola consulta agrupada (`balances`, filtrada por ids en el caso del cliente), no de una por cuenta. No bloquea ni modifica nada. |
| `AccountFunder`, `AccountWithdrawer` | Bloquean la cuenta, exigen `DEPOSIT` o `WITHDRAW` sobre su alcance, arman la transacción, validan §6 y la guardan. |
| `AccountTransfer` | Bloquea ambas cuentas en orden de id. Exige `TRANSFER` solo sobre el origen; el destino solo debe existir. |
| `TransactionReverser` | Bloquea las cuentas de la transacción original y exige `REVERSE` sobre el alcance de cada una; por la semilla solo lo cumple el admin. Arma `Transaction.reversal(original)`, valida §6 y la guarda. Rechaza transacción inexistente, reverso de un reverso, transacción ya reversada y fondos insuficientes. |
| `AccountBalanceReader` | Exige `VIEW` sobre el alcance de la cuenta. Devuelve el historial de la vista `ledger_history`, con el saldo en cada movimiento. No bloquea ni modifica nada. |

Cómo se arma una operación:

- Hay **un servicio por operación**, no uno por rol. `authorize(actor, action, ledger)` calcula el alcance con `ledger.scope_for(actor.id)` (`OWN`, `VOSTRO` o `NOSTRO`) y exige el permiso `(action, scope)`. Por eso el admin, que tiene los permisos sobre `VOSTRO`, también opera cuentas de clientes.
- `parse_amount` valida el monto antes de abrir la transacción de BD.
- `Ledger.open(account_class, alias, ...)` crea el ledger con su cuenta acreedora y su cuenta deudora; las aperturas no construyen `Ledger` ni `Account` directamente.
- `Transaction.deposit`, `.withdrawal` y `.transfer` reciben los ledgers y arman los movimientos de §5 sobre sus dos cuentas (`ledger.account(Nature.X)`). `transaction.validate(ledgers, balances)` aplica las invariantes de §6 y se llama siempre antes de `save_transaction`.
- `Transaction.reversal(original)` repite los movimientos de la original con el `entry_type` opuesto y la referencia en `original_transaction_id`, que es `UNIQUE`: una transacción se reversa una sola vez. La consulta `find_reversal_of` se hace con las cuentas ya bloqueadas.
- `find_by_ids_for_update` bloquea los ledgers (`SELECT ... FOR UPDATE`, ordenado por id) y `balance` se calcula después, en la misma sesión. El bloqueo del ledger cubre sus dos cuentas, que no se mueven sin él. El reverso parte de las cuentas de los movimientos y usa `find_by_account_ids_for_update`. El bloqueo se libera con el commit de `save_transaction` o con `close`.
- Cuenta inexistente, monto inválido y fondos insuficientes son `ValueError` (400); la falta de permiso es `PermissionDenied` (403).

## Autenticación y autorización

- JWT HS256 con un solo access token, sin refresh ni lista de revocación. Claims: `sub` (id del usuario), `role`, `iat`, `exp`. Se envía como `Authorization: Bearer <token>`.
- `@authenticated()` valida el token y pasa el usuario a la vista como argumento `actor: AuthenticatedUser`. Va **encima** de `@inject`.
- Mientras `must_change_password` sea true, el usuario solo puede entrar a rutas marcadas con `allow_pending_password=True`; en las demás recibe 403.
- La autorización se hace por **permisos, nunca por rol**: `actor.has_permission(Action.X, Scope.Y)`. Un permiso es el par `(Action, Scope)`; `MANAGE_USERS` va sin alcance.
- Las contraseñas se guardan con bcrypt, que admite como máximo 72 bytes (`MAX_PASSWORD_BYTES`); se valida al crear el usuario y al cambiar la contraseña.

Semilla fija de roles (`create_admin.py`, §9):

| Rol | Permisos |
|---|---|
| `CLIENT` | VIEW, DEPOSIT, WITHDRAW, TRANSFER sobre `OWN` |
| `OPERATOR` | VIEW, DEPOSIT, WITHDRAW, TRANSFER, OPEN_ACCOUNT sobre `NOSTRO`; VIEW y OPEN_ACCOUNT sobre `VOSTRO` |
| `ADMIN` | VIEW, DEPOSIT, WITHDRAW, TRANSFER, OPEN_ACCOUNT, REVERSE sobre `VOSTRO` y `NOSTRO`; `MANAGE_USERS` |

Tablas: `users`, `roles`, `permissions`, `role_permissions`, `ledgers`, `accounts`, `transactions`, `movements`. Las claves primarias son UUID.

Vista `ledger_history` (`CREATE_LEDGER_HISTORY` en `src/account/domain_model.py`): una fila por movimiento de la cuenta acreedora de cada ledger, con el tipo de su transacción y el saldo acumulado del ledger, calculado en SQL con una función de ventana ordenada por `created_at`. Por eso `movements.created_at` toma `clock_timestamp()` y no `now()`: se asigna después de obtener el bloqueo del ledger, así que el orden por fecha es el orden en que se aplicaron los movimientos. Se lee con la tabla `ledger_history`, declarada en un `MetaData` aparte para que `create_all` no la cree como tabla.

Decisiones que cierran pendientes de §11:

- Toda cuenta lleva un `alias` obligatorio, NOSTRO y VOSTRO. Es único por titular (`UNIQUE NULLS NOT DISTINCT (holder_id, alias)`), así que también es único entre las NOSTRO.
- `users.name` es el dato del cliente que se pide en el alta (§8.3). Es nulo en admins y operadores.
- El admin sí opera cuentas VOSTRO, por los permisos de la semilla; no hay un servicio aparte para eso.
- Solo se desactivan usuarios (§8.14): no hay reactivación ni cambio de rol, esos casos de uso no aplican. Un admin puede desactivarse a sí mismo si queda otro activo, y las cuentas de un cliente desactivado se conservan.
- Un reverso es una transacción de tipo `REVERSAL` que referencia a la original (§8.15). Es total, único por transacción y no se puede reversar; si deja una cuenta en negativo se rechaza (§6). En el historial aparece como un movimiento más, con tipo `REVERSAL`.
- Lo que la API llama cuenta es un **ledger** (`ledgers`: clase, alias, titular), y `account_id` es su id. Cada ledger tiene dos filas en `accounts` (`UNIQUE (ledger_id, nature)`): la cuenta acreedora (`Nature.CREDIT`, pasivo, créditos − débitos) y la deudora (`Nature.DEBIT`, activo, débitos − créditos). Ambas tienen siempre el mismo saldo (§6.2), y el saldo del ledger es el de su cuenta acreedora. Por ahora la API solo expone ledgers; las cuentas no se consultan por separado.
- La consulta de saldo devuelve el historial de movimientos con el saldo tras cada uno, sin saldo global; no hay un servicio aparte.

## Convenciones

- Indentación de 2 espacios.
- Idioma: identificadores, rutas, claves JSON, esquema de BD, valores de enums, comentarios y mensajes de error en **inglés**. Los comentarios citan la sección de la especificación (`§7`, `§8.1`). La especificación y `README.md` también están en inglés; este archivo y los mensajes de commit siguen en español.
- Errores como JSON `{"error": "..."}`:
  - 400: la ruta valida los campos obligatorios y convierte en 400 los `ValueError` de los servicios.
  - 401 y 403: los servicios lanzan `AuthenticationError` o `PermissionDenied`, y los manejadores globales de `src/main/routes.py` los convierten.
- Las rutas leen el cuerpo con `json_body()`, que devuelve `{}` si no es un objeto JSON.
- Inyección de dependencias: cada servicio nuevo se registra como `Factory` en `DIContainer` y se recibe en la ruta con `Provide[DIContainer.<nombre>]` bajo `@inject`. Un módulo de rutas nuevo se agrega a `container.wire(...)` y a `register_blueprint` en `app.py`.
- Sesiones de BD: `session` es un `Factory`, cada repositorio recibe la suya. `save` y `update` hacen commit y cierran; los servicios que solo leen cierran el repositorio en un `finally` para devolver la conexión al pool.
- El repo no tiene remoto y los commits van directo a `main`.
