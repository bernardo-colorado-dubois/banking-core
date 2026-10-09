from flask import Blueprint

blueprint = Blueprint("account", __name__)

@blueprint.route("/")
def hello_account():
  return "<p>Hello, Account!</p>"
