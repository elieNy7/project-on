# Project-On en Rust natif

La refonte de Project-On en Rust, décidée le 9 novembre 2026 : architecture, décisions et plan dans
[`../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md`](../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md).

**État : phase 7 (première partie) terminée — reprise après coupure, historique, sauvegardes,
contrôle avant culte, page Réglages ; [liste de parité](docs/phase7/PARITE.md) avec la 2.8.**
Rapports : [phase 0](docs/phase0/RAPPORT_PHASE0.md), [phase 1](docs/phase1/RAPPORT_PHASE1.md),
[phase 2](docs/phase2/RAPPORT_PHASE2.md), [phase 3](docs/phase3/RAPPORT_PHASE3.md),
[phase 4](docs/phase4/RAPPORT_PHASE4.md) ([essai guidé](docs/phase4/ESSAI_GUIDE.md)),
[phase 5](docs/phase5/RAPPORT_PHASE5.md), [phase 6](docs/phase6/RAPPORT_PHASE6.md),
[phase 7](docs/phase7/RAPPORT_PHASE7.md). La version livrée reste la
2.8 (Python) jusqu'à la bascule 3.0. Ce code ne touche jamais aux vraies données : les essais et les
mesures travaillent sur des copies.

## Organisation

| Crate | Rôle |
|---|---|
| `po-core` | les fondations : dossiers de données (2.x, bêta 3.0), journal, conversions « à la Python » |
| `po-text` | le texte : sans accents, nettoyage, clés et requêtes de recherche, découpage en parties, strophes, références bibliques, titres et repères |
| `po-settings` | les réglages, lus dans le `settings.json` de la 2.x avec les mêmes règles ; écriture atomique et `.bak` |
| `po-db` | la base SQLite de la 2.x, sans conversion : schéma et migrations, Bible, cantiques, prédications, livres, Exposé, playlists, déroulé, médias, copie cohérente |
| `po-design` | le style de la salle (`RoomDesign`), lu depuis les réglages « Projection » de la 2.x ; le bandeau de la diffusion (`Band`, 4 dispositions), lu depuis les réglages « OBS » ; lower thirds et sous-titres (`graphics`) ; la bibliothèque de designs et « Mes designs » (`library`) ; couleurs et contraste ; genre d'un slide |
| `po-layout` | la mise en page plein écran de la 2.8, au pixel près (métriques de Qt, largeurs DirectWrite), le fond, l'identification de Branham et les transitions ; le bandeau sur fond transparent et le retour de scène ; lower thirds, sous-titres (découpage équilibré) et leurs animations, mire HDMI ; le tout en **liste d'affichage** (fond, contenu, surcouche) |
| `po-render` | le dessin d'une liste d'affichage en image (moniteurs, NDI, HDMI, captures) : dégradés, images, ombres et halos, groupes animés ; les trois couches d'un slide pour la carte graphique |
| `po-program` | le programme : ce qu'un clic prépare (tout le sermon, le chapitre, le cantique), découpé en slides « réf (i/n) » comme la 2.8 |
| `po-web` | la projection Web : serveur local en lecture seule (axum), quatre genres d'écrans, registre des écrans, jeton du réseau local et QR code, adresses de la 2.8 (`/obs`, `/slide.json`), WebSocket, client navigateur (`web/`) aux transitions du vidéoprojecteur |
| `po-ndi` | la source NDI (bibliothèque chargée à la demande, reprise de Pgraphics) : BGRA avec transparence |
| `project-on` | l'application egui : rail, bibliothèques (Bible, Cantiques, Prédications, Exposé, Livres), playlist et déroulé du culte, Designs (bibliothèque, Mes designs, habillage en direct L / S), Réglages et entretien (sauvegardes, contrôle avant culte, historique, reprise après coupure), Aperçu / Direct, projection native sur la carte graphique, sorties HDMI et NDI, écrans Web (bouton « Web »), recherche globale, raccourcis ; données de la bêta (copie de la 2.x) |
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

