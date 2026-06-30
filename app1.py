from flask import Flask, render_template, request, redirect
import cv2
import face_recognition
import sqlite3
import numpy as np
from datetime import datetime
import smtplib
import os

app = Flask(__name__)

# Use an absolute path for the database
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "create_db/models/attendance1.db")

# Initialize DB
def init_db():
    # Ensure directory structure exists
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
            # Create Attendance table with a UNIQUE constraint
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    time TIME NOT NULL,
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
                            cursor.execute("INSERT INTO Students (name, roll_number, email, face_encoding) VALUES (?, ?, ?, ?)", 
                                           (name, roll_number, email, face_encoding.tobytes()))
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
            students = cursor.execute("SELECT id, face_encoding FROM Students").fetchall()

        known_encodings = [np.frombuffer(row[1]) for row in students]
        student_ids = [row[0] for row in students]

        camera = cv2.VideoCapture(0)
        while True:
            ret, frame = camera.read()
            if not ret:
                break
            face_locations = face_recognition.face_locations(frame)
            face_encodings = face_recognition.face_encodings(frame, face_locations)

            for face_encoding in face_encodings:
                matches = face_recognition.compare_faces(known_encodings, face_encoding)
                if True in matches:
                    match_index = matches.index(True)
                    student_id = student_ids[match_index]

                    # Convert date and time to strings
                    date = datetime.now().strftime('%Y-%m-%d')  # YYYY-MM-DD
                    time = datetime.now().strftime('%H:%M:%S')  # HH:MM:SS

                    try:
                        with sqlite3.connect(DATABASE) as conn:
                            cursor = conn.cursor()
                            # Check if attendance already exists for this student on the same date
                            cursor.execute("SELECT * FROM Attendance WHERE student_id = ? AND date = ?", (student_id, date))
                            existing_record = cursor.fetchone()

                            if existing_record:
                                print(f"Attendance already marked for student_id {student_id} on {date}.")
                            else:
                                # Insert new attendance record
                                cursor.execute("INSERT INTO Attendance (student_id, date, time) VALUES (?, ?, ?)", 
                                               (student_id, date, time))
                                conn.commit()

                                # Send email
                                cursor.execute("SELECT email FROM Students WHERE id = ?", (student_id,))
                                email = cursor.fetchone()[0]
                                send_email(email, date, time)
                    except sqlite3.Error as e:
                        print(f"Failed to mark attendance: {e}")

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
                SELECT Students.name, Students.roll_number, Attendance.date, Attendance.time
                FROM Attendance
                JOIN Students ON Attendance.student_id = Students.id
            ''').fetchall()
    except sqlite3.Error as e:
        print(f"Failed to fetch records: {e}")
        records = []
    return render_template('view_records.html', records=records)

# Send email notification
def send_email(to_email, date, time):
    sender_email = "mohammedkhabab029@gmail.com"
    sender_password = "mfke jcde zlxf nkdw"

    message = f"""Subject: Attendance Notification

Your attendance was marked successfully on {date} at {time}.
"""
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, message)
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

# Home page
@app.route('/')
def index():
    return render_template('index.html')

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
