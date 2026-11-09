# Project-On en Rust natif

La refonte de Project-On en Rust, décidée le 9 novembre 2026 : architecture, décisions et plan dans
[`../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md`](../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md).

**État : phase 0 terminée (prototype de validation technique) : GO**, voir
[`docs/phase0/RAPPORT_PHASE0.md`](docs/phase0/RAPPORT_PHASE0.md). La version livrée reste la 2.8 (Python)
jusqu'à la bascule 3.0. Ce code ne touche jamais aux données : la base est ouverte en lecture seule.

## Organisation

| Crate | Rôle |
|---|---|
| `po-text` | pliage sans accents (`unaccent`), clés et requêtes de recherche, mots (ponctuation française collée) |
| `po-db` | la base SQLite de la 2.x, sans conversion : sermons, recherche FTS5 et par sous-chaîne |
| `po-layout` | la mise en page d'un slide (texte qui remplit l'écran, zone de sécurité, lignes équilibrées) en **liste d'affichage** |
| `po-render` | le dessin d'une liste d'affichage en image (NDI, HDMI, aperçus, captures) |
| `po-web` | la projection Web : serveur local en lecture seule (axum), WebSocket, client navigateur (`web/`) |
| `project-on` | l'application egui (thème repris de Pgraphics) ; en phase 0, une coque de validation |
| `po-mesures` | les mesures de la phase 0 (jamais livré) |

## Construire et vérifier

Windows 10 ou 11, Rust (chaîne MSVC) et Visual Studio avec les outils C++ (SQLite est compilé avec
l'application).

```powershell
cd project-on-rs
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Les tests de l'interface la rendent hors écran (`egui_kittest` + wgpu) : aucune fenêtre ne s'ouvre.

## Les mesures de la phase 0

Toujours sur une **copie** de la base :

```powershell
cargo run --release -p po-mesures -- tout <copie\project_on.db> <dossier de sortie>
cargo run --release -p po-mesures -- demarrage <copie\project_on.db>
cargo run --release -p po-mesures -- servir <copie\project_on.db> 8091   # puis http://127.0.0.1:8091/ecran/salle
```

## À savoir

- **SQLite sans informations de débogage.** Avec `-Z7`, `cl.exe` de Visual Studio 2026 échoue sur
  le poste de développement quand Cargo le lance (« D8050 … enregistrements de débogage »). Le
  `Cargo.toml` de l'espace de travail le désactive pour `libsqlite3-sys` seulement.
- **Polices** : celles de `../assets/fonts` (partagées avec la 2.x). Le serveur Web les sert aux
  navigateurs, qui dessinent donc avec les mêmes fichiers que le rendu natif.
- **Code repris de Pgraphics** : `crates/project-on/src/theme.rs` (en-tête d'origine), publié sous
  MIT dans Project-On.
