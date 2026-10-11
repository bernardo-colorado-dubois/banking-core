# Core bancario — Especificación

> Documento de especificación para implementar con Claude Code. Las secciones marcadas como **Pendiente** aún no están decididas y no deben implementarse por suposición.

## 1. Contexto

Core bancario mínimo que registra cuentas y movimientos de dinero bajo la **ley de partida doble**. Todo cambio de saldo ocurre mediante movimientos balanceados; nunca se modifica un saldo directamente.

## 2. Stack técnico

- **Lenguaje:** Python
- **Framework web:** Flask
- **ORM:** SQLAlchemy
- **Base de datos:** PostgreSQL, ejecutándose en Docker (`docker-compose`)
- **Moneda:** únicamente pesos mexicanos (MXN)

## 3. Arquitectura

Arquitectura limpia, con dependencias apuntando siempre hacia el dominio.

| Capa | Responsabilidad | Puede depender de |
|---|---|---|
| **Dominio** | Entidades, value objects, reglas contables e invariantes | Nada externo (sin Flask, sin SQLAlchemy) |
| **Aplicación** | Casos de uso (fondeo, retiro, transferencia, apertura) e interfaces de repositorios | Dominio |
| **Infraestructura** | Implementación de repositorios con SQLAlchemy, modelos ORM, sesión y transacciones de BD | Aplicación, Dominio |
| **Entrega (API)** | Rutas Flask, serialización de entrada y salida | Aplicación |

Reglas:

- El dominio no importa nada de Flask ni de SQLAlchemy.
- Los repositorios se definen como interfaces (`Protocol` o clases abstractas) en la capa de aplicación o dominio, y se implementan en infraestructura.
- Los casos de uso reciben sus dependencias por inyección.

### Estructura de carpetas

El código se organiza por módulos de negocio, y cada módulo lleva dentro sus capas:

```
docker-compose.yml        # PostgreSQL
.env.example              # variables de entorno de referencia (.env no se versiona)
app.py                    # punto de entrada: crea la app Flask desde src/main
migrations/
tests/
src/
├── main/                 # compartido: configuración, sesión de BD, JWT, manejo de errores, registro de rutas, inyección de dependencias
├── user/                 # usuarios, roles, RBAC, autenticación
│   ├── domain_model/
│   ├── application_service/
│   ├── infrastructure/
│   └── api/
└── account/              # cuentas, transacciones, movimientos y operaciones
    ├── domain_model/
    ├── application_service/
    ├── infrastructure/
    └── api/
```

| Carpeta | Capa (§3) |
|---|---|
| `domain_model/` | Dominio |
| `application_service/` | Aplicación |
| `infrastructure/` | Infraestructura |
| `api/` | Entrega |

### Base de datos local

- PostgreSQL 17 en Docker, definido en `docker-compose.yml`. Se requiere 15+ por `UNIQUE NULLS NOT DISTINCT`.
- Credenciales y configuración vienen de `.env`, a partir de `.env.example`.
- Levantar con `docker compose up -d`.

## 4. Modelo contable

### 4.1 Cuentas

Existe **un solo tipo de cuenta**. Todas tienen la misma estructura y las mismas reglas. Se distinguen únicamente por una etiqueta interna:

```python
class ClaseCuenta(Enum):
    NOSTRO = "NOSTRO"   # cuenta propia del banco
    VOSTRO = "VOSTRO"   # cuenta de cliente
```

La etiqueta **no cambia el comportamiento contable**. Solo indica si el titular es el banco o un cliente.

### 4.2 Libro fractalizado: cuenta y contrapartida

Cada cuenta es en sí misma un pequeño libro de partida doble, formado por dos lados:

- **Principal:** el saldo de la cuenta.
- **Contrapartida:** el reflejo contable de todo lo que entra y sale de esa cuenta.

