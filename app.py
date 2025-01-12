from flask import Flask, render_template, jsonify, request, flash, redirect, url_for, send_file
from flask.ctx import AppContext  # New import to replace _app_ctx_stack
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json
from werkzeug.utils import secure_filename
import os
import traceback  # Add at the top with other imports
from flask_dance.contrib.github import make_github_blueprint, github
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.consumer.storage.sqla import SQLAlchemyStorage
from flask_dance.consumer import oauth_authorized
from sqlalchemy.orm.exc import NoResultFound  # Add this import at the top
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Update database URL to work with Render PostgreSQL
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

# Configure app first
app.config.update({
    'SECRET_KEY': os.environ.get('SECRET_KEY', 'default-secret-key'),
    'SQLALCHEMY_DATABASE_URI': database_url or 'sqlite:///portfolio.db',
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'UPLOAD_FOLDER': 'static/uploads',
    'MAX_CONTENT_LENGTH': 16 * 1024 * 1024,
    'GITHUB_OAUTH_CLIENT_ID': os.environ.get('GITHUB_OAUTH_CLIENT_ID'),
    'GITHUB_OAUTH_CLIENT_SECRET': os.environ.get('GITHUB_OAUTH_CLIENT_SECRET'),
    'OAUTHLIB_INSECURE_TRANSPORT': True
})

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}

# Define OAuth model first
class OAuth(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(50), nullable=False)
    provider_user_id = db.Column(db.String(256), unique=True, nullable=False)
    token = db.Column(db.JSON, nullable=False)  # Changed to JSON type for better token storage
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    student = db.relationship('Student')

    def __repr__(self):
        return f'<OAuth {self.provider}:{self.provider_user_id}>'

    def to_token(self):
        return self.token

# Initialize OAuth blueprints after OAuth model definition
github_bp = make_github_blueprint(
    client_id=os.environ.get('GITHUB_OAUTH_CLIENT_ID'),
    client_secret=os.environ.get('GITHUB_OAUTH_CLIENT_SECRET'),
    redirect_url='http://127.0.0.1:5000/login/github/authorized',
    scope=['user:email']
)
google_bp = make_google_blueprint(
    scope=['profile', 'email'],
    storage=SQLAlchemyStorage(OAuth, db.session, user=current_user),
    client_id=os.environ.get('GOOGLE_OAUTH_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
)

# Register blueprints after db initialization
app.register_blueprint(github_bp, url_prefix='/login/github')
app.register_blueprint(google_bp, url_prefix='/login/google')

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(200))
    resume_url = db.Column(db.String(200))
    github_url = db.Column(db.String(200))
    linkedin_url = db.Column(db.String(200))
    skills = db.relationship('Skill', backref='student', lazy=True)
    projects = db.relationship('Project', backref='student', lazy=True)
    certificates = db.relationship('Certificate', backref='student', lazy=True)
    education = db.relationship('Education', backref='student', lazy=True)
    discussions = db.relationship('Discussion', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    shared_files = db.relationship('SharedFile', backref='author', lazy=True)

class Skill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    proficiency = db.Column(db.Integer)
    category = db.Column(db.String(50))
    description = db.Column(db.Text)
    years_experience = db.Column(db.Float)
    last_used = db.Column(db.DateTime)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(200))
    project_url = db.Column(db.String(200))
    github_url = db.Column(db.String(200))
    technologies = db.Column(db.String(200))
    completion_date = db.Column(db.DateTime, default=datetime.utcnow)
    featured = db.Column(db.Boolean, default=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    @property
    def technologies_list(self):
        return [tech.strip() for tech in self.technologies.split(',')] if self.technologies else []

class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    issuer = db.Column(db.String(100))
    issue_date = db.Column(db.DateTime)
    expiry_date = db.Column(db.DateTime)
    credential_url = db.Column(db.String(200))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

class Education(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    institution = db.Column(db.String(100), nullable=False)
    degree = db.Column(db.String(100))
    field = db.Column(db.String(100))
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    gpa = db.Column(db.Float)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

class Discussion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    comments = db.relationship('Comment', backref='discussion', lazy=True, cascade='all, delete-orphan')
    # Remove this line as it creates a circular relationship
    # student = db.relationship('Student', backref='authored_discussions')

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    discussion_id = db.Column(db.Integer, db.ForeignKey('discussion.id'), nullable=False)

class SharedFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    downloads = db.Column(db.Integer, default=0)

class Experience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(db.String(100), nullable=False)
    company_name = db.Column(db.String(100), nullable=False)
    company_logo = db.Column(db.String(200))
    location = db.Column(db.String(100))
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime)
    current = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text)
    technologies = db.Column(db.String(200))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    @property
    def technologies_list(self):
        return [tech.strip() for tech in self.technologies.split(',')] if self.technologies else []

