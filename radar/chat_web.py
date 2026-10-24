"""Loopback-only FastAPI interface. No browser credentials or publishing routes."""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .chat import ChatError, ChatService, refresh_links
from .http import HTTP, IntegrationError
from .notion import Notion
from .store import Store


class ChatRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(min_length=1,max_length=1000,strict=True)
    conversation_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{20,64}$')


def create_app(service=None,db_path=None):
    service=service or ChatService(db_path or os.getenv('RADAR_DB','var/radar.sqlite3'))
    app=FastAPI(title='AI Technology Radar Assistant',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.chat=service
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','[::1]'])

    @app.middleware('http')
    async def local_requests(request:Request,call_next):
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):
                return JSONResponse({'error':{'code':'origin','message':'다른 사이트에서 보낸 요청은 허용하지 않습니다.'}},403)
            try:length=int(request.headers.get('content-length','0'))
            except ValueError:return JSONResponse({'error':{'code':'body','message':'잘못된 요청입니다.'}},400)
            if length>10000:return JSONResponse({'error':{'code':'body','message':'질문이 너무 깁니다.'}},413)
        response=await call_next(request)
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(ChatError)
    async def chat_error(request,exc):
        return JSONResponse({'error':{'code':exc.code,'message':exc.message}},exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request,exc):
        return JSONResponse({'error':{'code':'invalid_request','message':'질문과 대화 식별자를 확인해 주세요.'}},422)

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request,exc):
        logging.getLogger('radar').error('chat_storage_error')
        return JSONResponse({'error':{'code':'storage','message':'지식 저장소를 잠시 사용할 수 없습니다.'}},503)

    @app.get('/api/health')
    def health():return service.status()

    @app.post('/api/chat')
    def chat(body:ChatRequest):return service.ask(body.message,body.conversation_id)

    @app.delete('/api/conversations/{conversation_id}')
    def forget(conversation_id:str):
        if not service.lock.acquire(blocking=False):raise ChatError('busy','이전 질문이 끝난 뒤 새 대화를 시작해 주세요.',429)
        try:service.sessions.pop(conversation_id,None)
        finally:service.lock.release()
        return {'cleared':True}  # Clearing conversation never resets model usage.

    static=Path(__file__).with_name('static')
    app.mount('/static',StaticFiles(directory=static),name='static')

    @app.get('/')
    def home():return FileResponse(static/'chat.html')

    return app


def main(argv=None):
    parser=argparse.ArgumentParser(description='Local AI Technology Radar conversational assistant')
    commands=parser.add_subparsers(dest='command',required=True)
    serve=commands.add_parser('serve');serve.add_argument('--db',default=os.getenv('RADAR_DB','var/radar.sqlite3'))
    serve.add_argument('--port',type=int,default=8000);serve.add_argument('--max-requests',type=int,choices=[1,2,3],default=2)
    serve.add_argument('--log',default='var/chat.log')
    links=commands.add_parser('refresh-links');links.add_argument('--db',default=os.getenv('RADAR_DB','var/radar.sqlite3'))
    args=parser.parse_args(argv)
    if args.command=='refresh-links':
        if not Path(args.db).is_file():parser.error('Select an existing knowledge database')
        store=Store(args.db)
        try:
            count=refresh_links(store,Notion(HTTP(),os.getenv('NOTION_TOKEN'),os.getenv('NOTION_PARENT_PAGE_ID')))
            print(f'Validated and cached {count} canonical Notion links; no remote writes')
        except (IntegrationError,ValueError):
            print('Could not refresh links; check Notion credentials, permissions, and connectivity')
            return 1
        finally:store.close()
        return 0
    if not 1024<=args.port<=65535:parser.error('port must be 1024..65535')
    import uvicorn
    Path(args.log).parent.mkdir(parents=True,exist_ok=True)
    handler=RotatingFileHandler(args.log,maxBytes=1_000_000,backupCount=3)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger=logging.getLogger('radar');logger.setLevel(logging.INFO);logger.addHandler(handler)
    try:
        uvicorn.run(create_app(ChatService(args.db,max_requests=args.max_requests)),
                    host='127.0.0.1',port=args.port,access_log=False)
    finally:logger.removeHandler(handler);handler.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
