from pymongo import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime

class MongoDB:
    def __init__(self, uri):
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        self.db = self.client['athen_db']
        
        # Collections
        self.users = self.db.users
        self.conversations = self.db.conversations
        self.reminders = self.db.reminders
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        # User indexes
        self.users.create_index("email", unique=True, sparse=True)
        self.users.create_index("google_id", unique=True, sparse=True)
        
        # Conversation indexes
        self.conversations.create_index([("user_id", 1), ("date", 1)])
        
        # Reminder indexes
        self.reminders.create_index([("user_id", 1), ("completed", 1)])
    
    def create_user(self, user_data):
        """Create a new user or update existing one"""
        user_data["updated_at"] = datetime.utcnow()
        
        if user_data.get("google_id"):
            # Try to find existing user by Google ID or email
            existing_user = self.users.find_one({
                "$or": [
                    {"google_id": user_data["google_id"]},
                    {"email": user_data["email"]}
                ]
            })
            
            if existing_user:
                # Update existing user
                update_data = {
                    "$set": user_data,
                    "$setOnInsert": {"created_at": datetime.utcnow()}
                }
                
                # If user was previously a guest, remove guest-specific fields
                if existing_user.get("is_guest"):
                    update_data["$unset"] = {"is_guest": "", "_id": ""}
                
                return self.users.update_one(
                    {"_id": existing_user["_id"]},
                    update_data
                )
            else:
                # Create new user
                user_data["created_at"] = datetime.utcnow()
                return self.users.insert_one(user_data)
                
        elif user_data.get("is_guest"):
            # For guest users, always create new
            user_data["created_at"] = datetime.utcnow()
            return self.users.insert_one(user_data)
        
        raise ValueError("Invalid user data")
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        return self.users.find_one({"_id": user_id})
    
    def get_user_by_google_id(self, google_id):
        """Get user by Google ID"""
        return self.users.find_one({"google_id": google_id})
    
    def get_user_by_email(self, email):
        """Get user by email"""
        return self.users.find_one({"email": email})
    
    def get_user_conversations(self, user_id, date=None):
        """Get conversations for a specific user"""
        query = {"user_id": user_id}
        if date:
            query["date"] = date
        return self.conversations.find(query)
    
    def add_conversation_message(self, user_id, message_data):
        """Add a message to user's conversation history"""
        date = datetime.utcnow().date().isoformat()
        
        return self.conversations.update_one(
            {"user_id": user_id, "date": date},
            {
                "$push": {"messages": message_data},
                "$setOnInsert": {"created_at": datetime.utcnow()}
            },
            upsert=True
        )
    
    def get_user_reminders(self, user_id, include_completed=False):
        """Get reminders for a specific user"""
        query = {"user_id": user_id}
        if not include_completed:
            query["completed"] = False
        return self.reminders.find(query)
    
    def add_reminder(self, user_id, reminder_data):
        """Add a reminder for a user"""
        reminder_data["user_id"] = user_id
        reminder_data["created_at"] = datetime.utcnow()
        reminder_data["completed"] = False
        
        return self.reminders.insert_one(reminder_data)
    
    def complete_reminder(self, user_id, reminder_text):
        """Mark a reminder as completed"""
        return self.reminders.update_one(
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

    def test_connection(self):
        try:
            self.client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
            return True
        except Exception as e:
            print(e)
            return False 