from datetime import date
import pytest
from scripts.notify_latest import qualifies

EXPECTED = dict(city="helsinki", category="citizenship", service="citizenship-matters", people=2, family_members=False)

def result(**changes):
    return dict(EXPECTED, status="available", latest_at="2027-05-07T15:05:00+03:00", horizon="2027-05-09", evidence="Last week and Friday appointment label", **changes)

@pytest.mark.parametrize("threshold,match", [("2027-05-06", True), ("2027-05-07", False), ("2027-05-08", False)])
def test_strict_date(threshold, match):
    assert qualifies(result(), EXPECTED, date.fromisoformat(threshold)) is match

def test_helsinki_date():
    data = result(); data["latest_at"] = "2027-05-06T22:05:00+00:00"
    assert qualifies(data, EXPECTED, date(2027,5,6))

@pytest.mark.parametrize("change", [{"people":1}, {"latest_at":"2027-05-07T15:05:00"}, {"status":"error"}, {"horizon":None}, {"horizon":"2027-05-01"}])
def test_invalid_evidence(change):
    data=result(); data.update(change)
    with pytest.raises(ValueError): qualifies(data, EXPECTED, date(2027,5,1))

def test_no_availability():
    data=result(); data.update(status="no_availability", latest_at=None)
    assert not qualifies(data, EXPECTED, date(2027,5,1))

@pytest.mark.parametrize("status,send_ok,expected_code", [("available",True,0),("error",True,1),("available",False,2)])
def test_launcher(tmp_path, monkeypatch, status, send_ok, expected_code):
    import json
    from pathlib import Path
    from scripts import notify_latest as module
    skill=tmp_path/"SKILL.md"; skill.write_text("external skill")
    calls=[]
    class Child:
        returncode=0
        def __init__(self, command, **kwargs):
            assert "ALARMER_KEY" not in kwargs["env"]
            assert "--approve-for-me" in command
            self.output=Path(command[command.index("--output-last-message")+1])
        def communicate(self, prompt, timeout):
            assert "secret-key" not in prompt
            data=result(); data["status"]=status
            self.output.write_text(json.dumps(data))
    monkeypatch.setenv("ALARMER_KEY", "secret-key")
    monkeypatch.setattr(module.subprocess,"Popen",Child)
    monkeypatch.setattr(module,"send_alarmer_message",lambda key,message: calls.append(message) or send_ok)
    args=["--browser-skill",str(skill),"--runtime-dir",str(tmp_path/"runtime"),"--after","2027-05-01"]
    assert module.main(args)==expected_code
    assert len(calls)==1
    assert module.main(args)==expected_code
    assert len(calls)==2
