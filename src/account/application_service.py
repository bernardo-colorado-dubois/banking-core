from decimal import Decimal, InvalidOperation
from uuid import UUID

from src.account.domain_model import Account, AccountRepository, ClaseCuenta, Transaction
from src.account.dto import AccountDetail, AccountBalance, AccountMovement, OperationResult
from src.user.domain_model import User, UserRepository, RoleRepository, Accion, Alcance
from src.user.dto import UserCreate, AuthenticatedUser
from src.main.errors import PermissionDenied
from src.main.utils import hash_password

class ClientSignup:
  """Alta de cliente con su primera cuenta VOSTRO (§8.3)."""

  def __init__(self,repository:AccountRepository,user_repository:UserRepository,role_repository:RoleRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository
    self.role_repository = role_repository

  def invoque(self,actor:AuthenticatedUser,dto:UserCreate,alias:str)->AccountDetail:
    # No requiere GESTIONAR_USUARIOS: el alta va cubierta por ABRIR_CUENTA:VOSTRO (§7)
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.VOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas de clientes')

    try:
      if self.user_repository.find_by_email(dto.email) is not None:
        raise ValueError(f'Ya existe un usuario con el email {dto.email}')

      rol = self.role_repository.find_by_name('CLIENTE')
      if rol is None:
        raise ValueError('No existe el rol CLIENTE')

      # Solo se persiste el hash, nunca la contraseña en claro
      user = User(
        email=dto.email,
        nombre=dto.nombre,
        password_hash=hash_password(dto.password),
        rol_id=rol.id,
        activo=dto.activo,
        debe_cambiar_password=dto.debe_cambiar_password
      )
      # Usuario y cuenta van en un solo commit: se crean ambos o ninguno
      account = Account(clase=ClaseCuenta.VOSTRO, alias=alias, titular=user)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=user.nombre,
        titular_id=user.id,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()
      self.user_repository.close()
      self.role_repository.close()

class VostroAccountOpener:
  """Cuenta VOSTRO adicional para un cliente que ya existe (§8.4)."""

  def __init__(self,repository:AccountRepository,user_repository:UserRepository) -> None:
    self.repository = repository
    self.user_repository = user_repository

  def invoque(self,actor:AuthenticatedUser,email:str,alias:str)->AccountDetail:
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.VOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas de clientes')

    try:
      user = self.user_repository.find_by_email(email)
      if user is None:
        raise ValueError(f'No existe un usuario con el email {email}')

      # No se puede expresar con un CHECK: se valida aquí (§9)
      if user.rol.nombre != 'CLIENTE':
        raise ValueError(f'El usuario {email} no es un cliente')

      if not user.activo:
        raise ValueError(f'El usuario {email} está inactivo')

      if self.repository.find_by_titular_and_alias(user.id, alias) is not None:
        raise ValueError(f'El cliente ya tiene una cuenta con el alias {alias}')

      account = Account(clase=ClaseCuenta.VOSTRO, alias=alias, titular_id=user.id)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=user.nombre,
        titular_id=user.id,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()
      self.user_repository.close()

class NostroAccountOpener:
  """Apertura de cuenta NOSTRO (§8.13)."""

  def __init__(self,repository:AccountRepository,banco_nombre:str) -> None:
    self.repository = repository
    self.banco_nombre = banco_nombre

  def invoque(self,actor:AuthenticatedUser,alias:str)->AccountDetail:
    if not actor.tiene_permiso(Accion.ABRIR_CUENTA, Alcance.NOSTRO):
      raise PermissionDenied('No tiene permiso para abrir cuentas del banco')

    try:
      if self.repository.find_by_titular_and_alias(None, alias) is not None:
        raise ValueError(f'Ya existe una cuenta del banco con el alias {alias}')

      # Sin usuario titular: el titular es el nombre del banco (§7)
      account = Account(clase=ClaseCuenta.NOSTRO, alias=alias, titular_id=None)
      self.repository.save(account)

      return AccountDetail(
        id=account.id,
        clase=account.clase,
        alias=account.alias,
        titular=self.banco_nombre,
        titular_id=None,
        creada_en=account.creada_en
      )
    finally:
      self.repository.close()

# NUMERIC(18,2): hasta 16 dígitos enteros
MONTO_MAXIMO = Decimal('9999999999999999.99')

def parse_monto(valor)->Decimal:
  """Reglas comunes a las operaciones (§8): Decimal mayor que cero y con máximo 2 decimales."""
  # Nunca float (§4.4): un número JSON se convierte desde su texto, no desde su valor binario
  if isinstance(valor, bool) or not isinstance(valor, (str, int, float)):
    raise ValueError('El monto no es válido')
  try:
    monto = Decimal(str(valor).strip())
  except InvalidOperation:
    raise ValueError('El monto no es válido')

  if not monto.is_finite():
    raise ValueError('El monto no es válido')
  if monto <= 0:
    raise ValueError('El monto debe ser mayor que cero')
  if monto != monto.quantize(Decimal('0.01')):
    raise ValueError('El monto admite máximo 2 decimales')
  if monto > MONTO_MAXIMO:
    raise ValueError('El monto excede el máximo permitido')
  return monto.quantize(Decimal('0.01'))

def autorizar(actor:AuthenticatedUser,accion:Accion,account:Account)->None:
  """Exige el permiso (acción, alcance) según el alcance de la cuenta frente al actor (§7)."""
  if not actor.tiene_permiso(accion, account.alcance_para(actor.id)):
    raise PermissionDenied('No tiene permiso para esta operación sobre la cuenta')

class AccountFunder:
  """Fondeo (§8.5 y §8.10): entra dinero externo a la cuenta."""

  def __init__(self,repository:AccountRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser,cuenta_id:UUID,monto)->OperationResult:
    monto = parse_monto(monto)
    try:
      # Se bloquea la cuenta antes de calcular su saldo (§10)
      cuentas = self.repository.find_by_ids_for_update([cuenta_id])
      if not cuentas:
        raise ValueError('No existe la cuenta')
      account = cuentas[0]
      autorizar(actor, Accion.FONDEAR, account)

      saldo = self.repository.balance(account.id)
      transaction = Transaction.fondeo(account.id, monto)
      transaction.validar({account.id: saldo})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaccion_id=transaction.id,
        tipo=transaction.tipo,
        monto=monto,
        cuenta_id=account.id,
        cuenta_destino_id=None,
        saldo=saldo + monto,
        creada_en=transaction.creada_en
      )
    finally:
      self.repository.close()

