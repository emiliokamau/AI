-- ==================== USSD Support Tables ====================
-- Database schema for USSD integration
-- Created: February 2026

-- 1. USSD SESSIONS TABLE
-- Stores active USSD session data for state management
CREATE TABLE IF NOT EXISTS ussd_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    user_id INT DEFAULT NULL,
    session_data JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'active',  -- active, completed, expired, error
    gateway VARCHAR(50) DEFAULT 'africastalking',  -- africastalking, twilio
    
    INDEX idx_phone (phone_number),
    INDEX idx_user (user_id),
    INDEX idx_expires (expires_at),
    INDEX idx_status (status),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- 2. USSD TRANSACTIONS LOG
-- Audit trail for all USSD operations
CREATE TABLE IF NOT EXISTS ussd_transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    phone_number VARCHAR(20) NOT NULL,
    user_id INT DEFAULT NULL,
    transaction_type VARCHAR(100),  -- symptom_check, emergency_alert, booking, etc
    menu_path VARCHAR(500),  -- 1*2*3 navigation
    input_text VARCHAR(255),
    response_text TEXT,
    status VARCHAR(20),  -- success, error, timeout
    error_message VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_time_ms INT,  -- Response time in milliseconds
    
    INDEX idx_phone (phone_number),
    INDEX idx_user (user_id),
    INDEX idx_type (transaction_type),
    INDEX idx_date (created_at),
    INDEX idx_session (session_id),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (session_id) REFERENCES ussd_sessions(session_id) ON DELETE CASCADE
);

-- 3. USSD OTP TABLE
-- One-Time Passwords for phone-based authentication
CREATE TABLE IF NOT EXISTS ussd_otp (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    user_id INT DEFAULT NULL,
    otp_code VARCHAR(6) NOT NULL,
    otp_type VARCHAR(50) DEFAULT 'registration',  -- registration, verification, password_reset
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
);

-- 4. USSD EMERGENCY ALERTS (Extended from emergency_triages)
-- Tracks emergency alerts specifically sent via USSD
CREATE TABLE IF NOT EXISTS ussd_emergency_alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    emergency_triage_id INT NOT NULL,
    ussd_session_id VARCHAR(255),
    phone_number VARCHAR(20) NOT NULL,
    severity_level INT DEFAULT 3,  -- 1-5
    symptoms VARCHAR(255),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    doctors_notified INT DEFAULT 0,
    sms_sent BOOLEAN DEFAULT FALSE,
    whatsapp_sent BOOLEAN DEFAULT FALSE,
    response_time_seconds INT DEFAULT NULL,
    first_doctor_assigned_at TIMESTAMP NULL,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, notified, assigned, resolved
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP NULL,
    
    INDEX idx_phone (phone_number),
    INDEX idx_severity (severity_level),
    INDEX idx_status (status),
    
    FOREIGN KEY (emergency_triage_id) REFERENCES emergency_triages(id) ON DELETE CASCADE,
    FOREIGN KEY (ussd_session_id) REFERENCES ussd_sessions(session_id) ON DELETE SET NULL
);

-- 5. USSD APPOINTMENTS (Extended)
-- Bookings made via USSD
CREATE TABLE IF NOT EXISTS ussd_appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    user_id INT DEFAULT NULL,
    doctor_id INT NOT NULL,
    specialization VARCHAR(100),
    appointment_type VARCHAR(50) DEFAULT 'ussd',  -- ussd, web, in-person
    appointment_date DATE NOT NULL,
    appointment_time TIME,
    symptoms VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending',  -- pending, confirmed, completed, cancelled
    confirmation_sms_sent BOOLEAN DEFAULT FALSE,
    reminder_sms_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    scheduled_at TIMESTAMP NULL,
    completed_at TIMESTAMP NULL,
    
    INDEX idx_phone (phone_number),
    INDEX idx_user (user_id),
    INDEX idx_doctor (doctor_id),
    INDEX idx_date (appointment_date),
    INDEX idx_status (status),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES users(id) ON DELETE RESTRICT
);

-- 6. USSD LINKED PHONES
-- Phone numbers registered to user accounts for USSD access
CREATE TABLE IF NOT EXISTS ussd_linked_phones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    phone_type VARCHAR(50) DEFAULT 'primary',  -- primary, secondary, emergency
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_used TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user (user_id),
    INDEX idx_phone (phone_number),
    INDEX idx_verified (verified),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 7. USSD SMS CREDITS
-- Tracks SMS credit usage for USSD operations
CREATE TABLE IF NOT EXISTS ussd_sms_credits (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    user_id INT DEFAULT NULL,
    sms_sent INT DEFAULT 0,
    sms_limit INT DEFAULT 50,  -- Monthly limit
    sms_used INT DEFAULT 0,
    sms_remaining INT DEFAULT 50,
    refresh_at TIMESTAMP DEFAULT DATE_ADD(NOW(), INTERVAL 1 MONTH),
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_phone (phone_number),
    INDEX idx_user (user_id),
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 8. USSD ERROR LOGS
-- Tracks errors and issues for debugging
CREATE TABLE IF NOT EXISTS ussd_error_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(255),
    phone_number VARCHAR(20),
    error_type VARCHAR(100),  -- session_timeout, invalid_input, gateway_error, db_error
    error_message TEXT,
    stack_trace TEXT,
    user_agent VARCHAR(255),
    gateway_response TEXT,
    severity VARCHAR(20) DEFAULT 'warning',  -- info, warning, error, critical
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_type (error_type),
    INDEX idx_phone (phone_number),
    INDEX idx_severity (severity),
    INDEX idx_resolved (resolved)
);

