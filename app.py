from flask import Flask
from src.main.container import DIContainer
from dotenv import load_dotenv
import os

# Importar rutas
import src.main.routes as main_routes
import src.user.routes as user_routes
import src.account.routes as account_routes

# Cargar variables de entorno siempre
load_dotenv()

# Acceder a las variables de entorno
database_url = os.getenv("DATABASE_URL")
jwt_secret = os.getenv("JWT_SECRET")
jwt_expiracion_minutos = int(os.getenv("JWT_EXPIRACION_MINUTOS", "20"))

# Inicializar el contenedor
container = DIContainer()
container.config.connection_string.override(database_url)
container.config.jwt_secret.override(jwt_secret)
container.config.jwt_expiracion_minutos.override(jwt_expiracion_minutos)

# Wire antes de crear la app
container.wire(modules=[
  main_routes
  ,user_routes
  ,account_routes
])

# Crear la aplicación
app = Flask(__name__)
app.register_blueprint(main_routes.blueprint, url_prefix='/')
app.register_blueprint(user_routes.blueprint, url_prefix='/user')
app.register_blueprint(account_routes.blueprint, url_prefix='/account')

# Solo ejecutar el servidor si se llama directamente
if __name__ == "__main__":
  app.run(debug=True,port=8080)