Toda operación que afecta una cuenta registra un movimiento en su principal y el movimiento opuesto en su contrapartida. Así, **cada cuenta cuadra consigo misma** y puede auditarse de forma aislada, sin consultar el resto del libro.

### 4.3 Saldos

- Los saldos **no se almacenan**. Se calculan siempre a partir de los movimientos.
- Convención de signo: **saldo = créditos − débitos**.
  - Un crédito al principal aumenta el saldo de la cuenta.
  - Un débito al principal lo disminuye.
- Por construcción, el saldo de la contrapartida siempre es el opuesto del saldo del principal.

### 4.4 Movimientos

- Los movimientos son **inmutables**: nunca se editan ni se borran.
- Todo movimiento pertenece a una transacción.
- El monto de un movimiento siempre es positivo; la dirección la indica si es débito o crédito.
- Montos con `Decimal` en el dominio y `NUMERIC(18,2)` en la base de datos. Nunca `float`.

## 5. Operaciones

Cada operación es una **transacción atómica**: se registran todos sus movimientos o ninguno.

| Operación | Débito | Crédito |
|---|---|---|
| **Fondeo** a A | Contrapartida A | Principal A |
| **Retiro** de A | Principal A | Contrapartida A |
| **Transferencia** A → B | Principal A | Contrapartida A |
| | Contrapartida B | Principal B |

- **Fondeo:** entra dinero externo a la cuenta. 2 movimientos.
- **Retiro:** sale dinero de la cuenta hacia fuera del banco. 2 movimientos.
- **Transferencia:** solo entre cuentas del mismo banco. Cada lado pasa por su propia contrapartida. 4 movimientos en una sola transacción.

Las operaciones aplican igual a cuentas NOSTRO y VOSTRO.

### Tipo de transacción

Dentro del libro de una cuenta, un retiro y una transferencia saliente producen movimientos idénticos. Lo que los distingue es la transacción a la que pertenecen, por lo que toda transacción lleva un tipo:

```python
class TipoTransaccion(Enum):
    FONDEO = "FONDEO"
    RETIRO = "RETIRO"
    TRANSFERENCIA = "TRANSFERENCIA"
```

## 6. Invariantes

El dominio debe validar estas reglas **antes de persistir** cualquier transacción:

1. **Balance de la transacción:** la suma de débitos es igual a la suma de créditos.
2. **Balance por cuenta:** para cada cuenta, saldo del principal + saldo de la contrapartida = 0.
3. **Sin saldos negativos:** ninguna cuenta, NOSTRO o VOSTRO, puede quedar con saldo negativo en su principal. Retiros y transferencias sin fondos suficientes se rechazan.
   - La regla no aplica a las contrapartidas, cuyo saldo siempre es el opuesto del principal.
4. **Montos positivos:** todo movimiento tiene monto > 0.
5. **Transferencias:** la cuenta origen y la cuenta destino deben ser distintas.

## 7. Usuarios y roles

Todo usuario tiene exactamente uno de estos roles. Los roles y sus permisos son una **semilla fija** en la base de datos (ver §9, Esquema RBAC):

| Rol | Alcance |
|---|---|
| **Cliente** | Puede tener varias cuentas. Hace fondeos, retiros y transferencias, únicamente sobre sus propias cuentas. |
| **Operador** | Opera y abre cuentas NOSTRO. Abre cuentas VOSTRO y puede ver sus saldos y movimientos, pero no puede hacer operaciones sobre ellas. |
| **Admin** | Acceso total a todo el libro: cuentas NOSTRO y VOSTRO, y gestión de usuarios. |

### RBAC

La autorización se basa en **permisos**, no en roles. Los casos de uso preguntan "¿el usuario tiene este permiso?" y nunca "¿el usuario es operador?". Un rol es solo una agrupación de permisos.

Un permiso es la combinación de una **acción** y un **alcance**:

