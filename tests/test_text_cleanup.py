from apps.annotator.pipeline.text_cleanup import collapse_repeated_tokens


def test_join_asr_words_apostrophes():
    from apps.annotator.pipeline.text_cleanup import fix_apostrophe_spacing, join_asr_words

    assert join_asr_words(["c", "'est", "nécessaire"]) == "c'est nécessaire"
    assert join_asr_words(["l", "'ai", "dit"]) == "l'ai dit"
    assert join_asr_words(["secteur", "-là"]) == "secteur-là"
    assert fix_apostrophe_spacing("c 'est d 'ailleurs l 'ai secteur -là") == (
        "c'est d'ailleurs l'ai secteur-là"
    )


def test_hallucination_thank_you_for_watching():
    from apps.annotator.pipeline.text_cleanup import is_whisper_hallucination

    assert is_whisper_hallucination("Thank you for watching!", 0.3)
    assert is_whisper_hallucination("Thanks for watching", 1.0)
    assert not is_whisper_hallucination(
        "Le journaliste explique la liberté de la presse à Maurice.",
        5.0,
    )


def test_collapse_repeated_nous():
    text = "nous, nous, nous, nous, nous, nous, nous, nous, nous, de l'île Maurice"
    assert collapse_repeated_tokens(text) == "nous, nous, de l'île Maurice"


def test_collapse_preserves_distinct_words():
    text = "nous nous, nou ena pou réaménage l'aéroport"
    assert collapse_repeated_tokens(text) == text
