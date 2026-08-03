from app.models.database import init_db

if __name__ == "__main__":
    print("Inicializando base de datos...")
    init_db()
    print("✅ Base de datos lista.")