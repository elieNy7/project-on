//! Les références bibliques tapées par l'opérateur (« Jean 3:16 », « 1 co 13 », « esaie 53.5 »,
//! « Ps 23 »), lues avec les noms de livres d'une traduction (`app.utils.bible_reference`).

use std::sync::LazyLock;

use regex::Regex;

use crate::fold::fold;
use crate::py;

/// `<livre> <chapitre>[ :., <verset>]` ; le livre peut commencer par 1 à 3.
#[allow(clippy::unwrap_used)] // expression fixe, vérifiée par les tests
static REFERENCE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(
        r"^[\s\x1C-\x1F]*(?P<book>(?:[1-3][\s\x1C-\x1F]*)?[^\d\s\x1C-\x1F][^\d]*?)[\s\x1C-\x1F]*(?P<chapter>\d{1,3})(?:[\s\x1C-\x1F]*[:.,\s\x1C-\x1F][\s\x1C-\x1F]*(?P<verse>\d{1,3}))?[\s\x1C-\x1F]*$",
    )
    .unwrap()
});

/// Un livre d'une traduction : son numéro et son nom.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Book {
    pub id: i64,
    pub name: String,
}

/// Une référence comprise.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BibleReference {
    pub book_id: i64,
    pub book_name: String,
    pub chapter: u32,
    pub verse: Option<u32>,
}

impl BibleReference {
    /// « Jean 3:16 », ou « Psaumes 23 » sans verset.
    pub fn label(&self) -> String {
        match self.verse {
            Some(verse) => format!("{} {}:{verse}", self.book_name, self.chapter),
            None => format!("{} {}", self.book_name, self.chapter),
        }
    }
}

/// Lettres ASCII et chiffres seulement, sans accents.
fn key(text: &str) -> String {
    fold(text).to_lowercase().chars().filter(|c| c.is_ascii_digit() || c.is_ascii_lowercase()).collect()
}

/// Le livre tapé : le nom exact d'abord, puis le premier livre (dans l'ordre canonique) dont le nom
/// commence par ce qui est tapé. Il faut au moins deux lettres.
pub fn match_book<'a>(query: &str, books: &'a [Book]) -> Option<&'a Book> {
    let wanted = key(query);
    if wanted.chars().filter(|c| !c.is_ascii_digit()).count() < 2 {
        return None;
    }
    books.iter().find(|b| key(&b.name) == wanted).or_else(|| books.iter().find(|b| key(&b.name).starts_with(&wanted)))
}

/// La référence tapée, ou `None` si elle ne désigne aucun livre de la traduction.
pub fn parse_reference(query: &str, books: &[Book]) -> Option<BibleReference> {
    let caps = REFERENCE.captures(query)?;
    let book = match_book(&caps["book"], books)?;
    // Les chiffres non ASCII, que Python accepte, ne se tapent pas dans Project-On.
    let chapter = py::ascii_int(&caps["chapter"])?;
    let verse = match caps.name("verse") {
        Some(verse) => Some(py::ascii_int(verse.as_str())?),
        None => None,
    };
    if chapter < 1 {
        return None;
    }
    Some(BibleReference { book_id: book.id, book_name: py::strip(&book.name).to_string(), chapter, verse })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn books() -> Vec<Book> {
        ["Genèse", "Exode", "Psaumes", "Ésaïe", "Jean", "1 Corinthiens", "2 Corinthiens", "1 Jean"]
            .iter()
            .enumerate()
            .map(|(i, name)| Book { id: i as i64 + 1, name: name.to_string() })
            .collect()
    }

    // Valeurs attendues données par la 2.8.
    #[test]
    fn references_are_understood() {
        let books = books();
        let label = |q: &str| parse_reference(q, &books).map(|r| r.label());
        assert_eq!(label("Jean 3:16").as_deref(), Some("Jean 3:16"));
        assert_eq!(label("1 co 13").as_deref(), Some("1 Corinthiens 13"));
        assert_eq!(label("esaie 53.5").as_deref(), Some("Ésaïe 53:5"));
        assert_eq!(label("Ps 23").as_deref(), Some("Psaumes 23"));
        assert_eq!(label("1jean 1 9").as_deref(), Some("1 Jean 1:9"));
        assert_eq!(label("J 3"), None);
        assert_eq!(label("Jean 0"), None);
        assert_eq!(label("Apocalypse 1"), None);
        assert_eq!(label("Jean"), None);
    }
}
