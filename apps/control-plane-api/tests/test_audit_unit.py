from careai_common.correlation import clear_correlation_id, set_correlation_id
from careai_control_plane_api.api import write_audit_event
from careai_control_plane_api.database import Database
from careai_control_plane_api.models import AuditEventORM
from sqlalchemy import select


def test_write_audit_event_persists_correlation_id() -> None:
    database = Database("sqlite:///:memory:")
    database.create_all()
    token = set_correlation_id("unit-correlation-id")
    session_generator = database.session()
    session = next(session_generator)

    try:
        write_audit_event(
            session,
            actor="unit-test",
            action="model.promoted",
            target_type="model",
            target_id="model-001",
            metadata={"to_stage": "staging"},
        )
        session.commit()

        event = session.scalars(select(AuditEventORM)).one()
        assert event.correlation_id == "unit-correlation-id"
        assert event.metadata_json == {"to_stage": "staging"}
    finally:
        session_generator.close()
        clear_correlation_id(token)
