from datetime import date, datetime

class ConversationHistoryManager:
    def __init__(self, conversations_collection, context_length=8):
        self.conversations = conversations_collection
        self.context_length = context_length

    def get_today_document(self):
        today = date.today().isoformat()
        return self.conversations.find_one({"date": today}) or {"date": today, "messages": []}

    def add_message(self, role, content):
        today_doc = self.get_today_document()
        today_doc["messages"].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow()
        })
        self.conversations.update_one(
            {"date": today_doc["date"]},
            {"$set": today_doc},
            upsert=True
        )

    def get_recent_context(self):
        today_doc = self.get_today_document()
        return today_doc["messages"][-self.context_length:]

    def store_temp_audio(self, audio_data):
        today = date.today().isoformat()
        self.conversations.update_one(
            {"date": today},
            {"$set": {"temp_audio": audio_data}},
            upsert=True
        )

    def get_temp_audio(self):
        today = date.today().isoformat()
        doc = self.conversations.find_one({"date": today})
        return doc.get("temp_audio") if doc else None

    def clear_temp_audio(self):
        today = date.today().isoformat()
        self.conversations.update_one(
            {"date": today},
            {"$unset": {"temp_audio": ""}}
        ) 