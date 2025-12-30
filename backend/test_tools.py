import copy
import pytest

# IMPORTANT: adjust this import if your tools module path differs
# If you run from backend/, this is typically:
#   from app import tools
from app import tools


@pytest.fixture()
def fake_db(monkeypatch):
    """
    Replaces load_json/save_json with an in-memory "DB".
    This makes tests fast and deterministic (no real file IO).
    """
    state = {
        "medications.json": [
            {
                "medication_id": "m001",
                "name_brand": "Advil",
                "name_generic": "Ibuprofen",
                "active_ingredients": [{"name": "Ibuprofen", "amount": 200, "unit": "mg"}],
                "requires_prescription": False,
                "otc": True,
            },
            {
                "medication_id": "m005",
                "name_brand": "SomeRxMed",
                "name_generic": "RxGeneric",
                "active_ingredients": [{"name": "RxIngredient", "amount": 10, "unit": "mg"}],
                "requires_prescription": True,
                "otc": False,
            },
        ],
        "inventory.json": [
            {
                "store_id": "s001",
                "medication_id": "m001",
                "quantity_on_hand": 24,
                "reserved": 2,
                "last_updated_iso": "2025-12-27T10:00:00Z",
            },
            {
                "store_id": "s001",
                "medication_id": "m005",
                "quantity_on_hand": 3,
                "reserved": 0,
                "last_updated_iso": "2025-12-27T10:00:00Z",
            },
        ],
        "users.json": [
            {
                "user_id": "u001",
                "phone_last4": "1234",
                "allergies": ["Penicillin"],
                "active_prescriptions": [
                    {"rx_id": "rx1003", "medication_id": "m005", "status": "active"}
                ],
                "reservations": [],
            },
            {
                "user_id": "u002",
                "phone_last4": "9999",
                "allergies": [],
                "active_prescriptions": [],
                "reservations": [],
            },
        ],
    }

    def _load_json(name: str):
        # return a deep copy so code can mutate without affecting "stored" until save_json
        return copy.deepcopy(state[name])

    def _save_json(name: str, data):
        state[name] = copy.deepcopy(data)

    monkeypatch.setattr(tools, "load_json", _load_json, raising=True)
    monkeypatch.setattr(tools, "save_json", _save_json, raising=True)

    # stabilize timestamps and ids
    monkeypatch.setattr(tools, "_now_iso", lambda: "2025-12-30T00:00:00Z", raising=False)

    class _FakeUUID:
        hex = "aaaaaaaaaabbbbbbbbbbccccccccccdddddddddd"

    monkeypatch.setattr(tools.uuid, "uuid4", lambda: _FakeUUID(), raising=True)

    return state


def test_get_medication_by_name_exact(fake_db):
    out = tools.get_medication_by_name("Advil")
    assert out["found"] is True
    assert out["medication"]["medication_id"] == "m001"


def test_get_medication_by_name_partial_matches(fake_db):
    out = tools.get_medication_by_name("ibu")
    assert out["found"] is False  # partial shouldn't be "exact"
    assert len(out["matches"]) >= 1
    assert any(m["medication_id"] == "m001" for m in out["matches"])


def test_get_medication_by_id_found(fake_db):
    out = tools.get_medication_by_id("m001")
    assert out["found"] is True
    assert out["medication"]["name_brand"] == "Advil"


def test_get_medication_by_id_not_found(fake_db):
    out = tools.get_medication_by_id("m999")
    assert out["error_code"] == "NOT_FOUND"


def test_check_inventory_ok(fake_db):
    out = tools.check_inventory("m001", "s001")
    assert out["available"] is True
    assert out["quantity_available"] == 22  # 24 on hand - 2 reserved


def test_check_inventory_missing_record(fake_db):
    out = tools.check_inventory("m001", "s999")
    assert out["error_code"] == "NOT_FOUND"


def test_get_user_by_last4_ok_shape(fake_db):
    users = tools.load_json("users.json")
    user_rec, err = tools.get_user_by_last4(users, "1234")
    assert err is None
    assert user_rec["user_id"] == "u001"


