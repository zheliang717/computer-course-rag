"""Guard the capped lexical rescue while preserving pure ablations."""

from app.pgvector_store import PgVectorStore


def test_rescue_only_boosts_strong_exact_overlap_and_is_capped():
    base = 0.9 * 0.4245 + 0.1 * 0.5641
    assert PgVectorStore._candidate_score(0.4245, 0.5641, 0.9) > base
    assert PgVectorStore._candidate_score(0.5, 0.4, 0.9) == 0.49
    assert PgVectorStore._candidate_score(0.42, 1.0, 0.9) == 0.598
    assert PgVectorStore._candidate_score(0.5, 1.0, 0.9) == 0.55
    assert PgVectorStore._candidate_score(1.0, 1.0, 0.9) == 1.0


def test_vector_and_keyword_only_modes_do_not_receive_extra_boost():
    assert PgVectorStore._candidate_score(0.42, 0.8, 1.0) == 0.42
    assert PgVectorStore._candidate_score(0.42, 0.8, 0.0) == 0.8


def test_short_generic_chinese_question_keeps_original_ranking():
    assert not PgVectorStore._supports_lexical_rescue("什么是虚拟内存？")
    assert PgVectorStore._supports_lexical_rescue("地址在编译时、加载时和执行时生成有什么区别？")
    assert PgVectorStore._candidate_score(0.583, 0.615, 0.9, lexical_rescue=False) < 0.619


def test_existing_vector_window_does_not_receive_lexical_rescue():
    # The second Chinese page in the old English-target set was already inside
    # the original 40 vector candidates. Only truly newly surfaced candidates
    # may receive the rescue bonus.
    original = PgVectorStore._candidate_score(0.3707, 0.7714, 0.9, lexical_rescue=False)
    expanded = PgVectorStore._candidate_score(0.3707, 0.7714, 0.9, lexical_rescue=True)
    assert original < 0.5 < expanded
