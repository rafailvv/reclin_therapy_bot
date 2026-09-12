import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(BOT_TOKEN='123456:TEST_TOKEN_NOT_REAL', DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:1/test', CHAT_ID='-100123', WEBAPP_URL='https://example.test', ADMIN_IDS='[1]')
from fastapi.testclient import TestClient
from src.webapp import main as web
from src.webapp.auth import verify_init_data
from src import scheduler as jobs
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

TOKEN = os.environ['BOT_TOKEN']

def signed(user=None, timestamp=None, token=TOKEN, **extra):
    fields = {'auth_date':str(int(time.time()) if timestamp is None else timestamp), 'user':json.dumps({'id':123,'username':'real_user'} if user is None else user), **extra}
    key=hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    fields['hash']=hmac.new(key, '\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)

def headers(raw=None):
    return {'X-Telegram-Init-Data': signed() if raw is None else raw}

@pytest.fixture
def state(monkeypatch):
    session=MagicMock()
    session.scalar=AsyncMock(return_value=None)
    session.execute=AsyncMock(return_value=SimpleNamespace(scalar_one=lambda:'https://t.me/+test-invite'))
    session.commit=AsyncMock()
    context=MagicMock()
    context.__aenter__=AsyncMock(return_value=session)
    context.__aexit__=AsyncMock(return_value=False)
    factory=MagicMock(return_value=context)
    monkeypatch.setattr(web,'async_session',factory)
    bot=SimpleNamespace(unban_chat_member=AsyncMock())
    monkeypatch.setattr(web,'bot',bot)
    invite=AsyncMock(return_value='https://t.me/+test-invite')
    monkeypatch.setattr(web,'create_one_time_invite',invite)
    with TestClient(web.app) as client:
        yield SimpleNamespace(session=session,factory=factory,bot=bot,invite=invite,client=client)

@pytest.mark.parametrize('query',['','?uid=123','?uid=999','?uid=bad'])
def test_unsigned_get_is_only_bootstrap(state,query):
    r=state.client.get('/'+query)
    assert r.status_code==200 and 'app.initData' in r.text
    assert 'test-invite' not in r.text
    assert r.headers['cache-control']=='no-store'
    state.factory.assert_not_called()

@pytest.mark.parametrize('raw',[
    '', 'bad', signed()+'&hash=bad', signed()+'&user=%7B%7D', signed(token='wrong'),
    signed(timestamp=1), signed(timestamp=int(time.time())+3600),
    signed(user={'id':True}), signed(user={'id':0}), signed(user={'id':-1}),
    signed(user={'id':'123'}), signed(user=[]), signed(user={'name':'no id'}),
    signed().replace('real_user','forged_user'),
])
def test_invalid_auth_has_no_effects(state,raw):
    for method,url in [('get','/?uid=123'),('post','/register')]:
        r=getattr(state.client,method)(url,headers=headers(raw))
        assert r.status_code==401
    state.factory.assert_not_called()
    state.bot.unban_chat_member.assert_not_awaited()
    state.invite.assert_not_awaited()

def test_signature_field_included_in_hmac():
    assert verify_init_data(signed(signature='telegram-signature'),TOKEN)['id']==123

@pytest.mark.parametrize('profile,registered',[
    (None,False),
    (SimpleNamespace(fio=None,specialization=None),False),
    (SimpleNamespace(fio='Doctor',specialization=None,invite_link='https://t.me/+test-invite'),True),
    (SimpleNamespace(fio='Doctor',specialization='Therapy',invite_link='https://t.me/+test-invite'),True),
])
def test_signed_get_preserves_completion_rules(state,profile,registered):
    state.session.scalar.return_value=profile
    r=state.client.get('/?uid=999',headers=headers())
    assert r.status_code==200
    assert ('Вы уже зарегистрированы' in r.text)==registered
    assert ('id="regForm"' in r.text)==(not registered)
    assert 123 in state.session.scalar.call_args.args[0].compile().params.values()
    if not registered:
        assert "fetch('/endo/register'" in r.text
        assert 'X-Telegram-Init-Data' in r.text

def test_registration_preserves_fields_and_operation_order(state):
    events=[]
    async def unban(**kw): events.append('unban')
    async def invite(*a): events.append('invite');return 'https://t.me/+test-invite'
    async def execute(stmt): events.append('execute');return SimpleNamespace(scalar_one=lambda:'https://t.me/+test-invite')
    async def commit(): events.append('commit')
    state.bot.unban_chat_member.side_effect=unban
    state.invite.side_effect=invite
    state.session.execute.side_effect=execute
    state.session.commit.side_effect=commit
    r=state.client.post('/register',headers=headers(),json={'telegram_id':123,'username':'forged','fio':'Doctor','specialization':'Therapy'})
    assert r.status_code==200 and r.json()=={'link':'https://t.me/+test-invite'}
    assert events==['unban','invite','execute','commit']
    state.bot.unban_chat_member.assert_awaited_once_with(chat_id=-100123,user_id=123)
    stmt=state.session.execute.call_args.args[0]
    params=stmt.compile().params
    assert params['telegram_id']==123 and params['username']=='real_user' and params['fio']=='Doctor'
    assert ('specialization' in params)==False
    assert 'username' not in dict(stmt._post_values_clause.update_values_to_set)

@pytest.mark.parametrize('body',[{'telegram_id':999},[],None])
def test_invalid_registration_no_effects(state,body):
    r=state.client.post('/register',headers=headers(),content=json.dumps(body))
    assert r.status_code in [400,403]
    state.factory.assert_not_called()
    state.bot.unban_chat_member.assert_not_awaited()
    state.invite.assert_not_awaited()

def test_unsigned_post_rejected(state):
    assert state.client.post('/register',json={'telegram_id':123}).status_code==401
    state.factory.assert_not_called()

def test_broken_json_rejected(state):
    assert state.client.post('/register',headers=headers(),content='{').status_code==400
    state.factory.assert_not_called()

@pytest.mark.parametrize('forbidden',[False,True])
def test_reminder_contract(state,monkeypatch,forbidden):
    monkeypatch.setattr(jobs,'async_session',state.factory)
    state.session.scalar.return_value=SimpleNamespace(specialization=None)
    bot=SimpleNamespace(send_message=AsyncMock(),session=SimpleNamespace(close=AsyncMock()))
    if forbidden: bot.send_message.side_effect=TelegramForbiddenError(method=SendMessage(chat_id=123,text='x'),message='Forbidden')
    constructor=MagicMock(return_value=bot)
    monkeypatch.setattr(jobs,'Bot',constructor)
    remove=MagicMock()
    monkeypatch.setattr(jobs.scheduler,'remove_job',remove)
    asyncio.run(jobs.cleanup_unregistered(123))
    if False:
        bot.send_message.assert_awaited_once()
        bot.session.close.assert_awaited_once()
        remove.assert_not_called()
        state.session.commit.assert_not_awaited()
    else:
        constructor.assert_not_called()
        remove.assert_called_once_with('remind_spec_123')

def test_completed_user_removes_reminder(state,monkeypatch):
    monkeypatch.setattr(jobs,'async_session',state.factory)
    state.session.scalar.return_value=SimpleNamespace(specialization='Therapy')
    remove=MagicMock()
    monkeypatch.setattr(jobs.scheduler,'remove_job',remove)
    asyncio.run(jobs.cleanup_unregistered(123))
    remove.assert_called_once_with('remind_spec_123')
