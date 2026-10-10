from flask import Blueprint, jsonify

blueprint = Blueprint("account", __name__)

@blueprint.route("/")
def hello_account():
  return jsonify(mensaje="Hello, Account!")
