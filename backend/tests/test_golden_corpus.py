from app.evaluation.golden_corpus import load_golden_corpus, validate_corpus_structure


def test_nodex_golden_corpus_structure():
    corpus = load_golden_corpus()
    errors = validate_corpus_structure(corpus)
    assert errors == [], errors
    assert len(corpus["topics"]) >= 12
    assert "platform_fit" in corpus["rubric_dimensions"]
