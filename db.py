"""MySQL/PostgreSQL database utilities for the Medical AI Assistant."""

import os
import pymysql
import psycopg2
from psycopg2.extras import DictCursor as PgDictCursor
from flask import g
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()

IntegrityError = pymysql.err.IntegrityError

DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "3306"))
DB_USER = os.environ.get("DB_USER", "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "medical_ai")

def parse_database_url(url):
    """Parse DATABASE_URL format (MySQL or PostgreSQL)
    
    Supports:
    - MySQL: mysql://user:pass@host:port/db
    - PostgreSQL: postgresql://user:pass@host:port/db
    """
    parsed = urlparse(url)
    config = {
        'engine': parsed.scheme,  # 'mysql' or 'postgresql'
        'host': parsed.hostname,
        'port': parsed.port,
        'user': parsed.username,
        'password': parsed.password,
        'db': parsed.path[1:] if parsed.path else 'medical_ai'
    }
    
    # Set default ports if not specified
    if not config['port']:
        config['port'] = 5432 if config['engine'] == 'postgresql' else 3306
    
    return config


def db_connect():
    """Connect to database - supports Render (PostgreSQL), Railway (MySQL), and local (MySQL)"""
    
    # Try to parse DATABASE_URL first (used by Render and Railway)
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Parse the database URL
        config = parse_database_url(database_url)
        
        if config['engine'] == 'postgresql':
            # Render uses PostgreSQL
            return psycopg2.connect(
                host=config['host'],
                user=config['user'],
                password=config['password'],
                database=config['db'],
                port=config['port']
            )
        else:
            # Railway or other MySQL provider
            return pymysql.connect(
                host=config['host'],
                user=config['user'],
                password=config['password'],
                database=config['db'],
                port=config['port'],
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
            )
    else:
        # Fall back to individual environment variables (local development with MySQL)
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            port=DB_PORT,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    
def get_db():
    db = getattr(g, "db", None)
    if db is None:
        db = g.db = db_connect()
    return db


def init_db():
    # Initialize database - supports both MySQL and PostgreSQL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        config = parse_database_url(database_url)
        # Use DATABASE_URL credentials for all operations
        host = config['host']
        user = config['user']
        password = config['password']
        port = config['port']
        db_name = config['db']
    else:
        host = DB_HOST
        user = DB_USER
        password = DB_PASSWORD
        port = DB_PORT
        db_name = DB_NAME
    
    admin_conn = pymysql.connect(
        host=host,
        user=user,
        password=password,
        port=port,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    with admin_conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    admin_conn.close()

    db = db_connect()
    cur = db.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_name VARCHAR(255),
            age VARCHAR(32),
            gender VARCHAR(32),
            contact VARCHAR(255),
            medical_history TEXT,
            task TEXT,
            locale VARCHAR(64),
            is_private TINYINT DEFAULT 0,
            created_at DATETIME,
            patient_user_id INT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT,
            role VARCHAR(32),
            content TEXT,
            emergency TINYINT DEFAULT 0,
            timestamp DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT,
            stored_path TEXT,
            original_name VARCHAR(255),
            mime_type VARCHAR(128),
            uploaded_by INT,
            timestamp DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE,
            password_hash TEXT,
            role VARCHAR(32),
            profession VARCHAR(255),
            created_at DATETIME,
            creator_id INT,
            full_name VARCHAR(255),
            age VARCHAR(32),
            gender VARCHAR(32),
            contact VARCHAR(255),
            medical_history TEXT,
            latitude DECIMAL(10, 8),
            longitude DECIMAL(11, 8),
            location_updated_at DATETIME,
            location_permission_granted BOOLEAN DEFAULT FALSE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit (
            id INT AUTO_INCREMENT PRIMARY KEY,
            actor_id INT,
            action VARCHAR(64),
            target_id INT,
            details TEXT,
            timestamp DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS one_time_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            token VARCHAR(255) UNIQUE,
            expires_at DATETIME,
            used TINYINT DEFAULT 0,
            created_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INT PRIMARY KEY,
            language VARCHAR(16),
            response_style VARCHAR(32),
            reminders VARCHAR(32),
            privacy_default VARCHAR(16),
            created_at DATETIME,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS health_goals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            title VARCHAR(255),
            notes TEXT,
            target_date DATE,
            status VARCHAR(32),
            created_at DATETIME,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_profiles (
            user_id INT PRIMARY KEY,
            professionalism VARCHAR(255),
            specialization VARCHAR(255),
            experience_years INT,
            hospital_id INT,
            bio TEXT,
            created_at DATETIME,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hospitals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255),
            address VARCHAR(255),
            city VARCHAR(128),
            country VARCHAR(128),
            phone VARCHAR(64),
            email VARCHAR(255),
            website VARCHAR(255),
            map_query VARCHAR(255),
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_user_id INT,
            doctor_user_id INT,
            hospital_id INT,
            appointment_time DATETIME,
            reason TEXT,
            status VARCHAR(32),
            created_at DATETIME,
            updated_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session_summaries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT,
            summary TEXT,
            created_at DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS patient_health_metrics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_user_id INT NOT NULL,
            metric_type VARCHAR(64),
            metric_value FLOAT,
            metric_date DATE,
            notes TEXT,
            created_at DATETIME,
            FOREIGN KEY (patient_user_id) REFERENCES users(id),
            INDEX idx_patient_metric_date (patient_user_id, metric_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_statistics (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doctor_user_id INT NOT NULL,
            total_patients INT DEFAULT 0,
            total_appointments INT DEFAULT 0,
            avg_response_time_minutes INT DEFAULT 0,
            patient_satisfaction_score FLOAT,
            cases_handled_this_month INT DEFAULT 0,
            most_common_condition VARCHAR(256),
            updated_at DATETIME,
            FOREIGN KEY (doctor_user_id) REFERENCES users(id),
            INDEX idx_doctor_stats (doctor_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_availability (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doctor_user_id INT NOT NULL,
            day_of_week INT DEFAULT 0,
            start_time TIME,
            end_time TIME,
            is_available BOOLEAN DEFAULT TRUE,
            consultation_type VARCHAR(32),
            max_patients_per_slot INT DEFAULT 1,
            slot_duration_minutes INT DEFAULT 30,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (doctor_user_id) REFERENCES users(id),
            INDEX idx_doctor_day (doctor_user_id, day_of_week)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS video_consultations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            appointment_id INT,
            doctor_user_id INT NOT NULL,
            patient_user_id INT NOT NULL,
            consultation_type VARCHAR(32),
            google_meet_link VARCHAR(500),
            start_time DATETIME,
            end_time DATETIME,
            duration_minutes INT DEFAULT 30,
            status VARCHAR(32),
            recording_link VARCHAR(500),
            notes TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (doctor_user_id) REFERENCES users(id),
            FOREIGN KEY (patient_user_id) REFERENCES users(id),
            FOREIGN KEY (appointment_id) REFERENCES appointments(id),
            INDEX idx_doctor_patient (doctor_user_id, patient_user_id),
            INDEX idx_start_time (start_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            event_type VARCHAR(64),
            event_data JSON,
            ip_address VARCHAR(45),
            user_agent TEXT,
            created_at DATETIME,
            INDEX idx_user_event (user_id, created_at),
            INDEX idx_event_type (event_type, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS patient_risk_scores (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_user_id INT NOT NULL,
            risk_level VARCHAR(32),
            readmission_risk FLOAT DEFAULT 0,
            no_show_risk FLOAT DEFAULT 0,
            complication_risk FLOAT DEFAULT 0,
            risk_factors JSON,
            calculated_at DATETIME,
            FOREIGN KEY (patient_user_id) REFERENCES users(id),
            INDEX idx_patient_risk (patient_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS direct_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sender_id INT NOT NULL,
            recipient_id INT NOT NULL,
            message_text TEXT NOT NULL,
            attachment_path TEXT,
            created_at DATETIME,
            read_at DATETIME,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (recipient_id) REFERENCES users(id),
            INDEX idx_dm_sender_recipient (sender_id, recipient_id, created_at),
            INDEX idx_dm_recipient_unread (recipient_id, read_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            type VARCHAR(64),
            title VARCHAR(255),
            body TEXT,
            data JSON,
            is_read TINYINT DEFAULT 0,
            created_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_notifications_user (user_id, is_read, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_schedules (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            medication_name VARCHAR(255) NOT NULL,
            dosage VARCHAR(100),
            frequency VARCHAR(100),
            times JSON,
            start_date DATE,
            end_date DATE,
            notes TEXT,
            active BOOLEAN DEFAULT TRUE,
            created_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user_active (user_id, active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medication_intake_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            schedule_id INT NOT NULL,
            user_id INT NOT NULL,
            scheduled_time DATETIME NOT NULL,
            taken_time DATETIME,
            status ENUM('taken', 'missed', 'skipped', 'pending') DEFAULT 'pending',
            notes TEXT,
            created_at DATETIME,
            FOREIGN KEY (schedule_id) REFERENCES medication_schedules(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user_status (user_id, status),
            INDEX idx_scheduled (user_id, scheduled_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS health_predictions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            prediction_type VARCHAR(100) NOT NULL,
            risk_score DECIMAL(5,2),
            risk_level ENUM('low', 'medium', 'high', 'critical'),
            factors JSON,
            recommendations TEXT,
            predicted_at DATETIME,
            expires_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user_type (user_id, prediction_type),
            INDEX idx_risk_level (risk_level, predicted_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS medical_documents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            document_type VARCHAR(50) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            extracted_text TEXT,
            extracted_data JSON,
            upload_date DATETIME,
            processed BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user_type (user_id, document_type),
            INDEX idx_processed (processed, upload_date)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS conversation_insights (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT NOT NULL,
            user_id INT NOT NULL,
            symptoms JSON,
            medical_codes JSON,
            confidence_score DECIMAL(5,2),
            follow_up_needed BOOLEAN DEFAULT FALSE,
            created_at DATETIME,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_session (session_id),
            INDEX idx_user_followup (user_id, follow_up_needed)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wellness_recommendations (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            category VARCHAR(100),
            recommendation TEXT NOT NULL,
            priority ENUM('low', 'medium', 'high') DEFAULT 'medium',
            status ENUM('active', 'completed', 'dismissed') DEFAULT 'active',
            created_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_user_status (user_id, status),
            INDEX idx_category (category, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL UNIQUE,
            medication_reminders BOOLEAN DEFAULT TRUE,
            health_alerts BOOLEAN DEFAULT TRUE,
            appointment_reminders BOOLEAN DEFAULT TRUE,
            wellness_tips BOOLEAN DEFAULT TRUE,
            email_notifications BOOLEAN DEFAULT TRUE,
            sms_notifications BOOLEAN DEFAULT FALSE,
            push_notifications BOOLEAN DEFAULT TRUE,
            quiet_hours_start TIME,
            quiet_hours_end TIME,
            timezone VARCHAR(64) DEFAULT 'UTC',
            updated_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    try:
        cur.execute("ALTER TABLE notification_preferences ADD COLUMN timezone VARCHAR(64) DEFAULT 'UTC'")
    except Exception:
        pass
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS forum_posts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            title VARCHAR(255) NOT NULL,
            body TEXT NOT NULL,
            condition_tag VARCHAR(128),
            created_at DATETIME,
            updated_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_forum_condition (condition_tag, created_at),
            INDEX idx_forum_user (user_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS forum_replies (
            id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INT NOT NULL,
            user_id INT NOT NULL,
            body TEXT NOT NULL,
            created_at DATETIME,
            FOREIGN KEY (post_id) REFERENCES forum_posts(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            INDEX idx_forum_replies_post (post_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    db.commit()
    db.close()