class AccountWithdrawer:
  """Retiro (§8.6 y §8.11): sale dinero de la cuenta hacia fuera del banco."""

  def __init__(self,repository:AccountRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser,cuenta_id:UUID,monto)->OperationResult:
    monto = parse_monto(monto)
    try:
      cuentas = self.repository.find_by_ids_for_update([cuenta_id])
      if not cuentas:
        raise ValueError('No existe la cuenta')
      account = cuentas[0]
      autorizar(actor, Accion.RETIRAR, account)

      # Sin fondos suficientes, validar rechaza el retiro (§6)
      saldo = self.repository.balance(account.id)
      transaction = Transaction.retiro(account.id, monto)
      transaction.validar({account.id: saldo})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaccion_id=transaction.id,
        tipo=transaction.tipo,
        monto=monto,
        cuenta_id=account.id,
        cuenta_destino_id=None,
        saldo=saldo - monto,
        creada_en=transaction.creada_en
      )
    finally:
      self.repository.close()

class AccountTransfer:
  """Transferencia entre cuentas del mismo banco (§8.7 y §8.12)."""

  def __init__(self,repository:AccountRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser,origen_id:UUID,destino_id:UUID,monto)->OperationResult:
    monto = parse_monto(monto)
    if origen_id == destino_id:
      raise ValueError('La cuenta origen y la cuenta destino deben ser distintas')

    try:
      # Ambas cuentas se bloquean siempre en el mismo orden, por id (§10)
      cuentas = {account.id: account for account in self.repository.find_by_ids_for_update([origen_id, destino_id])}
      origen = cuentas.get(origen_id)
      if origen is None:
        raise ValueError('No existe la cuenta origen')

      # El permiso se evalúa sobre la cuenta origen; el destino solo debe existir (§7)
      autorizar(actor, Accion.TRANSFERIR, origen)
      destino = cuentas.get(destino_id)
      if destino is None:
        raise ValueError('No existe la cuenta destino')

      saldo = self.repository.balance(origen.id)
      transaction = Transaction.transferencia(origen.id, destino.id, monto)
      transaction.validar({origen.id: saldo, destino.id: self.repository.balance(destino.id)})
      self.repository.save_transaction(transaction)

      return OperationResult(
        transaccion_id=transaction.id,
        tipo=transaction.tipo,
        monto=monto,
        cuenta_id=origen.id,
        cuenta_destino_id=destino.id,
        saldo=saldo - monto,
        creada_en=transaction.creada_en
      )
    finally:
      self.repository.close()

class AccountBalanceReader:
  """Consulta de saldo con su historial de movimientos (§8.8 y §8.9). No modifica nada."""

  def __init__(self,repository:AccountRepository) -> None:
    self.repository = repository

  def invoque(self,actor:AuthenticatedUser,cuenta_id:UUID)->AccountBalance:
    try:
      account = self.repository.find_by_id(cuenta_id)
      if account is None:
        raise ValueError('No existe la cuenta')
      autorizar(actor, Accion.VER, account)

      movimientos = [
        AccountMovement(
          movimiento_id=fila.movimiento_id,
          transaccion_id=fila.transaccion_id,
          tipo=fila.tipo,
          naturaleza=fila.naturaleza,
          monto=fila.monto,
          saldo=fila.saldo,
          creado_en=fila.creado_en
        )
        for fila in self.repository.history(account.id)
      ]
      return AccountBalance(
        cuenta_id=account.id,
        clase=account.clase,
        alias=account.alias,
        movimientos=movimientos
      )
    finally:
      self.repository.close()
