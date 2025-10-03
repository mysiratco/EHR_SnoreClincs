#!/usr/bin/env python3
"""
Comprehensive Backend Testing for EHR System
Tests authentication, patient management, SOAP notes, and complete workflow
"""

import requests
import json
import uuid
from datetime import datetime, timezone
import sys

# Backend URL from environment
BACKEND_URL = "https://medtrack-clinic.preview.emergentagent.com/api"

# Demo credentials for testing
DEMO_CREDENTIALS = {
    "super_admin": {"email": "admin@clinic.com", "password": "admin123"},
    "front_desk": {"email": "frontdesk@clinic.com", "password": "front123"},
    "doctor": {"email": "doctor@clinic.com", "password": "doctor123"},
    "patient": {"email": "patient@example.com", "password": "patient123"}
}

class EHRTester:
    def __init__(self):
        self.tokens = {}
        self.test_results = []
        self.created_patient_id = None
        self.created_soap_notes_id = None
        
    def log_result(self, test_name, success, message="", details=""):
        """Log test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "message": message,
            "details": details
        }
        self.test_results.append(result)
        print(f"{status}: {test_name}")
        if message:
            print(f"   Message: {message}")
        if details and not success:
            print(f"   Details: {details}")
        print()

    def test_health_check(self):
        """Test API health check"""
        try:
            response = requests.get(f"{BACKEND_URL}/")
            if response.status_code == 200:
                data = response.json()
                self.log_result("Health Check", True, f"API is running: {data.get('message', '')}")
                return True
            else:
                self.log_result("Health Check", False, f"Status code: {response.status_code}")
                return False
        except Exception as e:
            self.log_result("Health Check", False, f"Connection failed: {str(e)}")
            return False

    def test_authentication(self):
        """Test authentication for all user roles"""
        print("=== AUTHENTICATION TESTING ===")
        
        for role, credentials in DEMO_CREDENTIALS.items():
            try:
                response = requests.post(f"{BACKEND_URL}/login", json=credentials)
                
                if response.status_code == 200:
                    data = response.json()
                    token = data.get("access_token")
                    user_info = data.get("user", {})
                    
                    if token and user_info.get("role") == role:
                        self.tokens[role] = token
                        self.log_result(f"Login - {role}", True, 
                                      f"User: {user_info.get('name')}, Role: {user_info.get('role')}")
                    else:
                        self.log_result(f"Login - {role}", False, "Invalid token or role mismatch")
                else:
                    self.log_result(f"Login - {role}", False, 
                                  f"Status: {response.status_code}, Response: {response.text}")
                    
            except Exception as e:
                self.log_result(f"Login - {role}", False, f"Exception: {str(e)}")

    def test_jwt_validation(self):
        """Test JWT token validation"""
        print("=== JWT TOKEN VALIDATION ===")
        
        for role, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{BACKEND_URL}/me", headers=headers)
                
                if response.status_code == 200:
                    user_data = response.json()
                    if user_data.get("role") == role:
                        self.log_result(f"JWT Validation - {role}", True, 
                                      f"Token valid for {user_data.get('name')}")
                    else:
                        self.log_result(f"JWT Validation - {role}", False, "Role mismatch")
                else:
                    self.log_result(f"JWT Validation - {role}", False, 
                                  f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_result(f"JWT Validation - {role}", False, f"Exception: {str(e)}")

    def test_role_based_access_control(self):
        """Test role-based access control"""
        print("=== ROLE-BASED ACCESS CONTROL ===")
        
        # Test patient creation - only front_desk and super_admin should succeed
        patient_data = {
            "name": "Test Patient",
            "email": f"testpatient_{uuid.uuid4().hex[:8]}@example.com",
            "phone": "+91-9876543210",
            "date_of_birth": "1985-05-15",
            "gender": "Female",
            "address": "456 Test St, Test City",
            "emergency_contact": "+91-9876543211",
            "medical_history": "No known allergies"
        }
        
        for role, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.post(f"{BACKEND_URL}/patients", 
                                       json=patient_data, headers=headers)
                
                if role in ["front_desk", "super_admin"]:
                    if response.status_code == 200:
                        self.log_result(f"Patient Creation Access - {role}", True, 
                                      "Authorized role can create patients")
                        if role == "front_desk":  # Save for later tests
                            self.created_patient_id = response.json().get("id")
                    else:
                        self.log_result(f"Patient Creation Access - {role}", False, 
                                      f"Authorized role failed: {response.status_code}")
                else:
                    if response.status_code == 403:
                        self.log_result(f"Patient Creation Access - {role}", True, 
                                      "Unauthorized role correctly blocked")
                    else:
                        self.log_result(f"Patient Creation Access - {role}", False, 
                                      f"Should be blocked but got: {response.status_code}")
                        
            except Exception as e:
                self.log_result(f"Patient Creation Access - {role}", False, f"Exception: {str(e)}")

    def test_patient_management(self):
        """Test patient management operations"""
        print("=== PATIENT MANAGEMENT ===")
        
        if not self.created_patient_id:
            self.log_result("Patient Management Setup", False, "No patient created for testing")
            return
            
        # Test patient retrieval
        for role, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{BACKEND_URL}/patients", headers=headers)
                
                if response.status_code == 200:
                    patients = response.json()
                    if role == "patient":
                        # Patients should only see their own record
                        patient_emails = [p.get("email") for p in patients]
                        if len(patients) <= 1 and DEMO_CREDENTIALS["patient"]["email"] in patient_emails:
                            self.log_result(f"Patient List Access - {role}", True, 
                                          "Patient can only see own record")
                        else:
                            self.log_result(f"Patient List Access - {role}", False, 
                                          "Patient can see other records")
                    else:
                        self.log_result(f"Patient List Access - {role}", True, 
                                      f"Retrieved {len(patients)} patients")
                else:
                    self.log_result(f"Patient List Access - {role}", False, 
                                  f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_result(f"Patient List Access - {role}", False, f"Exception: {str(e)}")

        # Test patient status update
        if "front_desk" in self.tokens:
            try:
                headers = {"Authorization": f"Bearer {self.tokens['front_desk']}"}
                doctor_id = None
                
                # Get doctor ID first
                if "doctor" in self.tokens:
                    doctor_headers = {"Authorization": f"Bearer {self.tokens['doctor']}"}
                    me_response = requests.get(f"{BACKEND_URL}/me", headers=doctor_headers)
                    if me_response.status_code == 200:
                        doctor_id = me_response.json().get("id")
                
                # Update patient status to consulting and assign doctor
                update_data = {
                    "status": "consulting"
                }
                if doctor_id:
                    update_data["assigned_doctor_id"] = doctor_id
                
                response = requests.put(f"{BACKEND_URL}/patients/{self.created_patient_id}/status",
                                      params=update_data, headers=headers)
                
                if response.status_code == 200:
                    self.log_result("Patient Status Update", True, 
                                  "Status updated to consulting with doctor assignment")
                else:
                    self.log_result("Patient Status Update", False, 
                                  f"Status: {response.status_code}, Response: {response.text}")
                    
            except Exception as e:
                self.log_result("Patient Status Update", False, f"Exception: {str(e)}")

    def test_soap_notes_workflow(self):
        """Test SOAP notes creation and retrieval"""
        print("=== SOAP NOTES WORKFLOW ===")
        
        if not self.created_patient_id or "doctor" not in self.tokens:
            self.log_result("SOAP Notes Setup", False, "Missing patient ID or doctor token")
            return
            
        # Test SOAP notes creation by doctor
        soap_data = {
            "patient_id": self.created_patient_id,
            "subjective": "Patient reports mild headache and fatigue for 2 days",
            "objective": "BP: 120/80, Temp: 98.6°F, Alert and oriented",
            "assessment": "Likely viral syndrome, rule out tension headache",
            "plan": "Rest, hydration, OTC pain relief. Follow up in 3 days if symptoms persist"
        }
        
        try:
            headers = {"Authorization": f"Bearer {self.tokens['doctor']}"}
            response = requests.post(f"{BACKEND_URL}/soap-notes", 
                                   json=soap_data, headers=headers)
            
            if response.status_code == 200:
                soap_notes = response.json()
                self.created_soap_notes_id = soap_notes.get("id")
                self.log_result("SOAP Notes Creation", True, 
                              f"Created SOAP notes for patient")
                
                # Verify patient status auto-updated to completed
                patient_response = requests.get(f"{BACKEND_URL}/patients/{self.created_patient_id}",
                                              headers=headers)
                if patient_response.status_code == 200:
                    patient = patient_response.json()
                    if patient.get("status") == "completed":
                        self.log_result("Patient Status Auto-Update", True, 
                                      "Patient status automatically updated to completed")
                    else:
                        self.log_result("Patient Status Auto-Update", False, 
                                      f"Status is {patient.get('status')}, expected 'completed'")
                        
            else:
                self.log_result("SOAP Notes Creation", False, 
                              f"Status: {response.status_code}, Response: {response.text}")
                
        except Exception as e:
            self.log_result("SOAP Notes Creation", False, f"Exception: {str(e)}")

        # Test SOAP notes retrieval
        for role, token in self.tokens.items():
            if role in ["doctor", "patient", "super_admin"]:
                try:
                    headers = {"Authorization": f"Bearer {token}"}
                    response = requests.get(f"{BACKEND_URL}/soap-notes/{self.created_patient_id}",
                                          headers=headers)
                    
                    if response.status_code == 200:
                        notes = response.json()
                        if len(notes) > 0:
                            self.log_result(f"SOAP Notes Retrieval - {role}", True, 
                                          f"Retrieved {len(notes)} SOAP notes")
                        else:
                            self.log_result(f"SOAP Notes Retrieval - {role}", False, 
                                          "No SOAP notes found")
                    else:
                        self.log_result(f"SOAP Notes Retrieval - {role}", False, 
                                      f"Status: {response.status_code}")
                        
                except Exception as e:
                    self.log_result(f"SOAP Notes Retrieval - {role}", False, f"Exception: {str(e)}")

    def test_dashboard_statistics(self):
        """Test dashboard statistics for different roles"""
        print("=== DASHBOARD STATISTICS ===")
        
        for role, token in self.tokens.items():
            try:
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{BACKEND_URL}/dashboard/stats", headers=headers)
                
                if response.status_code == 200:
                    stats = response.json()
                    
                    if role in ["super_admin", "front_desk"]:
                        expected_keys = ["total_patients", "registered_patients", 
                                       "consulting_patients", "completed_patients"]
                        if all(key in stats for key in expected_keys):
                            self.log_result(f"Dashboard Stats - {role}", True, 
                                          f"Admin stats: {stats}")
                        else:
                            self.log_result(f"Dashboard Stats - {role}", False, 
                                          f"Missing expected keys: {stats}")
                    elif role == "doctor":
                        expected_keys = ["assigned_patients", "consulting_patients"]
                        if all(key in stats for key in expected_keys):
                            self.log_result(f"Dashboard Stats - {role}", True, 
                                          f"Doctor stats: {stats}")
                        else:
                            self.log_result(f"Dashboard Stats - {role}", False, 
                                          f"Missing expected keys: {stats}")
                    else:  # patient
                        # Patients might get empty stats or specific patient stats
                        self.log_result(f"Dashboard Stats - {role}", True, 
                                      f"Patient stats: {stats}")
                else:
                    self.log_result(f"Dashboard Stats - {role}", False, 
                                  f"Status: {response.status_code}")
                    
            except Exception as e:
                self.log_result(f"Dashboard Stats - {role}", False, f"Exception: {str(e)}")

    def test_edge_cases(self):
        """Test edge cases and error handling"""
        print("=== EDGE CASES ===")
        
        # Test unauthorized access
        try:
            response = requests.get(f"{BACKEND_URL}/patients")
            if response.status_code == 401:
                self.log_result("Unauthorized Access Block", True, 
                              "Correctly blocked request without token")
            else:
                self.log_result("Unauthorized Access Block", False, 
                              f"Should be 401 but got: {response.status_code}")
        except Exception as e:
            self.log_result("Unauthorized Access Block", False, f"Exception: {str(e)}")

        # Test invalid token
        try:
            headers = {"Authorization": "Bearer invalid-token"}
            response = requests.get(f"{BACKEND_URL}/me", headers=headers)
            if response.status_code == 401:
                self.log_result("Invalid Token Block", True, 
                              "Correctly blocked request with invalid token")
            else:
                self.log_result("Invalid Token Block", False, 
                              f"Should be 401 but got: {response.status_code}")
        except Exception as e:
            self.log_result("Invalid Token Block", False, f"Exception: {str(e)}")

        # Test duplicate email registration
        try:
            duplicate_user = {
                "email": "admin@clinic.com",  # Already exists
                "password": "newpassword",
                "name": "Duplicate Admin",
                "role": "super_admin"
            }
            response = requests.post(f"{BACKEND_URL}/register", json=duplicate_user)
            if response.status_code == 400:
                self.log_result("Duplicate Email Block", True, 
                              "Correctly blocked duplicate email registration")
            else:
                self.log_result("Duplicate Email Block", False, 
                              f"Should be 400 but got: {response.status_code}")
        except Exception as e:
            self.log_result("Duplicate Email Block", False, f"Exception: {str(e)}")

    def test_user_management(self):
        """Test user management (super admin only)"""
        print("=== USER MANAGEMENT ===")
        
        if "super_admin" not in self.tokens:
            self.log_result("User Management Setup", False, "No super admin token available")
            return
            
        try:
            headers = {"Authorization": f"Bearer {self.tokens['super_admin']}"}
            response = requests.get(f"{BACKEND_URL}/users", headers=headers)
            
            if response.status_code == 200:
                users = response.json()
                if len(users) >= 4:  # At least the 4 demo users
                    self.log_result("User Management - Super Admin", True, 
                                  f"Retrieved {len(users)} users")
                else:
                    self.log_result("User Management - Super Admin", False, 
                                  f"Expected at least 4 users, got {len(users)}")
            else:
                self.log_result("User Management - Super Admin", False, 
                              f"Status: {response.status_code}")
                
        except Exception as e:
            self.log_result("User Management - Super Admin", False, f"Exception: {str(e)}")

        # Test that non-super-admin cannot access user list
        for role in ["front_desk", "doctor", "patient"]:
            if role in self.tokens:
                try:
                    headers = {"Authorization": f"Bearer {self.tokens[role]}"}
                    response = requests.get(f"{BACKEND_URL}/users", headers=headers)
                    
                    if response.status_code == 403:
                        self.log_result(f"User Management Block - {role}", True, 
                                      "Correctly blocked non-admin access")
                    else:
                        self.log_result(f"User Management Block - {role}", False, 
                                      f"Should be 403 but got: {response.status_code}")
                except Exception as e:
                    self.log_result(f"User Management Block - {role}", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🏥 EHR SYSTEM BACKEND TESTING")
        print("=" * 50)
        
        # Health check first
        if not self.test_health_check():
            print("❌ Backend is not accessible. Stopping tests.")
            return False
            
        # Core authentication tests
        self.test_authentication()
        self.test_jwt_validation()
        
        # Role-based access and workflow tests
        self.test_role_based_access_control()
        self.test_patient_management()
        self.test_soap_notes_workflow()
        self.test_dashboard_statistics()
        self.test_user_management()
        
        # Edge cases
        self.test_edge_cases()
        
        # Summary
        self.print_summary()
        return True

    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 50)
        print("📊 TEST SUMMARY")
        print("=" * 50)
        
        passed = sum(1 for result in self.test_results if "✅ PASS" in result["status"])
        failed = sum(1 for result in self.test_results if "❌ FAIL" in result["status"])
        total = len(self.test_results)
        
        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/total*100):.1f}%" if total > 0 else "0%")
        
        if failed > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if "❌ FAIL" in result["status"]:
                    print(f"  - {result['test']}: {result['message']}")
        
        print("\n" + "=" * 50)

if __name__ == "__main__":
    tester = EHRTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)