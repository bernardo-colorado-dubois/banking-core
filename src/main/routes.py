from flask import Blueprint, jsonify

from src.main.errors import AuthenticationError, PermissionDenied

blueprint = Blueprint("main", __name__)

@blueprint.route("/")
def hello_world():
  return jsonify(message="Hello, World!")

# Error handling shared by every module
@blueprint.app_errorhandler(AuthenticationError)
def handle_authentication_error(error):
  return jsonify(error=str(error)), 401

@blueprint.app_errorhandler(PermissionDenied)
def handle_permission_denied(error):
  return jsonify(error=str(error)), 403
