AGGREGATE_SYSTEM_PROMPT = """You are a habit and productivity expert in charge of data analytics at a habit startup. You will be given habit data of a user. The habit data will be a JSON object that has a list of habits. Each habit has a name and a set of completions. The completions are simply a dictionary mapping each date to true/false, where true means the user completed that habit, and false means the user did not complete that habit. Habits could also have a category, but it is not required."""

AGGREGATE_PROMPT = """
Habit data: {habit_data}
------------------------

Instructions: Given a user's habit data, your job is to generate 6 key insights for the user using the data. The key insights should not be things that are easy to calculate which a user could do simply by looking at the data themselves. Think outside the box and be creative.

The key insights must be structured as a JSON object, where each key_insight has the following properties:
- title: the title of the key insight
- description: the actual insight based on the data
- explanation: what this key insight means. IMPORTANT: This should read as if you are talking directly to the user.
- score: a score from 0 to 100
- impact_score: an internal score from 0 to 100 that indicates how impactful this insight would be for the user to know
- confidence: your confidence in this insight being meaningful to the user, from 0 to 100
- polarity: whether this insight is positive or negative
"""

CORRELATION_PROMPT = """
Habit data: {habit_data}
------------------------

Instructions: Given a user's habit data, your job is to generate correlations between {habit_of_interest} and each of the other habits in the data.

Consider the following:
- Which habits tend to be completed together
- Which habits might be competing for time/energy
- Potential positive or negative interactions

The correlations must be structured as a JSON object, where each correlation has the following properties:
- correlating_habit: the name of the habit that is being correlated with {habit_of_interest}
- insights: a list of strings that are short insights into why this correlation exists. There should be either 1 or 2 insights. IMPORTANT: These should read as if you are talking directly to the user.
- recommendations: a list of strings that are short recommendations for the user to improve their overall habits based on this specific correlation. There should be either 1 or 2 recommendations. IMPORTANT: These should read as if you are talking directly to the user.
"""

ACTIONABLE_RECOMMENDATIONS_PROMPT = """
Habit data: {habit_data}
------------------------

Instructions: Given this habit data, your job is to generate 1-3 actionable recommendations for the user to improve their habits.

The recommendations must be structured as a JSON object, where each recommendation has the following properties:
- title: a short title of the recommendation
- description: a description of the recommendation based on the data IMPORTANT: This should read as if you are talking directly to the user.
- expected_impact: an expected impact score from 0 to 100
"""

SUCCESS_PATTERNS_PROMPT = """
Habit data: {habit_data}
------------------------

Instructions: Given this habit data, your job is to generate 0-3 success patterns, and 0-3 failure patterns for the habit of interest. The number of each will depend on the data.

The habit of interest is {habit_of_interest}.

Success patterns are patterns in the habit data where the user completed the habit.
Failure patterns are patterns in the habit data where the user did not complete the habit.

You can also consider patterns with other habits and how they interact with each other, but this is not required.

The success/failure patterns must be structured as a JSON object, where each pattern has the following properties:
- title: a short title of the pattern
- description: a description of the pattern based on the data IMPORTANT: This should read as if you are talking directly to the user.
- time_period: the time period over which this pattern occurs
- confidence: your confidence in this pattern being meaningful to the user, from 0 to 100
- success: true if this is a success pattern, false if this is a failure pattern
"""

INDIVIDUAL_HABIT_PROMPT = """
Habit data: {habit_data}
------------------------

Instructions: Given this habit data, your job is to generate 3 key insights for the user using the data.
The key insights should not be things that are easy to calculate which a user could do simply by looking at the data themselves. Think outside the box and be creative.

The key insights must be structured as a JSON object, where each key_insight has the following properties:
- title: the title of the key insight
- description: the actual insight based on the data
- explanation: what this key insight means. IMPORTANT: This should read as if you are talking directly to the user.
- score: a score from 0 to 100
- impact_score: an internal score from 0 to 100 that indicates how impactful this insight would be for the user to know
- confidence: your confidence in this insight being meaningful to the user, from 0 to 100
- polarity: whether this insight is positive or negative

Consider the following:
- Completion rate and trends
- Pattern quality
- Day of week patterns
- Streaks and breaks
- Recommendations for improvement""" 