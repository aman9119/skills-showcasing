from app import app
from migrations import init_database

# Initialize the database
init_database()

if __name__ == '__main__':
    app.run()
