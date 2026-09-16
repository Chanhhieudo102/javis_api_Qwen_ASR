"""Import all models here for Alembic to detect schema changes.

Example:
    from app.users.models import User
    from app.auth.models import RefreshToken

"""

from app.auth.models.token import Token  # noqa: F401
from app.users.models.user import User  # noqa: F401