Le programme (phase 3) : le vrai code de la 2.8 prépare des sermons, cantiques, chapitres et livres
entiers, puis `po-parite` refait tout en Rust :

```powershell
py -3.14 project-on-rs\outils\references_programme_28.py <copie\project_on.db> project-on-rs\target\phase3\ref28
cd project-on-rs
cargo run --release -p po-parite -- programme target\phase3\ref28 <copie\project_on.db>
```

Les playlists (phase 4) : la 2.8 crée des playlists sur une copie de la base et prépare leurs
programmes, puis `po-parite` refait tout :

```powershell
py -3.14 project-on-rs\outils\references_playlist_28.py <copie\project_on.db> project-on-rs\target\phase4\ref28
cd project-on-rs
cargo run --release -p po-parite -- playlist target\phase4\ref28
```

Les références contiennent des textes de la base : elles restent dans `target\` (non versionné).

## Les mesures

Toujours sur une **copie** de la base :

```powershell
cargo run --release -p po-mesures -- tout <copie\project_on.db> <dossier de sortie>
cargo run --release -p po-mesures -- demarrage <copie\project_on.db>
cargo run --release -p po-mesures -- recherche <copie\project_on.db> <sortie.json>
cargo run --release -p po-mesures -- trigramme <copie\project_on.db> <dossier de sortie>
cargo run --release -p po-mesures -- servir <copie\project_on.db> 8091   # puis http://127.0.0.1:8091/
cargo run --release -p po-mesures -- web <copie\project_on.db> <dossier de sortie>   # planche des écrans Web
cargo run --release -p po-mesures -- designs <copie\project_on.db> <dossier de sortie>   # planche des designs
```

Pour une mesure « à froid » sans redémarrer, `outils\copie_froide.py` copie la base sans passer
par le cache de Windows.

## La bêta

```powershell
powershell -ExecutionPolicy Bypass -File project-on-rs\construire-beta.ps1
```

Compile l'application, prépare `dist\Project-On-3-beta` (exécutable, polices, licences et la base
fournie `data\project_on.db` du dépôt, la même que celle de la 2.8 ; `-SansBase` l'omet) et
construit `installer\Output\Project-On_<version>_Setup.exe` (Inno Setup 7). La bêta s'installe à
côté de la 2.8 ; au premier lancement, elle copie dans `%APPDATA%\Project-On 3 (bêta)` vos données
de la 2.x ou la base fournie (elle demande quand les deux existent) et ne touche jamais aux
originaux. `PROJECT_ON_DATA` impose un autre dossier de données (essais).

**La bascule** (phase 8, [document](docs/phase8/BASCULE.md)) : `construire-beta.ps1 -Bascule`
construit `installer\Output\ProjectOn_<version>_Setup.exe`, qui **remplace** la 2.x (même identifiant
d'application, même dossier) et travaille directement sur ses données, port Web 8080. À ne lancer
et à ne publier qu'avec l'accord de l'utilisateur.

**Carte graphique** : DirectX 12, puis OpenGL ; jamais Vulkan par défaut (le pilote Vulkan de
l'Intel UHD 620 plante dès la première image). `WGPU_BACKEND=vulkan|dx12|gl` impose un choix. Le
journal (`%APPDATA%\Project-On 3 (bêta)\data\logs\project-on.log`) note la carte choisie et toute
erreur.

## À savoir

- **SQLite sans informations de débogage.** Avec `-Z7`, `cl.exe` de Visual Studio 2026 échoue sur
  le poste de développement quand Cargo le lance (« D8050 … enregistrements de débogage »). Le
  `Cargo.toml` de l'espace de travail le désactive pour `libsqlite3-sys` seulement.
- **Polices** : celles de `../assets/fonts` (partagées avec la 2.x). Le serveur Web les sert aux
  navigateurs, qui dessinent donc avec les mêmes fichiers que le rendu natif.
- **Écrans Web de la bêta** : `http://127.0.0.1:8090/` (la 2.8 garde 8080 tant qu'elles
  cohabitent). L'essai des transitions du navigateur utilise Node s'il est installé ; sinon il est
  sauté.
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
