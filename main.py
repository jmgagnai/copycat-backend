import sys
from pathlib import Path

import uvicorn
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent / "src"))
try:
    from settings import ENV_FILE, settings
except ValidationError as e:
    missing = ", ".join(str(err["loc"][0]) for err in e.errors())
    raise SystemExit(f"Missing in {ENV_FILE}: {missing}")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, app_dir="src")
