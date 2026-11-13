from datetime import UTC, datetime

from sqlmodel import Session, delete

from .database import engine
from .models import RefreshToken


def purge_expired_refresh_tokens() -> int:
    """Deletes tokens past their expiry. Revoked but unexpired rows stay on purpose:
    they are what lets reuse detection catch a replayed token."""
    with Session(engine) as session:
        result = session.exec(
            delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC))
        )
        session.commit()
        return result.rowcount


if __name__ == "__main__":
    print(f"Deleted {purge_expired_refresh_tokens()} expired refresh tokens")

# Run it manually or schedule with crontab:
# docker compose exec app python -m my_first_app.cleanup
# 0 3 * * * cd ~/python_app && docker compose exec -T app python -m my_first_app.cleanup
