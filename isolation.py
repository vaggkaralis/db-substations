"""
Delegating wrappers for isolation requests UI in `DBrun.py`.
"""

def show_isolation_requests_delegate(app, instance=None):
    return app.show_isolation_requests(instance)


def show_add_isolation_request_delegate(app, parent_popup):
    return app.show_add_isolation_request(parent_popup)


def show_isolation_request_details_delegate(app, request_id, parent_popup=None):
    return app.show_isolation_request_details(request_id, parent_popup)
