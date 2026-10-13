"""The US19 demo seed uses the public API and never overwrites edits."""

import seed_equipment


def test_seed_creates_ten_varied_items_and_skips_existing(monkeypatch):
    saved: list[dict] = []

    def api(path, method="GET", body=None, token=""):
        if path == "/auth/login":
            assert method == "POST"
            assert body["email"] == seed_equipment.EMAIL
            return {"token": "test-token"}
        assert token == "test-token"
        if method == "GET":
            return saved
        assert path == "/equipment" and method == "POST"
        saved.append(body)
        return {"id": str(len(saved)), **body}

    monkeypatch.setattr(seed_equipment, "call", api)
    assert seed_equipment.seed() == (10, 0)
    assert len({item["type"] for item in saved}) >= 5
    assert len({item["location"] for item in saved}) >= 3
    assert sum(item["outOfServiceQuantity"] > 0 for item in saved) >= 3
    saved[0]["description"] = "Edited by staff"
    assert seed_equipment.seed() == (0, 10)
    assert saved[0]["description"] == "Edited by staff"
