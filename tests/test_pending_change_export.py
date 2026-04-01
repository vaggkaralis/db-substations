import DBrun


class _FakeConn:
    def __init__(self, in_transaction):
        self.in_transaction = in_transaction


def test_do_export_pending_changes_waits_for_commit(monkeypatch):
    app = object.__new__(DBrun.SubstationApp)
    app.conn = _FakeConn(in_transaction=True)
    app.db_path = "dummy.db"
    app._export_scheduled = True

    scheduled = []
    exported = []

    monkeypatch.setattr(
        DBrun.Clock,
        "schedule_once",
        lambda fn, timeout=0: scheduled.append((fn, timeout)),
    )
    monkeypatch.setattr(
        app,
        "_export_pending_changes",
        lambda show_popup=False: exported.append(show_popup),
    )

    app._do_export_pending_changes()

    assert exported == []
    assert len(scheduled) == 1
    assert app._export_scheduled is True

    callback, _timeout = scheduled.pop()
    app.conn.in_transaction = False
    callback(None)

    assert exported == [False]
    assert app._export_scheduled is False