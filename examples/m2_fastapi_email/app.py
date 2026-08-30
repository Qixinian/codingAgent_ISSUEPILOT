from fastapi import FastAPI, status
from pydantic import BaseModel


app = FastAPI()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict[str, str]:
    return {
        "username": payload.username,
        "email": payload.email,
        "status": "registered",
    }