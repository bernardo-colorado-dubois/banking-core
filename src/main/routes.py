from flask import Blueprint

blueprint = Blueprint("main", __name__)

@blueprint.route("/")
def hello_world():
  return "<p>Hello, World!</p>"
