from flask import Flask, render_template, request, redirect, url_for
import cv2
import face_recognition
import sqlite3
import numpy as np
from datetime import datetime
import smtplib
import os

app = Flask(__name__)

# Use absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "create_db/models/attendance2.db")
IMAGE_DIR = os.path.join(BASE_DIR, "static/attendance_logs")
os.makedirs(IMAGE_DIR, exist_ok=True)  # Ensure the folder exists for saving images

# Email details
SENDER_EMAIL = "mohammedkhabab029@gmail.com"  # Replace with your email
SENDER_PASSWORD = "izrh jprr wbjq mguq"  # Replace with your email app password
ADMIN_EMAIL = "ahteshambaje@gmail.com"  # Replace with your admin email

# Initialize Database
def init_db():
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            # Create Students table
            cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS Students ( 
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT NOT NULL, 
                    roll_number TEXT UNIQUE NOT NULL, 
                    email TEXT NOT NULL, 
                    face_encoding BLOB NOT NULL 
                ) 
            ''')
            # Create Attendance table with an image_path column
            cursor.execute(''' 
                CREATE TABLE IF NOT EXISTS Attendance ( 
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    student_id INTEGER NOT NULL, 
                    date DATE NOT NULL, 
                    time TIME NOT NULL, 
                    image_path TEXT NOT NULL, 
                    FOREIGN KEY (student_id) REFERENCES Students (id), 
                    UNIQUE(student_id, date) -- Ensure one record per student per day 
                ) 
            ''')
            conn.commit()
    except sqlite3.Error as e:
        print(f"Database initialization failed: {e}")

# Add student
@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        email = request.form['email']

        # Capture face
        camera = cv2.VideoCapture(0)
        while True:
            ret, frame = camera.read()
            if not ret:
                break
            cv2.imshow("Capture Face (Press 'S' to Save)", frame)
            if cv2.waitKey(1) & 0xFF == ord('s'):
                face_locations = face_recognition.face_locations(frame)
                if face_locations:
                    face_encoding = face_recognition.face_encodings(frame, face_locations)[0]
                    try:
                        with sqlite3.connect(DATABASE) as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                "INSERT INTO Students (name, roll_number, email, face_encoding) VALUES (?, ?, ?, ?)",
                                (name, roll_number, email, face_encoding.tobytes())
                            )
                            conn.commit()
                    except sqlite3.Error as e:
                        print(f"Failed to add student: {e}")
                    break
        camera.release()
        cv2.destroyAllWindows()
        return redirect('/')

    return render_template('add_student.html')

# Capture attendance
@app.route('/capture_attendance', methods=['GET'])
def capture_attendance():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            students = cursor.execute("SELECT id, name, roll_number, face_encoding FROM Students").fetchall()

        known_encodings = [np.frombuffer(row[3]) for row in students]
        student_ids = [row[0] for row in students]
        student_names = [row[1] for row in students]
        student_roll_numbers = [row[2] for row in students]

        camera = cv2.VideoCapture(0)
        while True:
            ret, frame = camera.read()
            if not ret:
                break
            face_locations = face_recognition.face_locations(frame)
            face_encodings = face_recognition.face_encodings(frame, face_locations)

            for (face_location, face_encoding) in zip(face_locations, face_encodings):
                matches = face_recognition.compare_faces(known_encodings, face_encoding)
                if True in matches:
                    match_index = matches.index(True)
                    student_id = student_ids[match_index]
                    student_name = student_names[match_index]
                    student_roll_number = student_roll_numbers[match_index]

                    # Save attendance
                    date = datetime.now().strftime('%Y-%m-%d')
                    time = datetime.now().strftime('%H:%M:%S')

                    # Check if attendance is already marked for this student on the same day
                    with sqlite3.connect(DATABASE) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT * FROM Attendance WHERE student_id = ? AND date = ?", (student_id, date))
                        existing_record = cursor.fetchone()

                        if existing_record:
                            print(f"Attendance already marked for student_id {student_id} on {date}. No new image saved.")
                        else:
                            # Save image if no attendance recorded for today
                            top, right, bottom, left = face_location
                            face_image = frame[top:bottom, left:right]
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')  # Unique timestamp
                            image_filename = f"{student_id}_{timestamp}.jpg"
                            image_path = os.path.join(IMAGE_DIR, image_filename)
                            cv2.imwrite(image_path, face_image)

                            # Insert new attendance record
                            cursor.execute(
                                "INSERT INTO Attendance (student_id, date, time, image_path) VALUES (?, ?, ?, ?)",
                                (student_id, date, time, image_filename)
                            )
                            conn.commit()

                            # Send email to both the student and the admin
                            cursor.execute("SELECT email FROM Students WHERE id = ?", (student_id,))
                            email = cursor.fetchone()[0]
                            send_email([email, ADMIN_EMAIL], date, time, image_filename, student_name, student_roll_number)

            cv2.imshow("Capture Attendance", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        camera.release()
        cv2.destroyAllWindows()
    except sqlite3.Error as e:
        print(f"Failed to retrieve students: {e}")

    return redirect('/')

# View attendance records
@app.route('/view_records', methods=['GET'])
def view_records():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            records = cursor.execute('''
                SELECT Students.name, Students.roll_number, Attendance.date, Attendance.time, Attendance.image_path
                FROM Attendance
                JOIN Students ON Attendance.student_id = Students.id
            ''').fetchall()
    except sqlite3.Error as e:
        print(f"Failed to fetch records: {e}")
        records = []
    return render_template('view_records.html', records=records)

# Send email notification
def send_email(to_emails, date, time, image_filename, student_name, student_roll_number):
    # Message for the student
    student_message = f"""Subject: Attendance Notification

Your attendance was marked successfully on {date} at {time}.
"""
    
    # Message for the admin
    admin_message = f"""Subject: Attendance Notification for {student_name} ({student_roll_number})

The attendance for student {student_name} with roll number {student_roll_number} was marked successfully on {date} at {time}.
"""
    
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        
        # Send email to the student
        server.sendmail(SENDER_EMAIL, to_emails[0], student_message)
        
        # Send email to the admin
        server.sendmail(SENDER_EMAIL, to_emails[1], admin_message)
        
        server.quit()
        print(f"Attendance email sent to {to_emails}")
    except Exception as e:
        print(f"Failed to send email: {e}")

# Home page
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
