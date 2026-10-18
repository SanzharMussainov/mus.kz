import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select,func
from app.models import Meeting,Ledger,Registration
from app.services import confirm_meeting,balance,register
from app.db import now

pytestmark=pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Concurrency requires PostgreSQL')


def test_concurrent_confirmation_once(db,data):
    m=Meeting(title='Concurrent',group_id=data['g1'].id,starts_at=now()-timedelta(hours=2),duration=60)
    db.add(m);db.commit();uid=data['alice'].id;pk=m.id
    sessions=sessionmaker(db.bind)
    def run(_):
        with sessions() as tx:
            confirm_meeting(tx,pk,60,{uid:'present'});tx.commit()
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(run,range(4)))
    assert balance(db,uid)==-60
    assert db.scalar(select(func.count()).select_from(Ledger))==1




def test_concurrent_registration_once(db,data):
    m=Meeting(title='Concurrent event',is_event=True,starts_at=now()+timedelta(days=1),duration=60)
    db.add(m);db.commit();pk=m.id;uid=data['alice'].id;sessions=sessionmaker(db.bind)
    def run(_):
        with sessions() as tx: register(tx,pk,uid);tx.commit()
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(run,range(4)))
    assert db.scalar(select(func.count()).select_from(Registration))==1
