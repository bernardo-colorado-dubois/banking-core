from flask import Blueprint, jsonify, request
from dependency_injector.wiring import inject, Provide

from src.main.container import DIContainer
from src.main.middleware import authenticated
from src.main.utils import json_body
from src.user.application_service import UserSignup, UserLogin, UserProfileReader, PasswordChanger
from src.user.application_service import UserDeactivator
from src.user.dto import UserCreate, AuthenticatedUser

blueprint = Blueprint("user", __name__)

# Profile of the authenticated user. Allowed with a pending password
# so the client can read must_change_password (§7)
@blueprint.route("/")
@authenticated(allow_pending_password=True)
@inject
def profile(
  actor: AuthenticatedUser,
  user_profile_reader: UserProfileReader = Provide[DIContainer.user_profile_reader]
):
  profile = user_profile_reader.invoke(actor)
  return jsonify(
    id=str(profile.id),
    email=profile.email,
    name=profile.name,
    role=profile.role,
    active=profile.active,
    must_change_password=profile.must_change_password,
    created_at=profile.created_at.isoformat()
  )

# §7 Authentication: email and password in exchange for the access token
@blueprint.route("/login", methods=["POST"])
@inject
def login(user_login: UserLogin = Provide[DIContainer.user_login]):
  data = json_body()
  email = data.get('email')
  password = data.get('password')
  if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
    return jsonify(error='email and password are required'), 400

  token, user = user_login.invoke(email.strip(), password)
  return jsonify(token=token, must_change_password=user.must_change_password)

# Password change: the only thing allowed while must_change_password is true (§7)
@blueprint.route("/password", methods=["POST"])
@authenticated(allow_pending_password=True)
@inject
def change_password(
  actor: AuthenticatedUser,
  password_changer: PasswordChanger = Provide[DIContainer.password_changer]
):
  data = json_body()
  current_password = data.get('current_password')
  new_password = data.get('new_password')
  if not isinstance(current_password, str) or not current_password or not isinstance(new_password, str) or not new_password:
    return jsonify(error='current_password and new_password are required'), 400

  try:
    password_changer.invoke(actor, current_password, new_password)
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(must_change_password=False)

def signup(role: str, email, password, actor: AuthenticatedUser, user_signup: UserSignup):
  if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
    return jsonify(error='email and password are required'), 400

  # The DTO leaves active and must_change_password set to true (§8, signup rules)
  try:
    user = user_signup.invoke(actor, UserCreate(email=email.strip(), password=password, role=role))
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    id=str(user.id),
    email=user.email,
    role=role,
    active=user.active,
    must_change_password=user.must_change_password
  ), 201

# §8.1 Admin signup
@blueprint.route("/admin", methods=["POST"])
@authenticated()
@inject
def signup_admin(
  actor: AuthenticatedUser,
  user_signup: UserSignup = Provide[DIContainer.user_signup]
):
  data = json_body()
  email = data.get('email')
  password = data.get('password')

  return signup('ADMIN', email, password, actor, user_signup)

# §8.2 Operator signup
@blueprint.route("/operator", methods=["POST"])
@authenticated()
@inject
def signup_operator(
  actor: AuthenticatedUser,
  user_signup: UserSignup = Provide[DIContainer.user_signup]
):
  data = json_body()
  email = data.get('email')
  password = data.get('password')

  return signup('OPERATOR', email, password, actor, user_signup)

# §8.14 User deactivation
@blueprint.route("/deactivate", methods=["POST"])
@authenticated()
@inject
def deactivate(
  actor: AuthenticatedUser,
  user_deactivator: UserDeactivator = Provide[DIContainer.user_deactivator]
):
  data = json_body()
  email = data.get('email')
  if not isinstance(email, str) or not email.strip():
    return jsonify(error='email is required'), 400

  try:
    profile = user_deactivator.invoke(actor, email.strip())
  except ValueError as error:
    return jsonify(error=str(error)), 400

  return jsonify(
    id=str(profile.id),
    email=profile.email,
    role=profile.role,
    active=profile.active,
    must_change_password=profile.must_change_password
  )
