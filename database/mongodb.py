from pymongo import MongoClient

def connect_mongodb():

    client = MongoClient(
        "mongodb://localhost:27017/"
    )

    database = client["lead_generation"]

    return database