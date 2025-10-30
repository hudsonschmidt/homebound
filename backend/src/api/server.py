from fastapi import FastAPI
# from src.api import # 
from starlette.middleware.cors import CORSMiddleware

description = """
Plan in seconds. Get found fast.
"""
tags_metadata = [
    {"name": "cart", "description": "Place potion orders."},
    {"name": "catalog", "description": "View the available potions."},
    {"name": "bottler", "description": "Bottle potions from the raw magical elixir."},
    {
        "name": "barrels",
        "description": "Buy barrels of raw magical elixir for making potions.",
    },
    {"name": "admin", "description": "Where you reset the game state."},
    {"name": "info", "description": "Get updates on time"},
    {
        "name": "inventory",
        "description": "Get the current inventory of shop and buying capacity.",
    },
]

app = FastAPI(
    title="Homebound",
    description=description,
    version="0.0.1",
    terms_of_service="http://example.com/terms/",
    contact={
        "name": "Hudson Schmidt",
        "email": "hudsonschmidt08@gmail.com",
    },
    openapi_tags=tags_metadata,
)

origins = ["https://homebound.onrender.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

# app.include_router(inventory.router)

@app.get("/")
async def root():
    return {"message": "Homebound backend is running."}
