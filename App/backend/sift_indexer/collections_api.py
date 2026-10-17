"""Private typed collection API; native main process grants paths, renderer gets IDs."""
from fastapi import HTTPException, Query
from pydantic import BaseModel, Field


class Attachment(BaseModel): path: str
class Destination(BaseModel): path:str; base:str; id:str
class Intake(BaseModel):
    text:str=Field(default='',max_length=100000)
    attachment_id:str|None=None
    collection_id:str|None=None
class Outline(BaseModel): outline:dict
class Decision(BaseModel): topic_id:str; file_id:int; decision:str; target:str|None=None
class Pack(BaseModel): path:str
class ExportState(BaseModel): state:str; plan:str; error:str|None=None


def register_collections(app,collections,auth):
    def call(work):
        try: return work()
        except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
        except KeyError as exc: raise HTTPException(404,str(exc)) from exc
        except (ValueError,TypeError) as exc: raise HTTPException(400,str(exc)) from exc
        except OSError as exc: raise HTTPException(400,'The selected source or folder is not accessible') from exc

    @app.get('/collections',dependencies=auth)
    def listing(): return collections.list()
    @app.post('/collections',dependencies=auth)
    def create(body:Intake): return call(lambda:collections.create(**body.model_dump()))
    @app.get('/collections/destination',dependencies=auth)
    def destination(): return collections.destination()
    @app.delete('/collections/destination',dependencies=auth)
    def revoke_destination(): return collections.revoke_destination()
    @app.post('/collections/destination',dependencies=auth)
    def set_destination(body:Destination): return call(lambda:collections.destination(body.path,body.base,body.id))
    @app.get('/collections/vision',dependencies=auth)
    def vision(): return collections.vision_status()
    @app.post('/collections/vision/pack',dependencies=auth)
    def pack(body:Pack): return call(lambda:collections.set_pack(body.path))
    @app.post('/collections/attachments',dependencies=auth)
    def attach(body:Attachment): return call(lambda:collections.attachment(body.path))
    @app.delete('/collections/attachments/{attachment}',dependencies=auth)
    def detach(attachment:str): return call(lambda:collections.revoke_attachment(attachment))
    @app.get('/collections/reference/{reference}',dependencies=auth)
    def reference(reference:str): return call(lambda:collections.reference(reference))
    @app.get('/collections/page/{reference}/{version}/{page}',dependencies=auth)
    def page(reference:str,version:str,page:int): return call(lambda:collections.page(reference,version,page))
    @app.get('/collections/exports/pending',dependencies=auth)
    def pending(): return call(collections.pending_exports)
    @app.post('/collections/exports/{export_id}',dependencies=auth)
    def export(export_id:str,body:ExportState): return call(lambda:collections.export_state(export_id,body.state,body.plan,body.error))
    @app.get('/collections/exports/{export_id}/access',dependencies=auth)
    def export_access(export_id:str): return call(lambda:collections.export_access(export_id))
    @app.post('/collections/exports/{export_id}/cancel',dependencies=auth)
    def export_cancel(export_id:str): return call(lambda:collections.cancel_export(export_id))
    @app.get('/collections/jobs/{job}',dependencies=auth)
    def job(job:int): return call(lambda:collections.job(job))
    @app.post('/collections/jobs/{job}/cancel',dependencies=auth)
    def cancel(job:int): return call(lambda:collections.cancel(job))
    @app.get('/collections/{collection}',dependencies=auth)
    def detail(collection:str,topic:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100)):
        return call(lambda:collections.detail(collection,topic,offset,limit))
    @app.patch('/collections/{collection}/outline',dependencies=auth)
    def outline(collection:str,body:Outline): return call(lambda:collections.outline(collection,body.outline))
    @app.post('/collections/{collection}/refresh',dependencies=auth)
    def refresh(collection:str): return call(lambda:{'job':collections.submit(collection)})
    @app.post('/collections/{collection}/assignments',dependencies=auth)
    def decision(collection:str,body:Decision): return call(lambda:collections.decide(collection,body.topic_id,body.file_id,body.decision,body.target))
    @app.post('/collections/{collection}/export',dependencies=auth)
    def retry(collection:str): return call(lambda:{'export':collections.prepare_export(collection)})