# Add relationship to Student model
Student.experiences = db.relationship('Experience', backref='student', lazy=True)

class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text)
    thumbnail = db.Column(db.String(200))
    published_date = db.Column(db.DateTime, default=datetime.utcnow)
    updated_date = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_published = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    tags = db.Column(db.String(200))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    @property
    def tags_list(self):
        return [tag.strip() for tag in self.tags.split(',')] if self.tags else []

    def generate_slug(self):
        self.slug = '-'.join(self.title.lower().split())

# Add relationship to Student model
Student.blog_posts = db.relationship('BlogPost', backref='author', lazy=True)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    company = db.Column(db.String(100))
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(200))
    rating = db.Column(db.Integer)  # 1-5 rating
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    is_featured = db.Column(db.Boolean, default=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

# Add relationship to Student model
Student.testimonials = db.relationship('Testimonial', backref='student', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            print(f"Login attempt - Username: {username}")
            
            student = Student.query.filter_by(username=username).first()
            if student:
                print(f"Found user: {student.username}")
                if check_password_hash(student.password_hash, password):
                    login_user(student)
                    print("Login successful")
                    flash('Logged in successfully!', 'success')
                    return redirect(url_for('dashboard'))
                print("Password verification failed")
            else:
                print(f"No user found with username: {username}")
            
            flash('Invalid username or password', 'error')
    except Exception as e:
        print(f"Login error: {str(e)}")
        print(traceback.format_exc())
        flash('An error occurred during login', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            name = request.form.get('name')
            email = request.form.get('email')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')

            # Add debug logging
            print(f"Signup attempt - Username: {username}, Email: {email}")

            if not all([username, name, email, password, confirm_password]):
                print("Missing required fields")
                flash('All fields are required', 'error')
                return redirect(url_for('signup'))

            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return redirect(url_for('signup'))

            if len(password) < 6:
                flash('Password must be at least 6 characters long', 'error')
                return redirect(url_for('signup'))

            if not any(c.isdigit() for c in password):
                flash('Password must contain at least one number', 'error')
                return redirect(url_for('signup'))

            if Student.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return redirect(url_for('signup'))

            if Student.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return redirect(url_for('signup'))

            # Create new user
            student = Student(
                username=username,
                name=name,
                email=email,
                password_hash=generate_password_hash(password),
                bio='Student at Computer Science'
            )
            
            try:
                db.session.add(student)
                db.session.commit()
                print(f"User created successfully: {username}")
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                print(f"Database error: {str(e)}")
                flash('Error creating user account', 'error')
                
        except Exception as e:
            print(f"Signup error: {str(e)}")
            print(traceback.format_exc())
            flash('An error occurred during registration', 'error')
            
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        try:
            # Validate URLs
            github_url = request.form.get('github_url')
            linkedin_url = request.form.get('linkedin_url')
            
            if github_url and not github_url.startswith('https://github.com/'):
                flash('Invalid GitHub URL', 'error')
                return redirect(url_for('edit_profile'))
                
            if linkedin_url and not linkedin_url.startswith('https://www.linkedin.com/'):
                flash('Invalid LinkedIn URL', 'error')
                return redirect(url_for('edit_profile'))

            current_user.name = request.form.get('name')
            current_user.bio = request.form.get('bio')
            current_user.github_url = github_url
            current_user.linkedin_url = linkedin_url
            db.session.commit()
            flash('Profile updated successfully', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash('Error updating profile', 'error')
            db.session.rollback()
            return redirect(url_for('edit_profile'))
    return render_template('edit_profile.html')

@app.route('/upload_profile_image', methods=['POST'])
@login_required
def upload_profile_image():
    if 'profile_image' in request.files:
        file = request.files['profile_image']
        if file and allowed_file(file.filename):
            filename = secure_filename(f'profile_{current_user.id}_{file.filename}')
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.profile_image = f'/static/uploads/{filename}'
            db.session.commit()
            flash('Profile image updated successfully!', 'success')
    return redirect(url_for('edit_profile'))

@app.route('/upload_resume', methods=['POST'])
@login_required
def upload_resume():
    if 'resume' in request.files:
        file = request.files['resume']
        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(f'resume_{current_user.id}.pdf')
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            current_user.resume_url = f'/static/uploads/{filename}'
            db.session.commit()
            flash('Resume updated successfully!', 'success')
    return redirect(url_for('edit_profile'))

@app.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('signup'))  # Changed to redirect to signup first
    return render_template('home.html', student=current_user)

@app.route('/skills')
def skills():
    student = Student.query.first()
    if student is None:
        flash('No student record found.')
        return redirect(url_for('home'))
        
    # Define category icons mapping
    category_icons = {
        'Programming': 'fa-code',
        'Web Development': 'fa-globe',
        'Database': 'fa-database',
        'DevOps': 'fa-server',
        'Mobile Development': 'fa-mobile-alt',
        'Data Science': 'fa-chart-bar',
        'Machine Learning': 'fa-brain',
        'Cloud Computing': 'fa-cloud',
        'UI/UX Design': 'fa-paint-brush',
        'Testing': 'fa-vial',
        'Security': 'fa-shield-alt',
        'Version Control': 'fa-code-branch',
        'Framework': 'fa-layer-group',
        'Tools': 'fa-tools',
        'Soft Skills': 'fa-users',
        'Languages': 'fa-language',
        'Other': 'fa-star'
    }
    
    skills_by_category = {}
    for skill in student.skills:
        if skill.category not in skills_by_category:
            skills_by_category[skill.category] = []
        skills_by_category[skill.category].append(skill)
        
    return render_template('skills.html', 
                         skills_by_category=skills_by_category,
                         category_icons=category_icons)

@app.route('/add_skill', methods=['GET', 'POST'])
@login_required
def add_skill():
    if request.method == 'POST':
        skill = Skill(
            name=request.form.get('name'),
            proficiency=int(request.form.get('proficiency')),
            category=request.form.get('category'),
            description=request.form.get('description'),
            years_experience=float(request.form.get('years_experience')),
            student=current_user
        )
        db.session.add(skill)
        db.session.commit()
        flash('Skill added successfully!', 'success')
        return redirect(url_for('skills'))
    return render_template('add_skill.html')

@app.route('/projects')
def projects():
    try:
        if current_user.is_authenticated:
            projects = current_user.projects
        else:
            # For non-authenticated users, show admin's projects
            admin = Student.query.filter_by(username='admin').first()
            projects = admin.projects if admin else []
            
        featured_projects = sorted([p for p in projects if p.featured], 
                                 key=lambda x: x.completion_date, reverse=True)
        regular_projects = sorted([p for p in projects if not p.featured], 
                                key=lambda x: x.completion_date, reverse=True)
        
        return render_template('projects.html', 
                             featured_projects=featured_projects,
                             regular_projects=regular_projects)
    except Exception as e:
        print(f"Error loading projects: {str(e)}")
        flash('Error loading projects', 'error')
        return redirect(url_for('home'))

@app.route('/add_project', methods=['GET', 'POST'])
@login_required
def add_project():
    if request.method == 'POST':
        project = Project(
            title=request.form.get('title'),
            description=request.form.get('description'),
            technologies=request.form.get('technologies'),
            github_url=request.form.get('github_url'),
            project_url=request.form.get('project_url'),
            student=current_user
        )
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                project.image_url = f'/static/uploads/{filename}'
        
        db.session.add(project)
        db.session.commit()
        flash('Project added successfully!', 'success')
        return redirect(url_for('projects'))
    return render_template('add_project.html')

@app.route('/edit_project/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_project(id):
    project = Project.query.get_or_404(id)
    if project.student_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('projects'))
        
    if request.method == 'POST':
        try:
            project.title = request.form.get('title')
            project.description = request.form.get('description')
            project.technologies = request.form.get('technologies')
            project.github_url = request.form.get('github_url')
            project.project_url = request.form.get('project_url')
            project.featured = 'featured' in request.form
            
            if 'image' in request.files:
                file = request.files['image']
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                    project.image_url = f'/static/uploads/{filename}'
            
            db.session.commit()
            flash('Project updated successfully!', 'success')
            return redirect(url_for('projects'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating project', 'error')
            
    return render_template('edit_project.html', project=project)

@app.route('/delete_project/<int:id>', methods=['POST'])
@login_required
def delete_project(id):
    project = Project.query.get_or_404(id)
    if project.student_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('projects'))
        
    try:
        db.session.delete(project)
        db.session.commit()
        flash('Project deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting project', 'error')
        
    return redirect(url_for('projects'))

@app.route('/debug/users')
def debug_users():
    if app.debug:  # Only allow in debug mode
        users = Student.query.all()
        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'username': user.username,
                'name': user.name,
                'email': user.email
            })
        return jsonify(user_list)
    return "Not available in production"

# In the init_db function, ensure we're not using order
def init_db():
    try:
        # Create tables
        db.create_all()
        
        # Check if admin user exists
        admin = Student.query.filter_by(username='admin').first()
        if not admin:
            # Create admin user
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

            # Add initial skills
            skills = [
                Skill(name="Python", proficiency=5, category="Programming", 
                      description="Experienced in Flask, Django, and Data Science",
                      years_experience=2.5, student=admin),
                Skill(name="JavaScript", proficiency=4, category="Programming",
                      description="Frontend development with React and Vue",
                      years_experience=2.0, student=admin),
                Skill(name="Machine Learning", proficiency=4, category="Data Science",
                      description="Experience with scikit-learn and TensorFlow",
                      years_experience=1.5, student=admin)
            ]
            db.session.add_all(skills)
            
            project = Project(
                title="Portfolio Website",
                description="Personal portfolio built with Flask and SQLAlchemy",
                technologies="Python, Flask, SQLAlchemy, HTML, CSS",
                featured=True,
                student=admin
            )
            db.session.add(project)
            db.session.commit()
            print("Initial content created!")
        
        # Add sample testimonial
        testimonial = Testimonial(
            name="John Smith",
            position="Senior Developer",
            company="Tech Corp",
            content="Excellent work ethic and technical skills. A pleasure to work with!",
            rating=5,
            is_featured=True,
            student=admin
        )
        db.session.add(testimonial)
        db.session.commit()
        
    except Exception as e:
        print(f"Database initialization error: {str(e)}")
        db.session.rollback()
        raise

@app.route('/discussions')
def discussions():
    try:
        discussions = Discussion.query.order_by(Discussion.created_at.desc()).all()
        return render_template('discussions.html', discussions=discussions)
    except Exception as e:
        print(f"Error in discussions route: {str(e)}")
        flash('Error loading discussions', 'error')
        return redirect(url_for('home'))

@app.route('/discussion/<int:id>')
def discussion_detail(id):
    try:
        discussion = Discussion.query.get_or_404(id)
        comments = Comment.query.filter_by(discussion_id=id)\
            .order_by(Comment.created_at.desc()).all()
        return render_template('discussion_detail.html', 
                             discussion=discussion, 
                             comments=comments)
    except Exception as e:
        print(f"Error in discussion detail route: {str(e)}")
        flash('Discussion not found', 'error')
        return redirect(url_for('discussions'))

@app.route('/create_discussion', methods=['GET', 'POST'])
@login_required
def create_discussion():
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            content = request.form.get('content')
            
            if not title or not content:
                flash('Title and content are required', 'error')
                return redirect(url_for('create_discussion'))
            
            discussion = Discussion(
                title=title,
                content=content,
                student_id=current_user.id
            )
            db.session.add(discussion)
            db.session.commit()
            
            flash('Discussion created successfully!', 'success')
            return redirect(url_for('discussion_detail', id=discussion.id))
            
        except Exception as e:
            print(f"Error creating discussion: {str(e)}")
            flash('Error creating discussion', 'error')
            db.session.rollback()
            return redirect(url_for('create_discussion'))
            
    return render_template('create_discussion.html')

@app.route('/add_comment/<int:discussion_id>', methods=['POST'])
@login_required
def add_comment(discussion_id):
    content = request.form.get('content')
    if not content:
        flash('Comment content is required', 'error')
        return redirect(url_for('discussion_detail', id=discussion_id))
        
    try:
        comment = Comment(
            content=content,
            discussion_id=discussion_id,
            student_id=current_user.id
        )
        db.session.add(comment)
        db.session.commit()
        flash('Comment added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding comment', 'error')
        
    return redirect(url_for('discussion_detail', id=discussion_id))

@app.route('/shared_files')
def shared_files():
    try:
        files = SharedFile.query.order_by(SharedFile.upload_date.desc()).all()
        return render_template('shared_files.html', files=files)
    except Exception as e:
        print(f"Error loading shared files: {str(e)}")
        flash('Error loading shared files', 'error')
        return redirect(url_for('home'))

@app.route('/upload_shared_file', methods=['GET', 'POST'])
@login_required
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(url_for('shared_files'))
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('shared_files'))
            
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                shared_file = SharedFile(
                    filename=filename,
                    file_path=f'/static/uploads/{filename}',
                    description=request.form.get('description'),
                    student_id=current_user.id
                )
                db.session.add(shared_file)
                db.session.commit()
                flash('File uploaded successfully!', 'success')
                return redirect(url_for('shared_files'))
            except Exception as e:
                db.session.rollback()
                print(f"Error uploading file: {str(e)}")
                flash('Error uploading file', 'error')
                
    return render_template('upload_file.html')

@app.route('/download_file/<int:file_id>')
def download_file(file_id):
    try:
        shared_file = SharedFile.query.get_or_404(file_id)
        shared_file.downloads += 1
        db.session.commit()
        
        file_path = os.path.join(app.root_path, shared_file.file_path.lstrip('/'))
        return send_file(
            file_path,
            as_attachment=True,
            download_name=shared_file.filename
        )
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        flash('Error downloading file', 'error')
        return redirect(url_for('shared_files'))

@app.route('/login/github')
def github_login():
    if not github.authorized:
        return redirect(url_for('github.login'))
    return redirect(url_for('dashboard'))

@oauth_authorized.connect_via(github_bp)
def github_logged_in(blueprint, token):
    if not token:
        flash("Failed to log in with GitHub.", "error")
        return False

    try:
        resp = github.get("/user")
        if not resp.ok:
            print(f"GitHub API Error: {resp.text}")  # Add debug logging
            flash("Failed to fetch GitHub user info.", "error")
            return False

        github_info = resp.json()
        github_user_id = str(github_info["id"])

        # Get email from GitHub
        emails_resp = github.get("/user/emails")
        if emails_resp.ok:
            emails = emails_resp.json()
            primary_email = next((e["email"] for e in emails if e["primary"]), None)
            email = primary_email or emails[0]["email"] if emails else None
        else:
            print(f"GitHub Email API Error: {emails_resp.text}")  # Add debug logging
            email = None

        # Find existing OAuth token
        oauth = OAuth.query.filter_by(
            provider='github',
            provider_user_id=github_user_id
        ).first()

        if oauth:
            # Update existing token
            oauth.token = token
            if oauth.student:
                login_user(oauth.student)
                db.session.commit()
                flash("Successfully signed in with GitHub.", "success")
                return False

        # Create new OAuth and Student if not exists
        student = Student(
            username=github_info["login"],
            email=email or f"{github_info['login']}@github.com",
            name=github_info.get("name", github_info["login"]),
            password_hash=generate_password_hash(os.urandom(24).hex()),
            bio=github_info.get("bio", "")
        )

        oauth = OAuth(
            provider='github',
            provider_user_id=github_user_id,
            token=token,
            student=student
        )

        db.session.add_all([student, oauth])
        db.session.commit()
        login_user(student)
        flash("Successfully signed in with GitHub.", "success")
        return False

    except Exception as e:
        print(f"GitHub login error: {str(e)}")
        print(traceback.format_exc())  # Add full traceback
        db.session.rollback()
        flash("An error occurred during GitHub login.", "error")
        return False

@oauth_authorized.connect_via(google_bp)
def google_logged_in(blueprint, token):
    if not token:
        flash("Failed to log in with Google.", "error")
        return False

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        flash("Failed to fetch Google user info.", "error")
        return False

    google_info = resp.json()
    google_user_id = google_info["id"]

    oauth = OAuth.query.filter_by(
        provider='google',
        provider_user_id=google_user_id
    ).first()

    if oauth:
        login_user(oauth.student)
        flash("Successfully signed in with Google.", "success")
        return False

    email = google_info["email"]
    username = email.split("@")[0]
    name = google_info.get("name", username)

    student = Student(
        username=username,
        email=email,
        name=name,
        password_hash=generate_password_hash(os.urandom(24).hex()),
    )
    oauth = OAuth(
        provider='google',
        provider_user_id=google_user_id,
        student=student
    )

    db.session.add_all([student, oauth])
    db.session.commit()
    login_user(student)
    flash("Successfully signed in with Google.", "success")
    return False

@app.route('/experience')
def experience():
    if current_user.is_authenticated:
        experiences = current_user.experiences
    else:
        admin = Student.query.filter_by(username='admin').first()
        experiences = admin.experiences if admin else []
    
    experiences = sorted(experiences, 
                        key=lambda x: x.end_date or datetime.max, 
                        reverse=True)
    return render_template('experience.html', experiences=experiences)

@app.route('/blog')
def blog():
    page = request.args.get('page', 1, type=int)
    posts = BlogPost.query.filter_by(is_published=True)\
        .order_by(BlogPost.published_date.desc())\
        .paginate(page=page, per_page=6)
    return render_template('blog/index.html', posts=posts)

@app.route('/blog/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        post = BlogPost(
            title=request.form.get('title'),
            content=request.form.get('content'),
            summary=request.form.get('summary'),
            tags=request.form.get('tags'),
            is_published=bool(request.form.get('publish')),
            student_id=current_user.id
        )
        post.generate_slug()
        
        if 'thumbnail' in request.files:
            file = request.files['thumbnail']
            if file and allowed_file(file.filename):
                filename = secure_filename(f'blog_{post.slug}_{file.filename}')
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.thumbnail = f'/static/uploads/{filename}'
        
        db.session.add(post)
        db.session.commit()
        flash('Blog post created successfully!', 'success')
        return redirect(url_for('blog_post', slug=post.slug))
        
    return render_template('blog/new.html')

@app.route('/blog/<slug>')
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug).first_or_404()
    post.views += 1
    db.session.commit()
    return render_template('blog/post.html', post=post)

