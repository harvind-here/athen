from datetime import datetime

class ConversationHistoryManager:
    def __init__(self, conversations_collection, context_length=10):
        self.conversations = conversations_collection
        self.context_length = context_length

    def get_today_document(self, user_id):
        """Get today's conversation document for a specific user"""
        today = datetime.utcnow().date().isoformat()
        return self.conversations.find_one({
            "user_id": user_id,
            "date": today
        })

    def get_recent_context(self, user_id):
        """Get recent conversation context for a specific user"""
        today_doc = self.get_today_document(user_id)
        if not today_doc or "messages" not in today_doc:
            return []
        return today_doc["messages"][-self.context_length:]

    def add_message(self, user_id, role, content):
        """Add a message to today's conversation for a specific user"""
        today = datetime.utcnow().date().isoformat()
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        }

        self.conversations.update_one(
            {
                "user_id": user_id,
                "date": today
            },
            {
                "$push": {"messages": message},
                "$setOnInsert": {
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )

    def store_temp_audio(self, audio_data):
        today = datetime.utcnow().date().isoformat()
        self.conversations.update_one(
            {"date": today},
            {"$set": {"temp_audio": audio_data}},
            upsert=True
        )

    def get_temp_audio(self):
        today = datetime.utcnow().date().isoformat()
        doc = self.conversations.find_one({"date": today})
        return doc.get("temp_audio") if doc else None

    def clear_temp_audio(self):
        today = datetime.utcnow().date().isoformat()
        self.conversations.update_one(
            {"date": today},
            {"$unset": {"temp_audio": ""}}
        )

    def clear_history(self, user_id):
        """Clear all conversation history for a specific user"""
        self.conversations.delete_many({
            "user_id": user_id
        }) 