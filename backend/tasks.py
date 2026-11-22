import asyncio
import logging

from backend.db_base import SessionLocal
from backend.services.enterprises import settle_shift, settlement_candidates
from backend.websockets import manager


def settle_due_workers():
    with SessionLocal() as db:
        candidates = settlement_candidates(db)
    notifications = []
    for worker_id in candidates:
        try:
            with SessionLocal.begin() as db:
                message = settle_shift(db, worker_id)
            if message:
                notifications.append((worker_id, message))
        except Exception:
            logging.exception("Unable to settle enterprise shift for worker %s", worker_id)
    return notifications


async def check_workers():
    while True:
        try:
            for worker_id, message in await asyncio.to_thread(settle_due_workers):
                await manager.send_personal_message(message, worker_id)
        except Exception:
            logging.exception("Unable to process enterprise shifts")
        await asyncio.sleep(60)
