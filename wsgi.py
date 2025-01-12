from app import app, db

# Ensure all tables exist
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run()
