from coruscant.intelligence.text import is_disclosure_sentence


def test_disclosure_filter_keeps_prose_drops_scaffolding() -> None:
    # Real disclosure sentences (carry a finite verb) are kept.
    assert is_disclosure_sentence(
        "We expect to face more competition as AI continues to advance and become integrated into payments."
    )
    assert is_disclosure_sentence(
        "The Firm is subject to extensive and comprehensive regulation under U.S. federal and state laws."
    )

    # The table-of-contents line that became a phantom 72% "regulatory" signal
    # (no verb, page-number runs) is dropped.
    toc = (
        "1 Overview 1 Business segments & Corporate 1 Competition 1 Supervision and regulation 2-6 "
        "Human capital 7-8 Distribution of assets, liabilities and stockholders' equity 315-319"
    )
    assert not is_disclosure_sentence(toc)
    # Bare headings, short fragments, and number rows are not disclosure sentences.
    assert not is_disclosure_sentence("Supervision and regulation")
    assert not is_disclosure_sentence("1,234 5,678 9,012 3,456 7,890 2,345")
