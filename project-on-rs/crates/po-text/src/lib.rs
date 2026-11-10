//! Le texte de Project-On : pliage sans accents, nettoyage, clés et requêtes de recherche,
//! découpage en parties, strophes, références bibliques, titres et repères.
//!
//! Chaque fonction rend le même résultat que sa version Python de la 2.8 (`app.utils.text_utils`,
//! `app.utils.bible_reference`, `app.database.connection`, `app.database.dao_*`,
//! `app.ui.slide_canvas`), qu'elle remplace. Les longueurs se comptent en caractères, comme en
//! Python, et les espaces sont celles de Python (voir [`py`]).

mod bible;
mod clean;
mod entities;
mod fold;
mod hymn;
pub mod py;
mod search;
mod split;
mod titles;
mod words;

pub use bible::{BibleReference, Book, looks_like_reference, match_book, parse_reference};
pub use clean::{clean_text, html_unescape};
pub use fold::fold;
pub use hymn::{is_chorus, stanza_labels, strip_hymn_projection_label};
pub use search::{fts_query, hymn_fts_query, plain_query, search_key};
pub use split::{MAX_CHARS_PER_SLIDE, MIN_CHARS_PER_SLIDE, split_hymn_stanza, split_text_into_slides};
pub use titles::{
    TitleCandidate, choose_canonical_title, clean_expose_title, clean_hymn_title_for_canonical,
    clean_sermon_title_for_canonical, display_location, expose_chapter_num, expose_ref_parts, format_reference,
    marker_from_ref, mostly_uppercase, normalize_filter_date, paragraph_marker, sermon_year, title_case_french,
    title_case_words,
};
pub use words::words;
