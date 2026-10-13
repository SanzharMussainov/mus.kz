import pytest
from app.grading import check, number


@pytest.mark.parametrize('kind,expected,actual,extra,result',[
 ('number','-1.5',' −1,5 ',{},True),('number','3','3.001',{'tolerance':'0.01'},True),
 ('number','3','3.1',{'tolerance':'0.01'},False),('fraction','2/3','4/6',{},True),
 ('fraction','2/3','4/6',{'exact_form':True},False),('set','-2;2','2; -2',{},True),
 ('set','-2;2','2;-2',{'ordered':True},False),('set','2;2','2',{},False),
 ('single','A','A',{'options':'A\nB'},True),('multiple','A;B','B;A',{'options':'A\nB\nC'},True),
 ('multiple','A;B','A;C',{'options':'A\nB\nC'},False)])
def test_grading(kind,expected,actual,extra,result):
    assert check(dict(kind=kind,answer=expected,**extra),actual)==result


@pytest.mark.parametrize('value',['1/0','nan','inf','1e100000','__import__("os")','1 2','', '9'*101])
def test_invalid(value):
    with pytest.raises(ValueError): number(value)
