from adaptcache import AdaptCache


def test_invalidate_tag_clears_all_tagged_entries():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=300)
    calls = []

    @cache.intelligent(tags=["users"])
    def get_all_user_names():
        calls.append(1)
        return ["Ana", "Bob"]

    get_all_user_names()
    get_all_user_names()
    assert calls == [1]  # second call was a cache hit

    cache.invalidate_tag("users")
    get_all_user_names()
    assert calls == [1, 1]  # recomputed after the tag was invalidated


def test_invalidate_tag_does_not_affect_other_tags():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=300)
    user_calls, order_calls = [], []

    @cache.intelligent(tags=["users"])
    def get_users():
        user_calls.append(1)
        return ["Ana"]

    @cache.intelligent(tags=["orders"])
    def get_orders():
        order_calls.append(1)
        return ["#1"]

    get_users()
    get_orders()

    cache.invalidate_tag("orders")
    get_users()  # still cached, untouched by the "orders" invalidation
    get_orders()  # recomputed

    assert user_calls == [1]
    assert order_calls == [1, 1]


def test_untagged_entries_are_unaffected_by_invalidate_tag():
    cache = AdaptCache(backend="memory", adaptive_ttl=False, default_ttl=300)
    calls = []

    @cache.intelligent()  # no tags
    def get_value():
        calls.append(1)
        return 42

    get_value()
    cache.invalidate_tag("anything")
    get_value()
    assert calls == [1]  # untagged entry survives an unrelated tag invalidation
