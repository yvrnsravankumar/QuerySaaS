def test_public_api():
    from querysaas import OracleSqlPlanner, count_query, limit_query, page_query, validate_query, copy_fusion_to_local_parallel, connect, FusionConnection
    assert OracleSqlPlanner and connect and FusionConnection