@app.route('/testimonials')
def testimonials():
    testimonials = Testimonial.query.filter_by(is_featured=True)\
        .order_by(Testimonial.date_added.desc()).all()
    return render_template('testimonials.html', testimonials=testimonials)

@app.route('/testimonials/add', methods=['GET', 'POST'])
@login_required
def add_testimonial():
    if request.method == 'POST':
        testimonial = Testimonial(
            name=request.form.get('name'),
            position=request.form.get('position'),
            company=request.form.get('company'),
            content=request.form.get('content'),
            rating=int(request.form.get('rating', 5)),
            is_featured=bool(request.form.get('featured')),
            student_id=current_user.id
        )
        
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f'testimonial_{testimonial.id}_{file.filename}')
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                testimonial.image_url = f'/static/uploads/{filename}'
        
        db.session.add(testimonial)
        db.session.commit()
        flash('Testimonial added successfully!', 'success')
        return redirect(url_for('testimonials'))
        
    return render_template('add_testimonial.html')

@app.route('/testimonials/delete/<int:id>', methods=['POST'])
@login_required
def delete_testimonial(id):
    testimonial = Testimonial.query.get_or_404(id)
    if testimonial.student_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('testimonials'))
    
    try:
        if testimonial.image_url:
            # Delete image file if it exists
            image_path = os.path.join(app.root_path, testimonial.image_url.lstrip('/'))
            if os.path.exists(image_path):
                os.remove(image_path)
                
        db.session.delete(testimonial)
        db.session.commit()
        flash('Testimonial deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting testimonial', 'error')
    
    return redirect(url_for('testimonials'))

@app.route('/login/error')
def oauth_error():
    error = request.args.get('error')
    return render_template('error.html',
                         error_code='Auth Error',
                         error_message=error or 'An authentication error occurred.')

# Add this after all models are defined but before routes
def init_app(app):
    with app.app_context():
        db.create_all()
        init_db()

# Modify the main block at the bottom
if __name__ == '__main__':
    init_app(app)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)