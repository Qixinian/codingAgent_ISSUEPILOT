"""IssuePilot M3.1 asynchronous API and persistence layer. IssuePilot M3.1异步API与持久化层。"""

from .api import create_app

__all__ = ["create_app"] # issuepilot.m3 这个包主要对外提供 create_app

