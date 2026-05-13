"""fastapi-users application object.

Keeping this object in its own module lets both main.py and api/deps.py reuse
the same authentication configuration without duplicating setup code.
"""

from fastapi_users import FastAPIUsers

from app.auth.backend import auth_backend
from app.auth.user_manager import get_user_manager
from app.db.models import User

fastapi_users = FastAPIUsers[User, int](
    get_user_manager,
    [auth_backend],
)