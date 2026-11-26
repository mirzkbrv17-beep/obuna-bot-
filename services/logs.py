import logging

log = logging.getLogger("admin")


async def log_admin(db, admin_id: int, action: str, target: str = "", details: str = "") -> None:
    """Muhim admin amallarini bazaga va logga yozadi."""
    log.info("ADMIN %s | %s | %s | %s", admin_id, action, target, details)
    await db.execute(
        "INSERT INTO admin_logs(admin_id, action, target, details) VALUES($1,$2,$3,$4)",
        admin_id, action, target, details,
    )
