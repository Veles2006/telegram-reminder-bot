from pymongo import MongoClient

uri = "mongodb+srv://lifeup_user:19001789@pixiv-cluster.3bfpwin.mongodb.net/?appName=pixiv-cluster"
client = MongoClient(uri)
db = client["mygame"]

print("Databases:", client.list_database_names())
