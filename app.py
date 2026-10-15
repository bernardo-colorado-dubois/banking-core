from flask import Flask
from src.main.container import DIContainer
from dotenv import load_dotenv
import os

# Import routes
import src.main.routes as main_routes
import src.main.middleware as main_middleware
import src.user.routes as user_routes
import src.account.routes as account_routes

# Always load environment variables
load_dotenv()

# Read environment variables
database_url = os.getenv("DATABASE_URL")
jwt_secret = os.getenv("JWT_SECRET")
jwt_expiration_minutes = int(os.getenv("JWT_EXPIRATION_MINUTES", "20"))
bank_name = os.getenv("BANK_NAME")
port = int(os.getenv("PORT", "8080"))

# Initialize the container
container = DIContainer()
container.config.connection_string.override(database_url)
container.config.jwt_secret.override(jwt_secret)
container.config.jwt_expiration_minutes.override(jwt_expiration_minutes)
container.config.bank_name.override(bank_name)

# Wire before creating the app
container.wire(modules=[
  main_routes
  ,main_middleware
  ,user_routes
  ,account_routes
])

# Create the application
app = Flask(__name__)
app.register_blueprint(main_routes.blueprint, url_prefix='/')
app.register_blueprint(user_routes.blueprint, url_prefix='/user')
app.register_blueprint(account_routes.blueprint, url_prefix='/account')

# Only run the server when called directly
if __name__ == "__main__":
  app.run(debug=True,port=port)
