"""
Diagnostic: compare paid_users WITH and WITHOUT category_cnt_for_ad filter.
Also lists available tables to find broader listing-category source.
Run: python3 debug_ch.py
"""
from datetime import date
from clickhouse_loader import _get_client, COUNTRY_ID_MAP

CATEGORY_ID = 5134
GEO = "KG"
DATE_FROM = date(2026, 3, 1)
DATE_TO   = date(2026, 3, 31)

country_id = COUNTRY_ID_MAP[GEO]

SQL_WITH_FILTER = f"""
    SELECT uniqExact(user_id) AS paid_users, COUNT(*) AS campaigns
    FROM (
        SELECT user_id, campaign_id
        FROM analytics_reports.spendings_distributed
        WHERE operationdate >= '{DATE_FROM}'
          AND operationdate <= '{DATE_TO}'
          AND category_id = {CATEGORY_ID}
          AND spending > 0
          AND country_id = {country_id}
          AND ad_id GLOBAL IN (
              SELECT ad_id
              FROM analytics_reports.spendings_distributed
              GROUP BY ad_id
              HAVING uniqExact(category_id) = 1
          )
        GROUP BY user_id, campaign_id
    )
"""

SQL_WITHOUT_FILTER = f"""
    SELECT uniqExact(user_id) AS paid_users, COUNT(*) AS campaigns
    FROM (
        SELECT user_id, campaign_id
        FROM analytics_reports.spendings_distributed
        WHERE operationdate >= '{DATE_FROM}'
          AND operationdate <= '{DATE_TO}'
          AND category_id = {CATEGORY_ID}
          AND spending > 0
          AND country_id = {country_id}
        GROUP BY user_id, campaign_id
    )
"""

# List all tables in analytics_reports to find listing-category table
SQL_TABLES = "SHOW TABLES FROM analytics_reports"

client = _get_client()
try:
    r1 = client.query(SQL_WITH_FILTER)
    r2 = client.query(SQL_WITHOUT_FILTER)
    with1, camp1 = r1.result_rows[0]
    with2, camp2 = r2.result_rows[0]
    print(f"WITH filter:    paid_users={with1}, campaigns={camp1}")
    print(f"WITHOUT filter: paid_users={with2}, campaigns={camp2}")
    print(f"Filter removed: {with2 - with1} users, {camp2 - camp1} campaigns")
    print(f"Tableau expected: paid_users=109, campaigns=708")
    # Step 1: get the specific ad_ids from our spendings period (small set)
    SQL_AD_IDS = f"""
        SELECT DISTINCT ad_id
        FROM analytics_reports.spendings_distributed
        WHERE operationdate >= '{DATE_FROM}'
          AND operationdate <= '{DATE_TO}'
          AND category_id = {CATEGORY_ID}
          AND spending > 0
          AND country_id = {country_id}
          AND ad_id IS NOT NULL
    """
    print("\nFetching ad_ids from spendings period...")
    r_ads = client.query(SQL_AD_IDS)
    ad_ids = [row[0] for row in r_ads.result_rows]
    print(f"Found {len(ad_ids)} distinct ad_ids in period")

    if ad_ids:
        ad_ids_str = ", ".join(str(a) for a in ad_ids)
        # Step 2: check which of those ad_ids appear in multiple categories in active_listers
        SQL_MULTI_CAT = f"""
            SELECT COUNT(DISTINCT ad_id) AS multi_cat_ads
            FROM (
                SELECT ad_id, uniqExact(category_id) AS cat_cnt
                FROM analytics_reports.active_listers_and_listings_distributed
                WHERE ad_id IN ({ad_ids_str})
                  AND country_id = {country_id}
                GROUP BY ad_id
                HAVING cat_cnt > 1
            )
        """
        print("Checking multi-category ads in active_listers...")
        r_multi = client.query(SQL_MULTI_CAT)
        multi_cnt = r_multi.result_rows[0][0]
        print(f"ad_ids with multiple categories (active_listers): {multi_cnt}")
        print(f"vs spendings filter excluded: {with2 - with1} users from multi-cat ads")

        # Step 3: get paid_users using active_listers-based filter
        SQL_SINGLE_CAT_IDS = f"""
            SELECT ad_id
            FROM (
                SELECT ad_id, uniqExact(category_id) AS cat_cnt
                FROM analytics_reports.active_listers_and_listings_distributed
                WHERE ad_id IN ({ad_ids_str})
                  AND country_id = {country_id}
                GROUP BY ad_id
            )
            WHERE cat_cnt = 1
        """
        r_sc = client.query(SQL_SINGLE_CAT_IDS)
        single_cat_ads = [row[0] for row in r_sc.result_rows]
        single_cat_str = ", ".join(str(a) for a in single_cat_ads)

        if single_cat_ads:
            SQL_FINAL = f"""
                SELECT uniqExact(user_id) AS paid_users, COUNT(*) AS campaigns
                FROM (
                    SELECT user_id, campaign_id
                    FROM analytics_reports.spendings_distributed
                    WHERE operationdate >= '{DATE_FROM}'
                      AND operationdate <= '{DATE_TO}'
                      AND category_id = {CATEGORY_ID}
                      AND spending > 0
                      AND country_id = {country_id}
                      AND ad_id IN ({single_cat_str})
                    GROUP BY user_id, campaign_id
                )
            """
            r_final = client.query(SQL_FINAL)
            with_listings, camp_listings = r_final.result_rows[0]
            print()
            print(f"WITH listings filter only:   paid_users={with_listings}, campaigns={camp_listings}")

        # Combined: spendings filter PLUS active_listers filter
        # Get multi-cat ad_ids from active_listers
        SQL_MULTI_IDS = f"""
            SELECT ad_id
            FROM (
                SELECT ad_id, uniqExact(category_id) AS cat_cnt
                FROM analytics_reports.active_listers_and_listings_distributed
                WHERE ad_id IN ({ad_ids_str})
                  AND country_id = {country_id}
                GROUP BY ad_id
            )
            WHERE cat_cnt > 1
        """
        r_multi_ids = client.query(SQL_MULTI_IDS)
        multi_cat_ids = [row[0] for row in r_multi_ids.result_rows]
        multi_cat_str = ", ".join(str(a) for a in multi_cat_ids) if multi_cat_ids else "0"
        print(f"\nMulti-cat ad_ids from active_listers: {len(multi_cat_ids)}")

        SQL_COMBINED = f"""
            SELECT uniqExact(user_id) AS paid_users, COUNT(*) AS campaigns
            FROM (
                SELECT user_id, campaign_id
                FROM analytics_reports.spendings_distributed
                WHERE operationdate >= '{DATE_FROM}'
                  AND operationdate <= '{DATE_TO}'
                  AND category_id = {CATEGORY_ID}
                  AND spending > 0
                  AND country_id = {country_id}
                  AND ad_id NOT IN ({multi_cat_str})
                  AND ad_id GLOBAL IN (
                      SELECT ad_id
                      FROM analytics_reports.spendings_distributed
                      GROUP BY ad_id
                      HAVING uniqExact(category_id) = 1
                  )
                GROUP BY user_id, campaign_id
            )
        """
        r_comb = client.query(SQL_COMBINED)
        with_comb, camp_comb = r_comb.result_rows[0]
        print(f"WITH combined filter:        paid_users={with_comb}, campaigns={camp_comb}")
        print(f"Tableau expected:            paid_users=109, campaigns=708")
finally:
    client.close()
