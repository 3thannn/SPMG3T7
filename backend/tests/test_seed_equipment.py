"""The US19 seed refreshes placeholders without overwriting staff edits."""

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
        if method == "POST":
            assert path == "/equipment"
            item = {"id": str(len(saved) + 1), **body}
            saved.append(item)
            return item
        assert method == "PUT"
        item = next(item for item in saved if path == f"/equipment/{item['id']}")
        item.update(body)
        return item

    monkeypatch.setattr(seed_equipment, "call", api)
    assert seed_equipment.seed() == (10, 0, 0)
    assert len({item["type"] for item in saved}) >= 5
    assert len({item["location"] for item in saved}) >= 3
    assert sum(item["outOfServiceQuantity"] > 0 for item in saved) >= 3
    assert len({item["description"] for item in saved}) == 10
    assert all(not item["description"].startswith("Demo ") for item in saved)
    saved[0]["description"] = "Edited by staff"
    saved[1]["description"] = "Demo projector equipment"
    assert seed_equipment.seed() == (0, 1, 9)
    assert saved[0]["description"] == "Edited by staff"
    assert saved[1]["description"] == seed_equipment.SAMPLES[1][-1]
    assert seed_equipment.seed() == (0, 0, 10)
