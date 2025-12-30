# 🛠️ Tools Documentation

This document describes all backend tools exposed to the pharmacy assistant agent. Each tool is documented with its purpose, inputs, output schema, error handling, and fallback behavior.

---

## Table of Contents
1. [Medication Lookup](#medication-lookup)
   - [get_medication_by_name](#get_medication_by_name)
   - [get_medication_by_id](#get_medication_by_id)
   - [check_prescription_requirement](#check_prescription_requirement)
2. [Inventory & Reservations](#inventory--reservations)
   - [check_inventory](#check_inventory)
   - [reserve_medication](#reserve_medication)
   - [cancel_reservation_by_medication_id](#cancel_reservation_by_medication_id)
   - [cancel_reservation_by_reservation_id](#cancel_reservation_by_reservation_id)
   - [find_reservations_for_user](#find_reservations_for_user)
3. [Prescriptions](#prescriptions)
   - [find_active_prescriptions_for_user](#find_active_prescriptions_for_user)

---

## Medication Lookup

### `get_medication_by_name`
**Purpose** Look up a medication using a brand or generic name. Returns the full medication record when found, as well as partial matches.

**Inputs**
| Name | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | Brand or generic medication name |

**Output Schema**
```json
{
  "found": true,
  "medication": {
    "medication_id": "m001",
    "name_brand": "Advil",
    "name_generic": "Ibuprofen",
    "active_ingredients": [],
    "otc": true,
    "requires_prescription": false
  },
  "matches": [
    { "medication_id": "m001", "name_brand": "Advil", "name_generic": "Ibuprofen" }
  ]
}
```
Error Handling - No hard error is raised.

If no exact match is found, found is set to false.

Fallback Behavior - Returns partial matches when available.

Agent may ask the user to clarify between multiple matches.

### `get_medication_by_id`

***Purpose*** Retrieve basic medication details using a unique medication ID.

***Inputs*** 
| Name | Type | Required |
| :--- | :--- | :--- | 
| medication_id | string | Yes |

Output Schema
```JSON

{
  "found": true,
  "medication": {
    "medication_id": "m001",
    "name_brand": "Advil",
    "name_generic": "Ibuprofen"
  }
}
```
Error Handling 
| error_code | Meaning | 
| :--- | :--- | 
| NOT_FOUND | No medication exists with this ID |

### `check_prescription_requirement`

***Purpose*** Check whether a medication requires a prescription.

***Inputs***
| Name | Type | Required | 
| :--- | :--- | :--- | 
| medication_id | string | Yes |

Output Schema
```JSON

{
  "medication_id": "m001",
  "requires_prescription": false
}
```
Error Handling 
| error_code | Meaning | 
| :--- | :--- | 
| NOT_FOUND | Medication ID not found |


## Inventory & Reservations
### `check_inventory`

***Purpose*** Check inventory availability for a medication at a specific store.

***Inputs***
| Name | Type | Required | Default | 
| :--- | :--- | :--- | :--- |
| medication_id | string | Yes | — |
| store_id | string | No | "s001" |

Output Schema
```JSON

{
  "medication_id": "m001",
  "store_id": "s001",
  "available": true,
  "quantity_available": 22,
  "quantity_on_hand": 24,
  "reserved": 2,
  "last_updated_iso": "2025-12-27T10:00:00Z"
}
```
Error Handling 
| error_code | Meaning |
| :--- | :--- |
| NOT_FOUND | Inventory record not found |

Fallback Behavior - Defaults to store s001 if none provided.

### `reserve_medication`

***Purpose*** Reserve medication inventory for a user at a specific store. Validates stock availability, duplicate reservations, and prescription requirements.

***Inputs*** 
| Name | Type | Required | Description |
| :--- | :--- | :--- | :--- | 
| medication_id | string | Yes | Medication ID to reserve |
| requested_quantity | integer | Yes | Number of units |
| users_phone_last4 | string | Yes | Last 4 digits of user phone |
| store_id | string | No | Store ID (default s001) |

Output Schema
```JSON

{
  "success": true,
  "reservation": {
    "reservation_id": "r_abcd1234",
    "medication_id": "m001",
    "store_id": "s001",
    "quantity": 2,
    "created_at_iso": "2025-12-30T12:00:00Z",
    "expires_at_iso": "2025-12-31T12:00:00Z"
  }
}
```
Error Handling 
| error_code | Meaning |
| :--- | :--- |
| BAD_REQUEST | Invalid quantity |
| NOT_FOUND | User or inventory not found |
| ALREADY_RESERVED | User already has a reservation for this item |
| INSUFFICIENT_STOCK | Not enough inventory available |
| PRESCRIPTION_REQUIRED | Active prescription required to reserve |

### `cancel_reservation_by_medication_id`

***Purpose*** Cancel a reservation using medication ID and store ID. Releases reserved inventory back into availability.

***Inputs*** 
| Name | Type | Required |
| :--- | :--- | :--- |
| medication_id | string | Yes |
| users_phone_last4 | string | Yes | 
| store_id | string | No |

Output Schema
```JSON
{
  "success": true,
  "message": "Reservation cancelled."
}
```
Error Handling 
| error_code | Meaning | 
| :--- | :--- | 
| NO_RESERVATION | No reservation exists for this criteria | 
| NOT_FOUND | User not found |


### `cancel_reservation_by_reservation_id`

***Purpose*** Cancel a reservation using its unique reservation ID.

***Inputs*** 
| Name | Type | Required | 
| :--- | :--- | :--- | 
| reservation_id | string | Yes | 
| users_phone_last4 | string | Yes |

Output Schema
```JSON
{
  "success": true,
  "message": "Reservation cancelled."
}
```

### `find_reservations_for_user`

***Purpose*** List all active reservations for a specific user.

***Inputs*** 
| Name | Type | Required | 
| :--- | :--- | :--- | 
| users_phone_last4 | string | Yes |

Output Schema
```JSON

{
  "success": true,
  "users_phone_last4": "1234",
  "reservations": [
    {
      "reservation_id": "r_abcd1234",
      "medication_id": "m001",
      "medication": {
        "name_brand": "Advil",
        "name_generic": "Ibuprofen",
        "requires_prescription": false
      }
    }
  ],
  "count": 1
}
```

## Prescriptions
### `find_active_prescriptions_for_user`

***Purpose*** List all active prescriptions associated with a user's phone number.

***Inputs*** 
| Name | Type | Required | 
| :--- | :--- | :--- | 
| users_phone_last4 | string | Yes |

Output Schema
```JSON

{
  "success": true,
  "users_phone_last4": "1234",
  "active_prescriptions": [
    {
      "rx_id": "rx1003",
      "medication_id": "m005",
      "medication": {
        "name_brand": "Amoxicillin",
        "name_generic": "Amoxicillin"
      }
    }
  ],
  "count": 1
}
```
Error Handling 
| error_code | Meaning | 
| :--- | :--- | 
| NO_PRESCRIPTIONS | No active prescriptions on file | 
| NOT_FOUND | User phone digits not found |