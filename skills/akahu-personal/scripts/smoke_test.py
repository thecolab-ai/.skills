#!/usr/bin/env python3
"""Intentional smoke-test skip.

Akahu Personal App data is authenticated personal banking data. CI must not call
live endpoints or require real tokens, and fixtures should not be committed.
"""

print('[SKIP] akahu-personal smoke test intentionally skipped: requires personal Akahu tokens and banking data')
