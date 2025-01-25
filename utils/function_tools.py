function_tools = [
    {
        "name": "get_upcoming_events",
        "description": "Get details of the upcoming events from Google Calendar",
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer"}
            },
            "required": ["max_results"]
        }
    },
    {
        "name": "create_event",
        "description": "Create an event in Google Calendar, by identifying and passing the necessary event details such as summary, start time, end time, location, attendees based on the information provided by user. These details should be inside a dictionary with necessary keys that mentioned.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_details": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "location": {"type": "string"},
                        "description": {"type": "string"},
                        "attendees": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["summary", "start_time", "end_time"]
                }
            },
            "required": ["event_details"]
        }
    },
    {
        "name": "get_active_reminders",
        "description": "Get active reminders which are yet to be completed",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "add_reminder",
        "description": "Use this function to add/create a new reminder for any task or just store something that you are asked to remind the user later. This is a tentative to-do list for the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "reminder": {"type": "string"}
            },
            "required": ["reminder"]
        }
    },
    {
        "name": "complete_reminder",
        "description": "Use this function to mark a reminder as completed by the user. Make sure that you mark the reminder that said by the user that he finished doing or completed.",
        "parameters": {
            "type": "object",
            "properties": {
                "reminder_text": {"type": "string"}
            },
            "required": ["reminder_text"]
        }
    },
    {
        "name": "delete_event",
        "description": "Use this function to delete an existing event in the user's Google Calendar using the event's summary. This removes an upcoming event from the calendar.",
        "parameters": {
          "type": "object",
          "properties": {
            "summary": {"type": "string", "description": "Summary of the event to delete"}
          },
          "required": ["summary"]
        }
    },
    {
        "name": "web_search",
        "description": "Perform an intelligent web search and analysis, Use this function to get context from the top internet sources. To use this function you need to query as much as related to the user's need and demand. So that you get promising results, So focus on betterment of what users tries to get or what you want to know in order to answer the user even more accurately.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 3}
            },
            "required": ["query"]
        }
    }
] 