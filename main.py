import os

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Any, List, Optional, Dict
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware
from models import (
    User,
    UserUpdate,
    HabitBase,
    KeyInsight,
    Analytics,
    UserHabits,
    UserAnalytics,
    LoginRequest,
    ToggleCompletionRequest
)
from scheduler import init_scheduler
from contextlib import asynccontextmanager

# Initialize FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_scheduler()
    yield
    # Shutdown
    pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://674e18bf34bb7a4af4439ba7--habitai.netlify.app/", "https://habitai.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection details
MONGO_URI = os.environ.get("MONGO_URI")
DATABASE_NAME = os.environ.get("MONGO_DATABASE_NAME", "")
USER_COLLECTION_NAME = os.environ.get("MONGO_USER_COLLECTION_NAME", "")
HABIT_COLLECTION_NAME = os.environ.get("MONGO_HABIT_COLLECTION_NAME", "")
ANALYTICS_COLLECTION_NAME = os.environ.get("MONGO_ANALYTICS_COLLECTION_NAME", "")

# MongoDB client and collection
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]
user_collection = db[USER_COLLECTION_NAME]
habit_collection = db[HABIT_COLLECTION_NAME]
analytics_collection = db[ANALYTICS_COLLECTION_NAME]

# Add password hashing utility
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@app.get("/")
async def read_root():
    return {"message": "Welcome to the MongoDB-powered FastAPI Example API"}

@app.get("/users", response_model=List[User])
async def get_users():
    users = []
    async for user in user_collection.find():
        user["id"] = str(user["_id"])
        del user["_id"]
        users.append(user)
    return users

@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: str):
    user = await user_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["id"] = str(user["_id"])
    del user["_id"]
    return user

# Create user with password hashing
@app.post("/users", response_model=User)
async def create_user(user: User):
    # Check if email already exists
    if await user_collection.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_dict = user.dict(exclude={"id"})
    user_dict["password"] = pwd_context.hash(user_dict["password"])
    user_dict["createdAt"] = datetime.utcnow().isoformat()
    
    result = await user_collection.insert_one(user_dict)
    user.id = str(result.inserted_id)
    
    # Initialize empty habits for the user
    habit_data = UserHabits(userId=str(result.inserted_id), habits=[])
    await habit_collection.insert_one(habit_data.dict())

    # Initialize empty analytics for the user
    analytics_data = UserAnalytics(userId=str(result.inserted_id), analytics=[])
    await analytics_collection.insert_one(analytics_data.dict())
    
    return user

@app.put("/users/{user_id}", response_model=User)
async def update_user(user_id: str, updated_fields: UserUpdate):
    existing_user = await user_collection.find_one({"_id": ObjectId(user_id)})
    if not existing_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Convert to dict and remove None values
    update_dict = updated_fields.dict(exclude_unset=True, exclude_none=True)
    
    # Hash password if it's being updated
    if "password" in update_dict:
        update_dict["password"] = pwd_context.hash(update_dict["password"])
    
    # Update only the provided fields
    update_result = await user_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": update_dict}
    )
    
    # Get and return the updated user
    updated_user = await user_collection.find_one({"_id": ObjectId(user_id)})
    updated_user["id"] = str(updated_user["_id"])
    del updated_user["_id"]
    
    return updated_user

@app.delete("/users/{user_id}", response_model=dict)
async def delete_user(user_id: str):
    delete_result = await user_collection.delete_one({"_id": ObjectId(user_id)})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}

# Add login endpoint
@app.post("/login")
async def login(login_request: LoginRequest):
    user = await user_collection.find_one({"email": login_request.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not pwd_context.verify(login_request.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user["id"] = str(user["_id"])
    del user["_id"]
    return user

# Habit Management Endpoints
@app.get("/users/{user_id}/habits", response_model=List[HabitBase])
async def get_habits(user_id: str):
    user_habits = await habit_collection.find_one({"userId": user_id})
    if not user_habits:
        raise HTTPException(status_code=404, detail="Habits not found")
    return user_habits["habits"]

@app.post("/users/{user_id}/habits", response_model=HabitBase)
async def create_habit(user_id: str, habit: HabitBase):
    user_habits = await habit_collection.find_one({"userId": user_id})
    if not user_habits:
        raise HTTPException(status_code=404, detail="User habits not found")
    
    # Add the new habit to the list
    update_result = await habit_collection.update_one(
        {"userId": user_id},
        {"$push": {"habits": habit.dict()}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to create habit")
    
    return habit

@app.delete("/users/{user_id}/habits/{habit_id}")
async def delete_habit(user_id: str, habit_id: str):
    update_result = await habit_collection.update_one(
        {"userId": user_id},
        {"$pull": {"habits": {"id": habit_id}}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    return {"message": "Habit deleted successfully"}

@app.put("/users/{user_id}/habits/{habit_id}", response_model=HabitBase)
async def update_habit(user_id: str, habit_id: str, updated_habit: HabitBase):
    update_result = await habit_collection.update_one(
        {
            "userId": user_id,
            "habits.id": habit_id
        },
        {"$set": {"habits.$": updated_habit.dict()}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    return updated_habit

@app.post("/users/{user_id}/habits/{habit_id}/toggle")
async def toggle_habit_completion(
    user_id: str,
    habit_id: str,
    toggle_request: ToggleCompletionRequest
):
    update_result = await habit_collection.update_one(
        {
            "userId": user_id,
            "habits.id": habit_id
        },
        {"$set": {f"habits.$.completions.{toggle_request.date}": toggle_request.completed}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    return {"message": "Habit completion toggled successfully"}

@app.delete("/users/{user_id}/habits")
async def delete_all_habits(user_id: str):
    update_result = await habit_collection.update_one(
        {"userId": user_id},
        {"$set": {"habits": []}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User habits not found")
    
    return {"message": "All habits deleted successfully"}

# Analytics Endpoints
@app.get("/users/{user_id}/analytics", response_model=UserAnalytics)
async def get_analytics(user_id: str):
    analytics = await analytics_collection.find_one({"userId": user_id})
    if not analytics:
        return UserAnalytics(userId=user_id, analytics=[])
    return analytics
