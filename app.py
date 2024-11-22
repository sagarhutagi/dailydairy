from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import csv
from fpdf import FPDF
import os
import tempfile  # Import tempfile for creating temporary files

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    entries = db.relationship('DiaryEntry', backref='author', lazy=True)

class DiaryEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    mood_rating = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tags = db.relationship('Tag', secondary='entry_tags')

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

entry_tags = db.Table('entry_tags',
    db.Column('entry_id', db.Integer, db.ForeignKey('diary_entry.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        
        # Create new user
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        
        try:
            db.session.commit()
            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {e}. Please try again.')
            return redirect(url_for('signup'))
            
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Diary routes
# Update the root route to show landing page for non-logged in users
@app.route('/')
def home():
    if current_user.is_authenticated:
        sort = request.args.get('sort', 'latest')
        entries = DiaryEntry.query.filter_by(user_id=current_user.id)
        
        if sort == 'latest':
            entries = entries.order_by(DiaryEntry.date.desc())
        else:
            entries = entries.order_by(DiaryEntry.date.asc())
            
        return render_template('home.html', entries=entries)
    return render_template('landing.html')

@app.route('/entry/new', methods=['GET', 'POST'])
@login_required
def new_entry():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        date_str = request.form.get('date')
        mood_rating = int(request.form.get('mood_rating'))
        tags = request.form.get('tags').split(',')
        
        date = datetime.strptime(date_str, '%Y-%m-%d')
        entry = DiaryEntry(title=title, content=content, date=date,
                          mood_rating=mood_rating, user_id=current_user.id)
        
        for tag_name in tags:
            tag = Tag.query.filter_by(name=tag_name.strip()).first()
            if not tag:
                tag = Tag(name=tag_name.strip())
                db.session.add(tag)
            entry.tags.append(tag)
            
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('home'))
    return render_template('new_entry.html')

@app.route('/entry/<int:id>')
@login_required
def view_entry(id):
    entry = DiaryEntry.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    return render_template('view_entry.html', entry=entry)

@app.route('/entry/<int:id>/delete', methods=['POST'])
@login_required
def delete_entry(id):
    entry = DiaryEntry.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(entry)
    db.session.commit()
    flash('Entry deleted successfully!')
    return redirect(url_for('home'))

@app.route('/entry/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def edit_entry(id):
    entry = DiaryEntry.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        entry.title = request.form.get('title')
        entry.content = request.form.get('content')
        date_str = request.form.get('date')
        entry.mood_rating = int(request.form.get('mood_rating'))
        tags = request.form.get('tags').split(',')
        
        # Update the date
        entry.date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Update tags
        entry.tags.clear()  # Clear existing tags
        for tag_name in tags:
            tag = Tag.query.filter_by(name=tag_name.strip()).first()
            if not tag:
                tag = Tag(name=tag_name.strip())
                db.session.add(tag)
            entry.tags.append(tag)

        db.session.commit()
        flash('Entry updated successfully!')
        return redirect(url_for('home'))
    
    return render_template('edit_entry.html', entry=entry)



@app.route('/search')
@login_required
def search():
    query = request.args.get('query', '')
    search_type = request.args.get('search_type', 'title')
    
    # Initialize the query
    entries = DiaryEntry.query.filter_by(user_id=current_user.id)
    
    if query:
        if search_type == 'title':
            entries = entries.filter(DiaryEntry.title.ilike(f'%{query}%'))
        else:  # date search
            try:
                search_date = datetime.strptime(query, '%Y-%m-%d').date()
                entries = entries.filter(DiaryEntry.date == search_date)
            except ValueError:
                flash('Please enter date in YYYY-MM-DD format', 'error')
    
    # Order by date descending (most recent first)
    entries = entries.order_by(DiaryEntry.date.desc())
    
    return render_template('search_results.html', entries=entries)

@app.route('/mood-analysis')
@login_required
def mood_analysis():
    entries = DiaryEntry.query.filter_by(user_id=current_user.id).order_by(DiaryEntry.date).all()
    dates = [entry.date for entry in entries]
    ratings = [entry.mood_rating for entry in entries]
    
    plt.figure(figsize=(10, 6))
    plt.plot(dates, ratings, 'b-')
    plt.title('Mood Over Time')
    plt.xlabel('Date')
    plt.ylabel('Mood Rating')
    plt.grid(True)
    
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    return send_file(img, mimetype='image/png')

@app.route('/calendar')
@login_required
def calendar():
    entries = DiaryEntry.query.filter_by(user_id=current_user.id).all()
    calendar_data = {}
    for entry in entries:
        date_str = entry.date.strftime('%Y-%m-%d')
        calendar_data[date_str] = {
            'mood': entry.mood_rating,
            'title': entry.title
        }
    return render_template('calendar.html', calendar_data=calendar_data)

@app.route('/export/<format>')
@login_required
def export(format):
    entries = DiaryEntry.query.filter_by(user_id=current_user.id).order_by(DiaryEntry.date).all()
    
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Title', 'Content', 'Mood Rating', 'Tags'])
        
        for entry in entries:
            writer.writerow([
                entry.date.strftime('%Y-%m-%d'),
                entry.title,
                entry.content,
                entry.mood_rating,
                ','.join(tag.name for tag in entry.tags) if entry.tags else ''
            ])
            
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='diary_entries.csv'
        )
        
    elif format == 'pdf':
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        
        for entry in entries:
            pdf.cell(0, 10, f"Date: {entry.date.strftime('%Y-%m-%d')}", ln=True)
            pdf.cell(0, 10, f"Title: {entry.title}", ln=True)
            pdf.cell(0, 10, f"Mood Rating: {entry.mood_rating}", ln=True)
            pdf.multi_cell(0, 10, f"Content: {entry.content}")
            pdf.cell(0, 10, f"Tags: {','.join(tag.name for tag in entry.tags) if entry.tags else ''}", ln=True)
            pdf.add_page()
            
        # Create a temporary file to store the PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            pdf.output(temp_file.name)  # Save to the temporary file

            # Read the content of the temporary file into BytesIO
            with open(temp_file.name, 'rb') as f:
                pdf_output = io.BytesIO(f.read())
        
        return send_file(
            pdf_output,
            mimetype='application/pdf',    
            as_attachment=True,
            download_name='diary_entries.pdf'
        )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
