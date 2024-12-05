from typing import List, Optional
from pydantic import BaseModel
from bson import ObjectId

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

class HabitBase(BaseModel):
    id: str
    name: str
    emoji: str
    color: Optional[str] = None
    createdAt: str
    completions: dict[str, bool] = {}
    category: Optional[str] = None

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
    completed: bool