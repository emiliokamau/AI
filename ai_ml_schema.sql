-- AI/ML Enhancement Database Schema
-- Run this to add new tables for medication tracking, reminders, and predictions

-- Medication schedules table
CREATE TABLE IF NOT EXISTS medication_schedules (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    medication_name VARCHAR(255) NOT NULL,
    dosage VARCHAR(100),
    frequency VARCHAR(100),  -- e.g., "Once daily", "Twice daily", "Every 8 hours"
    times JSON,  -- Array of times like ["08:00", "20:00"]
    start_date DATE,
    end_date DATE,
    notes TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_active (user_id, active)
);

-- Medication intake log (adherence tracking)
CREATE TABLE IF NOT EXISTS medication_intake_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    schedule_id INT NOT NULL,
    user_id INT NOT NULL,
    scheduled_time DATETIME NOT NULL,
    taken_time DATETIME,
    status ENUM('taken', 'missed', 'skipped', 'pending') DEFAULT 'pending',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (schedule_id) REFERENCES medication_schedules(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_status (user_id, status),
    INDEX idx_scheduled (user_id, scheduled_time)
);

-- Health predictions and risk scores
CREATE TABLE IF NOT EXISTS health_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    prediction_type VARCHAR(100) NOT NULL,  -- e.g., 'diabetes_risk', 'hypertension_risk'
    risk_score DECIMAL(5,2),  -- 0-100
    risk_level ENUM('low', 'medium', 'high', 'critical'),
    factors JSON,  -- Contributing factors
    recommendations TEXT,
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- When prediction should be recalculated
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_type (user_id, prediction_type),
    INDEX idx_risk_level (risk_level, predicted_at)
);

-- Medical document uploads (prescriptions, lab results)
CREATE TABLE IF NOT EXISTS medical_documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    document_type VARCHAR(50) NOT NULL,  -- 'prescription', 'lab_result', 'report'
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    extracted_text TEXT,  -- OCR result
    extracted_data JSON,  -- Structured data from document
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_type (user_id, document_type),
    INDEX idx_processed (processed, upload_date)
);

-- AI conversation insights (for context and learning)
CREATE TABLE IF NOT EXISTS conversation_insights (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id INT NOT NULL,
    user_id INT NOT NULL,
    symptoms JSON,  -- Extracted symptoms
    medical_codes JSON,  -- ICD-10/SNOMED codes
    confidence_score DECIMAL(5,2),
    follow_up_needed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_session (session_id),
    INDEX idx_user_followup (user_id, follow_up_needed)
);

-- Wellness recommendations history
CREATE TABLE IF NOT EXISTS wellness_recommendations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category VARCHAR(100),  -- 'Diet', 'Exercise', 'Sleep', etc.
    recommendation TEXT NOT NULL,
    priority ENUM('low', 'medium', 'high') DEFAULT 'medium',
    status ENUM('active', 'completed', 'dismissed') DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_status (user_id, status),
    INDEX idx_category (category, created_at)
);

-- Notification preferences
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
    quiet_hours_start TIME,  -- e.g., "22:00"
    quiet_hours_end TIME,  -- e.g., "08:00"
    timezone VARCHAR(64) DEFAULT 'UTC',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
