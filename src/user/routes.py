from flask import Blueprint

blueprint = Blueprint("user", __name__)

@blueprint.route("/")
def hello_user():
  return "<p>Hello, User!</p>"
