from datetime import datetime, timedelta
import time
from typing import List, Dict
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from models import ActionableRecommendation, ActionableRecommendationList, CorrelationInsight, CorrelationInsightList, HabitBase, KeyInsight, KeyInsightList, SuccessFailurePattern, Analytics, SuccessFailurePatternList
import json
from prompts import ACTIONABLE_RECOMMENDATIONS_PROMPT, AGGREGATE_SYSTEM_PROMPT, AGGREGATE_PROMPT, CORRELATION_PROMPT, INDIVIDUAL_HABIT_PROMPT, SUCCESS_PATTERNS_PROMPT
from openai import OpenAI
import os

async def get_premium_users(user_collection) -> List[str]:
    """Get all premium user IDs."""
    premium_users = []
    async for user in user_collection.find({"isPremium": True}):
        premium_users.append(str(user["_id"]))
    return premium_users

async def get_user_habit_data(habit_collection, user_id: str, days: int = 14) -> List[HabitBase]:
    """Get user's habit data for the specified number of days."""
    start_date = (datetime.utcnow() - timedelta(days=days)).date()
    end_date = (datetime.utcnow() - timedelta(days=1)).date()
    
    user_habits = await habit_collection.find_one({"userId": user_id})
    if not user_habits or not user_habits["habits"]:
        return []
    
    # Filter completions to only include dates within our range
    filtered_habits = []
    for habit in user_habits["habits"]:
        # Generate all dates in range
        all_dates = {
            (start_date + timedelta(days=x)).isoformat(): False 
            for x in range((end_date - start_date).days + 1)
        }
        
        # Update with actual completion data
        existing_completions = {
            date: completed 
            for date, completed in habit["completions"].items()
            if datetime.fromisoformat(date).date() >= start_date
        }
        all_dates.update(existing_completions)
        
        # Create habit copy with complete date range
        habit_copy = habit.copy()
        habit_copy["completions"] = dict(sorted(all_dates.items()))  # Sort by date
        filtered_habits.append(habit_copy)
    
    return filtered_habits

async def get_aggregate_key_insights(habit_data: Dict) -> List[KeyInsight]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY_HABITAI_AGGREGATE"))

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
                {"role": "user", "content": AGGREGATE_PROMPT.format(habit_data=habit_data)}
            ],
            response_format=KeyInsightList,
            #temperature=0.7,
            #max_tokens=1000
        )
        
        insights = completion.choices[0].message.parsed
        return insights
    except Exception as e:
        print(f"Error generating aggregate key insights: {e}")
        return []
    
async def get_individual_habit_key_insights(habit_data: Dict) -> List[KeyInsight]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY_HABITAI_INDIVIDUAL"))

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
                {"role": "user", "content": INDIVIDUAL_HABIT_PROMPT.format(habit_data=habit_data)}
            ],
            response_format=KeyInsightList,
            #temperature=0.7,
            #max_tokens=1000
        )
        
        insights = completion.choices[0].message.parsed
        return insights
    except Exception as e:
        print(f"Error generating individual habit key insights: {e}")
        return []
    
async def get_success_failure_patterns(habit_data: Dict, habit_of_interest: str) -> List[SuccessFailurePattern]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY_HABITAI_SUCCESS_PATTERNS"))

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
                {"role": "user", "content": SUCCESS_PATTERNS_PROMPT.format(habit_data=habit_data, habit_of_interest=habit_of_interest)}
            ],
            response_format=SuccessFailurePatternList,
            #temperature=0.7,
            #max_tokens=1000
        )
        
        patterns = completion.choices[0].message.parsed
        return patterns
    except Exception as e:
        print(f"Error generating success/failure patterns: {e}")
        return []
    
async def get_actionable_recommendations(habit_data: Dict) -> List[ActionableRecommendation]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY_HABITAI_INDIVIDUAL"))

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
                {"role": "user", "content": ACTIONABLE_RECOMMENDATIONS_PROMPT.format(habit_data=habit_data)}
            ],
            response_format=ActionableRecommendationList,
            #temperature=0.7,
            #max_tokens=1000
        )
        
        recommendations = completion.choices[0].message.parsed
        return recommendations
    except Exception as e:
        print(f"Error generating actionable recommendations: {e}")
        return []
    
