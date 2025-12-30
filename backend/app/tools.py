from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from app.db import load_json, save_json
import uuid

def _now_iso() -> str:
    """
    Return the current UTC time as an ISO-8601 string (seconds precision).
    """
    return  datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def get_medication_by_name(name: str) -> Dict[str, Any]:
    """
    Look up a medication by brand or generic name.
    Returns exact match if found, plus partial matches.
    """
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

def get_medication_by_id(medication_id: str) -> Dict[str, Any]:
    """
    Retrieve basic medication details by medication_id.
    """
    meds = load_json("medications.json")
    q = medication_id.strip().lower()

    for m in meds:
        m_id = m.get("medication_id", "").lower()
        if q == m_id:
            return {
                "found": True,
                "medication": {
                    "medication_id": m.get("medication_id"),
                    "name_brand": m.get("name_brand"),
                    "name_generic": m.get("name_generic"),
                },
            }

    return {
        "error_code": "NOT_FOUND",
        "message": "No such medication_id on file."
    }

def check_inventory(medication_id: str, store_id: str = "s001") -> Dict[str, Any]:
    """
    Check inventory availability for a medication at a given store.
    """
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

def has_active_prescription(user_rec: dict, medication_id: str) -> bool:
    """
    Return True if the user has an active prescription for the medication.
    """
    for rx in user_rec.get("active_prescriptions", []):
        if (
            rx.get("medication_id") == medication_id
            and rx.get("status") == "active"
        ):
            return True
    return False

