import threading

from uedcli.serve.claims import ClaimRegistry


def test_mint_returns_a_token():
    registry = ClaimRegistry()
    token = registry.mint("sess1")
    assert isinstance(token, str) and len(token) > 8


def test_check_matching_token_returns_true():
    registry = ClaimRegistry()
    token = registry.mint("sess1")
    assert registry.check("sess1", token) is True


def test_check_stale_token_returns_false():
    registry = ClaimRegistry()
    old = registry.mint("sess1")
    registry.mint("sess1")  # a second window claims
    assert registry.check("sess1", old) is False


def test_check_with_no_claim_recorded_establishes_it_and_returns_true():
    registry = ClaimRegistry()
    assert registry.check("sess1", "whatever-token") is True
    assert registry.check("sess1", "whatever-token") is True
    assert registry.check("sess1", "a-different-token") is False


def test_mint_after_a_restart_equivalent_new_registry_does_not_see_old_token():
    registry = ClaimRegistry()
    old_token = registry.mint("sess1")
    fresh_registry = ClaimRegistry()  # simulates a server restart -- new process, empty map
    assert fresh_registry.check("sess1", old_token) is True  # no claim recorded -> establishes it


def test_lock_for_returns_the_same_lock_object_for_the_same_session():
    registry = ClaimRegistry()
    assert registry.lock_for("sess1") is registry.lock_for("sess1")


def test_lock_for_returns_different_locks_for_different_sessions():
    registry = ClaimRegistry()
    assert registry.lock_for("sess1") is not registry.lock_for("sess2")


def test_check_and_mint_are_thread_safe_under_concurrent_access():
    registry = ClaimRegistry()
    registry.mint("sess1")
    errors = []

    def hammer():
        try:
            for _ in range(200):
                registry.mint("sess1")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
