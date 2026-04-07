# vectordb/routers/admin.py
# NOTE: /v1/health and /metrics are now in vectordb/routers/observability.py
# This file is kept only for the IndexManager injection used by the app factory.

index_manager = None


def set_index_manager(mgr):
    global index_manager
    index_manager = mgr
