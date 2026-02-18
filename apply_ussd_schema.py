#!/usr/bin/env python
"""
Apply USSD database schema to existing MySQL database
"""

import pymysql
import sys
import os
from dotenv import load_dotenv

load_dotenv()

def apply_ussd_schema():
    """Apply USSD database schema"""
    
    try:
        # Database connection from environment variables
        conn = pymysql.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            port=int(os.environ.get('DB_PORT', 3306)),
            user=os.environ.get('DB_USER', 'root'),
            password=os.environ.get('DB_PASSWORD', ''),
            database=os.environ.get('DB_NAME', 'defaultdb'),
            charset='utf8mb4'
        )
        
        cur = conn.cursor()
        print("✓ Connected to MySQL database")
        
        # Create USSD session table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_sessions (
                session_id VARCHAR(255) PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL,
                user_id INT DEFAULT NULL,
                session_data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                status VARCHAR(20) DEFAULT 'active',
                gateway VARCHAR(50) DEFAULT 'twilio',
                INDEX idx_phone (phone_number),
                INDEX idx_user (user_id),
                INDEX idx_expires (expires_at),
                INDEX idx_status (status),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        print("✓ Created ussd_sessions table")
        
        # Create USSD transactions table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_transactions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255),
                phone_number VARCHAR(20) NOT NULL,
                user_id INT DEFAULT NULL,
                transaction_type VARCHAR(100),
                menu_path VARCHAR(500),
                input_text VARCHAR(255),
                response_text TEXT,
                status VARCHAR(20),
                error_message VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processing_time_ms INT,
                INDEX idx_phone (phone_number),
                INDEX idx_user (user_id),
                INDEX idx_type (transaction_type),
                INDEX idx_date (created_at),
                INDEX idx_session (session_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created ussd_transactions table")
        
        # Create USSD OTP table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_otp (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL,
                user_id INT DEFAULT NULL,
                otp_code VARCHAR(6) NOT NULL,
                otp_type VARCHAR(50) DEFAULT 'registration',
                attempts INT DEFAULT 0,
                max_attempts INT DEFAULT 3,
                is_used BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                verified_at TIMESTAMP NULL,
                INDEX idx_phone (phone_number),
                INDEX idx_user (user_id),
                INDEX idx_expires (expires_at),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        ''')
        print("✓ Created ussd_otp table")
        
        # Create USSD emergency alerts table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_emergency_alerts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                emergency_triage_id INT,
                ussd_session_id VARCHAR(255),
                phone_number VARCHAR(20) NOT NULL,
                severity_level INT DEFAULT 3,
                symptoms VARCHAR(255),
                latitude DECIMAL(10, 8),
                longitude DECIMAL(11, 8),
                doctors_notified INT DEFAULT 0,
                sms_sent BOOLEAN DEFAULT FALSE,
                whatsapp_sent BOOLEAN DEFAULT FALSE,
                response_time_seconds INT DEFAULT NULL,
                first_doctor_assigned_at TIMESTAMP NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP NULL,
                INDEX idx_phone (phone_number),
                INDEX idx_severity (severity_level),
                INDEX idx_status (status)
            )
        ''')
        print("✓ Created ussd_emergency_alerts table")
        
        # Create USSD appointments table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_appointments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL,
                user_id INT DEFAULT NULL,
                doctor_id INT,
                specialization VARCHAR(100),
                appointment_type VARCHAR(50) DEFAULT 'ussd',
                appointment_date DATE NOT NULL,
                appointment_time TIME,
                symptoms VARCHAR(255),
                status VARCHAR(20) DEFAULT 'pending',
                confirmation_sms_sent BOOLEAN DEFAULT FALSE,
                reminder_sms_sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scheduled_at TIMESTAMP NULL,
                completed_at TIMESTAMP NULL,
                INDEX idx_phone (phone_number),
                INDEX idx_user (user_id),
                INDEX idx_date (appointment_date),
                INDEX idx_status (status),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created ussd_appointments table")
        
        # Create USSD linked phones table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_linked_phones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                phone_number VARCHAR(20) NOT NULL UNIQUE,
                phone_type VARCHAR(50) DEFAULT 'primary',
                verified BOOLEAN DEFAULT FALSE,
                verified_at TIMESTAMP NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_used TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user (user_id),
                INDEX idx_phone (phone_number),
                INDEX idx_verified (verified),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created ussd_linked_phones table")
        
        # Create USSD SMS credits table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_sms_credits (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL,
                user_id INT DEFAULT NULL,
                sms_sent INT DEFAULT 0,
                sms_limit INT DEFAULT 50,
                sms_used INT DEFAULT 0,
                sms_remaining INT DEFAULT 50,
                refresh_at TIMESTAMP DEFAULT (DATE_ADD(NOW(), INTERVAL 1 MONTH)),
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_phone (phone_number),
                INDEX idx_user (user_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created ussd_sms_credits table")
        
        # Create USSD error logs table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_error_logs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                session_id VARCHAR(255),
                phone_number VARCHAR(20),
                error_type VARCHAR(100),
                error_message TEXT,
                stack_trace TEXT,
                user_agent VARCHAR(255),
                gateway_response TEXT,
                severity VARCHAR(20) DEFAULT 'warning',
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TIMESTAMP NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_type (error_type),
                INDEX idx_phone (phone_number),
                INDEX idx_severity (severity),
                INDEX idx_resolved (resolved)
            )
        ''')
        print("✓ Created ussd_error_logs table")
        
        # Create USSD menu analytics table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_menu_analytics (
                id INT AUTO_INCREMENT PRIMARY KEY,
                menu_choice VARCHAR(50),
                menu_name VARCHAR(100),
                total_selections INT DEFAULT 0,
                successful_completions INT DEFAULT 0,
                abandoned_count INT DEFAULT 0,
                avg_response_time_ms INT,
                last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_menu (menu_choice),
                INDEX idx_name (menu_name)
            )
        ''')
        print("✓ Created ussd_menu_analytics table")
        
        # Create USSD language preferences table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS ussd_language_preferences (
                id INT AUTO_INCREMENT PRIMARY KEY,
                phone_number VARCHAR(20) NOT NULL UNIQUE,
                user_id INT,
                language VARCHAR(10) DEFAULT 'en',
                preferred_on_switch BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        print("✓ Created ussd_language_preferences table")
        
        # Extend users table with USSD fields (if not exist)
        try:
            cur.execute("ALTER TABLE users ADD COLUMN ussd_enabled BOOLEAN DEFAULT FALSE")
        except:
            pass  # Column already exists
        try:
            cur.execute("ALTER TABLE users ADD COLUMN ussd_phone VARCHAR(20)")
        except:
            pass  # Column already exists
        try:
            cur.execute("ALTER TABLE users ADD COLUMN ussd_verified BOOLEAN DEFAULT FALSE")
        except:
            pass  # Column already exists
        try:
            cur.execute("ALTER TABLE users ADD COLUMN last_ussd_activity TIMESTAMP NULL")
        except:
            pass  # Column already exists
        print("✓ Extended users table with USSD fields")
        
        # Initialize sample menu analytics data
        cur.execute("DELETE FROM ussd_menu_analytics")
        sample_menus = [
            ('1', 'symptom_checker'),
            ('2', 'emergency_alert'),
            ('3', 'book_doctor'),
            ('4', 'medications'),
            ('5', 'health_history'),
            ('0', 'exit')
        ]
        for choice, name in sample_menus:
            cur.execute(
                "INSERT INTO ussd_menu_analytics (menu_choice, menu_name) VALUES (%s, %s)",
                (choice, name)
            )
        print("✓ Initialized menu analytics data")
        
        conn.commit()
        conn.close()
        
        print("\n✅ All USSD database tables created successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Database setup failed: {str(e)}")
        return False

if __name__ == '__main__':
    success = apply_ussd_schema()
    sys.exit(0 if success else 1)
