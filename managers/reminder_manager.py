from datetime import datetime

class RemindersManager:
    def __init__(self, reminders_collection):
        self.reminders = reminders_collection
        self.initialize_reminders()

    def initialize_reminders(self):
        if not self.reminders.find_one({}):
            self.reminders.insert_one({'reminders': []})

    def add_reminder(self, reminder):
        self.reminders.update_one(
            {},
            {'$push': {'reminders': {
                "flag": 0,
                "reminder": reminder,
                "timestamp": datetime.utcnow()
            }}}
        )

    def get_active_reminders(self):
        reminders_doc = self.reminders.find_one({})
        if reminders_doc and 'reminders' in reminders_doc:
            return [r for r in reminders_doc['reminders'] if r['flag'] == 0]
        return []

    def complete_reminder(self, reminder_text):
        result = self.reminders.update_one(
            {"reminders.reminder": reminder_text, "reminders.flag": 0},
            {"$set": {"reminders.$.flag": 1}}
        )
        return result.modified_count > 0 