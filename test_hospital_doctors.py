#!/usr/bin/env python3
"""
Test suite for Hospital Doctor Management System
Tests hospital-doctor associations, professionalism tracking, and AI-powered doctor matching
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
HEADERS = {"Content-Type": "application/json"}

# Test data
TEST_HOSPITAL_ID = 1
TEST_DOCTOR_USER_ID = 5  # Assume doctor exists
TEST_PATIENT_USER_ID = 10  # Assume patient exists
TEST_TOKEN = None  # Will be set after login

def set_auth_header(token):
    """Update auth header with token"""
    global HEADERS
    HEADERS["Authorization"] = f"Bearer {token}"

def test_setup():
    """Setup test environment - login to get token"""
    print("\n" + "="*60)
    print("TEST SETUP: Authentication")
    print("="*60)
    
    global TEST_TOKEN
    
    # This assumes users exist. Adjust credentials as needed.
    login_data = {
        "username": "testdoctor",
        "password": "password123"
    }
    
    try:
        resp = requests.post(f"{BASE_URL}/login", json=login_data, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            TEST_TOKEN = data.get('access_token')
            set_auth_header(TEST_TOKEN)
            print(f"✓ Login successful, token: {TEST_TOKEN[:20]}...")
            return True
        else:
            print(f"✗ Login failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error during login: {e}")
        return False

# ==================== TEST CASES ====================

def test_get_hospital_doctors():
    """Test GET /hospital/<id>/doctors"""
    print("\n" + "="*60)
    print("TEST 1: Get Hospital Doctors")
    print("="*60)
    
    try:
        url = f"{BASE_URL}/hospital/{TEST_HOSPITAL_ID}/doctors"
        resp = requests.get(url, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Retrieved {data.get('count', 0)} doctors")
            
            if data.get('doctors'):
                doctor = data['doctors'][0]
                print(f"  - Name: {doctor.get('full_name')}")
                print(f"  - Specialization: {doctor.get('specialization')}")
                print(f"  - Overall Rating: {doctor.get('overall_rating', 0)}/5")
                print(f"  - Total Reviews: {doctor.get('total_reviews', 0)}")
                print(f"  - Completed Appointments: {doctor.get('completed_appointments', 0)}")
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_add_doctor_to_hospital():
    """Test POST /hospital/<id>/add-doctor"""
    print("\n" + "="*60)
    print("TEST 2: Add Doctor to Hospital")
    print("="*60)
    
    # Note: Need a doctor_user_id that isn't already in hospital
    add_data = {
        "doctor_user_id": TEST_DOCTOR_USER_ID,
        "department": "Cardiology",
        "position": "Consultant",
        "specialization": "Cardiology"
    }
    
    try:
        url = f"{BASE_URL}/hospital/{TEST_HOSPITAL_ID}/add-doctor"
        resp = requests.post(url, json=add_data, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Doctor added successfully (ID: {data.get('hospital_doctor_id')})")
            return True
        elif resp.status_code == 409:
            print(f"⚠ Doctor already in hospital (expected if re-running)")
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_doctor_professionalism():
    """Test GET /doctor/<id>/professionalism"""
    print("\n" + "="*60)
    print("TEST 3: Get Doctor Professionalism")
    print("="*60)
    
    try:
        url = f"{BASE_URL}/doctor/{TEST_DOCTOR_USER_ID}/professionalism"
        resp = requests.get(url, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            prof = data.get('professionalism', {})
            
            print(f"✓ Retrieved professionalism metrics")
            print(f"  - Overall Rating: {prof.get('overall_rating', 0)}/5")
            print(f"  - Total Reviews: {prof.get('total_reviews', 0)}")
            print(f"  - Patient Satisfaction: {prof.get('patient_satisfaction_score', 0)}/5")
            print(f"  - Completed Appointments: {prof.get('completed_appointments', 0)}")
            print(f"  - Response Time: {prof.get('average_response_time_minutes', 0)} min")
            print(f"  - Certifications: {len(prof.get('certifications', []))} items")
            print(f"  - Recent Reviews: {len(data.get('recent_reviews', []))} reviews")
            
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_submit_doctor_review():
    """Test POST /doctor/<id>/review"""
    print("\n" + "="*60)
    print("TEST 4: Submit Doctor Review")
    print("="*60)
    
    review_data = {
        "rating": 5,
        "review_text": "Excellent doctor with great bedside manner. Very thorough and professional.",
        "aspects": {
            "professionalism": 5,
            "communication": 5,
            "bedside_manner": 5,
            "appointment_timing": 4
        }
    }
    
    try:
        url = f"{BASE_URL}/doctor/{TEST_DOCTOR_USER_ID}/review"
        resp = requests.post(url, json=review_data, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Review submitted successfully")
            print(f"  - Rating: {review_data['rating']}/5")
            print(f"  - Text: {review_data['review_text']}")
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_get_doctor_reviews():
    """Test GET /doctor/<id>/reviews"""
    print("\n" + "="*60)
    print("TEST 5: Get Doctor Reviews (Paginated)")
    print("="*60)
    
    try:
        url = f"{BASE_URL}/doctor/{TEST_DOCTOR_USER_ID}/reviews?page=1&limit=5&sort_by=recent"
        resp = requests.get(url, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            
            print(f"✓ Retrieved reviews")
            print(f"  - Total Reviews: {data.get('total', 0)}")
            print(f"  - Page: {data.get('page', 1)}/{data.get('pages', 1)}")
            
            reviews = data.get('reviews', [])
            print(f"  - Current Page Count: {len(reviews)}")
            
            for i, review in enumerate(reviews[:3], 1):
                print(f"\n  Review {i}:")
                print(f"    - Rating: {review.get('rating')}/5")
                print(f"    - Reviewer: {review.get('reviewer_name')}")
                print(f"    - Verified: {review.get('is_verified_patient')}")
                print(f"    - Helpful: {review.get('helpful_count')} votes")
                print(f"    - Text: {review.get('review_text', '')[:60]}...")
            
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_ai_recommend_doctor_with_hospital():
    """Test POST /ai/recommend-doctor with hospital_id"""
    print("\n" + "="*60)
    print("TEST 6: AI Doctor Recommendation (Hospital-Filtered)")
    print("="*60)
    
    recommend_data = {
        "symptoms": "chest pain and shortness of breath",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "hospital_id": TEST_HOSPITAL_ID
    }
    
    try:
        url = f"{BASE_URL}/ai/recommend-doctor"
        resp = requests.post(url, json=recommend_data, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            condition = data.get('condition', {})
            doctors = data.get('recommended_doctors', [])
            
            print(f"✓ Got recommendations")
            print(f"  - Condition: {condition.get('primary_specialization')}")
            print(f"  - Confidence: {condition.get('confidence', 0)*100:.0f}%")
            print(f"  - Urgency: {condition.get('urgency_level')}")
            print(f"  - Hospital Filtered: {data.get('hospital_filtered')}")
            print(f"  - Recommended Doctors: {len(doctors)}")
            
            for i, doc in enumerate(doctors[:3], 1):
                print(f"\n  Doctor {i}:")
                print(f"    - Name: {doc.get('full_name')}")
                print(f"    - Hospital: {doc.get('hospital_name')}")
                print(f"    - Specialization: {doc.get('specialization')}")
                print(f"    - Rating: {doc.get('overall_rating')}/5")
                print(f"    - Reviews: {doc.get('total_reviews')}")
                print(f"    - Match Score: {doc.get('match_score')}%")
            
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_ai_recommend_doctor_without_hospital():
    """Test POST /ai/recommend-doctor without hospital filter"""
    print("\n" + "="*60)
    print("TEST 7: AI Doctor Recommendation (All Hospitals)")
    print("="*60)
    
    recommend_data = {
        "symptoms": "headache and fever",
        "latitude": 40.7128,
        "longitude": -74.0060
    }
    
    try:
        url = f"{BASE_URL}/ai/recommend-doctor"
        resp = requests.post(url, json=recommend_data, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            condition = data.get('condition', {})
            doctors = data.get('recommended_doctors', [])
            
            print(f"✓ Got recommendations (no hospital filter)")
            print(f"  - Condition: {condition.get('primary_specialization')}")
            print(f"  - Hospital Filtered: {data.get('hospital_filtered')}")
            print(f"  - Recommended Doctors: {len(doctors)}")
            
            return True
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_remove_doctor_from_hospital():
    """Test DELETE /hospital/<id>/remove-doctor/<doctor_id>"""
    print("\n" + "="*60)
    print("TEST 8: Remove Doctor from Hospital")
    print("="*60)
    
    try:
        url = f"{BASE_URL}/hospital/{TEST_HOSPITAL_ID}/remove-doctor/{TEST_DOCTOR_USER_ID}"
        resp = requests.delete(url, headers=HEADERS)
        
        print(f"Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"✓ Doctor removed from hospital")
            print(f"  - Message: {data.get('message')}")
            return True
        elif resp.status_code == 404:
            print(f"✗ Doctor not found at hospital")
            return False
        else:
            print(f"✗ Failed: {resp.status_code}")
            print(resp.text)
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_error_cases():
    """Test error handling and validation"""
    print("\n" + "="*60)
    print("TEST 9: Error Handling & Validation")
    print("="*60)
    
    tests_passed = 0
    
    # Test invalid rating in review
    print("\n  Testing invalid rating (0)...")
    try:
        resp = requests.post(
            f"{BASE_URL}/doctor/{TEST_DOCTOR_USER_ID}/review",
            json={"rating": 0, "review_text": "test"},
            headers=HEADERS
        )
        if resp.status_code == 400:
            print("    ✓ Correctly rejected invalid rating")
            tests_passed += 1
        else:
            print(f"    ✗ Should reject, got {resp.status_code}")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    # Test missing review text
    print("\n  Testing missing review text...")
    try:
        resp = requests.post(
            f"{BASE_URL}/doctor/{TEST_DOCTOR_USER_ID}/review",
            json={"rating": 4, "review_text": ""},
            headers=HEADERS
        )
        if resp.status_code == 400:
            print("    ✓ Correctly rejected empty review")
            tests_passed += 1
        else:
            print(f"    ✗ Should reject, got {resp.status_code}")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    # Test invalid hospital ID
    print("\n  Testing invalid hospital ID...")
    try:
        resp = requests.get(
            f"{BASE_URL}/hospital/99999/doctors",
            headers=HEADERS
        )
        if resp.status_code in [200, 404]:  # Either empty or not found
            print("    ✓ Handled invalid hospital ID")
            tests_passed += 1
        else:
            print(f"    ✗ Unexpected status {resp.status_code}")
    except Exception as e:
        print(f"    ✗ Error: {e}")
    
    print(f"\n  Error handling tests: {tests_passed}/3 passed")
    return tests_passed == 3

# ==================== MAIN TEST RUNNER ====================

def run_all_tests():
    """Run all test cases"""
    print("\n" + "="*70)
    print(" HOSPITAL DOCTOR MANAGEMENT SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*70)
    print(f"Base URL: {BASE_URL}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Setup
    if not test_setup():
        print("\n✗ Setup failed, cannot run tests")
        return False
    
    # Run tests
    results = {
        "Get Hospital Doctors": test_get_hospital_doctors(),
        "Add Doctor to Hospital": test_add_doctor_to_hospital(),
        "Get Doctor Professionalism": test_get_doctor_professionalism(),
        "Submit Doctor Review": test_submit_doctor_review(),
        "Get Doctor Reviews": test_get_doctor_reviews(),
        "AI Recommend (Hospital-Filtered)": test_ai_recommend_doctor_with_hospital(),
        "AI Recommend (All Hospitals)": test_ai_recommend_doctor_without_hospital(),
        "Remove Doctor from Hospital": test_remove_doctor_from_hospital(),
        "Error Handling": test_error_cases(),
    }
    
    # Summary
    print("\n" + "="*70)
    print(" TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{'='*70}")
    print(f"TOTAL: {passed}/{total} tests passed")
    print(f"{'='*70}\n")
    
    return passed == total

if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
