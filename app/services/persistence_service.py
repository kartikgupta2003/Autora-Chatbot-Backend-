from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
from dotenv import load_dotenv
import os

load_dotenv()

DB_URL = os.getenv("DB_URL")

pool = ConnectionPool(
    conninfo=DB_URL,
    min_size=0,
    max_size=5,
    kwargs={
        "autocommit": True,
        "prepare_threshold": 0
    },
    check=ConnectionPool.check_connection,
    open=False
)

# Both workflows share the same connection pool
car_checkpointer = PostgresSaver(pool)
document_checkpointer = PostgresSaver(pool)


def initialize_checkpointing():

    pool.open(wait=True)

    # Both checkpointers use the same checkpoint tables.
    car_checkpointer.setup()


def close_checkpointing():

    pool.close()
    
    
    
    