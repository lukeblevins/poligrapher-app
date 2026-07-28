from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Provider, Schedule
from poligrapher_app.api.routers.schedules import list_all_schedules


def test_list_all_schedules_returns_the_tasks_workspace_data_in_one_query():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = Provider(name="First")
        second = Provider(name="Second")
        db.add_all([
            Schedule(provider=first, cadence="daily", enabled=True),
            Schedule(provider=second, cadence="weekly", enabled=False),
        ])
        db.commit()

        schedules = list_all_schedules(db)

        assert len(schedules) == 2
        assert {(schedule.provider.name, schedule.enabled) for schedule in schedules} == {
            ("First", True),
            ("Second", False),
        }
