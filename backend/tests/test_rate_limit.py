from app.core.security import RateLimitMiddleware


def test_idle_clients_are_forgotten():
    limiter = RateLimitMiddleware(app=None, per_minute=5)
    limiter.hits["1.1.1.1"].append(0.0)
    limiter.hits["2.2.2.2"].append(100.0)
    limiter._forget_idle(now=120.0)
    assert list(limiter.hits) == ["2.2.2.2"]
