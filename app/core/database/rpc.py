# app/core/database/rpc.py
# SQLAlchemy wrappers for Supabase PostgreSQL RPC functions.
# Usage: import the function and pass a db Session from get_db().
from sqlalchemy.orm import Session
from sqlalchemy import text


def rpc_get_account_id_from_uid(db: Session, user_uid: str) -> int | None:
    """
    Resolves a Supabase auth UUID to an account_id.
    Replaces: supabase.rpc('get_account_id_from_uid', {'user_uid': uuid}).execute()
    """
    result = db.execute(
        text("SELECT get_account_id_from_uid(:user_uid)"),
        {"user_uid": user_uid}
    ).scalar()
    return result


def rpc_get_account_charts(db: Session, account_id: int) -> list:
    """
    Returns all active chart selections for an account with integration metadata.
    Replaces: supabase.rpc('get_account_charts', {'p_account_id': account_id}).execute()
    Returns list of dicts with keys:
      account_id, integration_id, integration_display_name, integration_key,
      chart_id, chart_key, chart_display_name, chart_description, json_path
    """
    rows = db.execute(
        text("SELECT * FROM get_account_charts(:p_account_id)"),
        {"p_account_id": account_id}
    ).fetchall()
    return [dict(row._mapping) for row in rows]


def rpc_create_account_and_platform_user(
    db: Session,
    company_name: str,
    user_id: str,
    user_email: str
) -> dict:
    """
    Creates a new account + platform_user in one atomic operation.
    Replaces: supabase.rpc('create_account_and_platform_user', {...}).execute()
    Returns dict with keys: account_id, platform_user_id
    """
    row = db.execute(
        text(
            "SELECT * FROM create_account_and_platform_user("
            ":p_company_name, :p_user_id, :p_user_email)"
        ),
        {
            "p_company_name": company_name,
            "p_user_id": user_id,
            "p_user_email": user_email,
        }
    ).fetchone()
    result = dict(row._mapping)

    print("ROW =", row)
    print("ROW MAPPING =", row._mapping)
    print("DICT =", result)

    return result["create_account_and_platform_user"]
