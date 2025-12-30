from pprint import pprint

from app.tools import (
    get_medication_by_name,
    check_inventory,
    check_prescription_requirement,
    check_allergy_concerns_and_ingredients,
    submit_customer_feedback,
)

def run():
    print("\n=== 1) get_medication_by_name: exact ===")
    pprint(get_medication_by_name("Advil"))

    print("\n=== 2) get_medication_by_name: fuzzy ===")
    pprint(get_medication_by_name("ibu"))

    print("\n=== 3) check_inventory: existing ===")
    pprint(check_inventory("m001", "s001"))

    print("\n=== 4) check_inventory: missing record ===")
    pprint(check_inventory("m999", "s001"))

    print("\n=== 5) check_prescription_requirement: existing ===")
    pprint(check_prescription_requirement("m003"))

    print("\n=== 6) check_prescription_requirement: unknown ===")
    pprint(check_prescription_requirement("m999"))

    print("\n=== 7) check_allergy_concerns_and_ingredients: without user ===")
    pprint(check_allergy_concerns_and_ingredients("m001"))

    print("\n=== 8) check_allergy_concerns_and_ingredients: with user (match) ===")
    pprint(check_allergy_concerns_and_ingredients("m001", "u001"))

if __name__ == "__main__":
    run()