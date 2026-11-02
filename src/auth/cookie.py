import os

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7


def session_cookie_options() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": os.getenv("APP_ENV") == "production",
        "path": "/",
        "max_age": SESSION_MAX_AGE,
    }
