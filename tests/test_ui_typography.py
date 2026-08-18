"""Regression tests for the application typography hierarchy."""

from app.ui.theme import (
    Typography,
    build_app_stylesheet,
    get_combo_style,
    get_input_style,
)


def test_semantic_typography_roles_keep_labels_readable_and_numbers_compact() -> None:
    assert Typography.SIZE_NUMBER < Typography.SIZE_META
    assert Typography.SIZE_META < Typography.SIZE_FILTER
    assert Typography.SIZE_FILTER < Typography.SIZE_CONTROL
    assert Typography.SIZE_CONTROL < Typography.SIZE_BODY
    assert Typography.SIZE_LABEL == Typography.SIZE_BODY
    assert Typography.SIZE_BODY < Typography.SIZE_SECTION
    assert Typography.SIZE_SECTION < Typography.SIZE_TITLE
    assert Typography.SIZE_TITLE <= Typography.SIZE_DIALOG_TITLE


def test_global_styles_separate_filters_from_body_copy() -> None:
    app_style = build_app_stylesheet()

    assert f"font-size: {Typography.SIZE_BODY}px" in app_style
    assert f"font-size: {Typography.SIZE_FILTER}px" in get_input_style()
    assert f"font-size: {Typography.SIZE_FILTER}px" in get_combo_style()
    assert f"font-size: {Typography.SIZE_NUMBER}px" in app_style
