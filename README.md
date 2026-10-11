# Core bancario

Core bancario mínimo que registra cuentas y movimientos de dinero bajo la **ley de partida doble**, solo en pesos mexicanos (MXN). Ningún saldo se guarda ni se modifica directamente: todo cambio ocurre mediante movimientos balanceados, y el saldo de una cuenta se calcula a partir de ellos.

La especificación completa está en [`especificacion-core-bancario.md`](especificacion-core-bancario.md). Las referencias `§N` de este documento apuntan a sus secciones.

## Contenido

- [Funcionalidades](#funcionalidades)
- [Stack](#stack)
- [Puesta en marcha](#puesta-en-marcha)
- [Arquitectura](#arquitectura)
- [Modelo contable](#modelo-contable)
- [Usuarios, roles y permisos](#usuarios-roles-y-permisos)
- [Endpoints](#endpoints)
- [Servicios de aplicación](#servicios-de-aplicación)
- [Modelo de datos](#modelo-de-datos)
- [Concurrencia](#concurrencia)
- [Ejemplo de punta a punta](#ejemplo-de-punta-a-punta)
- [Pendientes](#pendientes)

## Funcionalidades

- **Usuarios y acceso:** login con JWT, cambio de contraseña obligatorio en el primer ingreso, perfil del usuario autenticado y alta de administradores y operadores.
- **Control de acceso por permisos (RBAC):** tres roles fijos (`CLIENTE`, `OPERADOR`, `ADMIN`), cada uno con permisos de la forma *(acción, alcance)*.
- **Apertura de cuentas:** alta de cliente con su primera cuenta, cuentas adicionales para un cliente existente y cuentas propias del banco.
- **Operaciones:** fondeo, retiro y transferencia entre cuentas del mismo banco, cada una como una transacción atómica de partida doble.
- **Consulta de saldo e historial:** lista de movimientos de una cuenta con el saldo que dejó cada uno, calculado en SQL por una vista.
- **Invariantes contables:** validadas en el dominio antes de persistir cualquier transacción.
- **Concurrencia segura:** bloqueo de filas para que dos operaciones simultáneas no gasten el mismo saldo.

## Stack

| Componente | Tecnología |
|---|---|
| Lenguaje | Python |
| Framework web | Flask 3.1 |
| ORM | SQLAlchemy 2.1 |
| Base de datos | PostgreSQL 17 en Docker (se requiere 15+ por `UNIQUE NULLS NOT DISTINCT`) |
| Driver | psycopg 3 |
| Autenticación | PyJWT (HS256) y bcrypt |
| Inyección de dependencias | dependency-injector |
| Configuración | python-dotenv |

Las versiones exactas están fijadas en `requirements.txt`.

## Puesta en marcha

```bash
# 1. Variables de entorno
cp .env.example .env            # y ajustar los valores

# 2. Dependencias
python -m venv venv
venv/bin/pip install -r requirements.txt

# 3. Base de datos
docker compose up -d

# 4. Esquema, roles, permisos y primer admin
venv/bin/python create_admin.py

# 5. Servidor de desarrollo en http://localhost:8080
venv/bin/python app.py
```

> **`create_admin.py` es destructivo:** borra y recrea todas las tablas y la vista `historial_cuentas`. Hoy es la única forma de crear el esquema, porque todavía no hay migraciones.

### Variables de entorno

| Variable | Uso |
|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | Contenedor de `docker-compose.yml` |
| `DATABASE_URL` | Cadena de conexión de SQLAlchemy (`postgresql+psycopg://...`) |
| `JWT_SECRET` | Clave de firma HS256 |
| `JWT_EXPIRACION_MINUTOS` | Duración del access token, 20 por defecto |
| `BANCO_NOMBRE` | Titular que se muestra en las cuentas NOSTRO |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Primer admin que crea `create_admin.py` |

`.env` no se versiona.

## Arquitectura

El código se organiza por **módulos de negocio**. Cada módulo tiene cuatro archivos, uno por responsabilidad, y las dependencias apuntan hacia el dominio:

```
rutas (routes.py)  →  servicios de aplicación (application_service.py)  →  dominio y repositorios (domain_model.py)
                                    ↑
                              DTO (dto.py)
```

```
app.py                       # crea el contenedor, lo cablea y registra los blueprints
create_admin.py              # esquema + semilla RBAC + primer admin
docker-compose.yml           # PostgreSQL
src/
├── main/                    # compartido por todos los módulos
│   ├── container.py         # DIContainer: engine, sesiones, repositorios y servicios
│   ├── database.py          # Base declarativa de SQLAlchemy
│   ├── errors.py            # AuthenticationError (401), PermissionDenied (403)
│   ├── middleware.py        # decorador @authenticated
│   ├── routes.py            # GET / y manejadores de error globales
│   └── utils.py             # bcrypt, JWT, bearer_token(), json_body()
├── user/                    # usuarios, roles, permisos y autenticación
│   ├── domain_model.py
│   ├── dto.py
│   ├── application_service.py
│   └── routes.py
└── account/                 # cuentas, transacciones, movimientos y operaciones
    ├── domain_model.py
    ├── dto.py
    ├── application_service.py
    └── routes.py
```

| Archivo | Responsabilidad |
|---|---|
| `routes.py` | Blueprint de Flask. Lee y valida la forma del cuerpo, llama a un servicio y serializa la respuesta. No contiene reglas de negocio. |
| `application_service.py` | Casos de uso. Cada servicio es una clase con un único método `invoque(...)`: autoriza, coordina el dominio y el repositorio, y devuelve un DTO. |
| `domain_model.py` | Enums, modelos ORM con sus reglas (movimientos, invariantes, alcance de una cuenta) y el repositorio del módulo. |
| `dto.py` | Dataclasses que cruzan entre rutas y servicios. Ningún modelo ORM sale de un servicio. |

> La especificación (§3) propone una carpeta por capa dentro de cada módulo. El código usa archivos planos por módulo, con el modelo ORM y su repositorio juntos en `domain_model.py`.

### Inyección de dependencias

`DIContainer` (`src/main/container.py`) declara el engine como `Singleton` y las sesiones, repositorios y servicios como `Factory`. Cada repositorio recibe su propia sesión. Las rutas reciben el servicio que necesitan:

```python
@blueprint.route("/<uuid:cuenta_id>/fondeo", methods=["POST"])
@authenticated()
@inject
def fund(
  cuenta_id: UUID,
  actor: AuthenticatedUser,
  account_funder: AccountFunder = Provide[DIContainer.account_funder]
):
  ...
```

### Ciclo de una solicitud

1. `@authenticated()` toma el token del header `Authorization`, lo valida con `UserAuthenticator` y pasa el usuario a la ruta como `actor`.
2. La ruta lee el cuerpo con `json_body()` y revisa que estén los campos obligatorios.
3. El servicio de aplicación exige el permiso, ejecuta el caso de uso y devuelve un DTO.
4. La ruta convierte el DTO a JSON.

### Errores

Todos los errores se devuelven como `{"error": "..."}`.

| Código | Cuándo | Dónde se produce |
|---|---|---|
| 400 | Falta un campo, monto inválido, cuenta inexistente, fondos insuficientes, alias o email repetido | La ruta valida los campos y convierte los `ValueError` de los servicios |
| 401 | Token ausente, inválido o expirado; credenciales incorrectas | `AuthenticationError`, manejador global |
| 403 | Falta el permiso, o el usuario aún debe cambiar su contraseña | `PermissionDenied`, manejador global |

## Modelo contable

### Cuentas

Existe **un solo tipo de cuenta**, con las mismas reglas para todas. Solo las distingue una etiqueta:

| Clase | Qué es | Titular |
|---|---|---|
| `VOSTRO` | Cuenta de un cliente | El usuario cliente |
| `NOSTRO` | Cuenta propia del banco | El banco (`BANCO_NOMBRE`), sin usuario titular |

Toda cuenta lleva un `alias` obligatorio, único por titular. Como las NOSTRO comparten titular, el alias también es único entre ellas.

### Principal y contrapartida

Cada cuenta tiene dos lados en el libro: el **principal**, que es el saldo que ve el titular, y la **contrapartida**, que representa el exterior de la cuenta. La contrapartida no es otra fila en `cuentas`: es el lado `CONTRAPARTIDA` de los movimientos de esa misma cuenta, y su saldo siempre es el opuesto del principal.

```
saldo = créditos − débitos del lado PRINCIPAL
```

### Operaciones

Cada operación es una transacción atómica: se registran todos sus movimientos o ninguno.

| Operación | Débito | Crédito | Movimientos |
|---|---|---|---|
| **Fondeo** a A | Contrapartida A | Principal A | 2 |
| **Retiro** de A | Principal A | Contrapartida A | 2 |
| **Transferencia** A → B | Principal A | Contrapartida A | 4 |
| | Contrapartida B | Principal B | |

Un retiro y una transferencia saliente dejan movimientos idénticos en el libro de la cuenta; los distingue el `tipo` de la transacción (`FONDEO`, `RETIRO`, `TRANSFERENCIA`).

Los movimientos son **inmutables**: nunca se editan ni se borran. Su monto siempre es positivo; la dirección la da la naturaleza (`DEBITO` o `CREDITO`).

### Invariantes

`Transaction.validar(saldos)` las aplica antes de guardar cualquier transacción (§6):

1. **Balance de la transacción:** la suma de débitos es igual a la suma de créditos.
2. **Balance por cuenta:** en cada cuenta, principal + contrapartida = 0.
3. **Sin saldos negativos:** ningún principal queda negativo. Los retiros y transferencias sin fondos se rechazan.
4. **Montos positivos:** todo movimiento tiene monto mayor que cero.
5. **Transferencias:** el origen y el destino son cuentas distintas.

### Montos

Se manejan con `Decimal` en el código y `NUMERIC(18,2)` en la base, nunca con `float`. La API los acepta como texto o número JSON, mayores que cero y con máximo 2 decimales, y los devuelve siempre como texto con 2 decimales (`"100.50"`).

## Usuarios, roles y permisos

### Autenticación

- JWT HS256 con un solo access token, sin refresh ni lista de revocación. Claims: `sub` (id del usuario), `rol`, `iat`, `exp`.
- Se envía como `Authorization: Bearer <token>`.
- El usuario se consulta en cada solicitud, así que una desactivación o un cambio de rol surten efecto de inmediato, sin esperar a que expire el token.
- Las contraseñas se guardan con bcrypt y admiten como máximo 72 bytes.
- Todo usuario nuevo nace con `debe_cambiar_password: true`. Mientras siga así, solo puede consultar su perfil y cambiar su contraseña; el resto de las rutas responde 403.
- El login devuelve el mismo error en todos los fallos, para no revelar qué emails existen.

### Autorización

La autorización se hace **por permisos, nunca por rol**. Un permiso es el par *(acción, alcance)*:

| Acciones | `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR`, `ABRIR_CUENTA`, `GESTIONAR_USUARIOS` |
|---|---|
| **Alcances** | `PROPIAS` (cuentas del usuario autenticado), `VOSTRO` (cualquier cuenta de cliente), `NOSTRO` (cuentas del banco) |

`GESTIONAR_USUARIOS` no lleva alcance.

Para operar una cuenta, el servicio calcula el alcance de esa cuenta frente al usuario (`Account.alcance_para`) y exige el permiso correspondiente:

| Cuenta | Alcance |
|---|---|
| NOSTRO | `NOSTRO` |
| VOSTRO cuyo titular es el usuario autenticado | `PROPIAS` |
| VOSTRO de otro titular | `VOSTRO` |

### Roles

Los roles y sus permisos son una semilla fija que crea `create_admin.py`:

| Permiso | Cliente | Operador | Admin |
|---|:-:|:-:|:-:|
| `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `PROPIAS` | ✓ | | |
| `VER` sobre `VOSTRO` | | ✓ | ✓ |
| `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `VOSTRO` | | | ✓ |
| `ABRIR_CUENTA` sobre `VOSTRO` | | ✓ | ✓ |
| `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `NOSTRO` | | ✓ | ✓ |
| `ABRIR_CUENTA` sobre `NOSTRO` | | ✓ | ✓ |
| `GESTIONAR_USUARIOS` | | | ✓ |

En una transferencia el permiso se evalúa solo sobre la cuenta **origen**; el destino solo debe existir. Por eso el operador puede acreditar una cuenta de cliente transfiriendo desde una NOSTRO, aunque no pueda fondearla ni retirar de ella.

## Endpoints

Todas las rutas reciben y devuelven JSON. Salvo las marcadas, requieren `Authorization: Bearer <token>`.

### Usuarios

| Método | Ruta | Qué hace | Permiso |
|---|---|---|---|
| POST | `/user/login` | Inicia sesión | Sin token |
| GET | `/user/` | Perfil del usuario autenticado | Cualquier usuario¹ |
| POST | `/user/password` | Cambia la contraseña | Cualquier usuario¹ |
| POST | `/user/admin` | Alta de administrador (§8.1) | `GESTIONAR_USUARIOS` |
| POST | `/user/operador` | Alta de operador (§8.2) | `GESTIONAR_USUARIOS` |

¹ Disponibles aunque el usuario tenga pendiente el cambio de contraseña.

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /user/login` | `email`, `password` | 200: `token`, `debe_cambiar_password` |
| `GET /user/` | — | 200: `id`, `email`, `nombre`, `rol`, `activo`, `debe_cambiar_password`, `creado_en` |
| `POST /user/password` | `password_actual`, `password_nueva` | 200: `debe_cambiar_password: false` |
| `POST /user/admin`, `/user/operador` | `email`, `password` | 201: `id`, `email`, `rol`, `activo`, `debe_cambiar_password` |

### Cuentas

| Método | Ruta | Qué hace | Permiso |
|---|---|---|---|
| GET | `/account/` | Lista de todas las cuentas, NOSTRO y VOSTRO, con su titular y su saldo actual | `VER:VOSTRO` y `VER:NOSTRO` |
| POST | `/account/cliente` | Alta de cliente con su primera cuenta VOSTRO (§8.3) | `ABRIR_CUENTA:VOSTRO` |
| POST | `/account/vostro` | Cuenta VOSTRO adicional para un cliente existente (§8.4) | `ABRIR_CUENTA:VOSTRO` |
| POST | `/account/nostro` | Cuenta NOSTRO (§8.13) | `ABRIR_CUENTA:NOSTRO` |
| POST | `/account/<cuenta_id>/fondeo` | Fondeo (§8.5, §8.10) | `FONDEAR` sobre el alcance de la cuenta |
| POST | `/account/<cuenta_id>/retiro` | Retiro (§8.6, §8.11) | `RETIRAR` sobre el alcance de la cuenta |
| POST | `/account/<cuenta_id>/transferencia` | Transferencia; la cuenta de la ruta es el origen (§8.7, §8.12) | `TRANSFERIR` sobre el alcance del origen |
| GET | `/account/<cuenta_id>/saldo` | Historial de movimientos con saldo (§8.8, §8.9) | `VER` sobre el alcance de la cuenta |

| Ruta | Cuerpo |
|---|---|
| `POST /account/cliente` | `email`, `password`, `nombre`, `alias` |
| `POST /account/vostro` | `email` (del cliente), `alias` |
| `POST /account/nostro` | `alias` |
| `POST /account/<cuenta_id>/fondeo`, `/retiro` | `monto` |
| `POST /account/<cuenta_id>/transferencia` | `cuenta_destino_id`, `monto` |

**Aperturas** — responden 201:

```json
{
  "id": "5f0c…",
  "clase": "VOSTRO",
  "alias": "Ahorro",
  "titular": "Juan Pérez",
  "titular_id": "9a31…",
  "creada_en": "2026-10-10T12:45:24.680332-06:00"
}
```

En una cuenta NOSTRO, `titular` es el nombre del banco y `titular_id` es nulo.

**Operaciones** — responden 201:

```json
{
  "transaccion_id": "0115…",
  "tipo": "TRANSFERENCIA",
  "monto": "100.00",
  "cuenta_id": "5f0c…",
  "cuenta_destino_id": "76a4…",
  "saldo": "649.50",
  "creada_en": "2026-10-10T12:45:24.705659-06:00"
}
```

`saldo` es el de `cuenta_id` después de la operación. `cuenta_destino_id` es nulo salvo en transferencias.

**Saldo e historial** — responde 200:

```json
{
  "cuenta_id": "5f0c…",
  "clase": "VOSTRO",
  "alias": "Ahorro",
  "movimientos": [
    {
      "movimiento_id": "19d5…",
      "transaccion_id": "9c45…",
      "tipo": "FONDEO",
      "naturaleza": "CREDITO",
      "monto": "1000.00",
      "saldo": "1000.00",
      "creado_en": "2026-10-10T12:45:24.680332-06:00"
    },
    {
      "movimiento_id": "e96a…",
      "transaccion_id": "ddc3…",
      "tipo": "RETIRO",
      "naturaleza": "DEBITO",
      "monto": "250.50",
      "saldo": "749.50",
      "creado_en": "2026-10-10T12:45:24.696163-06:00"
    }
  ]
}
```

Los movimientos van del más antiguo al más reciente, completos y sin paginación. No hay un saldo global en la cabecera: el saldo actual es el del último movimiento, y una cuenta sin movimientos devuelve la lista vacía (saldo cero).

`GET /account/` responde 200 con `{"cuentas": [...]}`, de la más antigua a la más reciente y sin paginación. Cada cuenta trae los mismos campos que una apertura (`id`, `clase`, `alias`, `titular`, `titular_id` y `creada_en`) más `saldo`, su saldo actual como texto con 2 decimales (`"0.00"` si no tiene movimientos). Exige `VER` sobre `VOSTRO` y sobre `NOSTRO`, así que solo la ven el operador y el admin; un cliente recibe 403.

`GET /` es una ruta de prueba, sin token, que responde `{"mensaje": "Hello, World!"}`.

## Servicios de aplicación

Cada servicio es una clase con un único método `invoque(...)`, registrada como `Factory` en `DIContainer`.

### Módulo `user`

| Servicio | Qué hace |
|---|---|
| `UserCreator` | Valida email único y rol existente, y guarda el usuario con el hash de su contraseña. Lo usan `UserSignup` y `create_admin.py`. |
| `UserSignup` | Exige `GESTIONAR_USUARIOS` y solo acepta los roles `ADMIN` y `OPERADOR`. Los clientes se dan de alta junto con su cuenta. |
| `UserLogin` | Verifica credenciales y que el usuario esté activo, y emite el JWT. |
| `UserAuthenticator` | Traduce el token a un `AuthenticatedUser` con su id, rol y permisos. Lo usa `@authenticated`. |
| `UserProfileReader` | Devuelve el perfil del usuario autenticado, sin el hash de la contraseña. |
| `PasswordChanger` | Cambia la contraseña y apaga `debe_cambiar_password`. |

### Módulo `account`

| Servicio | Qué hace |
|---|---|
| `ClientSignup` | Crea el usuario `CLIENTE` y su primera cuenta en un solo commit: se crean ambos o ninguno. |
| `VostroAccountOpener` | Abre otra cuenta a un cliente. Rechaza email inexistente, usuario que no es cliente o está inactivo, y alias repetido para ese cliente. |
| `NostroAccountOpener` | Abre una cuenta del banco. Rechaza alias repetido entre las NOSTRO. |
| `AccountLister` | Exige `VER` sobre `VOSTRO` y sobre `NOSTRO` y devuelve todas las cuentas con su titular y su saldo actual. No bloquea ni modifica nada. |
| `AccountFunder` | Fondeo: bloquea la cuenta, exige `FONDEAR`, arma la transacción, la valida y la guarda. |
| `AccountWithdrawer` | Retiro: igual que el fondeo, con `RETIRAR`. Sin fondos suficientes, la validación lo rechaza. |
| `AccountTransfer` | Transferencia: bloquea ambas cuentas en orden de id y exige `TRANSFERIR` solo sobre el origen. |
| `AccountBalanceReader` | Exige `VER` y devuelve el historial de la vista `historial_cuentas`. No bloquea ni modifica nada. |

Hay **un servicio por operación**, no uno por rol: el mismo `AccountFunder` atiende al cliente que fondea su cuenta y al admin que fondea la de un cliente o una del banco. La diferencia la resuelve `autorizar(actor, accion, account)` con el alcance de la cuenta.

Así se arma una operación:

```python
monto = parse_monto(monto)                                  # valida antes de abrir la transacción de BD
cuentas = repository.find_by_ids_for_update([cuenta_id])    # SELECT ... FOR UPDATE
autorizar(actor, Accion.FONDEAR, account)                   # permiso (acción, alcance)
saldo = repository.balance(account.id)                      # créditos − débitos del principal
transaction = Transaction.fondeo(account.id, monto)         # arma los movimientos
transaction.validar({account.id: saldo})                    # invariantes
repository.save_transaction(transaction)                    # un solo commit, libera el bloqueo
```

## Modelo de datos

Las claves primarias son UUID y las fechas son `timestamptz`.

```
roles ──< rol_permisos >── permisos
  │
  └──< usuarios ──< cuentas ──< movimientos >── transacciones
```

### RBAC

| Tabla | Columnas | Restricciones |
|---|---|---|
| `roles` | `id`, `nombre`, `descripcion` | `nombre` único |
| `permisos` | `id`, `accion`, `alcance` | Par `(accion, alcance)` único. `alcance` es nulo solo en `GESTIONAR_USUARIOS`. `ABRIR_CUENTA` no admite `PROPIAS` |
| `rol_permisos` | `rol_id`, `permiso_id` | PK compuesta |
| `usuarios` | `id`, `email`, `nombre`, `password_hash`, `rol_id`, `activo`, `debe_cambiar_password`, `creado_en` | `email` único. `nombre` solo lo llevan los clientes |

### Contabilidad

| Tabla | Columnas | Restricciones |
|---|---|---|
| `cuentas` | `id`, `clase`, `alias`, `titular_id`, `creada_en` | VOSTRO exige titular y NOSTRO lo prohíbe. `UNIQUE NULLS NOT DISTINCT (titular_id, alias)` |
| `transacciones` | `id`, `tipo`, `descripcion`, `creada_en` | |
| `movimientos` | `id`, `transaccion_id`, `cuenta_id`, `lado`, `naturaleza`, `monto`, `creado_en` | `monto > 0`. `creado_en` toma `clock_timestamp()` |

No existe una columna de saldo en ninguna tabla.

### Vista `historial_cuentas`

Tiene una fila por cada movimiento del lado `PRINCIPAL`, con el tipo de su transacción y el saldo acumulado de la cuenta, calculado con una función de ventana:

```sql
CREATE OR REPLACE VIEW historial_cuentas AS
SELECT
  m.id AS movimiento_id,
  m.cuenta_id,
  m.transaccion_id,
  t.tipo,
  m.naturaleza,
  m.monto,
  SUM(CASE WHEN m.naturaleza = 'CREDITO' THEN m.monto ELSE -m.monto END)
    OVER (PARTITION BY m.cuenta_id ORDER BY m.creado_en, m.id) AS saldo,
  m.creado_en
FROM movimientos m
JOIN transacciones t ON t.id = m.transaccion_id
WHERE m.lado = 'PRINCIPAL'
```

Está definida en `src/account/domain_model.py` y se crea y se borra junto con las tablas. También se puede consultar directamente desde SQL:

```sql
SELECT tipo, naturaleza, monto, saldo, creado_en
FROM historial_cuentas
WHERE cuenta_id = '<cuenta_id>'
ORDER BY creado_en, movimiento_id;
```

## Concurrencia

Como el saldo se calcula a partir de los movimientos, dos operaciones simultáneas sobre la misma cuenta podrían pasar la validación de fondos al mismo tiempo. Para evitarlo (§10):

- Cada operación bloquea las filas de las cuentas involucradas con `SELECT ... FOR UPDATE` **antes** de calcular saldos. El bloqueo se libera con el commit.
- Una transferencia bloquea ambas cuentas siempre en el mismo orden, por `id`, para evitar deadlocks.
- `movimientos.creado_en` usa `clock_timestamp()` y no `now()`. `now()` es la hora en que empezó la transacción de BD, antes de obtener el bloqueo; con la hora real de inserción, el orden por fecha del historial es el orden en que se aplicaron los movimientos.

La consulta de saldo no bloquea nada.

## Ejemplo de punta a punta

Con el servidor corriendo y [`jq`](https://jqlang.github.io/jq/) instalado:

```bash
BASE=http://localhost:8080

# Login del admin y cambio de la contraseña inicial
TOKEN=$(curl -s -X POST $BASE/user/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"PASSWORD_INICIAL"}' | jq -r .token)

curl -s -X POST $BASE/user/password \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"password_actual":"PASSWORD_INICIAL","password_nueva":"PASSWORD_NUEVA"}'

# Dos clientes, cada uno con su cuenta
A=$(curl -s -X POST $BASE/account/cliente \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"juan@example.com","password":"inicial123","nombre":"Juan Pérez","alias":"Ahorro"}' | jq -r .id)

B=$(curl -s -X POST $BASE/account/cliente \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"email":"maria@example.com","password":"inicial123","nombre":"María López","alias":"Ahorro"}' | jq -r .id)

# Fondeo de la primera y transferencia a la segunda
curl -s -X POST $BASE/account/$A/fondeo \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"monto":"500.00"}'

curl -s -X POST $BASE/account/$A/transferencia \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d "{\"cuenta_destino_id\":\"$B\",\"monto\":\"100.00\"}"

# Historial de cada cuenta: 400.00 en la primera, 100.00 en la segunda
curl -s $BASE/account/$A/saldo -H "Authorization: Bearer $TOKEN"
curl -s $BASE/account/$B/saldo -H "Authorization: Bearer $TOKEN"
```

## Pendientes

Siguen abiertos en §11 de la especificación y no están implementados:

- Reversos de transacciones.
- Idempotencia de operaciones (clave de idempotencia por solicitud).
- Migraciones: `migrations/` está vacío y el esquema se crea con `create_admin.py`.
- Pruebas automatizadas: `tests/` está vacío. Para verificar una ruta se usa `app.test_client()`.
- Servicios para desactivar usuarios o cambiarles el rol.
- Paginación del historial de movimientos.
