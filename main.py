import os

import certifi
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
    HabitType,
    Subscription,
    User,
    UserUpdate,
    HabitBase,
    KeyInsight,
    Analytics,
    UserHabits,
    UserAnalytics,
    LoginRequest,
    ToggleCompletionRequest,
    GroupHabitCompletion,
    GroupHabit,
    Group,
    GroupCreate,
    GroupUpdate,
    GroupJoin,
    GroupMember
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
        "https://habitsense.app",  # Mobile app origin
        "https://localhost",       # Local development
        "capacitor://localhost",   # Capacitor local
        "http://localhost",        # Local development
        "http://localhost:3000",   # React development server
        # Add your production web domain if different
        "http://127.0.0.1:8000",
        "https://674e18bf34bb7a4af4439ba7--habitai.netlify.app",
        "https://habitai.netlify.app",
        "https://habitsense.ai",
        "https://www.habitsense.ai",
        "http://habitsense.ai",
        "http://www.habitsense.ai"
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
GROUP_COLLECTION_NAME = os.environ.get("MONGO_GROUP_COLLECTION_NAME", "groups")

# MongoDB client and collection
client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where(), tlsInsecure=True)
db = client[DATABASE_NAME]
user_collection = db[USER_COLLECTION_NAME]
habit_collection = db[HABIT_COLLECTION_NAME]
analytics_collection = db[ANALYTICS_COLLECTION_NAME]
subscription_collection = db[SUBSCRIPTION_COLLECTION_NAME]
group_collection = db[GROUP_COLLECTION_NAME]

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
    # Validate config based on habit type
    if habit.type != HabitType.BOOLEAN and not habit.config:
        raise HTTPException(
            status_code=400, 
            detail=f"Configuration required for {habit.type} habit type"
        )
    
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
    # Convert the habit model to a dict and handle the config field properly
    habit_dict = updated_habit.dict()
    
    # Only remove config if it's explicitly None, not if it contains valid zeros
    if habit_dict.get('config') is None:
        habit_dict.pop('config', None)
    elif isinstance(habit_dict.get('config'), dict):
        # Keep any numeric values, even if they're 0
        config = {k: v for k, v in habit_dict['config'].items() if v is not None}
        if config:
            habit_dict['config'] = config
        else:
            habit_dict.pop('config', None)
    
    update_result = await habit_collection.update_one(
        {
            "userId": user_id,
            "habits.id": habit_id
        },
        {"$set": {"habits.$": habit_dict}}
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
    
    return {"message": "Habit completion updated successfully"}

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
                    "price": "price_1QTGKJLtlL58rL0tUsA5b7Y4",
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url="https://habitsense.ai/settings?success=true",
            cancel_url="https://habitsense.ai/settings?canceled=true",
            allow_promotion_codes=True,
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

# Group Management Endpoints
@app.post("/groups", response_model=Group)
async def create_group(group_data: GroupCreate, user_id: str):
    join_code = await generate_unique_join_code()
    
    # Get creator's details
    creator = await user_collection.find_one({"_id": ObjectId(user_id)})
    if not creator:
        raise HTTPException(status_code=404, detail="User not found")
    
    creator_details = GroupMember(
        id=user_id,
        name=creator["name"],
        profileImage=creator.get("profileImage"),
        isAdmin=True
    )
    
    group = Group(
        name=group_data.name,
        description=group_data.description,
        emoji=group_data.emoji,
        adminId=user_id,
        joinCode=join_code,
        members=[user_id],
        memberDetails=[creator_details],
        habits=[],
        createdAt=datetime.utcnow().isoformat()
    )
    
    result = await group_collection.insert_one(group.dict(exclude={"id"}))
    group.id = str(result.inserted_id)
    
    return group

@app.get("/groups/user/{user_id}", response_model=List[Group])
async def get_user_groups(user_id: str):
    groups = []
    async for group in group_collection.find({"members": user_id}):
        # Ensure habits have all required fields
        for habit in group.get("habits", []):
            # Ensure completions is a list
            if "completions" not in habit or not isinstance(habit["completions"], list):
                habit["completions"] = []
            # Ensure type field exists
            if "type" not in habit:
                habit["type"] = HabitType.BOOLEAN
            # Ensure config field exists
            if "config" not in habit:
                habit["config"] = None
        
        # Fetch member details for each group
        member_details = []
        for member_id in group["members"]:
            user = await user_collection.find_one({"_id": ObjectId(member_id)})
            if user:
                member_details.append(GroupMember(
                    id=str(user["_id"]),
                    name=user["name"],
                    profileImage=user.get("profileImage"),
                    isAdmin=member_id == group["adminId"]
                ))
        
        group["id"] = str(group["_id"])
        group["memberDetails"] = member_details
        del group["_id"]
        groups.append(group)
    return groups

@app.get("/groups/{group_id}", response_model=Group)
async def get_group(group_id: str, user_id: str):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "members": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Ensure habits have all required fields
    for habit in group.get("habits", []):
        # Ensure completions is a list
        if "completions" not in habit or not isinstance(habit["completions"], list):
            habit["completions"] = []
        # Ensure type field exists
        if "type" not in habit:
            habit["type"] = HabitType.BOOLEAN
        # Ensure config field exists
        if "config" not in habit:
            habit["config"] = None
    
    # Fetch member details
    member_details = []
    for member_id in group["members"]:
        user = await user_collection.find_one({"_id": ObjectId(member_id)})
        if user:
            member_details.append(GroupMember(
                id=str(user["_id"]),
                name=user["name"],
                profileImage=user.get("profileImage"),
                isAdmin=member_id == group["adminId"]
            ))
    
    group["id"] = str(group["_id"])
    group["memberDetails"] = member_details
    del group["_id"]
    return group

@app.put("/groups/{group_id}", response_model=Group)
async def update_group(group_id: str, group_data: GroupUpdate, user_id: str):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "adminId": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or unauthorized")

    update_data = group_data.dict(exclude_unset=True)
    if update_data:
        await group_collection.update_one(
            {"_id": ObjectId(group_id)},
            {"$set": update_data}
        )
    
    updated_group = await group_collection.find_one({"_id": ObjectId(group_id)})
    updated_group["id"] = str(updated_group["_id"])
    del updated_group["_id"]
    return updated_group

@app.delete("/groups/{group_id}")
async def delete_group(group_id: str, user_id: str):
    result = await group_collection.delete_one({
        "_id": ObjectId(group_id),
        "adminId": user_id
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Group not found or unauthorized")
    return {"message": "Group deleted successfully"}

@app.post("/groups/join", response_model=Group)
async def join_group(join_request: GroupJoin, user_id: str):
    group = await group_collection.find_one({"joinCode": join_request.joinCode})
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if user_id in group["members"]:
        raise HTTPException(status_code=400, detail="Already a member of this group")
    
    # Get new member's details
    user = await user_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    new_member_details = GroupMember(
        id=user_id,
        name=user["name"],
        profileImage=user.get("profileImage"),
        isAdmin=False
    )
    
    # Update both members array and memberDetails
    await group_collection.update_one(
        {"_id": group["_id"]},
        {
            "$push": {
                "members": user_id,
                "memberDetails": new_member_details.dict()
            }
        }
    )
    
    # Get updated group
    updated_group = await group_collection.find_one({"_id": group["_id"]})
    updated_group["id"] = str(updated_group["_id"])
    del updated_group["_id"]
    
    return updated_group

@app.post("/groups/{group_id}/habits", response_model=GroupHabit)
async def create_group_habit(group_id: str, habit: HabitBase, user_id: str):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "adminId": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or unauthorized")
    
    group_habit = GroupHabit(
        id=habit.id,
        name=habit.name,
        emoji=habit.emoji,
        color=habit.color,
        type=habit.type,
        config=habit.config,
        createdAt=habit.createdAt,
        category=habit.category,
        completions=[]
    )
    
    await group_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$push": {"habits": group_habit.dict()}}
    )
    
    return group_habit

@app.post("/groups/{group_id}/habits/{habit_id}/toggle")
async def toggle_group_habit_completion(
    group_id: str,
    habit_id: str,
    toggle_request: ToggleCompletionRequest,
    user_id: str
):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "members": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or not a member")

    # Find the habit to check its type
    habit = next((h for h in group["habits"] if h["id"] == habit_id), None)
    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    # Validate completion value based on habit type
    if habit["type"] != HabitType.BOOLEAN:
        if not isinstance(toggle_request.completed, (int, float)):
            raise HTTPException(
                status_code=400,
                detail=f"Numeric value required for {habit['type']} habit type"
            )

    completion = {
        "userId": user_id,
        "date": toggle_request.date,
        "completed": toggle_request.completed
    }

    # Remove any existing completion for this user and date
    await group_collection.update_one(
        {"_id": ObjectId(group_id), "habits.id": habit_id},
        {"$pull": {
            "habits.$.completions": {
                "userId": user_id,
                "date": toggle_request.date
            }
        }}
    )

    # Add the new completion if it has a value
    if toggle_request.completed is not None and (
        isinstance(toggle_request.completed, bool) or 
        (isinstance(toggle_request.completed, (int, float)) and toggle_request.completed > 0)
    ):
        await group_collection.update_one(
            {"_id": ObjectId(group_id), "habits.id": habit_id},
            {"$push": {"habits.$.completions": completion}}
        )

    return {"message": "Habit completion updated successfully"}

@app.get("/groups/habits/user/{user_id}", response_model=List[Dict])
async def get_all_group_habits(user_id: str):
    groups = []
    async for group in group_collection.find({"members": user_id}):
        for habit in group["habits"]:
            groups.append({
                "groupId": str(group["_id"]),
                "groupName": group["name"],
                "habit": habit
            })
    return groups

@app.put("/groups/{group_id}/habits/{habit_id}", response_model=GroupHabit)
async def update_group_habit(group_id: str, habit_id: str, habit: HabitBase, user_id: str):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "adminId": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or unauthorized")
    
    # Validate config based on habit type
    if habit.type != HabitType.BOOLEAN and not habit.config:
        raise HTTPException(
            status_code=400, 
            detail=f"Configuration required for {habit.type} habit type"
        )
    
    # Convert the habit model to a dict and handle the config field properly
    habit_dict = habit.dict()
    if habit_dict.get('config') is None:
        habit_dict.pop('config', None)
    elif isinstance(habit_dict.get('config'), dict):
        config = {k: v for k, v in habit_dict['config'].items() if v is not None}
        if config:
            habit_dict['config'] = config
        else:
            habit_dict.pop('config', None)
    
    # Keep existing completions and ensure it's a list
    existing_habit = next((h for h in group["habits"] if h["id"] == habit_id), None)
    if existing_habit:
        # Convert completions to list if it's a dict
        completions = existing_habit.get("completions", [])
        if isinstance(completions, dict):
            completions = [
                {"userId": user_id, "date": date, "completed": value}
                for date, value in completions.items()
            ]
        habit_dict["completions"] = completions
    else:
        habit_dict["completions"] = []
    
    result = await group_collection.update_one(
        {"_id": ObjectId(group_id), "habits.id": habit_id},
        {"$set": {"habits.$": habit_dict}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    return habit_dict

@app.delete("/groups/{group_id}/habits/{habit_id}")
async def delete_group_habit(group_id: str, habit_id: str, user_id: str):
    group = await group_collection.find_one({
        "_id": ObjectId(group_id),
        "adminId": user_id
    })
    if not group:
        raise HTTPException(status_code=404, detail="Group not found or unauthorized")
    
    result = await group_collection.update_one(
        {"_id": ObjectId(group_id)},
        {"$pull": {"habits": {"id": habit_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Habit not found")
    
    return {"message": "Habit deleted successfully"}

# Add these helper functions
async def generate_unique_join_code():
    import random
    import string
    while True:
        # Generate a 6-character alphanumeric code
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        # Check if code already exists
        if not await group_collection.find_one({"joinCode": code}):
            return code