def test_get_user_by_last4_not_found(fake_db):
    users = tools.load_json("users.json")
    user_rec, err = tools.get_user_by_last4(users, "0000")
    assert user_rec is None
    assert err["error_code"] == "NOT_FOUND"


def test_reserve_medication_rejects_bad_quantity(fake_db):
    out = tools.reserve_medication("m001", 0, "1234", "s001")
    assert out["error_code"] == "BAD_REQUEST"


def test_reserve_medication_not_found_med(fake_db):
    out = tools.reserve_medication("m999", 1, "1234", "s001")
    assert out["error_code"] == "NOT_FOUND"


def test_reserve_medication_not_found_user(fake_db):
    out = tools.reserve_medication("m001", 1, "0000", "s001")
    assert out["error_code"] == "NOT_FOUND"


def test_reserve_medication_insufficient_stock(fake_db):
    # m005 has 3 on hand
    out = tools.reserve_medication("m005", 10, "1234", "s001")
    assert out["error_code"] == "INSUFFICIENT_STOCK"


def test_reserve_medication_requires_prescription_blocks_without_rx(fake_db):
    # user 9999 has no active rx for m005
    out = tools.reserve_medication("m005", 1, "9999", "s001")
    assert out["error_code"] == "PRESCRIPTION_REQUIRED"


def test_reserve_medication_requires_prescription_allows_with_rx_and_updates(fake_db):
    out = tools.reserve_medication("m005", 2, "1234", "s001")
    assert out["success"] is True
    assert out["reservation"]["reservation_id"].startswith("r_")
    # confirm inventory reserved got updated in "DB"
    inv = fake_db["inventory.json"]
    rec = next(x for x in inv if x["store_id"] == "s001" and x["medication_id"] == "m005")
    assert rec["reserved"] == 2


def test_reserve_medication_prevents_duplicate_reservation(fake_db):
    out1 = tools.reserve_medication("m001", 1, "1234", "s001")
    assert out1["success"] is True
    out2 = tools.reserve_medication("m001", 1, "1234", "s001")
    assert out2["error_code"] == "ALREADY_RESERVED"


def test_cancel_reservation_by_reservation_id_happy_path(fake_db):
    # create reservation first
    created = tools.reserve_medication("m001", 2, "1234", "s001")
    assert created["success"] is True
    res_id = created["reservation"]["reservation_id"]

    # cancel
    out = tools.cancel_reservation_by_reservation_id(res_id, "1234")
    assert out["success"] is True

    # confirm removed from user + inventory reserved reduced
    users = fake_db["users.json"]
    u = next(x for x in users if x["phone_last4"] == "1234")
    assert all(r.get("reservation_id") != res_id for r in u.get("reservations", []))

    inv = fake_db["inventory.json"]
    rec = next(x for x in inv if x["store_id"] == "s001" and x["medication_id"] == "m001")
    assert rec["reserved"] == 2  # started at 2, reserved +2 -> 4, cancel -2 -> 2


def test_cancel_reservation_by_reservation_id_not_found(fake_db):
    out = tools.cancel_reservation_by_reservation_id("r_missing", "1234")
    assert out["error_code"] in ("NOT_FOUND", "NO_RESERVATION")


def test_find_active_prescriptions_for_user_none(fake_db):
    out = tools.find_active_prescriptions_for_user("9999")
    assert out["error_code"] == "NO_PRESCRIPTIONS"


def test_find_active_prescriptions_for_user_enriched(fake_db):
    out = tools.find_active_prescriptions_for_user("1234")
    assert out["success"] is True
    assert out["count"] >= 1
    assert out["active_prescriptions"][0]["medication"]["name_brand"] is not None


def test_find_reservations_for_user_none(fake_db):
    out = tools.find_reservations_for_user("9999")
    assert out["error_code"] == "NO_RESERVATIONS"


def test_find_reservations_for_user_enriched(fake_db):
    tools.reserve_medication("m001", 1, "1234", "s001")
    out = tools.find_reservations_for_user("1234")
    assert out["success"] is True
    assert out["count"] == 1
    assert out["reservations"][0]["medication"]["name_brand"] == "Advil"
