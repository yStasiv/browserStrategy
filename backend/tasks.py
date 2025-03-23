import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from backend import database, models
from backend.websockets import manager


async def check_workers():
    """Фоновий процес для перевірки працівників підприємств"""
    while True:
        try:
            db = next(database.get_db())
            current_time = datetime.now()

            # Отримуємо всіх активних працівників
            workers = (
                db.query(models.User)
                .filter(
                    models.User.workplace.isnot(None),
                    models.User.work_start_time.isnot(None),
                )
                .all()
            )

            for worker in workers:
                try:
                    # Перевіряємо чи пройшла година
                    hours_worked = (
                        current_time - worker.work_start_time
                    ).total_seconds() / 3600

                    if hours_worked >= 1:
                        # Отримуємо підприємство
                        enterprise_id = int(worker.workplace.split("_")[1])
                        enterprise = (
                            db.query(models.Enterprise)
                            .filter(models.Enterprise.id == enterprise_id)
                            .first()
                        )

                        if enterprise:
                            # Нараховуємо зарплату
                            earned = enterprise.salary
                            worker.gold += earned
                            enterprise.balance -= earned

                            # Додаємо ресурс на склад підприємства в залежності від типу
                            if enterprise.resource_type == "wood":
                                enterprise.wood_stored += (
                                    1  #  enterprise.production_rate
                                )
                                logging.info(
                                    f"Added 1 wood to enterprise {enterprise.id}"
                                )
                            elif enterprise.resource_type == "stone":
                                enterprise.stone_stored += (
                                    1  #  enterprise.production_rate
                                )
                                logging.info(
                                    f"Added 1 stone to enterprise {enterprise.id}"
                                )

                            # Звільняємо працівника
                            worker.workplace = None
                            worker.work_start_time = None
                            enterprise.workers_count -= 1

                            # Відправляємо повідомлення через WebSocket
                            await manager.send_personal_message(
                                {
                                    "type": "work_finished",
                                    "earned": earned,
                                    "enterprise_name": enterprise.name,
                                },
                                worker.id,
                            )

                            logging.info(
                                f"Worker {worker.id} finished work at enterprise {enterprise.id}"
                            )

                except Exception as e:
                    logging.error(f"Error processing worker {worker.id}: {str(e)}")
                    continue

            db.commit()
            db.close()

        except Exception as e:
            logging.error(f"Error in check_workers: {str(e)}")

        # Чекаємо 1 хвилину перед наступною перевіркою
        await asyncio.sleep(60)
