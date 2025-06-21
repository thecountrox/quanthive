# FastAPI JWT Authentication & External API Integration (Dockerized)

This project demonstrates a robust FastAPI application with JSON Web Token (JWT) based authentication, integration with external APIs, and detailed API usage logging. The entire application, including its testing environment, is designed to run within Docker containers, simplifying setup and ensuring consistent environments.

## Table of Contents

1.  Features
2.  Prerequisites
3.  Setup
    - Clone the Repository
    - Docker Files
    - Set the Secret Key
4.  Running the Application
5.  API Endpoints
6.  Logging
7.  Testing
    - Automated Tests
    - Linting & Formatting Checks

## Prerequisites

Before you begin, ensure you have the following installed:

- **Git**: For cloning the repository.
- **Docker Desktop** (or Docker Engine and Docker Compose): [Install Docker](https://docs.docker.com/get-docker/)

## Setup

Follow these steps to get the project up and running using Docker Compose.

### Clone the Repository

```bash
git clone https://github.com/thecountrox/quanthive.git
cd quanthive
```

### Docker Files

This repository includes:

- `Dockerfile`: Defines the build instructions for your FastAPI application image.
- `docker-compose.yml`: Orchestrates the building and running of your application's Docker containers.

### Set the Secret Key

**Crucially**, you need to set the `SECRET_KEY` used for JWT signing. You can generate this using `openssl rand -hex 32`

1.  Create a file named `.env` in your project root:
    ```
    SECRET_KEY="your_very_strong_secret_key_here_at_least_32_bytes_long"
    ```

## Running the Application

To build the Docker image (if not already built) and start the FastAPI application:

```bash
docker compose up --build
```

- The `--build` flag ensures that your Docker image is built or re-built before starting the containers. You can omit it on subsequent runs if no changes were made to the `Dockerfile` or your dependencies.
- The application will be accessible at `http://localhost:8000`.
- You can access the interactive API documentation (Swagger UI) at `http://localhost:8000/docs`.

To run it in detached mode (in the background):

```bash
docker compose up -d
```

To stop the application:

```bash
docker compose down
```

## API Endpoints

Here's a list of the main API endpoints:

| Endpoint           | Method | Authentication Required | Description                                         |
| :----------------- | :----- | :---------------------- | :-------------------------------------------------- |
| `/`                | `GET`  | No                      | Welcome message.                                    |
| `/register/`       | `POST` | No                      | Register a new user.                                |
| `/token`           | `POST` | No                      | Login and receive an access JWT.                    |
| `/users/me/`       | `GET`  | Yes                     | Retrieve details of the current authenticated user. |
| `/users/me/items/` | `GET`  | Yes                     | Retrieve items owned by the current user.           |
| `/photos`          | `GET`  | Yes                     | Fetches photos from JSONPlaceholder (external API). |
| `/posts`           | `GET`  | Yes                     | Fetches posts from JSONPlaceholder (external API).  |

To interact with authenticated endpoints, you must include the `Authorization` header with a `Bearer` token obtained from the `/token` endpoint:

`Authorization: Bearer <YOUR_ACCESS_TOKEN>`

## Logging

The application includes a robust logging mechanism that writes API usage data to `api_usage.log` _inside the Docker container_. You can view these logs using `docker compose logs <service_name>` (e.g., `docker compose logs app`).

Each log entry includes:

- Timestamp
- Logger Name (`api_monitor`)
- Log Level (INFO, ERROR)
- **User Identity**: The username extracted from the JWT's `sub` claim (or `unauthenticated`/`invalid_token` if applicable).
- **API Key**: The full JWT string used in the request.
- Endpoint path
- HTTP Method
- HTTP Status Code of the response
- Request Duration
- A message indicating success or failure.

**Security Warning**: Logging full JWTs can expose sensitive information in our log file, In a real world environment we should not do this. This is done for demonstration purposes.
## Testing

The project comes with a comprehensive suite of automated tests using `pytest` to ensure all features work as expected. These tests are designed to run within the Docker environment.

### Automated Tests (Pytest)

The `test_main.py` file contains the automated tests. To run them:

```bash
docker compose run --rm app pytest
```

- `docker compose run`: Executes a one-off command in a new container based on your `app` service definition.
- `--rm`: Automatically removes the container after the command exits.
- `app`: The name of your service in `docker-compose.yml` (assuming your main application service is named `app`).
- `pytest`: The command to execute inside the container.

The tests cover:

- Unprotected endpoint access.
- User registration (success and duplicate attempts).
- User login and JWT generation (success and various failure scenarios).
- Accessing protected endpoints (with valid, invalid, missing, and disabled user tokens).
- Integration with external APIs (`/photos`, `/posts`), using `respx` to **mock** the external `jsonplaceholder.typicode.com` calls. This makes tests fast and reliable, without depending on external service availability.

### Linting & Formatting Checks

You can also run code quality checks within the Docker environment:

```bash
# Apply formatting (modifies files - changes will be reflected in your host volume mount)
docker compose run --rm app black .
docker compose run --rm app isort .

# Run linting checks (reports issues, does not modify files)
docker compose run --rm app flake8 .
docker compose run --rm app pylint main.py # Adjust if you have a .pylintrc
```
