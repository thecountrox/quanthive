import pytest
from fastapi.testclient import TestClient
import httpx # Keep httpx import for Response/RequestError objects if needed for mocking
from main import app, fake_users_db, pwd_context, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from datetime import timedelta, datetime, timezone
from jose import jwt
import respx # Import respx for mocking external HTTP calls
import logging

# Suppress console logging from the app during tests for cleaner test output
logging.getLogger("api_monitor").propagate = False
logging.getLogger("api_monitor").handlers = []


# Create a TestClient instance for your FastAPI app
# This simulates requests to your app without running a live server.
sync_client = TestClient(app) # This client handles both sync and async endpoints


# --- Fixtures ---

# Fixture to clear the fake database before each test
@pytest.fixture(autouse=True)
def clear_db():
    fake_users_db.clear()
    yield
    fake_users_db.clear()


# Helper fixture to get authentication headers for tests
@pytest.fixture
def auth_headers():
    username = "testuser_auth"
    password = "authpassword"
    if username not in fake_users_db:
        hashed_password = pwd_context.hash(password)
        fake_users_db[username] = {
            "username": username,
            "hashed_password": hashed_password,
            "email": f"{username}@example.com",
            "full_name": username.title(),
            "disabled": False
        }
    token_data = {"sub": username}
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(token_data, expires_delta=access_token_expires)
    return {"Authorization": f"Bearer {access_token}"}

# Helper fixture for a disabled user's auth headers
@pytest.fixture
def disabled_auth_headers():
    username = "disableduser_auth"
    password = "disabledpassword"
    if username not in fake_users_db:
        hashed_password = pwd_context.hash(password)
        fake_users_db[username] = {
            "username": username,
            "hashed_password": hashed_password,
            "email": f"{username}@example.com",
            "full_name": username.title(),
            "disabled": True
        }
    token_data = {"sub": username}
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(token_data, expires_delta=access_token_expires)
    return {"Authorization": f"Bearer {access_token}"}


# --- Test Unprotected Endpoint ---
def test_read_root():
    response = sync_client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the JWT Authentication API!"}

# --- Test Registration ---
def test_register_user_success():
    response = sync_client.post(
        "/register/",
        json={"username": "testuser1", "password": "password123", "email": "test1@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "testuser1"
    assert "hashed_password" not in response.json()
    assert "testuser1" in fake_users_db
    assert pwd_context.verify("password123", fake_users_db["testuser1"]["hashed_password"])

def test_register_user_duplicate():
    sync_client.post("/register/", json={"username": "testuser2", "password": "password123"})
    response = sync_client.post("/register/", json={"username": "testuser2", "password": "anotherpassword"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Username already registered"}

# --- Test Token Generation (Login) ---
def test_login_for_access_token_success():
    hashed_password = pwd_context.hash("password123")
    fake_users_db["testuser3"] = {
        "username": "testuser3",
        "hashed_password": hashed_password,
        "email": "test3@example.com",
        "full_name": "Test User 3",
        "disabled": False
    }
    response = sync_client.post(
        "/token",
        json={"username": "testuser3", "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"

def test_login_for_access_token_invalid_credentials():
    hashed_password = pwd_context.hash("correctpassword")
    fake_users_db["testuser4"] = {
        "username": "testuser4",
        "hashed_password": hashed_password,
        "email": "test4@example.com",
        "full_name": "Test User 4",
        "disabled": False
    }
    response = sync_client.post(
        "/token",
        json={"username": "testuser4", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}

def test_login_for_access_token_non_existent_user():
    response = sync_client.post(
        "/token",
        json={"username": "nonexistent", "password": "anypassword"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Incorrect username or password"}


# --- Test Protected Endpoints (`/users/me/`, `/users/me/items/`) ---
def test_read_users_me_success(auth_headers):
    response = sync_client.get("/users/me/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["username"] == "testuser_auth"

def test_read_users_me_not_authenticated():
    response = sync_client.get("/users/me/")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

def test_read_users_me_invalid_token():
    headers = {"Authorization": "Bearer not.a.real.token"}
    response = sync_client.get("/users/me/", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}

def test_read_users_me_disabled_user(disabled_auth_headers):
    response = sync_client.get("/users/me/", headers=disabled_auth_headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "Inactive user"}


def test_read_own_items_success(auth_headers):
    response = sync_client.get("/users/me/items/", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == [{"item_id": "Foo", "owner": "testuser_auth"}]

# --- Test External API Endpoints (`/photos`, `/posts`) with Respx Mocking ---

@pytest.mark.asyncio
@respx.mock
async def test_get_photos_success(auth_headers):
    respx.get("https://jsonplaceholder.typicode.com/photos").return_value = httpx.Response(
        200, json=[{"id": 1, "title": "photo1", "url": "url1", "thumbnailUrl": "thumb1"}]
    )
    # Use sync_client directly here as it correctly handles async operations from pytest-asyncio
    response = sync_client.get("/photos", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [{"id": 1, "title": "photo1", "url": "url1", "thumbnailUrl": "thumb1"}]
    assert respx.calls.call_count == 1

@pytest.mark.asyncio
@respx.mock
async def test_get_posts_failure_external_api(auth_headers):
    respx.get("https://jsonplaceholder.typicode.com/posts").return_value = httpx.Response(
        500, text="Internal Server Error"
    )
    response = sync_client.get("/posts", headers=auth_headers)

    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to fetch posts from external API"}
    assert respx.calls.call_count == 1

@pytest.mark.asyncio
async def test_get_photos_not_authenticated():
    response = sync_client.get("/photos") # No headers provided
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

@pytest.mark.asyncio
@respx.mock
async def test_get_posts_network_error_external_api(auth_headers):
    respx.get("https://jsonplaceholder.typicode.com/posts").side_effect = httpx.RequestError("Network error occurred")
    response = sync_client.get("/posts", headers=auth_headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "Could not connect to external post API"}
    assert respx.calls.call_count == 1
