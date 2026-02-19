import os
raw = os.getenv("KAFKA_BROKERS", "localhost:9092")
KAFKA_BROKERS = raw  # Keep as STRING, NOT list
KAFKA_BROKER_LIST = raw.split(",")  # Optional if consumer needs a list

KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "microservice_one.events")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "payment_service_id")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_RETRIES = int(os.getenv("KAFKA_RETRIES", 5))
KAFKA_ENABLE_AUTO_COMMIT = os.getenv("KAFKA_ENABLE_AUTO_COMMIT", "false").lower() == "true"
KAFKA_AUTO_OFFSET_RESET = os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest")
KAFKA_POLL_TIMEOUT = float(os.getenv("KAFKA_POLL_TIMEOUT", 1.0))
