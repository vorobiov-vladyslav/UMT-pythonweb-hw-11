from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter instance — imported by both main.py (app.state + handler)
# and the routers that decorate endpoints, so there is a single token bucket.
limiter = Limiter(key_func=get_remote_address)