def get_user_by_last4(
    users: List[Dict[str, Any]],
    users_phone_last4: str,) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Find a user by the last 4 digits of their phone number.
    Returns (user_record, error) where exactly one is non-None.
    """
    idx = next(
        (i for i, u in enumerate(users) if u.get("phone_last4") == users_phone_last4),
        None
    )
    if idx is None:
        return None, {
            "error_code": "NOT_FOUND",
            "message": "No recorded user with that number."
        }
    return users[idx], None

def reserve_medication(
    medication_id: str,
    requested_quantity: int,
    users_phone_last4: str,
    store_id: str = "s001",) -> Dict[str, Any]:
    """
    Reserve a medication at a store for a user.
    Validates stock, duplicate reservations, and prescription requirements.
    """
    if requested_quantity <= 0:
        return {"error_code": "BAD_REQUEST", "message": "requested_quantity must be > 0."}

    inv = load_json("inventory.json")
    users = load_json("users.json")
    meds = load_json("medications.json")

    med = next((m for m in meds if m["medication_id"] == medication_id), None)
    if not med:
        return {"error_code": "NOT_FOUND", "message": "Medication not found."}

    med_rec = next((x for x in inv if x["store_id"] == store_id and x["medication_id"] == medication_id), None)
    if not med_rec:
        return {"error_code": "NOT_FOUND", "message": "No inventory record for that store/medication."}

    user_rec, err = get_user_by_last4(users, users_phone_last4)
    if err:
        return err

    # Ensure reservations field exists
    reservations = user_rec.get("reservations") or []
    user_rec["reservations"] = reservations

    # Check if user already has an active reservation for same med+store
    for r in reservations:
        if (
            r.get("medication_id") == medication_id
            and r.get("store_id") == store_id
        ):
            return {
                "error_code": "ALREADY_RESERVED",
                "message": "User already has a reservation for this medication at this store.",
                "existing_reservation": r,
            }

    # Prescription gate (simple)
    if med.get("requires_prescription", False):
        if not has_active_prescription(user_rec, medication_id):
            return {
                "error_code": "PRESCRIPTION_REQUIRED",
                "message": "This medication requires a prescription and the user has no active prescription on file."
            }

    available_qty = max(0, int(med_rec.get("quantity_on_hand", 0)) - int(med_rec.get("reserved", 0)))
    if available_qty < requested_quantity:
        return {
            "error_code": "INSUFFICIENT_STOCK",
            "message": "Not enough medication in stock for that store.",
            "quantity_available": available_qty,
        }

    # Apply reservation
    reservation_id = f"r_{uuid.uuid4().hex[:10]}"
    created_at = _now_iso()

    med_rec["reserved"] = int(med_rec.get("reserved", 0)) + requested_quantity
    med_rec["last_updated_iso"] = created_at

    reservation = {
        "reservation_id": reservation_id,
        "medication_id": medication_id,
        "store_id": store_id,
        "quantity": requested_quantity,
        "created_at_iso": created_at,
    }
    reservations.append(reservation)

    # Persist updates
    save_json("inventory.json", inv)
    save_json("users.json", users)

    return {
        "success": True,
        "reservation": reservation,
        "inventory": {
            "medication_id": medication_id,
            "store_id": store_id,
            "quantity_on_hand": med_rec.get("quantity_on_hand"),
            "reserved": med_rec.get("reserved"),
            "quantity_available_after": max(0, int(med_rec.get("quantity_on_hand", 0)) - int(med_rec.get("reserved", 0))),
            "last_updated_iso": med_rec.get("last_updated_iso"),
        },
        "note": "Reservation created.",
    }

def cancel_reservation_by_medication_id(
    medication_id: str,
    users_phone_last4: str,
    store_id: str = "s001",) -> Dict[str, Any]:
    """
    Cancel a user's reservation for a medication at a specific store.
    Restores reserved inventory back to available stock.
    """

    users = load_json("users.json")
    inv = load_json("inventory.json")

    user_rec, err = get_user_by_last4(users, users_phone_last4)
    if err:
        return err

    # Ensure reservations field exists
    reservations = user_rec.get("reservations") or []
    user_rec["reservations"] = reservations

    if not reservations:
        return {
            "error_code": "NO_RESERVATION",
            "message": "This user has no reservation on file."
        }

    # Find matching reservation
    res_idx = next(
        (i for i, r in enumerate(reservations)
         if r.get("medication_id") == medication_id and r.get("store_id", store_id) == store_id),
        None
    )
    if res_idx is None:
        return {
            "error_code": "NO_RESERVATION",
            "message": "No reservation found for this medication (and store) for this user."
        }

    reservation = reservations[res_idx]
    qty = int(reservation.get("quantity", 0))
    if qty <= 0:
        return {
            "error_code": "BAD_RESERVATION",
            "message": "Reservation quantity is missing or invalid.",
            "reservation": reservation
        }

    # Find inventory record
    med_rec = next((x for x in inv if x.get("store_id") == store_id and x.get("medication_id") == medication_id), None)
    if not med_rec:
        return {
            "error_code": "NOT_FOUND",
            "message": "No inventory record for that store/medication.",
            "reservation": reservation
        }

    # Update inventory reserved (releasing stock back to available)
    current_reserved = int(med_rec.get("reserved", 0))
    med_rec["reserved"] = max(0, current_reserved - qty)

    # Remove reservation from user (since presence == active)
    reservations.pop(res_idx)

    # Persist changes
    save_json("inventory.json", inv)
    save_json("users.json", users)
    return {
        "success": True,
        "message": "Reservation cancelled.",
        "cancelled": {
            "medication_id": medication_id,
            "store_id": store_id,
            "quantity_released": qty,
            "users_phone_last4": users_phone_last4,
        },
    }

def cancel_reservation_by_reservation_id(
    reservation_id: str,
    users_phone_last4: str,) -> Dict[str, Any]:
    """
    Cancel a reservation using its reservation_id.
    """
    users = load_json("users.json")
    inv = load_json("inventory.json")

    user_rec, err = get_user_by_last4(users, users_phone_last4)
    if err:
        return err
    
    reservations = user_rec.get("reservations") or []
    user_rec["reservations"] = reservations

    if not reservations:
        return {
            "error_code": "NO_RESERVATION",
            "message": "This user has no reservation on file."
        }

    # Find reservation by ID
    res_idx = next(
        (i for i, r in enumerate(reservations) if r.get("reservation_id") == reservation_id),
        None
    )
    if res_idx is None:
        return {
            "error_code": "NOT_FOUND",
            "message": "No reservation found with that reservation_id for this user."
        }

    reservation = reservations[res_idx]
    medication_id = reservation.get("medication_id")
    store_id = reservation.get("store_id", "s001")
    qty = int(reservation.get("quantity", 0))

    if qty <= 0:
        return {
            "error_code": "BAD_RESERVATION",
            "message": "Reservation quantity is missing or invalid.",
            "reservation": reservation,
        }

    # Find inventory record
    med_rec = next(
        (x for x in inv if x.get("store_id") == store_id and x.get("medication_id") == medication_id),
        None
    )
    if not med_rec:
        return {
            "error_code": "NOT_FOUND",
            "message": "No inventory record for that store/medication.",
            "reservation": reservation,
        }

    # Release reserved quantity
    med_rec["reserved"] = max(0, int(med_rec.get("reserved", 0)) - qty)
    med_rec["last_updated_iso"] = _now_iso()

    # Remove reservation from user
    reservations.pop(res_idx)

    # Persist changes
    save_json("inventory.json", inv)
    save_json("users.json", users)
    return {
        "success": True,
        "message": "Reservation cancelled.",
        "cancelled": {
            "reservation_id": reservation_id,
            "medication_id": medication_id,
            "store_id": store_id,
            "quantity_released": qty,
            "users_phone_last4": users_phone_last4,
        },
    }

def find_active_prescriptions_for_user(
    users_phone_last4: str,
) -> Dict[str, Any]:
    """
    List all active prescriptions for a user.
    """
    users = load_json("users.json")
    meds = load_json("medications.json")

    user_rec, err = get_user_by_last4(users, users_phone_last4)
    if err:
        return err

    # Ensure active_prescriptions field exists
    prescriptions = user_rec.get("active_prescriptions") or []
    if not prescriptions:
        return {
            "error_code": "NO_PRESCRIPTIONS",
            "message": "This user has no active prescriptions on file."
        }

    # Filter active prescriptions
    active_rx = [p for p in prescriptions if p.get("status") == "active"]

    if not active_rx:
        return {
            "error_code": "NO_PRESCRIPTIONS",
            "message": "This user has no active prescriptions on file."
        }

    # Enrich with medication details
    results = []
    for rx in active_rx:
        med = next(
            (m for m in meds if m.get("medication_id") == rx.get("medication_id")),
            None
        )

        results.append({
            "rx_id": rx.get("rx_id"),
            "medication_id": rx.get("medication_id"),
            "status": rx.get("status"),
            "medication": {
                "name_brand": med.get("name_brand") if med else None,
                "name_generic": med.get("name_generic") if med else None,
                "requires_prescription": med.get("requires_prescription") if med else None,
            }
        })

    return {
        "success": True,
        "users_phone_last4": users_phone_last4,
        "active_prescriptions": results,
        "count": len(results),
    }

def find_reservations_for_user(users_phone_last4: str) -> Dict[str, Any]:
    """
    List all active reservations for a user.
    """
    users = load_json("users.json")
    meds = load_json("medications.json")

    user_rec = next((u for u in users if u.get("phone_last4") == users_phone_last4), None)
    if not user_rec:
        return {"error_code": "NOT_FOUND", "message": "No recorded user with that number."}

    reservations = user_rec.get("reservations") or []
    if not reservations:
        return {"error_code": "NO_RESERVATIONS", "message": "This user has no reservations on file."}

    results = []
    for r in reservations:
        med = next((m for m in meds if m.get("medication_id") == r.get("medication_id")), None)

        results.append({
            "reservation_id": r.get("reservation_id"),
            "medication_id": r.get("medication_id"),
            "store_id": r.get("store_id"),
            "quantity": r.get("quantity"),
            "created_at_iso": r.get("created_at_iso"),
            "medication": {
                "name_brand": med.get("name_brand") if med else None,
                "name_generic": med.get("name_generic") if med else None,
                "requires_prescription": med.get("requires_prescription") if med else None,
            },
        })

    return {
        "success": True,
        "users_phone_last4": users_phone_last4,
        "reservations": results,
        "count": len(results),
    }
        
def check_prescription_requirement(medication_id: str) -> Dict[str, Any]:
    """
    Check whether a medication requires a prescription.
    """
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
