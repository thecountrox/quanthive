import os
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, Annotated
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
import logging
from logging.handlers import RotatingFileHandler
import time
import httpx

# --- Load Environment Variables ---
# This will load variables from a .env file in the same directory
# or parent directories. For Docker, it's usually in the same directory
# as docker-compose.yml.
load_dotenv()

# --- Configuration ---
# Get SECRET_KEY from environment variables
SECRET_KEY = os.getenv("SECRET_KEY")

# IMPORTANT: Add a check to ensure the key is loaded
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable not set. "
        "Please set it in your .env file or as a system environment variable."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# --- Logging Configuration (remains the same) ---
LOG_FILE = "api_usage.log"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 5

# Configure logger
logger = logging.getLogger("api_monitor")
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# File handler with rotation
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT)
file_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - User:%(user)s - APIKey:%(apikey)s - Endpoint:%(endpoint)s - Method:%(method)s - Status:%(status)s - Duration:%(duration)s - Message:%(message)s"
)
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)


# --- FastAPI App Initialization ---
app = FastAPI()

# --- Security Schemas (remains the same) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Pydantic Models (remains the same) ---
class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None

class UserInDB(User):
    hashed_password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    username: str
    password: str

# --- In-Memory "Database" (remains the same) ---
fake_users_db = {}

# --- Helper Functions (remains the same) ---
def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return UserInDB(**user_dict)
    return None

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception

    return user

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# --- Middleware for API Usage Logging (remains the same) ---
@app.middleware("http")
async def log_api_usage(request: Request, call_next):
    start_time = time.perf_counter()
    user_identifier = "unauthenticated"
    api_key_used = "N/A"
    endpoint_path = request.url.path
    http_method = request.method
    status_code = "N/A"

    authorization: Optional[str] = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        api_key_used = token
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_identifier = payload.get("sub", "unknown_token_user")
        except JWTError:
            user_identifier = "invalid_token"

    if endpoint_path == "/token" and request.method == "POST":
        try:
            req_body = await request.body()
            if req_body:
                import json
                try:
                    body_json = json.loads(req_body.decode('utf-8'))
                    user_identifier = body_json.get("username", user_identifier)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    elif endpoint_path == "/register/" and request.method == "POST":
        try:
            req_body = await request.body()
            if req_body:
                import json
                try:
                    body_json = json.loads(req_body.decode('utf-8'))
                    user_identifier = body_json.get("username", user_identifier)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    response = await call_next(request)
    end_time = time.perf_counter()
    duration = (end_time - start_time) * 1000
    status_code = response.status_code

    log_extra = {
        "user": user_identifier,
        "apikey": api_key_used,
        "endpoint": endpoint_path,
        "method": http_method,
        "status": status_code,
        "duration": f"{duration:.2f}ms"
    }

    if status_code >= 400:
        logger.error("API Request Failed", extra=log_extra)
    else:
        logger.info("API Request Succeeded", extra=log_extra)

    return response

# --- API Endpoints (remains the same) ---
@app.post("/register/", response_model=User)
async def register_user(user_data_in: UserRegister):
    if user_data_in.username in fake_users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    hashed_password = pwd_context.hash(user_data_in.password)
    user_data = {
        "username": user_data_in.username,
        "hashed_password": hashed_password,
        "email": user_data_in.email if user_data_in.email else f"{user_data_in.username}@example.com",
        "full_name": user_data_in.full_name if user_data_in.full_name else user_data_in.username.title(),
        "disabled": False
    }
    fake_users_db[user_data_in.username] = user_data
    return User(**user_data)


@app.post("/token", response_model=Token)
async def login_for_access_token(user_login: UserLogin):
    user = get_user(fake_users_db, user_login.username)
    if not user or not verify_password(user_login.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me/", response_model=User)
async def read_users_me(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user


@app.get("/users/me/items/")
async def read_own_items(current_user: Annotated[User, Depends(get_current_active_user)]):
    return [{"item_id": "Foo", "owner": current_user.username}]

@app.get("/")
async def root():
    return {"message": "Welcome to the JWT Authentication API!"}

# --- New Endpoints Requiring JWT Authentication (remains the same) ---
@app.get("/photos")
async def get_photos(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Fetches photos from JSONPlaceholder. Requires JWT authentication.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://jsonplaceholder.typicode.com/photos")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Error fetching photos for user {current_user.username}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch photos from external API"
            )
        except httpx.RequestError as e:
            logger.error(f"Network error fetching photos for user {current_user.username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to external photo API"
            )

@app.get("/posts")
async def get_posts(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Fetches posts from JSONPlaceholder. Requires JWT authentication.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://jsonplaceholder.typicode.com/posts")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Error fetching posts for user {current_user.username}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to fetch posts from external API"
            )
        except httpx.RequestError as e:
            logger.error(f"Network error fetching posts for user {current_user.username}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not connect to external post API"
            )
