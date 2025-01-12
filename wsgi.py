from app import app, db
from migrations import init_database
from sqlalchemy import text

# Test database connection before starting
with app.app_context():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.commit()
        print("Database connection successful")
        init_database()
    except Exception as e:
        print(f"Database connection failed: {str(e)}")
        raise

if __name__ == '__main__':
    app.run()
