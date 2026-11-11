from importlib import import_module

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

main = import_module("my_first_app.main")


def test_hero_mapping_and_crud():
    assert [column.name for column in main.Hero.__table__.primary_key] == ["id"]
    assert {index.name for index in main.Hero.__table__.indexes} == {
        "ix_hero_name",
        "ix_hero_age",
    }

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    def get_test_session():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[main.get_session] = get_test_session
    try:
        client = TestClient(main.app)
        created = client.post(
            "/heroes/", json={"name": "Hero", "secret_name": "Secret", "age": 20}
        )
        assert created.status_code == 200
        hero = created.json()
        assert hero == {"id": hero["id"], "name": "Hero", "age": 20}

        assert client.get(f"/heroes/{hero['id']}").json() == hero
        assert client.get("/heroes/").json() == [hero]
        updated = client.patch(f"/heroes/{hero['id']}", json={"age": 21})
        assert updated.status_code == 200
        assert updated.json() == {**hero, "age": 21}
        assert client.delete(f"/heroes/{hero['id']}").json() == {"ok": True}
        assert client.get(f"/heroes/{hero['id']}").status_code == 404
    finally:
        del main.app.dependency_overrides[main.get_session]
        engine.dispose()
