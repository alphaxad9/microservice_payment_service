import os
from dotenv import load_dotenv

load_dotenv()

RABBIT_HOST = os.getenv("RABBITMQ_HOST", "localhost")
RABBIT_PORT = int(os.getenv("RABBITMQ_PORT", 5672))
RABBIT_USER = os.getenv("RABBITMQ_USER", "guest")
RABBIT_PASSWORD = os.getenv("RABBITMQ_PASS", "guest")
RABBIT_VHOST = os.getenv("RABBITMQ_VHOST", "microservice_one")
RABBIT_QUEUE = os.getenv("RABBITMQ_QUEUE", "microservice_one.events")
MAX_RETRIES = int(os.getenv("OUTBOX_MAX_RETRIES", 5))