```python
class Accion(Enum):
    VER = "VER"
    FONDEAR = "FONDEAR"
    RETIRAR = "RETIRAR"
    TRANSFERIR = "TRANSFERIR"
    ABRIR_CUENTA = "ABRIR_CUENTA"
    GESTIONAR_USUARIOS = "GESTIONAR_USUARIOS"

class Alcance(Enum):
    PROPIAS = "PROPIAS"   # cuentas cuyo titular es el usuario autenticado
    VOSTRO = "VOSTRO"     # cualquier cuenta de cliente
    NOSTRO = "NOSTRO"     # cuentas del banco
```

Asignación de permisos:

| Permiso | Cliente | Operador | Admin |
|---|---|---|---|
| `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `PROPIAS` | ✓ | | |
| `VER:VOSTRO` | | ✓ | ✓ |
| `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `VOSTRO` | | | ✓ |
| `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `NOSTRO` | | ✓ | ✓ |
| `ABRIR_CUENTA:NOSTRO` | | ✓ | ✓ |
| `ABRIR_CUENTA:VOSTRO` | | ✓ | ✓ |
| `GESTIONAR_USUARIOS` | | | ✓ |

Evaluación:

1. El caso de uso determina el alcance de cada cuenta involucrada:
   - VOSTRO con `titular_id` igual al usuario autenticado → `PROPIAS`.
   - VOSTRO de otro titular → `VOSTRO`.
   - NOSTRO → `NOSTRO`.
2. Un servicio de autorización del dominio verifica si el rol del usuario incluye el permiso `(acción, alcance)`. Si no, la operación se rechaza antes de tocar el libro.
3. En una transferencia, el permiso se evalúa sobre la cuenta **origen**. La cuenta destino solo debe existir.

Reglas generales:

- La autorización se valida en la capa de aplicación (casos de uso), no solo en las rutas de Flask.
- Las cuentas NOSTRO pertenecen al banco como entidad y no tienen usuario titular. Su titular es el **nombre del banco**, que se toma de configuración (variable de entorno `BANCO_NOMBRE`) y se muestra como titular en las respuestas.
- Las cuentas VOSTRO siempre tienen un único cliente titular. Un cliente puede tener varias.

### Alta de clientes

- Los clientes no se registran solos. El operador da de alta al cliente como parte de la apertura de su cuenta VOSTRO.
- El caso de uso de apertura recibe los datos del cliente nuevo, crea el usuario con rol `CLIENTE` y abre la cuenta en **una sola transacción de BD**: se crean ambos o ninguno.
- Este alta va cubierta por `ABRIR_CUENTA:VOSTRO`. No requiere `GESTIONAR_USUARIOS` y solo permite crear usuarios con rol `CLIENTE`.
- El operador asigna una **contraseña inicial**. El usuario se crea con `debe_cambiar_password = true`.
- Mientras `debe_cambiar_password` sea `true`, el cliente puede autenticarse pero la única operación permitida es cambiar su contraseña. Al cambiarla, el flag pasa a `false`.
- El operador nunca ve ni guarda la contraseña en claro después del alta; solo se persiste el hash.

### Alta de operadores y admins

- Operadores y admins los crea un admin, con el permiso `GESTIONAR_USUARIOS`.
- Igual que con los clientes, el admin asigna una contraseña inicial y el usuario se crea con `debe_cambiar_password = true`.

### Al menos un admin

- El sistema siempre debe tener **al menos un admin activo**.
- Se rechaza cualquier operación que deje cero admins activos: desactivar al último admin o cambiarle el rol.
- La validación se hace en el caso de uso, dentro de la transacción de BD, bloqueando las filas de los admins activos (`SELECT ... FOR UPDATE`). Así, dos admins no pueden desactivarse mutuamente al mismo tiempo y dejar el sistema sin administrador.

### Primer admin

- Como ningún usuario puede crear al primer admin desde la API, se crea con un comando de consola (por ejemplo `flask crear-admin`) que se ejecuta una sola vez al instalar el sistema. A partir de ahí, los admins se crean desde la API.

### Cuentas adicionales

- Abrir una cuenta adicional sigue el mismo flujo: el operador la abre para el cliente.
- Si el cliente ya existe, no se crea un usuario nuevo. El operador identifica al cliente por su `email` (único) y la cuenta nueva se asocia a ese usuario.
- El caso de uso de apertura de cuenta VOSTRO, por tanto, acepta dos formas de entrada:
  - **Cliente nuevo:** datos del cliente + contraseña inicial → crea usuario y cuenta.
  - **Cliente existente:** email del cliente → solo crea la cuenta.
- Si se indica un email que ya existe al intentar crear un cliente nuevo, la operación se rechaza.

### Autenticación

- JWT tradicional: un solo **access token**, sin refresh tokens.
- El access token dura **20 minutos** (claim `exp`). El valor se toma de configuración, con 20 minutos como default.
- El usuario inicia sesión con email y contraseña y recibe el token. Cuando expira, vuelve a iniciar sesión.
- El token se envía en cada solicitud en el header `Authorization: Bearer <token>`.
- Firma con HS256 y una clave secreta tomada de variables de entorno, nunca escrita en el código.
- No hay lista de revocación: el cierre de sesión es del lado del cliente (descartar el token).
- El token lleva el `id` del usuario y el nombre de su rol.
- En cada solicitud se consulta el usuario en la base para verificar que siga activo y obtener su rol actual. Así, una desactivación o un cambio de rol surten efecto sin esperar a que expire el token.
- Como la matriz rol → permisos es fija, puede cargarse una vez al iniciar la aplicación y mantenerse en memoria.
- La capa de entrega traduce el token a un objeto de usuario autenticado (id, rol, permisos), que se pasa a los casos de uso para autorizar.

## 8. Servicios de aplicación

Cada servicio es un caso de uso en la capa de aplicación. Recibe el usuario autenticado, valida permisos y reglas de negocio, y ejecuta todo dentro de una sola transacción de BD.

Todos los servicios de alta comparten estas reglas:

- El `email` debe ser único; si ya existe, la operación se rechaza.
- Se asigna una contraseña inicial, se guarda solo su hash y el usuario se crea con `debe_cambiar_password = true`.
- El usuario se crea con `activo = true`.

### 8.1 Alta de administrador

| | |
|---|---|
| **Quién lo ejecuta** | Admin |
| **Permiso requerido** | `GESTIONAR_USUARIOS` |
| **Entrada** | `email`, contraseña inicial |
| **Efecto** | Crea un usuario con rol `ADMIN` |
| **Rechazos** | Sin permiso; email duplicado |

### 8.2 Alta de operador

| | |
|---|---|
| **Quién lo ejecuta** | Admin |
| **Permiso requerido** | `GESTIONAR_USUARIOS` |
| **Entrada** | `email`, contraseña inicial |
| **Efecto** | Crea un usuario con rol `OPERADOR` |
| **Rechazos** | Sin permiso; email duplicado |

### 8.3 Alta de cliente

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `ABRIR_CUENTA:VOSTRO` |
| **Entrada** | `email`, contraseña inicial, datos del cliente |
| **Efecto** | Crea un usuario con rol `CLIENTE` y su primera cuenta VOSTRO, en la misma transacción |
| **Rechazos** | Sin permiso; email duplicado |

### 8.4 Alta de cuenta

Cuenta VOSTRO adicional para un cliente que ya existe.

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `ABRIR_CUENTA:VOSTRO` |
| **Entrada** | `email` del cliente |
| **Efecto** | Crea una cuenta VOSTRO con ese cliente como titular. No crea usuario |
| **Rechazos** | Sin permiso; email inexistente; el usuario no tiene rol `CLIENTE`; el usuario está inactivo |

### Reglas comunes a las operaciones

Aplican a fondeos, retiros y transferencias (§8.5–8.7 y §8.10–8.12):

- El `monto` es un `Decimal` mayor que cero y con máximo 2 decimales.
- La cuenta (o cuentas) debe existir.
- Antes de calcular saldos se bloquean las filas de las cuentas involucradas (ver §10).
- Los movimientos se registran según la tabla de §5 y se validan las invariantes de §6 antes de persistir.
- La respuesta incluye el `id` de la transacción creada.

### 8.5 Fondeo (cliente)

| | |
|---|---|
| **Quién lo ejecuta** | Cliente |
| **Permiso requerido** | `FONDEAR:PROPIAS` |
| **Entrada** | `cuenta_id`, `monto` |
| **Efecto** | Transacción `FONDEO`: débito contrapartida, crédito principal de la cuenta |
| **Rechazos** | Sin permiso; la cuenta no es del cliente; monto inválido |

### 8.6 Retiro (cliente)

| | |
|---|---|
| **Quién lo ejecuta** | Cliente |
| **Permiso requerido** | `RETIRAR:PROPIAS` |
| **Entrada** | `cuenta_id`, `monto` |
| **Efecto** | Transacción `RETIRO`: débito principal, crédito contrapartida de la cuenta |
| **Rechazos** | Sin permiso; la cuenta no es del cliente; monto inválido; fondos insuficientes |

### 8.7 Transferencia (cliente)

| | |
|---|---|
| **Quién lo ejecuta** | Cliente |
| **Permiso requerido** | `TRANSFERIR:PROPIAS`, evaluado sobre la cuenta origen |
| **Entrada** | `cuenta_origen_id`, `cuenta_destino_id`, `monto` |
| **Efecto** | Transacción `TRANSFERENCIA` con 4 movimientos (§5) |
| **Rechazos** | Sin permiso; la cuenta origen no es del cliente; destino inexistente; origen = destino; monto inválido; fondos insuficientes |

El destino puede ser cualquier cuenta del banco, VOSTRO o NOSTRO.

### 8.8 Consulta de saldo (cliente)

| | |
|---|---|
| **Quién lo ejecuta** | Cliente |
| **Permiso requerido** | `VER:PROPIAS` |
| **Entrada** | `cuenta_id` |
| **Efecto** | Devuelve el saldo del principal, calculado a partir de los movimientos. No modifica nada |
| **Rechazos** | Sin permiso; la cuenta no es del cliente |

### 8.9 Consulta de saldo (operador)

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `VER:VOSTRO` o `VER:NOSTRO`, según la clase de la cuenta |
| **Entrada** | `cuenta_id` |
| **Efecto** | Devuelve el saldo del principal de cualquier cuenta, VOSTRO o NOSTRO. No modifica nada |
| **Rechazos** | Sin permiso; cuenta inexistente |

### 8.10 Fondeo (NOSTRO)

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `FONDEAR:NOSTRO` |
| **Entrada** | `cuenta_id`, `monto` |
| **Efecto** | Transacción `FONDEO` sobre la cuenta NOSTRO |
| **Rechazos** | Sin permiso; la cuenta no es NOSTRO; monto inválido |

### 8.11 Retiro (NOSTRO)

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `RETIRAR:NOSTRO` |
| **Entrada** | `cuenta_id`, `monto` |
| **Efecto** | Transacción `RETIRO` sobre la cuenta NOSTRO |
| **Rechazos** | Sin permiso; la cuenta no es NOSTRO; monto inválido; fondos insuficientes |

### 8.12 Transferencia (NOSTRO)

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `TRANSFERIR:NOSTRO`, evaluado sobre la cuenta origen |
| **Entrada** | `cuenta_origen_id`, `cuenta_destino_id`, `monto` |
| **Efecto** | Transacción `TRANSFERENCIA` con 4 movimientos (§5) desde una cuenta NOSTRO |
| **Rechazos** | Sin permiso; origen no es NOSTRO; destino inexistente; origen = destino; monto inválido; fondos insuficientes |

El destino puede ser cualquier cuenta del banco, NOSTRO o VOSTRO. Como el permiso se evalúa solo sobre la cuenta origen, el operador puede acreditar una cuenta VOSTRO mediante una transferencia desde NOSTRO, aunque no pueda fondear, retirar ni transferir desde ella.

### 8.13 Apertura de cuenta (NOSTRO)

| | |
|---|---|
| **Quién lo ejecuta** | Operador (o admin) |
| **Permiso requerido** | `ABRIR_CUENTA:NOSTRO` |
| **Entrada** | *Pendiente* (ver §11) |
| **Efecto** | Crea una cuenta NOSTRO, con `titular_id` nulo y saldo cero. Su titular es el nombre del banco |
| **Rechazos** | Sin permiso |

## 9. Persistencia (propuesta)

> Propuesta inicial; revisar antes de implementar.

### Esquema RBAC

Roles y permisos viven en la base de datos. Cada usuario tiene un solo rol.

Existen **exactamente tres roles**: `CLIENTE`, `OPERADOR` y `ADMIN`.

El RBAC es una **semilla fija**:

- Roles, permisos y `rol_permisos` se cargan en la migración inicial.
- No existe ningún endpoint para crear, editar o borrar roles, permisos o asignaciones.
- Cambiar la matriz de permisos requiere una nueva migración.
- Lo único que se gestiona en tiempo de ejecución es qué rol tiene cada usuario y si está activo.

**`roles`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `nombre` | texto | único: `CLIENTE`, `OPERADOR`, `ADMIN` |
| `descripcion` | texto | opcional |

**`permisos`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `accion` | enum `VER` / `FONDEAR` / `RETIRAR` / `TRANSFERIR` / `ABRIR_CUENTA` / `GESTIONAR_USUARIOS` | |
| `alcance` | enum `PROPIAS` / `VOSTRO` / `NOSTRO` | nulo solo para `GESTIONAR_USUARIOS` |

Restricciones:

- `UNIQUE NULLS NOT DISTINCT (accion, alcance)` (PostgreSQL 15+), para que no se dupliquen permisos sin alcance.
- `CHECK ((accion = 'GESTIONAR_USUARIOS' AND alcance IS NULL) OR (accion <> 'GESTIONAR_USUARIOS' AND alcance IS NOT NULL))`.
- `CHECK (accion <> 'ABRIR_CUENTA' OR alcance <> 'PROPIAS')`: abrir cuentas no aplica al alcance `PROPIAS`.

**`rol_permisos`**

| Columna | Tipo | Notas |
|---|---|---|
| `rol_id` | UUID | FK → `roles`, `ON DELETE CASCADE` |
| `permiso_id` | UUID | FK → `permisos`, `ON DELETE CASCADE` |

PK compuesta: `(rol_id, permiso_id)`.

**`usuarios`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `email` | texto | único |
| `password_hash` | texto | nunca la contraseña en claro |
| `rol_id` | UUID | FK → `roles`, obligatorio |
| `activo` | booleano | default `true`; un usuario inactivo no puede autenticarse |
| `debe_cambiar_password` | booleano | default `false`; `true` para clientes recién dados de alta |
| `creado_en` | timestamptz | |

**`cuentas`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `clase` | enum `NOSTRO` / `VOSTRO` | |
| `titular_id` | UUID | FK → `usuarios`. Obligatorio si es VOSTRO, nulo si es NOSTRO |
| `creada_en` | timestamptz | |

Restricción: `CHECK ((clase = 'VOSTRO' AND titular_id IS NOT NULL) OR (clase = 'NOSTRO' AND titular_id IS NULL))`.

El nombre del banco no se guarda en cada cuenta NOSTRO: es el mismo para todas y viene de configuración.

La regla "el titular de una cuenta VOSTRO debe tener rol `CLIENTE`" no se puede expresar con un `CHECK`; se valida en el caso de uso de apertura de cuenta.

### Datos semilla

Una migración inicial carga los roles y permisos:

| Rol | Permisos |
|---|---|
| `CLIENTE` | `VER:PROPIAS`, `FONDEAR:PROPIAS`, `RETIRAR:PROPIAS`, `TRANSFERIR:PROPIAS` |
| `OPERADOR` | `VER:NOSTRO`, `FONDEAR:NOSTRO`, `RETIRAR:NOSTRO`, `TRANSFERIR:NOSTRO`, `ABRIR_CUENTA:NOSTRO`, `VER:VOSTRO`, `ABRIR_CUENTA:VOSTRO` |
| `ADMIN` | `VER`, `FONDEAR`, `RETIRAR`, `TRANSFERIR` sobre `VOSTRO` y `NOSTRO`; `ABRIR_CUENTA:VOSTRO`, `ABRIR_CUENTA:NOSTRO`; `GESTIONAR_USUARIOS` |

El admin no necesita los permisos `PROPIAS`: no es titular de cuentas, y `VOSTRO` ya cubre cualquier cuenta de cliente.

### Esquema contable

**`transacciones`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `tipo` | enum `FONDEO` / `RETIRO` / `TRANSFERENCIA` | |
| `descripcion` | texto | opcional |
| `creada_en` | timestamptz | |

**`movimientos`**

| Columna | Tipo | Notas |
|---|---|---|
| `id` | UUID | PK |
| `transaccion_id` | UUID | FK → `transacciones` |
| `cuenta_id` | UUID | FK → `cuentas` |
| `lado` | enum `PRINCIPAL` / `CONTRAPARTIDA` | |
| `naturaleza` | enum `DEBITO` / `CREDITO` | |
| `monto` | `NUMERIC(18,2)` | `CHECK (monto > 0)` |
| `creado_en` | timestamptz | |

La contrapartida no es una fila aparte en `cuentas`; es el lado `CONTRAPARTIDA` de los movimientos de esa misma cuenta.

## 10. Concurrencia

Como el saldo se calcula a partir de movimientos, dos operaciones simultáneas sobre la misma cuenta podrían pasar la validación de fondos al mismo tiempo. Para evitarlo:

- Dentro de la transacción de BD, bloquear las filas de las cuentas involucradas con `SELECT ... FOR UPDATE` antes de calcular saldos.
- En transferencias, bloquear ambas cuentas **siempre en el mismo orden** (por `id`) para evitar deadlocks.

## 11. Pendientes

- [x] Servicios: todas las cuentas NOSTRO tienen el mismo titular (el banco). ¿Llevan un alias para distinguirlas entre sí (por ejemplo "Capital", "Comisiones")? Eso sería la entrada de §8.13 y una columna `alias` en `cuentas`.
- [x] Servicios: el admin tiene permisos para operar cuentas VOSTRO, pero no hay un servicio para eso. ¿Se agrega, o el admin no opera cuentas de clientes en la práctica?
- [x] Servicios: ¿la consulta de saldo incluye la lista de movimientos, o la consulta de movimientos es un servicio aparte?
- [x] Servicios: faltan inicio de sesión y cambio de contraseña (necesario por `debe_cambiar_password`). ¿Se agregan?
- [ ] Servicios: ¿hay servicios para desactivar usuarios o cambiarles el rol?
- [x] Endpoints de la API (rutas, payloads, respuestas, códigos de error).
- [x] Apertura de cuentas: datos requeridos del titular.
- [ ] Reversos: si se implementan como transacción de tipo propio que referencia a la original.
- [ ] Idempotencia de operaciones (por ejemplo, una clave de idempotencia por solicitud).
- [ ] Migraciones (Alembic u otra herramienta).
- [ ] Estrategia de pruebas.
