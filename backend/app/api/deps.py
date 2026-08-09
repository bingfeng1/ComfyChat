from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_settings(request: Request):
    return request.app.state.settings


def get_services(request: Request):
    return request.app.state.services


def get_db_session(request: Request) -> Iterator[Session]:
    database = get_services(request)["database"]
    with database.get_session() as session:
        yield session
