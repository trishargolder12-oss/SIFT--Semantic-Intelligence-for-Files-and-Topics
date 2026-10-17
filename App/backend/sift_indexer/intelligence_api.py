"""Authenticated intelligence endpoints; long work returns a cancellable durable job."""
from typing import Literal

from fastapi import HTTPException, Query
from pydantic import BaseModel, Field


class DiscoveryFilters(BaseModel):
    root_id: int | None = Field(default=None, ge=1)
    group_id: int | None = Field(default=None, ge=1)
    extension: Literal['.pdf', '.docx', '.txt'] | None = None


class ResultContext(BaseModel):
    turn_id: str = Field(min_length=36, max_length=36)
    offset: int = Field(default=0, ge=0)


class ChatInput(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None, max_length=36)
    timezone_offset: int = Field(default=0, ge=-840, le=840)
    filters: DiscoveryFilters = Field(default_factory=DiscoveryFilters)
    result_context: ResultContext | None = None


class ModelSetting(BaseModel):
    enabled: bool


class DownloadInput(BaseModel):
    role: Literal['embedding', 'intent', 'vision']
    confirmed: Literal[True]


class CorrectionInput(BaseModel):
    assignments: dict[str, list[str]]


class GroupName(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def register_intelligence(app, intelligence, auth):
    def call(work):
        try: return work()
        except PermissionError as exc: raise HTTPException(403, str(exc)) from exc
        except KeyError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(400, str(exc)) from exc

    @app.get('/intelligence/status', dependencies=auth)
    def status(): return intelligence.status()

    @app.patch('/intelligence/models', dependencies=auth)
    def configure(body: ModelSetting): return intelligence.configure(body.enabled)

    @app.post('/intelligence/models/download', dependencies=auth)
    def download(body: DownloadInput):
        if not intelligence.enabled(): raise HTTPException(400, 'Enable local models before downloading')
        return intelligence.submit('download', {'role': body.role})

    @app.post('/intelligence/rebuild', dependencies=auth)
    def rebuild(): return intelligence.submit('rebuild', {'all': True})

    @app.post('/intelligence/chat', dependencies=auth)
    def chat(body: ChatInput): return call(lambda: intelligence.submit('chat', body.model_dump()))

    @app.get('/intelligence/jobs/{job_id}', dependencies=auth)
    def job(job_id: int): return call(lambda: intelligence.job(job_id))

    @app.post('/intelligence/jobs/{job_id}/cancel', dependencies=auth)
    def cancel(job_id: int): return {'cancelled': intelligence.cancel(job_id)}

    @app.get('/intelligence/conversations/{conversation_id}', dependencies=auth)
    def history(conversation_id: str): return call(lambda: intelligence.history(conversation_id))

    @app.get('/intelligence/turns/{turn_id}', dependencies=auth)
    def turn(turn_id: str, offset: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=25)):
        return call(lambda: intelligence.turn(turn_id, offset, limit))

    @app.get('/intelligence/turns/{turn_id}/files/{file_id}', dependencies=auth)
    def citation(turn_id: str, file_id: int): return call(lambda: intelligence.citation(turn_id, file_id))

    @app.get('/intelligence/groups', dependencies=auth)
    def groups(): return intelligence.groups()

    @app.patch('/intelligence/groups/{group_id}', dependencies=auth)
    def rename(group_id: int, body: GroupName): return call(lambda: intelligence.rename(group_id, body.name))

    @app.get('/intelligence/documents/{file_id}/groups', dependencies=auth)
    def file_groups(file_id: int): return call(lambda: intelligence.file_groups(file_id))

    @app.patch('/intelligence/documents/{file_id}/groups', dependencies=auth)
    def correct(file_id: int, body: CorrectionInput): return call(lambda: intelligence.correct(file_id, body.assignments))