async def get_correlation_insights(habit_data: Dict, habit_of_interest: str) -> List[CorrelationInsight]:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY_HABITAI_CORRELATIONS"))

    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": AGGREGATE_SYSTEM_PROMPT},
                {"role": "user", "content": CORRELATION_PROMPT.format(habit_data=habit_data, habit_of_interest=habit_of_interest)}
            ],
            response_format=CorrelationInsightList,
            #temperature=0.7,
            #max_tokens=1000
        )
        
        correlations = completion.choices[0].message.parsed
        return correlations
    except Exception as e:
        print(f"Error generating correlation insights: {e}")
        return []

async def generate_all_analytics(
    user_collection,
    habit_collection,
    analytics_collection
) -> None:
    """Generate analytics for all premium users."""
    premium_users = await get_premium_users(user_collection)
    
    for user_id in premium_users:
        habits = await get_user_habit_data(habit_collection, user_id)
        if len(habits) > 0 and any(habit["completions"] for habit in habits):

            key_insights = await get_aggregate_key_insights(habits)
            print(f"Generated aggregate key insights for user {user_id}")
            time.sleep(1)

            individual_habit_key_insights = {}
            success_failure_patterns = {}
            actionable_recommendations = {}
            correlation_insights = {}
            for habit in habits:
                habit_insights = await get_individual_habit_key_insights(habit)
                print(f"Generated individual habit key insights for habit {habit['name']}")
                individual_habit_key_insights[habit["name"]] = habit_insights
                time.sleep(1)
                patterns = await get_success_failure_patterns(habits, habit["name"])
                print(f"Generated success/failure patterns for habit {habit['name']}")
                success_failure_patterns[habit["name"]] = patterns
                time.sleep(1)
                recommendations = await get_actionable_recommendations(habit)
                print(f"Generated actionable recommendations for habit {habit['name']}")
                actionable_recommendations[habit["name"]] = recommendations
                time.sleep(1)
                correlations = await get_correlation_insights(habits, habit["name"])
                print(f"Generated correlation insights for habit {habit['name']}")
                correlation_insights[habit["name"]] = correlations
                time.sleep(1)                

            analytics = Analytics(
                publishedAt=datetime.utcnow().isoformat(),
                keyInsights=key_insights,
                individualHabitKeyInsights=individual_habit_key_insights,
                successFailurePatterns=success_failure_patterns,
                actionableRecommendations=actionable_recommendations,
                correlationInsights=correlation_insights
            )

            await analytics_collection.update_one(
                {"userId": user_id},
                {
                    "$push": {
                        "analytics": analytics.dict()
                    }
                },
                upsert=True
            )

#if __name__ == "__main__":
#    import asyncio
#    from motor.motor_asyncio import AsyncIOMotorClient
#    import os

#    async def main():
#        # MongoDB connection details
#        MONGO_URI = os.environ.get("MONGO_URI")
#        DATABASE_NAME = os.environ.get("MONGO_DATABASE_NAME", "")
#        USER_COLLECTION_NAME = os.environ.get("MONGO_USER_COLLECTION_NAME", "")
#        HABIT_COLLECTION_NAME = os.environ.get("MONGO_HABIT_COLLECTION_NAME", "")
#        ANALYTICS_COLLECTION_NAME = os.environ.get("MONGO_ANALYTICS_COLLECTION_NAME", "")

#        # MongoDB client and collections
#        client = AsyncIOMotorClient(MONGO_URI)
#        db = client[DATABASE_NAME]
#        user_collection = db[USER_COLLECTION_NAME]
#        habit_collection = db[HABIT_COLLECTION_NAME]
#        analytics_collection = db[ANALYTICS_COLLECTION_NAME]

#        await generate_all_analytics(
#            user_collection,
#            habit_collection, 
#            analytics_collection
#        )

#    asyncio.run(main())