"""Tests for src.registry — the dynamic user registry."""

from __future__ import annotations


def test_register_user_is_idempotent(tmp_knowledge_dir, chat_id):
    from src.registry import is_registered, register_user

    assert register_user(chat_id) is True
    assert register_user(chat_id) is False  # already registered
    assert is_registered(chat_id) is True


def test_register_rejects_invalid_id(tmp_knowledge_dir):
    from src.registry import register_user

    assert register_user(0) is False
    assert register_user(-5) is False


def test_all_user_ids_excludes_blocked(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.registry import all_user_ids, register_user, set_blocked

    register_user(chat_id)
    register_user(other_chat_id)
    set_blocked(other_chat_id, True)

    ids = all_user_ids()
    assert chat_id in ids
    assert other_chat_id not in ids


def test_block_and_unblock(tmp_knowledge_dir, chat_id):
    from src.registry import is_blocked, register_user, set_blocked

    register_user(chat_id)
    assert is_blocked(chat_id) is False
    set_blocked(chat_id, True)
    assert is_blocked(chat_id) is True
    set_blocked(chat_id, False)
    assert is_blocked(chat_id) is False


def test_admin_role(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.registry import is_admin, register_user

    register_user(chat_id, role="admin")
    register_user(other_chat_id, role="user")
    assert is_admin(chat_id) is True
    assert is_admin(other_chat_id) is False


def test_register_upgrades_user_to_admin(tmp_knowledge_dir, chat_id):
    from src.registry import is_admin, register_user

    register_user(chat_id, role="user")
    assert is_admin(chat_id) is False
    register_user(chat_id, role="admin")  # idempotent call upgrades role
    assert is_admin(chat_id) is True


def test_seed_admins_is_idempotent(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.registry import is_admin, seed_admins

    created = seed_admins([chat_id, other_chat_id], {chat_id: "Owner"})
    assert created == 2
    assert is_admin(chat_id) and is_admin(other_chat_id)
    assert seed_admins([chat_id], {}) == 0  # already present


def test_get_user(tmp_knowledge_dir, chat_id):
    from src.registry import get_user, register_user

    register_user(chat_id, label="Alice")
    rec = get_user(chat_id)
    assert rec["label"] == "Alice"
    assert rec["role"] == "user"
    assert get_user(999999999) is None


def test_registry_persists_across_reload(tmp_knowledge_dir, chat_id, monkeypatch):
    import src.registry as registry

    registry.register_user(chat_id, label="Bob")
    # Simulate a fresh process — drop the cache and reload from disk.
    monkeypatch.setattr(registry, "_registry_cache", None)
    registry.init_registry()
    assert registry.is_registered(chat_id) is True
    assert registry.get_user(chat_id)["label"] == "Bob"


def test_registry_isolation(tmp_knowledge_dir, chat_id, other_chat_id):
    """Registering one user must not register another (tenant isolation)."""
    from src.registry import is_registered, register_user

    register_user(chat_id)
    assert is_registered(chat_id) is True
    assert is_registered(other_chat_id) is False
