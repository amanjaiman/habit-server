from enum import Enum
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime

# Add new enum for habit types
class HabitType(str, Enum):
    BOOLEAN = "boolean"
    NUMERIC = "numeric"
    RATING = "rating"

# Add configuration models for different habit types
class NumericHabitConfig(BaseModel):
    goal: float
    unit: str
    higherIsBetter: bool = True

class RatingHabitConfig(BaseModel):
    min: int = 1
    max: int = 5
    goal: int = 5

# Update HabitBase to include type and config
class HabitBase(BaseModel):
    id: str
    name: str
    emoji: str
    color: Optional[str] = None
    createdAt: str
    # Change completions to support both boolean and numeric values
    completions: dict[str, Union[bool, float]] = {}
    category: Optional[str] = None
    # Add new fields
    type: HabitType = Field(default=HabitType.BOOLEAN)  # Default to boolean for backwards compatibility
    config: Optional[Union[NumericHabitConfig, RatingHabitConfig]] = None

# Update GroupHabitCompletion to support numeric values
class GroupHabitCompletion(BaseModel):
    userId: str
    date: str
    completed: Union[bool, float]

# Update GroupHabit to match HabitBase
class GroupHabit(BaseModel):
    id: str
    name: str
    emoji: str
    color: Optional[str] = None
    createdAt: str
    completions: List[GroupHabitCompletion] = []
    category: Optional[str] = None
    type: HabitType = Field(default=HabitType.BOOLEAN)
    config: Optional[Union[NumericHabitConfig, RatingHabitConfig]] = None

class Subscription(BaseModel):
    id: str = None
    userId: str
    stripeId: str
    stripeSubscriptionId: str
    customerEmail: str
    customerName: str
    invoiceUrl: str
    status: str
    created: str
    currentPeriodStart: datetime
    currentPeriodEnd: datetime
    nextBillingDate: datetime
    priceId: str
    cancelAtPeriodEnd: bool = False


class User(BaseModel):
    id: str = None
    email: str
    password: str
    name: str
    isPremium: bool = False
    createdAt: Optional[str] = None
    profileImage: Optional[str] = None

    class Config:
        json_encoders = {
            ObjectId: str
        }

class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    name: Optional[str] = None
    isPremium: Optional[bool] = None
    profileImage: Optional[str] = None

    class Config:
        extra = "allow"
        json_encoders = {
            ObjectId: str
        }

class KeyInsight(BaseModel):
    title: str
    description: str
    explanation: str
    score: int
    impact_score: int
    confidence: int
    polarity: str

class SuccessFailurePattern(BaseModel):
    title: str
    description: str
    time_period: str
    confidence: int
    success: bool

class ActionableRecommendation(BaseModel):
    title: str
    description: str
    expected_impact: int

class CorrelationInsight(BaseModel):
    correlating_habit: str
    insights: List[str]
    recommendations: List[str]

class KeyInsightList(BaseModel):
    insights: List[KeyInsight]

class SuccessFailurePatternList(BaseModel):
    patterns: List[SuccessFailurePattern]

class ActionableRecommendationList(BaseModel):
    recommendations: List[ActionableRecommendation]

class CorrelationInsightList(BaseModel):
    correlations: List[CorrelationInsight]

class Analytics(BaseModel):
    publishedAt: str
    keyInsights: KeyInsightList = KeyInsightList(insights=[])
    individualHabitKeyInsights: dict[str, KeyInsightList] = {}
    successFailurePatterns: dict[str, SuccessFailurePatternList] = {}
    actionableRecommendations: dict[str, ActionableRecommendationList] = {}
    correlationInsights: dict[str, CorrelationInsightList] = {}

class UserHabits(BaseModel):
    userId: str
    habits: List[HabitBase] = []

    class Config:
        json_encoders = {
            ObjectId: str
        }

class UserAnalytics(BaseModel):
    userId: str
    analytics: List[Analytics] = []

    class Config:
        json_encoders = {
            ObjectId: str
        }

class LoginRequest(BaseModel):
    email: str
    password: str

class ToggleCompletionRequest(BaseModel):
    date: str
    completed: Union[bool, float]

class GroupMember(BaseModel):
    id: str
    name: str
    profileImage: Optional[str] = None
    isAdmin: bool = False

class Group(BaseModel):
    id: str = None
    name: str
    description: Optional[str] = None
    emoji: str
    adminId: str
    joinCode: str
    habits: List[GroupHabit] = []
    members: List[str] = []  # Keep this as List[str] for storage
    memberDetails: List[GroupMember] = []  # Add this new field
    createdAt: str

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    emoji: str

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    emoji: Optional[str] = None

class GroupJoin(BaseModel):
    joinCode: str