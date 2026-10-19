from apps.annotator.pipeline.lang_detector import classify_word, resolve_segment_lang, should_split_on_lang
from apps.annotator.pipeline.segment_merger import SegmentMerger


def test_classify_kreol_words():
    assert classify_word("Seki") == "kreol"
    assert classify_word("zot") == "kreol"
    assert classify_word("bann") == "kreol"


def test_classify_french_words():
    assert classify_word("parce") == "fr"
    assert classify_word("n'aurions") == "fr"
    assert classify_word("coûte") == "fr"
    assert classify_word("infrastructure") == "fr"
    assert classify_word("pas") == "fr"  # French "not", not Kreol


def test_should_split_on_lang():
    assert should_split_on_lang("fr", "kreol")
    assert not should_split_on_lang("fr", "unknown")
    assert not should_split_on_lang(None, "kreol")


def test_resolve_segment_lang_mixed():
    words = ["parce", "que", "nous", "Seki", "bann", "zot"]
    assert resolve_segment_lang(words) == "mix"


def test_kreol_source_overrides_french_whisper_artifact():
    from apps.annotator.db.models import SegmentLang
    from apps.annotator.pipeline.transcription_job import TranscriptionJob

    words = "Ce qui m'a permis depuis la COVID j'ai beaucoup souffert financièrement".split()
    lang = TranscriptionJob._score_segment_lang(words, SegmentLang.kreol, "fr")
    assert lang == SegmentLang.kreol



def test_merge_keeps_same_speaker_mixed_lang_together():
    from apps.annotator.pipeline.asr_engine import AsrSegment, AsrWord

    segments = [
        AsrSegment(
            start=17.0,
            end=27.0,
            text="parce que nous coûte cher Seki bann PME depi COVID zot bocou soufer",
            language="fr",
            words=[
                AsrWord(17.0, 17.4, "parce"),
                AsrWord(17.4, 17.6, "que"),
                AsrWord(17.6, 17.9, "nous"),
                AsrWord(17.9, 18.2, "coûte"),
                AsrWord(18.2, 18.5, "cher"),
                AsrWord(18.6, 18.9, "Seki"),
                AsrWord(19.0, 19.3, "bann"),
                AsrWord(19.3, 19.6, "PME"),
                AsrWord(19.6, 19.9, "depi"),
                AsrWord(19.9, 20.2, "COVID"),
                AsrWord(20.2, 20.5, "zot"),
                AsrWord(20.5, 20.9, "bocou"),
                AsrWord(20.9, 21.3, "soufer"),
            ],
        )
    ]
    merged = SegmentMerger().merge_asr_only(segments)
    assert len(merged) == 1
    assert "Seki" in merged[0].text
    assert "coûte" in merged[0].text

