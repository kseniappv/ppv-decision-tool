"""
Debug: test fetch_category_parents with known insufficient-data category IDs.
Run: python3 debug_parents.py
"""
from clickhouse_loader import _get_client

# A few known insufficient-data categories from Айгеша's file
TEST_IDS = [5397, 5438, 5444, 5633, 5664, 5691, 5696, 5698, 5700]

client = _get_client()
cats_str = ", ".join(str(c) for c in TEST_IDS)

print("=== Test 1: is_deleted = false ===")
try:
    rows = client.query(f"""
        SELECT id, parent_id, name
        FROM pg_catalog_microservice.category
        WHERE id IN ({cats_str})
          AND is_deleted = false
    """).result_rows
    print(f"OK — {len(rows)} rows returned")
    for r in rows:
        print(f"  id={r[0]}, parent_id={r[1]}, name={r[2]}")
except Exception as e:
    print(f"ERROR: {e}")

print()
print("=== Test 2: is_deleted = 0 ===")
try:
    rows = client.query(f"""
        SELECT id, parent_id, name
        FROM pg_catalog_microservice.category
        WHERE id IN ({cats_str})
          AND is_deleted = 0
    """).result_rows
    print(f"OK — {len(rows)} rows returned")
    for r in rows:
        print(f"  id={r[0]}, parent_id={r[1]}, name={r[2]}")
except Exception as e:
    print(f"ERROR: {e}")

print()
print("=== Test 3: without is_deleted filter ===")
try:
    rows = client.query(f"""
        SELECT id, parent_id, name
        FROM pg_catalog_microservice.category
        WHERE id IN ({cats_str})
    """).result_rows
    print(f"OK — {len(rows)} rows returned")
    for r in rows:
        print(f"  id={r[0]}, parent_id={r[1]}, name={r[2]}")
except Exception as e:
    print(f"ERROR: {e}")

client.close()
