"""
FastAPI 示例程序
"""

from fastapi import FastAPI

app = FastAPI()


@app.post("/login")
def login(username: str, password: str) -> dict[str, str]:
    return {"username": username, "status": "logged_in"}

