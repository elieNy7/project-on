# Project-On en Rust natif

La refonte de Project-On en Rust, décidée le 9 novembre 2026 : architecture, décisions et plan dans
[`../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md`](../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md).

**État : phase 2 terminée (moteur de projection et couche 1).** Phase 0 :
[`docs/phase0/RAPPORT_PHASE0.md`](docs/phase0/RAPPORT_PHASE0.md) ; phase 1 :
[`docs/phase1/RAPPORT_PHASE1.md`](docs/phase1/RAPPORT_PHASE1.md) ; phase 2 :
[`docs/phase2/RAPPORT_PHASE2.md`](docs/phase2/RAPPORT_PHASE2.md). La version livrée reste la
2.8 (Python) jusqu'à la bascule 3.0. Ce code ne touche jamais aux vraies données : les essais et les
mesures travaillent sur des copies.

## Organisation

| Crate | Rôle |
|---|---|
| `po-core` | les fondations : dossiers de données (2.x, bêta 3.0), journal, conversions « à la Python » |
| `po-text` | le texte : sans accents, nettoyage, clés et requêtes de recherche, découpage en parties, strophes, références bibliques, titres et repères |
| `po-settings` | les réglages, lus dans le `settings.json` de la 2.x avec les mêmes règles ; écriture atomique et `.bak` |
| `po-db` | la base SQLite de la 2.x, sans conversion : schéma et migrations, Bible, cantiques, prédications, livres, Exposé, playlists, déroulé, médias, copie cohérente |
| `po-design` | le style de la salle (`RoomDesign`), lu depuis les réglages « Projection » de la 2.x ; couleurs et contraste ; genre d'un slide |
| `po-layout` | la mise en page plein écran de la 2.8, au pixel près (métriques de Qt, largeurs DirectWrite), le fond, l'identification de Branham et les transitions, en **liste d'affichage** (fond, contenu, surcouche) |
| `po-render` | le dessin d'une liste d'affichage en image (moniteurs, NDI, HDMI, captures) : dégradés, images, ombres et halos, groupes animés |
| `po-web` | la projection Web : serveur local en lecture seule (axum), WebSocket, client navigateur (`web/`) |
| `project-on` | l'application egui (thème repris de Pgraphics) ; en phase 0, une coque de validation |
| `po-mesures` | les mesures et les planches de captures des phases 0 à 2 (jamais livré) |
| `po-parite` | les tests dorés : la 3.0 rejoue les références de la 2.8 et compare (jamais livré) |

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

## Les tests dorés (parité avec la 2.8)

Le vrai code de la 2.8 écrit ses résultats sur une **copie** de la base, puis `po-parite` refait
les mêmes appels en Rust et compare tout. Depuis la racine du dépôt (le module natif de la 2.8
extrait d'un paquet `build/native/*.whl`) :

```powershell
python project-on-rs\outils\references_28.py <copie\project_on.db> project-on-rs\target\parite <module natif>
cd project-on-rs
cargo run --release -p po-parite -- target\parite
```

La mise en page de la projection (phase 2) se compare de la même façon. Le script fait mettre en
page de vrais slides par le `SlideCanvas` de la 2.8, sans jamais l'afficher ; il faut le Python qui
a PySide6 (`py -3.14` sur le poste de développement) :

```powershell
py -3.14 project-on-rs\outils\references_projection_28.py <copie\project_on.db> project-on-rs\target\phase2\ref28
cd project-on-rs
cargo run --release -p po-parite -- projection target\phase2\ref28
cargo run --release -p po-mesures -- captures target\phase2\ref28 target\phase2\captures
```

Les références contiennent des textes de la base : elles restent dans `target\` (non versionné).

## Les mesures

Toujours sur une **copie** de la base :

```powershell
cargo run --release -p po-mesures -- tout <copie\project_on.db> <dossier de sortie>
cargo run --release -p po-mesures -- demarrage <copie\project_on.db>
cargo run --release -p po-mesures -- recherche <copie\project_on.db> <sortie.json>
cargo run --release -p po-mesures -- trigramme <copie\project_on.db> <dossier de sortie>
cargo run --release -p po-mesures -- servir <copie\project_on.db> 8091   # puis http://127.0.0.1:8091/ecran/salle
```

Pour une mesure « à froid » sans redémarrer, `outils\copie_froide.py` copie la base sans passer
par le cache de Windows.

## À savoir

- **SQLite sans informations de débogage.** Avec `-Z7`, `cl.exe` de Visual Studio 2026 échoue sur
  le poste de développement quand Cargo le lance (« D8050 … enregistrements de débogage »). Le
  `Cargo.toml` de l'espace de travail le désactive pour `libsqlite3-sys` seulement.
- **Polices** : celles de `../assets/fonts` (partagées avec la 2.x). Le serveur Web les sert aux
  navigateurs, qui dessinent donc avec les mêmes fichiers que le rendu natif.
- **Code repris de Pgraphics** : `crates/project-on/src/theme.rs` (en-tête d'origine) et le journal
  (`crates/po-core/src/journal.rs`), publiés sous MIT dans Project-On.
- **Dossier temporaire** : sur certains postes, le dossier temporaire de Windows est fermé en
  écriture aux programmes de test ; les tests écrivent donc dans `target\tmp`.
- **Le module natif de la 2.8** (`../rust/project_on_core`) n'est plus qu'une enveloppe de `po-text`.
- **DirectWrite** : sous Windows, `po-layout` prend les largeurs des lettres à DirectWrite, comme
  Qt dans la 2.8 (`crates/po-layout/src/dwrite.rs`, le seul module avec du code `unsafe`, limité
  aux appels Windows). Ailleurs, il utilise les largeurs de la police.
- **Identification de Branham** : « Reverend William Marrion Branham », sur les prédications,
  l'Exposé et les brochures seulement (`po_design::SlideSource::shows_identification`).
- **Entités HTML** : `crates/po-text/src/entities.rs` est généré par `outils/generer_entites.py`
  depuis la table de Python, pour décoder le HTML exactement comme la 2.8.
