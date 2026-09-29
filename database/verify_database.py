"""Live Supabase database verification and schema inspection utility."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.exceptions import (
    MissingSupabaseCredentialsError,
    SupabaseDatabaseError,
)
from database.supabase_client import get_supabase_client

REQUIRED_TABLES = ["companies", "posts", "post_revisions", "approvals", "publications"]


def verify_live_database() -> Tuple[bool, Dict[str, Dict[str, any]]]:
    """Verify presence and accessibility of all required tables in Supabase.

    Returns:
        (all_present: bool, table_reports: dict)
    """
    try:
        client = get_supabase_client()
    except MissingSupabaseCredentialsError as e:
        print(f"[ERROR] Supabase credentials missing: {e}", file=sys.stderr)
        return False, {}
    except Exception as e:
        print(f"[ERROR] Could not connect to Supabase: {e}", file=sys.stderr)
        return False, {}

    results: Dict[str, Dict[str, any]] = {}
    all_present = True

    print("=" * 60)
    print("JEVYAM TECHNOLOGIES — SUPABASE SCHEMA VERIFICATION")
    print("=" * 60)

    for table in REQUIRED_TABLES:
        try:
            res = client.table(table).select("*").limit(1).execute()
            count_data = len(res.data) if res.data else 0
            results[table] = {
                "exists": True,
                "accessible": True,
                "data_count": count_data,
                "sample": res.data[0] if count_data > 0 else None,
            }
            print(f"[OK] Table '{table}': Present and accessible (sample rows: {count_data})")
        except Exception as e:
            err_msg = str(e)
            all_present = False
            results[table] = {
                "exists": False,
                "accessible": False,
                "error": err_msg,
            }
            if "PGRST205" in err_msg or "schema cache" in err_msg:
                print(f"[MISSING] Table '{table}': Not found in Supabase schema cache.")
            else:
                print(f"[ERROR] Table '{table}': {err_msg}")

    print("=" * 60)
    if all_present:
        print("RESULT: All required Phase 1-3 tables are verified and active!")
    else:
        print("RESULT: One or more tables are missing from the live database.")
        print("ACTION REQUIRED: Execute 'database/schema.sql' in the Supabase SQL Editor.")
    print("=" * 60)

    return all_present, results


if __name__ == "__main__":
    success, _ = verify_live_database()
    sys.exit(0 if success else 1)
