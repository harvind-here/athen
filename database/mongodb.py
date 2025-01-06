from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

class MongoDB:
    def __init__(self, uri):
        self.client = MongoClient(uri, server_api=ServerApi('1'))
        self.db = self.client['athen_db']
        self.conversations = self.db['conversations']
        self.reminders = self.db['reminders']

    def test_connection(self):
        try:
            self.client.admin.command('ping')
            print("Pinged your deployment. You successfully connected to MongoDB!")
            return True
        except Exception as e:
            print(e)
            return False 