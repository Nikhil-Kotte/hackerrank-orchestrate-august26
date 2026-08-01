from router.evaluate import score

TRUTH = [
    {
        "message_id": "a",
        "action": "notify",
        "message_type": "urgent",
        "evidence_message_ids": "message_0001",
    },
    {
        "message_id": "b",
        "action": "mute",
        "message_type": "scam",
        "evidence_message_ids": "message_0002;message_0003",
    },
]


def test_a_perfect_prediction_set_scores_one_across_the_board():
    predictions = [
        {**row, "reason": "r", "confidence": "0.87"} for row in TRUTH
    ]

    report = score(predictions, TRUTH)

    assert report["action_accuracy"] == 1.0
    assert report["type_accuracy"] == 1.0
    assert report["evidence_recall"] == 1.0


def test_a_wrong_action_lands_in_the_confusion_matrix():
    predictions = [
        {**TRUTH[0], "action": "digest", "reason": "r", "confidence": "0.80"},
        {**TRUTH[1], "reason": "r", "confidence": "0.87"},
    ]

    report = score(predictions, TRUTH)

    assert report["action_accuracy"] == 0.5
    assert report["confusion"][("notify", "digest")] == 1


def test_a_confidence_outside_its_action_band_is_reported():
    predictions = [
        {**TRUTH[0], "reason": "r", "confidence": "0.40"},
        {**TRUTH[1], "reason": "r", "confidence": "0.87"},
    ]

    report = score(predictions, TRUTH)

    assert report["out_of_band"] == ["a"]


def test_partial_evidence_overlap_is_credited_proportionally():
    predictions = [
        {**TRUTH[0], "reason": "r", "confidence": "0.87"},
        {**TRUTH[1], "evidence_message_ids": "message_0002", "reason": "r", "confidence": "0.87"},
    ]

    report = score(predictions, TRUTH)

    assert report["evidence_recall"] == 0.75
