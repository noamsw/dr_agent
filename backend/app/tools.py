from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from app.db import load_json, save_json

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_medication_by_name(name: str) -> Dict[str, Any]:
    meds = load_json("medications.json")
    q = name.strip().lower()
    exact = None
    matches = []
    for m in meds:
        brand = m["name_brand"].lower()
        gen = m["name_generic"].lower()
        if q == brand or q == gen:
            exact = m
        if q in brand or q in gen:
            matches.append({
                "medication_id": m["medication_id"],
                "name_brand": m["name_brand"],
                "name_generic": m["name_generic"],
            })
    if exact:
        return {"found": True, "medication": exact, "matches": matches}
    return {"found": False, "medication": None, "matches": matches}

def check_inventory(medication_id: str, store_id: str = "s001") -> Dict[str, Any]:
    inv = load_json("inventory.json")
    rec = next((x for x in inv if x["store_id"] == store_id and x["medication_id"] == medication_id), None)
    if not rec:
        return {"error_code": "NOT_FOUND", "message": "No inventory record for that store/medication."}
    available_qty = max(0, rec["quantity_on_hand"] - rec["reserved"])
    return {
        "medication_id": medication_id,
        "store_id": store_id,
        "available": available_qty > 0,
        "quantity_available": available_qty,
        "quantity_on_hand": rec["quantity_on_hand"],
        "reserved": rec["reserved"],
        "last_updated_iso": rec["last_updated_iso"],
    }

def check_prescription_requirement(medication_id: str) -> Dict[str, Any]:
    meds = load_json("medications.json")
    m = next((x for x in meds if x["medication_id"] == medication_id), None)
    if not m:
        return {"error_code": "NOT_FOUND", "message": "Unknown medication_id."}
    req = bool(m["requires_prescription"])
    return {
        "medication_id": medication_id,
        "requires_prescription": req,
        "note": "Prescription-only" if req else "OTC (no prescription required)",
    }

def check_allergy_concerns_and_ingredients(medication_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    meds = load_json("medications.json")
    m = next((x for x in meds if x["medication_id"] == medication_id), None)
    if not m:
        return {"error_code": "NOT_FOUND", "message": "Unknown medication_id."}

    allergy_flag = None
    matches: List[str] = []

    if user_id:
        users = load_json("users.json")
        u = next((x for x in users if x["user_id"] == user_id), None)
        if not u:
            return {"error_code": "NOT_FOUND", "message": "Unknown user_id."}
        user_allergies = [a.lower() for a in u.get("allergies", [])]
        ingr_names = [i["name"].lower() for i in m.get("active_ingredients", [])]
        matches = [a for a in user_allergies if a in ingr_names]
        allergy_flag = len(matches) > 0

    return {
        "medication_id": medication_id,
        "active_ingredients": m.get("active_ingredients", []),
        "allergy_flag": allergy_flag,
        "allergy_matches": matches,
        "disclaimer": "This is not medical advice. For safety and personalized guidance, consult a pharmacist or healthcare professional.",
    }

def submit_customer_feedback(rating: int, message: str, user_id: Optional[str] = None) -> Dict[str, Any]:
    if rating < 1 or rating > 5:
        return {"error_code": "INVALID_RATING", "message": "Rating must be 1-5."}
    fb = load_json("feedback.json")
    fid = f"fb{len(fb)+1:04d}"
    rec = {"feedback_id": fid, "user_id": user_id, "rating": rating, "message": message, "created_at_iso": _now_iso()}
    fb.append(rec)
    save_json("feedback.json", fb)
    return {"success": True, "feedback_id": fid, "created_at_iso": rec["created_at_iso"]}
