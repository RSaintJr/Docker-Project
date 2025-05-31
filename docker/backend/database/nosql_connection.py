from pymongo import MongoClient
import os

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://admin:admin123@mongo:27017/")


def get_mongo_client():
    client = MongoClient(MONGODB_URL)
    return client
