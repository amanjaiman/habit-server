from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from analytics import generate_all_analytics
from motor.motor_asyncio import AsyncIOMotorClient
import os

# MongoDB connection details
MONGO_URI = os.environ.get("MONGO_URI")
DATABASE_NAME = os.environ.get("MONGO_DATABASE_NAME", "")
SUBSCRIPTION_COLLECTION_NAME = os.environ.get("MONGO_SUBSCRIPTION_COLLECTION_NAME", "")
HABIT_COLLECTION_NAME = os.environ.get("MONGO_HABIT_COLLECTION_NAME", "")
ANALYTICS_COLLECTION_NAME = os.environ.get("MONGO_ANALYTICS_COLLECTION_NAME", "")
GROUP_COLLECTION_NAME = os.environ.get("MONGO_GROUP_COLLECTION_NAME", "")

# MongoDB client and collections
client = AsyncIOMotorClient(MONGO_URI)
db = client[DATABASE_NAME]
subscription_collection = db[SUBSCRIPTION_COLLECTION_NAME]
habit_collection = db[HABIT_COLLECTION_NAME]
analytics_collection = db[ANALYTICS_COLLECTION_NAME]
group_collection = db[GROUP_COLLECTION_NAME]

async def run_analytics():
    """Run analytics generation for all premium users."""
    print("Starting weekly analytics generation...")
    await generate_all_analytics(
        subscription_collection,
        habit_collection,
        analytics_collection,
        group_collection
    )
    print("Completed weekly analytics generation.")


def init_scheduler():
    """Initialize the scheduler to run analytics weekly on Mondays."""
    scheduler = AsyncIOScheduler()
    
    # Run every Monday at 12 AM EST (5 AM UTC)
    scheduler.add_job(
        run_analytics,
        CronTrigger(day_of_week='thu', hour=6, minute=20),
        id='generate_analytics',
        name='Generate weekly analytics for premium users',
        replace_existing=True
    )
    
    scheduler.start()
    print("Scheduler initialized - Analytics will run weekly on Mondays at 12 AM EST") 