from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone
import bcrypt
import jwt
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Secret
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-here')
JWT_ALGORITHM = 'HS256'

# Security
security = HTTPBearer()

# Create the main app
app = FastAPI(title="EHR System API")
api_router = APIRouter(prefix="/api")

# Enums
class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    FRONT_DESK = "front_desk"
    DOCTOR = "doctor"
    PATIENT = "patient"

class PatientStatus(str, Enum):
    REGISTERED = "registered"
    CONSULTING = "consulting"
    COMPLETED = "completed"

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: UserRole
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    role: UserRole

class UserLogin(BaseModel):
    email: str
    password: str

class Patient(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str = Field(default_factory=lambda: f"P{str(uuid.uuid4())[:8].upper()}")
    name: str
    email: str
    phone: str
    date_of_birth: str
    gender: str
    address: str
    emergency_contact: str
    medical_history: str
    status: PatientStatus = PatientStatus.REGISTERED
    assigned_doctor_id: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PatientCreate(BaseModel):
    name: str
    email: str
    phone: str
    date_of_birth: str
    gender: str
    address: str
    emergency_contact: str
    medical_history: str

class SOAPNotes(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    doctor_id: str
    subjective: str
    objective: str
    assessment: str
    plan: str
    consultation_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SOAPNotesCreate(BaseModel):
    patient_id: str
    subjective: str
    objective: str
    assessment: str
    plan: str

class Appointment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    patient_id: str
    doctor_id: str
    appointment_date: datetime
    status: str = "scheduled"
    notes: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_id: str
    appointment_date: datetime
    notes: str = ""

# Helper functions
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_jwt_token(user_id: str, role: str) -> str:
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': datetime.now(timezone.utc).timestamp() + 86400  # 24 hours
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get('user_id')
        role = payload.get('role')
        
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        user = await db.users.find_one({"id": user_id})
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        
        return User(**user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Authentication routes
@api_router.post("/register")
async def register(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password and create user
    hashed_password = hash_password(user_data.password)
    user_dict = user_data.dict()
    user_dict['password'] = hashed_password
    user = User(**{k: v for k, v in user_dict.items() if k != 'password'})
    
    # Store in database
    user_with_password = user.dict()
    user_with_password['password'] = hashed_password
    await db.users.insert_one(user_with_password)
    
    return {"message": "User registered successfully", "user_id": user.id}

@api_router.post("/login")
async def login(login_data: UserLogin):
    user = await db.users.find_one({"email": login_data.email})
    if not user or not verify_password(login_data.password, user['password']):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_jwt_token(user['id'], user['role'])
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": User(**user)
    }

@api_router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

# Patient management routes
@api_router.post("/patients", response_model=Patient)
async def create_patient(patient_data: PatientCreate, current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.FRONT_DESK, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized to create patients")
    
    patient_dict = patient_data.dict()
    patient_dict['created_by'] = current_user.id
    patient = Patient(**patient_dict)
    
    await db.patients.insert_one(patient.dict())
    return patient

@api_router.get("/patients", response_model=List[Patient])
async def get_patients(current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.PATIENT:
        # Patients can only see their own record
        patient = await db.patients.find_one({"email": current_user.email})
        return [Patient(**patient)] if patient else []
    
    patients = await db.patients.find().to_list(length=None)
    return [Patient(**patient) for patient in patients]

@api_router.get("/patients/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str, current_user: User = Depends(get_current_user)):
    patient = await db.patients.find_one({"id": patient_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Authorization check
    if current_user.role == UserRole.PATIENT and patient['email'] != current_user.email:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return Patient(**patient)

@api_router.put("/patients/{patient_id}/status")
async def update_patient_status(patient_id: str, status: PatientStatus, assigned_doctor_id: Optional[str] = None, current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.FRONT_DESK, UserRole.DOCTOR, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    update_data = {
        "status": status,
        "updated_at": datetime.now(timezone.utc)
    }
    
    if assigned_doctor_id:
        update_data["assigned_doctor_id"] = assigned_doctor_id
    
    result = await db.patients.update_one({"id": patient_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    return {"message": "Patient status updated successfully"}

# SOAP Notes routes
@api_router.post("/soap-notes", response_model=SOAPNotes)
async def create_soap_notes(soap_data: SOAPNotesCreate, current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.DOCTOR, UserRole.SUPER_ADMIN]:
        raise HTTPException(status_code=403, detail="Only doctors can create SOAP notes")
    
    soap_dict = soap_data.dict()
    soap_dict['doctor_id'] = current_user.id
    soap_notes = SOAPNotes(**soap_dict)
    
    await db.soap_notes.insert_one(soap_notes.dict())
    
    # Update patient status to completed
    await db.patients.update_one(
        {"id": soap_data.patient_id},
        {"$set": {"status": PatientStatus.COMPLETED, "updated_at": datetime.now(timezone.utc)}}
    )
    
    return soap_notes

@api_router.get("/soap-notes/{patient_id}", response_model=List[SOAPNotes])
async def get_patient_soap_notes(patient_id: str, current_user: User = Depends(get_current_user)):
    # Check if user can access this patient's records
    patient = await db.patients.find_one({"id": patient_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if current_user.role == UserRole.PATIENT and patient['email'] != current_user.email:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    soap_notes = await db.soap_notes.find({"patient_id": patient_id}).to_list(length=None)
    return [SOAPNotes(**note) for note in soap_notes]

# User management routes (for super admin)
@api_router.get("/users", response_model=List[User])
async def get_users(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super admin can view all users")
    
    users = await db.users.find().to_list(length=None)
    return [User(**user) for user in users]

@api_router.get("/doctors", response_model=List[User])
async def get_doctors(current_user: User = Depends(get_current_user)):
    doctors = await db.users.find({"role": UserRole.DOCTOR}).to_list(length=None)
    return [User(**doctor) for doctor in doctors]

# Appointment routes
@api_router.post("/appointments", response_model=Appointment)
async def create_appointment(appointment_data: AppointmentCreate, current_user: User = Depends(get_current_user)):
    appointment = Appointment(**appointment_data.dict())
    await db.appointments.insert_one(appointment.dict())
    return appointment

@api_router.get("/appointments", response_model=List[Appointment])
async def get_appointments(current_user: User = Depends(get_current_user)):
    query = {}
    
    if current_user.role == UserRole.PATIENT:
        # Find patient record
        patient = await db.patients.find_one({"email": current_user.email})
        if patient:
            query["patient_id"] = patient["id"]
    elif current_user.role == UserRole.DOCTOR:
        query["doctor_id"] = current_user.id
    
    appointments = await db.appointments.find(query).to_list(length=None)
    return [Appointment(**appointment) for appointment in appointments]

# Dashboard stats
@api_router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(get_current_user)):
    stats = {}
    
    if current_user.role in [UserRole.SUPER_ADMIN, UserRole.FRONT_DESK]:
        total_patients = await db.patients.count_documents({})
        registered_patients = await db.patients.count_documents({"status": PatientStatus.REGISTERED})
        consulting_patients = await db.patients.count_documents({"status": PatientStatus.CONSULTING})
        completed_patients = await db.patients.count_documents({"status": PatientStatus.COMPLETED})
        
        stats = {
            "total_patients": total_patients,
            "registered_patients": registered_patients,
            "consulting_patients": consulting_patients,
            "completed_patients": completed_patients
        }
    
    elif current_user.role == UserRole.DOCTOR:
        assigned_patients = await db.patients.count_documents({"assigned_doctor_id": current_user.id})
        consulting_patients = await db.patients.count_documents({
            "assigned_doctor_id": current_user.id,
            "status": PatientStatus.CONSULTING
        })
        
        stats = {
            "assigned_patients": assigned_patients,
            "consulting_patients": consulting_patients
        }
    
    return stats

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

# Initialize sample data
@app.on_event("startup")
async def create_sample_data():
    # Check if super admin exists
    super_admin = await db.users.find_one({"role": "super_admin"})
    
    if not super_admin:
        # Create sample users
        sample_users = [
            {
                "id": str(uuid.uuid4()),
                "email": "admin@clinic.com",
                "password": hash_password("admin123"),
                "name": "Super Admin",
                "role": "super_admin",
                "created_at": datetime.now(timezone.utc),
                "is_active": True
            },
            {
                "id": str(uuid.uuid4()),
                "email": "frontdesk@clinic.com",
                "password": hash_password("front123"),
                "name": "Front Desk Staff",
                "role": "front_desk",
                "created_at": datetime.now(timezone.utc),
                "is_active": True
            },
            {
                "id": str(uuid.uuid4()),
                "email": "doctor@clinic.com",
                "password": hash_password("doctor123"),
                "name": "Dr. Smith",
                "role": "doctor",
                "created_at": datetime.now(timezone.utc),
                "is_active": True
            },
            {
                "id": str(uuid.uuid4()),
                "email": "patient@example.com",
                "password": hash_password("patient123"),
                "name": "John Doe",
                "role": "patient",
                "created_at": datetime.now(timezone.utc),
                "is_active": True
            }
        ]
        
        await db.users.insert_many(sample_users)
        
        # Create sample patient record
        sample_patient = {
            "id": str(uuid.uuid4()),
            "patient_id": "P12345678",
            "name": "John Doe",
            "email": "patient@example.com",
            "phone": "+91-9876543210",
            "date_of_birth": "1990-01-15",
            "gender": "Male",
            "address": "123 Main St, Hyderabad, Telangana",
            "emergency_contact": "+91-9876543211",
            "medical_history": "No known allergies. Previous history of hypertension.",
            "status": "registered",
            "created_by": sample_users[1]["id"],  # Front desk
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc)
        }
        
        await db.patients.insert_one(sample_patient)
        
        logger.info("Sample data created successfully")
