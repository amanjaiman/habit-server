import os

from fastapi import FastAPI, HTTPException, Body, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Any, List, Optional, Dict
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime, timezone
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware
from models import (
    Subscription,
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

import stripe
stripe.api_key = os.environ.get("STRIPE_API_KEY")
endpoint_secret = os.environ.get("STRIPE_ENDPOINT_SECRET")

# Add this temporary storage (in production, you'd want to use Redis or similar)
user_id_mapping = {}

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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "https://674e18bf34bb7a4af4439ba7--habitai.netlify.app",
        "https://habitai.netlify.app"
    ],
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
SUBSCRIPTION_COLLECTION_NAME = os.environ.get("MONGO_SUBSCRIPTION_COLLECTION_NAME", "")

# MongoDB client and collection
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]
user_collection = db[USER_COLLECTION_NAME]
habit_collection = db[HABIT_COLLECTION_NAME]
analytics_collection = db[ANALYTICS_COLLECTION_NAME]
subscription_collection = db[SUBSCRIPTION_COLLECTION_NAME]

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

# Stripe Endpoints
@app.get("/users/{user_id}/subscription")
async def get_subscription(user_id: str):
    try:
        subscription = await subscription_collection.find_one({"userId": user_id})
        if not subscription:
            return {"userId": user_id, "status": "none"}
        
        # Convert MongoDB ObjectId to string
        if "_id" in subscription:
            subscription["_id"] = str(subscription["_id"])
        
        # Convert datetime objects to ISO format strings
        datetime_fields = ["currentPeriodStart", "currentPeriodEnd", "nextBillingDate"]
        for field in datetime_fields:
            if field in subscription and subscription[field]:
                subscription[field] = subscription[field].isoformat()
        
        return subscription
    except Exception as e:
        print(f"Error fetching subscription: {str(e)}")  # Add logging for debugging
        return {"userId": user_id, "status": "none"}

@app.post("/users/{user_id}/create-checkout-session")
async def create_checkout_session(user_id: str):
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": "price_1QSo6pLtlL58rL0tGRHLE6tt",
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url="http://localhost:3000/settings?success=true",
            cancel_url="http://localhost:3000/settings?canceled=true",
            metadata={
                "user_id": user_id,
            },
        )
        return {"url": session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/webhook")
async def webhook(request: Request):
    event = None
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        print("Error: Invalid payload")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        print("Error: Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_type = event['type']
    event_data = event.data.object

    if event_type == 'checkout.session.completed':
        print("Handling checkout.session.completed event")
        user_id_mapping[event_data.customer] = event_data.metadata.get('user_id')
        
    elif event_type == 'customer.subscription.created':
        print("Handling customer.subscription.created event")
        customer_id = event_data.customer
        user_id = user_id_mapping.get(customer_id)
        
        if user_id:
            try:
                # Fetch customer details
                customer = stripe.Customer.retrieve(customer_id)
                
                subscription_data = {
                    "userId": user_id,
                    "stripeId": customer_id,
                    "stripeSubscriptionId": event_data.id,
                    "customerEmail": customer.email,
                    "customerName": customer.name,
                    "status": event_data.status,
                    "created": datetime.fromtimestamp(event_data.created, tz=timezone.utc).isoformat(),
                    "currentPeriodStart": datetime.fromtimestamp(event_data.current_period_start, tz=timezone.utc),
                    "currentPeriodEnd": datetime.fromtimestamp(event_data.current_period_end, tz=timezone.utc),
                    "nextBillingDate": datetime.fromtimestamp(event_data.current_period_end, tz=timezone.utc),
                    "priceId": event_data["plan"]["id"],
                    "cancelAtPeriodEnd": event_data["cancel_at_period_end"]
                }
                
                print(f"Attempting to insert subscription data: {subscription_data}")
                result = await subscription_collection.insert_one(subscription_data)
                print(f"Insert result: {result.inserted_id}")
                
                # Clean up mapping
                user_id_mapping.pop(customer_id, None)
            except Exception as e:
                print(f"Error processing subscription creation: {str(e)}")
                raise
        else:
            print(f"No user_id found for customer_id: {customer_id}")
    
    elif event_type == 'customer.subscription.updated':
        print("Handling customer.subscription.updated event")
        subscription_id = event_data.id

        # Update existing subscription
        update_data = {
            "status": event_data.status,
            "currentPeriodStart": datetime.fromtimestamp(event_data.current_period_start, tz=timezone.utc),
            "currentPeriodEnd": datetime.fromtimestamp(event_data.current_period_end, tz=timezone.utc),
            "nextBillingDate": datetime.fromtimestamp(event_data.current_period_end, tz=timezone.utc),
            "cancelAtPeriodEnd": event_data["cancel_at_period_end"]
        }
        
        await subscription_collection.update_one(
            {"stripeSubscriptionId": subscription_id},
            {"$set": update_data}
        )

    elif event_type == 'customer.subscription.deleted':
        print("Handling customer.subscription.deleted event")
        subscription_id = event_data.id
        
        await subscription_collection.update_one(
            {"stripeSubscriptionId": subscription_id},
            {"$set": {
                "status": "canceled",
                "canceled_at": datetime.fromtimestamp(event_data.canceled_at, tz=timezone.utc) if event_data.canceled_at else datetime.now(timezone.utc)
            }}
        )

    elif event_type == 'customer.subscription.paused':
        print("Handling customer.subscription.paused event")
        subscription_id = event_data.id
        
        await subscription_collection.update_one(
            {"stripeSubscriptionId": subscription_id},
            {"$set": {
                "status": "paused",
                "pause_collection": event_data.pause_collection
            }}
        )

    elif event_type == 'customer.subscription.resumed':
        print("Handling customer.subscription.resumed event")
        subscription_id = event_data.id
        
        await subscription_collection.update_one(
            {"stripeSubscriptionId": subscription_id},
            {"$set": {
                "status": event_data.status,
                "pause_collection": None
            }}
        )

    elif event_type == 'invoice.paid':
        print("Handling invoice.paid event")
        subscription_id = event_data.subscription
        
        if subscription_id:
            await subscription_collection.update_one(
                {"stripeSubscriptionId": subscription_id},
                {"$set": {
                    "invoiceUrl": event_data.hosted_invoice_url,
                    "status": "active"
                }}
            )

    else:
        print('Unhandled event type {}'.format(event['type']))

    return {"status": "success"}