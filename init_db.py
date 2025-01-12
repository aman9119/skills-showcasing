from app import app, db, Student, generate_password_hash

def init_database():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Check if admin exists
        admin = Student.query.filter_by(username='admin').first()
        if not admin:
            admin = Student(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                name='Aman Chauhan',
                email='Asc911973451@gmail.com',
                bio='Computer Science student passionate about web development and Machine Learning'
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")

if __name__ == '__main__':
    init_database()