-- 9. USSD MENU ANALYTICS
-- Tracks which menu items are used most
CREATE TABLE IF NOT EXISTS ussd_menu_analytics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    menu_choice VARCHAR(50),  -- 1, 2, 3, etc
    menu_name VARCHAR(100),  -- symptom_checker, emergency_alert, etc
    total_selections INT DEFAULT 0,
    successful_completions INT DEFAULT 0,
    abandoned_count INT DEFAULT 0,
    avg_response_time_ms INT,
    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE KEY unique_menu (menu_choice),
    INDEX idx_name (menu_name)
);

-- 10. USSD LANGUAGE PREFERENCES
-- Store preferred language for USSD interactions
CREATE TABLE IF NOT EXISTS ussd_language_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    user_id INT,
    language VARCHAR(10) DEFAULT 'en',  -- en, sw, fr, ar, etc
    preferred_on_switch BOOLEAN DEFAULT FALSE,  -- Offer language switch?
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ==================== EXTENDED USER TABLE FIELDS ====================
-- Add these columns to your existing users table if they don't exist

ALTER TABLE users ADD COLUMN IF NOT EXISTS ussd_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS ussd_phone VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS ussd_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_ussd_activity TIMESTAMP NULL;

-- ==================== INDEXES FOR PERFORMANCE ====================

-- Performance indexes for USSD operations
CREATE INDEX IF NOT EXISTS idx_ussd_sessions_expires ON ussd_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_ussd_transactions_date ON ussd_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_ussd_emergency_severity ON ussd_emergency_alerts(severity_level, created_at);
CREATE INDEX IF NOT EXISTS idx_ussd_appointments_doctor ON ussd_appointments(doctor_id, appointment_date);

-- ==================== STORED PROCEDURES ====================

-- Cleanup expired sessions
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS cleanup_expired_ussd_sessions()
BEGIN
    DELETE FROM ussd_sessions 
    WHERE expires_at < NOW() 
    OR (DATE_ADD(created_at, INTERVAL 10 MINUTE) < NOW() AND status = 'active');
    
    DELETE FROM ussd_otp 
    WHERE expires_at < NOW();
END//
DELIMITER ;

-- Get session statistics
DELIMITER //
CREATE PROCEDURE IF NOT EXISTS get_ussd_statistics(
    IN p_start_date DATETIME,
    IN p_end_date DATETIME
)
BEGIN
    SELECT 
        COUNT(DISTINCT session_id) as total_sessions,
        COUNT(DISTINCT phone_number) as unique_phones,
        COUNT(*) as total_transactions,
        AVG(processing_time_ms) as avg_response_time,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_transactions,
        SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as failed_transactions
    FROM ussd_transactions
    WHERE created_at BETWEEN p_start_date AND p_end_date;
END//
DELIMITER ;

-- ==================== VIEWS FOR REPORTING ====================

-- Active USSD users
CREATE OR REPLACE VIEW active_ussd_users AS
SELECT 
    u.id,
    u.username,
    u.contact,
    ulp.phone_number,
    ulp.verified,
    MAX(us.last_activity) as last_activity,
    COUNT(ut.id) as transaction_count
FROM users u
LEFT JOIN ussd_linked_phones ulp ON u.id = ulp.user_id
LEFT JOIN ussd_sessions us ON ulp.phone_number = us.phone_number
LEFT JOIN ussd_transactions ut ON us.session_id = ut.session_id
WHERE ulp.is_active = TRUE
GROUP BY u.id, ulp.phone_number;

-- USSD Emergency statistics
CREATE OR REPLACE VIEW ussd_emergency_stats AS
SELECT 
    DATE(created_at) as emergency_date,
    severity_level,
    COUNT(*) as count,
    SUM(CASE WHEN doctors_notified > 0 THEN 1 ELSE 0 END) as notified_count,
    AVG(CASE WHEN response_time_seconds IS NOT NULL THEN response_time_seconds ELSE NULL END) as avg_response_time
FROM ussd_emergency_alerts
GROUP BY DATE(created_at), severity_level;

-- ==================== SAMPLE DATA ====================

-- Insert sample menu analytics
INSERT INTO ussd_menu_analytics (menu_choice, menu_name, total_selections, successful_completions)
VALUES 
    ('1', 'symptom_checker', 0, 0),
    ('2', 'emergency_alert', 0, 0),
    ('3', 'book_doctor', 0, 0),
    ('4', 'medications', 0, 0),
    ('5', 'health_history', 0, 0),
    ('0', 'exit', 0, 0);
