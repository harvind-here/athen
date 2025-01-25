from datetime import datetime

class RemindersManager:
    def __init__(self, reminders_collection):
        self.reminders = reminders_collection
        self.initialize_reminders()

    def initialize_reminders(self, user_id=None):
        """Initialize reminders collection for a user"""
        if user_id:
            # Initialize for specific user
            if not self.reminders.find_one({"user_id": user_id}):
                self.reminders.insert_one({
                    "user_id": user_id,
                    "reminders": [],
                    "created_at": datetime.utcnow()
                })
        else:
            # Initialize collection if empty
            if self.reminders.count_documents({}) == 0:
                self.reminders.create_index([("user_id", 1), ("completed", 1)])

    def add_reminder(self, user_id, reminder, due_date=None):
        """Add a reminder for a specific user"""
        reminder_doc = {
            "user_id": user_id,
            "reminder": reminder,
            "created_at": datetime.utcnow(),
            "completed": False
        }
        
        if due_date:
            reminder_doc["due_date"] = due_date
            
        self.reminders.insert_one(reminder_doc)

    def get_active_reminders(self, user_id):
        """Get active reminders for a specific user"""
        return list(self.reminders.find({
            "user_id": user_id,
            "completed": False
        }))

    def complete_reminder(self, user_id, reminder_text):
        """Mark a reminder as completed for a specific user"""
        result = self.reminders.update_one(
            {
                "user_id": user_id,
                "reminder": reminder_text,
                "completed": False
            },
            {
                "$set": {
                    "completed": True,
                    "completed_at": datetime.utcnow()
                }
            }
        )
        return result.modified_count > 0

    def get_completed_reminders(self, user_id):
        """Get completed reminders for a specific user"""
        return list(self.reminders.find({
            "user_id": user_id,
            "completed": True
        }))

    def clear_reminders(self, user_id):
        """Clear all reminders for a specific user"""
        self.reminders.delete_many({"user_id": user_id}) 