# Project-On — audit, architecture cible en Rust et plan de migration

- **Date** : 9 novembre 2026
- **Base auditée** : 2.8.0, branche `claude/hdmi-projection-update-56a4v2` (commit `b016396`)
- **Statut** : les décisions du § 9 ont été prises le 9 novembre. **Phase 0 terminée le 9 novembre :
  GO**, les quatre critères sont tenus ([rapport](project-on-rs/docs/phase0/RAPPORT_PHASE0.md)). La
  phase 1 attend votre feu vert. Le code de la 2.8 n'a pas été modifié.
- Cette demande remplace le choix du 29 octobre 2026 (« Rust hybride, pas de réécriture complète ») :
  la logique et l'interface passent toutes les deux en Rust.

---

## 0. L'essentiel

1. Project-On 2.8.0, c'est **Python 3.14 + PySide6 (Qt 6)** : environ **48 000 lignes** réparties
   dans 109 modules, **546 tests** dans 75 fichiers et une base SQLite de **570 Mo**. Le Rust n'y est
   qu'un module d'accélération d'environ 290 lignes (recherche sans accents, redimensionnement
   d'images), appelé depuis Python par PyO3.
2. **Pgraphics**, l'autre logiciel de ParaTech dont la refonte doit s'inspirer, est **déjà passé en
   Rust natif** : egui + wgpu + cosmic-text, environ 71 000 lignes, version Python retirée le 2 novembre.
   Il a été mesuré sur un portable identique à celui-ci (i5-8350U, Intel UHD 620, 8 Go). On a donc la
   preuve que la pile proposée tient sur le matériel de l'église, et des composants à reprendre (thème,
   widgets, icônes, fenêtres de projection, rendu du texte).
3. **Recommandation** : une nouvelle application Rust avec une interface **egui + wgpu**, construite
   dans un espace de travail `project-on-rs/` à côté du code actuel, **par phases livrables**. La
   version Python reste celle qu'on livre jusqu'à la parité. Ensuite l'installeur 3.0 la remplace et
   garde la base, les playlists et les réglages. C'est la méthode qui a réussi pour Pgraphics.
4. **Un seul moteur de mise en page en Rust** calcule une « liste d'affichage ». Trois afficheurs la
   dessinent : la fenêtre de projection native, le navigateur (projection Web) et les images hors
   écran (NDI, HDMI, aperçus des designs). Le texte, les coupures et les positions sont donc les mêmes
   partout. Aujourd'hui, le bandeau est dessiné par deux moteurs différents qu'il faut garder alignés.
5. **Couche 1** (suppression des miniatures, identification de Branham) : **seulement dans la
   version Rust**, comme vous l'avez choisi. La 2.x ne reçoit aucune nouvelle fonction. Les miniatures ne sont tout
   simplement pas portées, et l'identification arrive avec le moteur de projection (phase 2).
6. **Prochaine étape proposée : la phase 0**, un prototype de validation technique avec des critères
   chiffrés de go / no-go, avant toute migration.
7. Les décisions prises sont au **§ 9**.

---

## 1. Audit : ce qu'est Project-On aujourd'hui

### 1.1 Chiffres

| Élément | Valeur |
|---|---|
| `app/ui` (interface Qt) | 56 fichiers, 25 680 lignes |
| `app/utils` (logique, sorties, graphismes) | 45 fichiers, 19 079 lignes |
| `app/database` (accès SQLite) | 8 fichiers, 3 216 lignes |
| `presentation/` (pages OBS : JS + CSS) | 1 884 lignes de `obs-script.js` + `obs-style.css` |
| `rust/project_on_core` (PyO3) | 289 lignes : `unaccent` natif (aussi extension SQLite), redimensionnement |
| Tests | 75 fichiers, 11 321 lignes, 546 tests |
| Base `project_on.db` | 570 Mo : 2 876 sermons (VGR 409, SHP 1 220, BSS 1 247), 568 000 paragraphes + FTS5, 11 Bibles (342 556 versets), 1 915 cantiques (10 980 strophes + FTS5), 5 livres, playlists, déroulé |
| Réglages | `settings.json` (7,5 Ko), 9 sections |
| Installeur 2.8.0 | 424 Mo (PyInstaller + Inno Setup), non signé |

### 1.2 Pile technique et équivalents Rust

| Brique actuelle | Usage | Équivalent Rust prévu |
|---|---|---|
| PySide6 QtWidgets / QtGui (180 imports) | interface, fenêtre de projection (QPainter), délégués de listes | **egui / eframe + wgpu** |
| QtMultimedia (11 imports) | vidéos : fonds animés, médias projetés | Media Foundation (crate `windows`), comme `pg-moteur` |
| QtWebSockets | pilotage d'OBS par WebSocket | `tokio-tungstenite` |
| `http.server` + SSE | page OBS (source navigateur) | `axum` + WebSocket (`po-web`) |
| `sqlite3` + FTS5 + UDF `unaccent` | base de données | `rusqlite` (SQLite intégré, FTS5) + `unaccent` natif (déjà écrit en Rust) |
| Pillow (45 imports), numpy | écrans de l'église, bandeau HDMI / NDI, miniatures | `tiny-skia` + `cosmic-text` + `image` + `fast_image_resize` |
| PyMuPDF (`fitz`) | import PDF des sermons, exposés, livres, cantiques | `pdfium-render` (PDFium, licence BSD / Apache) |
| pywin32 (`win32com`, `win32crypt`) | PowerPoint par COM, secrets (DPAPI) | crate `windows` (COM, DPAPI) |
| ndi-python | sortie NDI | SDK NDI chargé dynamiquement, comme Pgraphics |
| qrcode | QR codes (accueil, réseaux) | crate `qrcode` |
| urllib | mise à jour, téléchargement des Bibles | `ureq`, ou WinHTTP comme `pg-net` |
| PyInstaller + Inno Setup | installeur | `cargo` + Inno Setup (exécutable de 20 à 40 Mo, plus la base) |

À noter : PyMuPDF est sous licence **AGPL**, ce qui pose déjà question pour un projet publié sous MIT.
Passer à PDFium règle ce point.

### 1.3 Cartographie des modules

| Domaine | Modules principaux (lignes) | Devenir |
|---|---|---|
| **Données** | `connection` 1 274, `dao_sermons` 753, `dao_hymns` 484, `dao_playlist` 391, `dao_bible` 113, `dao_service_plan` 103, `dao_media` 97 | `po-db` |
| **Logique de la régie** | `library_controller` 2 167, `project_on_controller` 545, `slideshow_controller` 249, `slide_writer` 170, `service_plan` 132, `service_log` 207, `playlist_transfer` 187, `live_recovery` 88 | `po-core` + application |
| **Texte et recherche** | `text_utils` 456, `global_search` 263, `bible_reference` 69, `song_formats` 224 | `po-text` |
| **Projection locale** | `slide_canvas` 1 870, `projection_window` 752, `preview_panel` 1 221, `cue_monitor` 204, `preview_renderer` 95 | `po-layout` + `po-render` + application |
| **Sorties OBS / HDMI / NDI** | `obs_overlay_render` 2 123, `obs_web_server` 567, `ndi_lower_third` 568, `mixer_output_window` 803, `obs_controller` 340, `obs_websocket` 338, `montage_export` 86, `presentation/obs-*` 1 884 | `po-web` + `po-render` + `po-media` |
| **Église et graphismes** | `church_graphics` 2 068 (dont environ 650 lignes de miniatures), `church_profile_dialog` 1 354 (dont `ThumbnailDialog`) | `po-render` + application ; **miniatures supprimées** |
| **Imports** | `pdf_parser` 1 554, `pptx_parser` 684, `hymn_pdf_parser` 588, `bible_catalog` 462, `office_renderer` 349 | `po-import` + `po-media` |
| **Réglages** | `settings` 1 114, `app_paths` 740, `translations` 615, `shortcuts` 95, `settings_storage` 91 | `po-settings` + `po-core` |
| **Fiabilité** | `backup_manager` 322, `system_health` 302, `updater` 151, `power_guard` 78, `logger` 59 | `po-db` + application |
| **Interface** | `main_window` 1 909, `obs_output_settings_dialog` 1 629, `theme` 1 363, `playlist_tab` 1 084, `icons` 1 046, `sermons_tab` 849… | **réécrite en egui** |

### 1.4 Constats d'architecture

1. **Des objets-dieux.** `main_window.py` (1 909 lignes) et `library_controller.py` (2 167 lignes)
   mélangent l'interface, la logique et les entrées-sorties. Ils sont difficiles à tester sans Qt.
2. **Une communication interne par fichiers.** La régie écrit `presentation/slide.json` et
   `config.json`, puis la fenêtre de projection et la page OBS les relisent. La 2.8 a ajouté un
   écouteur pour supprimer l'attente de 250 ms, mais le modèle reste celui-là.
3. **Deux moteurs de rendu pour le même bandeau.** `obs-style.css` / `obs-script.js` le dessinent
   dans le navigateur, `obs_overlay_render.py` le redessine avec Pillow pour NDI, HDMI et le montage.
   Ils sont maintenus en parallèle, d'où le test `test_obs_band_parity.py`.
4. **Du rendu dans le fil de l'interface** (QPainter dans `slide_canvas`). Les citations sont
   passées en arrière-plan en 2.8, mais pas la projection.
5. **La recherche est liée au GIL de Python** : chaque appel à `unaccent` passe par Python. C'est en
   partie corrigé par l'extension Rust (sermons : 60 s → 3 s).
6. **Les réglages forment un seul bloc.** La section du bandeau OBS (`ObsOutputSettings`) fait à
   elle seule 220 lignes de champs. Il n'existe aucune notion de « design » réutilisable.
7. **Tests** : 546 tests, avec des échecs connus qui existaient déjà (`test_live_recovery`,
   `test_installer_safety`). Plusieurs fichiers plantent à la fermeture de Qt (code 139) alors que
   leurs tests passent.

### 1.5 Supprimer, conserver, remplacer

| Fonction | Décision |
|---|---|
| Miniatures YouTube : `ThumbnailSpec`, modèles, `ThumbnailDialog`, `render_youtube_thumbnail`, raccourci Ctrl+Maj+Y, `thumbnail_models` dans les réglages, `test_youtube_thumbnail.py` | **Supprimer** (couche 1) : **elles ne sont pas portées en Rust** ; la 2.x les garde jusqu'à la bascule. Vérifié : `_cover` sert aussi aux citations, qui seront portées. La galerie de photos de l'église est portée elle aussi. Les fichiers déjà créés dans `data/church/miniatures` ne sont **pas** effacés, et la clé `thumbnail_models` de `settings.json` est ignorée. |
| Vignettes de la médiathèque, miniatures floutées des fonds | **Conserver** : c'est une autre fonction, elle n'a rien à voir avec la création de miniatures. |
| Badge « orateur du jour » (photo et nom) sur les slides | **Retiré de tous les slides.** Sur les prédications, l'Exposé et les brochures, il est **remplacé** par l'identification fixe de Branham. Les réglages « Sur les slides de projection », côté et taille disparaissent. |
| Écran plein « Orateur du jour » (Ctrl+Maj+P) | Conserver. |
| Sortie « OBS » : page navigateur, styles par scène `?scene=` | **Remplacer** par la projection Web (§ 5). L'adresse `/obs` est gardée et redirigée, pour que les scènes OBS existantes continuent de marcher. |
| Pilotage d'OBS par WebSocket (bascule de scène) | **Conserver** comme intégration facultative, « Piloter OBS Studio ». C'est le seul endroit où le nom OBS reste visible, puisque cette fonction pilote réellement OBS. |
| Bandeau OBS, style HDMI, style de projection | **Remplacer** par la bibliothèque de designs. Vos réglages actuels deviennent des designs « repris de la 2.x » : l'apparence ne change pas le jour de la bascule. |
| Bible, Cantiques, Sermons, Exposé, Livres, Médias, Playlist, Déroulé, Historique, Église, Recherche globale, NDI, HDMI, PowerPoint, imports, sauvegardes, mise à jour, contrôle avant culte, reprise après coupure, mode PC modeste | **Conserver**, puis porter en Rust. |

---

## 2. Pgraphics : ce qu'on peut reprendre

| Pgraphics (`pgraphics-rs`) | Usage dans Project-On |
|---|---|
| `theme.rs` (186 lignes), `widgets.rs` (495), `icons.rs` (514) | Le système de design : palette ardoise et ambre, police Inter, une échelle de boutons à quatre tailles, interface à plat. C'est ce que demande « inspiré de PGraphics ». |
| `projector.rs` (212) | Projection plein écran sur un écran externe, ou en fenêtre. |
| `playlist.rs` (824) | Le modèle d'une playlist jouée à la main (IN / OUT, Suivant). |
| `pg-render` (texte cosmic-text, styles de calque, contours, ombres) | Le rendu du texte de projection, des lower thirds et des sous-titres. |
| `pg-moteur` (Media Foundation, NDI) | Les vidéos et la sortie NDI. |
| `journal.rs`, `recovery.rs`, `diagnostic.rs` | Le journal, les rapports de plantage (minidumps) et l'export d'un diagnostic. |
| `construire.ps1`, l'installeur, la CI | Construction, signature et vérifications (`fmt`, `clippy -D warnings`, `test`). |

**Licence** : Pgraphics est propriétaire (`LicenseRef-Proprietary`), Project-On est sous MIT. Vous
avez choisi de **reprendre le code** (§ 9, décision 1) : les parties copiées sont publiées sous MIT
dans Project-On, et chaque fichier repris indique son origine dans un commentaire d'en-tête.

---

## 3. Le choix de l'interface : egui + wgpu

**Pourquoi egui (eframe, rendu wgpu) :**

- **Tout en Rust**, une seule langue pour la logique et l'interface. C'est l'exigence de la demande.
- **Rendu sur la carte graphique, à 60 images/s.** Les listes sont virtualisées : les 568 000
  paragraphes défilent sans être chargés d'un coup.
- **Plusieurs fenêtres dans un même processus** (viewports) : la régie et une projection par écran.
- **Déjà maîtrisé chez ParaTech** : l'interface de Pgraphics fait environ 40 000 lignes en egui. On
  reprend le même design et les mêmes composants, et la même personne peut maintenir les deux
  logiciels.
- **Des tests sans fenêtre visible** avec `egui_kittest` (rendu hors écran, captures comparées).
  Rien ne s'ouvre sur votre écran pendant les tests.
- Licences MIT / Apache.

**Ses limites, et ce qu'on y fait :** en mode immédiat, l'état doit être tenu avec discipline (un
modèle par écran, des messages, aucune logique dans le dessin). Certains composants seront à
construire, par exemple l'éditeur de cantiques ou le sélecteur de polices, mais Pgraphics en a déjà
plusieurs. L'accessibilité passe par AccessKit (lecteurs d'écran), qui est correct mais moins riche
que Qt.

**Les solutions écartées :**

| Option | Pourquoi non |
|---|---|
| Tauri (interface HTML / JS dans WebView2) | L'interface ne serait pas en Rust, et le navigateur se retrouverait dans le chemin de l'image : c'est précisément ce que Pgraphics a quitté pour des raisons de performance. |
| Slint | Bonne bibliothèque, mais sous licence GPL ou licence gratuite avec attribution obligatoire, et vous n'avez aucun acquis dessus. |
| Iced | Comparable à egui, sans aucun acquis. |
| CXX-Qt (Qt piloté depuis Rust) | Il faudrait réécrire toute l'interface en QML et installer la chaîne C++ de Qt : on cumulerait les inconvénients des deux mondes. |

**La seule technologie complémentaire est HTML / CSS / JS**, uniquement pour le **client de
projection Web** : environ 500 lignes sans framework, embarquées dans l'exécutable. C'est le
navigateur de l'écran externe qui l'impose. Ce client ne contient aucune logique : il dessine ce que
Rust a calculé.

---

## 4. Architecture cible

### 4.1 L'espace de travail

```
project-on-rs/                     (espace de travail Cargo, édition 2024)
├── crates/
│   ├── po-core      domaine : Slide, Source, Référence, Programme (Aperçu / Direct), erreurs,
│   │                chemins de données (registre HKCU\Software\Project-On\DataPath, %APPDATA%)
│   ├── po-text      sans accents, découpage (alinéas, phrases, parts égales), références
│   │                bibliques, formats de cantiques (OpenLyrics, OpenSong, CCLI)
│   ├── po-db        SQLite (rusqlite) : Bible, Cantiques, Sermons, Exposé, Livres, Playlists,
│   │                Déroulé, Médias ; FTS5 ; migrations versionnées ; sauvegardes
│   ├── po-settings  réglages compatibles avec settings.json, écriture atomique + .bak
│   ├── po-design    modèles : design de salle, lower third, sous-titres, identification,
│   │                animations ; catalogue intégré + designs de l'utilisateur
│   ├── po-layout    mise en page : texte qui remplit l'écran, zone de sécurité, coupures,
│   │                référence, lower third, sous-titres → LISTE D'AFFICHAGE
│   ├── po-render    rendu de la liste d'affichage : cosmic-text + tiny-skia (images),
│   │                wgpu (fenêtres) ; aperçus des designs
│   ├── po-web       serveur local axum : pages, WebSocket, médias (Range), polices ;
│   │                client Web embarqué (web/ : html, css, js)
│   ├── po-media     images, vidéos (Media Foundation), PowerPoint (COM), NDI
│   ├── po-import    PDF (PDFium), PPTX, Bibles (Zefania, Beblia, JSON), téléchargements
│   └── project-on   l'application egui : régie, bibliothèque, playlist, aperçu / direct,
│                    designs, réglages, journal, plantages, mise à jour
└── assets/          polices, icônes, catalogue des designs, fonds
```

Les dépendances vont dans un seul sens : `po-core` ← `po-text` ← `po-db` / `po-settings` ←
`po-design` ← `po-layout` ← `po-render` / `po-web` ← `project-on`. Les crates de logique ne
connaissent ni egui ni Windows, si bien qu'on peut les tester sans fenêtre.

Le module actuel `rust/project_on_core` (PyO3) devient une **simple enveloppe de `po-text`**. Pendant
la transition, la version Python utilise donc le même code Rust que la nouvelle application, sans
rien dupliquer.

### 4.2 Le flux du direct

```
Bibliothèque / Playlist ──clic──► APERÇU (Programme) ──F2 / double-clic──► DIRECT (Programme)
                                                                              │
                                     design de chaque écran (po-design) ──────┤
                                                                              ▼
                                        po-layout : une liste d'affichage par écran (taille, ratio)
                                                                              │
                     ┌─────────────────────────────┬──────────────────────────┼───────────────────────┐
                     ▼                             ▼                          ▼                       ▼
           fenêtre de projection           navigateurs (po-web)        NDI / HDMI (po-render        aperçus, historique,
           (wgpu, un écran chacune)        WebSocket, plusieurs écrans  → image → po-media)          exports (po-render)
```

- La **liste d'affichage** décrit des calques déjà placés en pixels : fond (couleur, image, vidéo),
  rectangles, lignes de texte (texte, police, taille, couleur, contour, ombre, position), images.
  Chaque calque porte son animation d'entrée et de sortie. Les afficheurs ne prennent aucune
  décision de mise en page.
- **Un état unique, en mémoire** (`ProgramState`), diffusé par des canaux (`crossbeam`). Il n'y a
  plus d'échange de fichiers JSON. Une copie sur disque est gardée pour la reprise après coupure.

### 4.3 Les fils d'exécution

| Fil | Rôle |
|---|---|
| Interface (egui) | Dessin et saisie uniquement. Rien ne bloque plus de quelques millisecondes. |
| Base de données | Un fil, une file de requêtes, la réponse la plus récente gagne. Recherches enchaînées, les plus rapides d'abord (leçon de la 2.x). |
| Mise en page et rendu | Calcul des listes d'affichage et des images NDI / HDMI / aperçus. |
| Serveur Web | Un runtime tokio réduit à deux fils. |
| Vidéo, NDI | Leurs propres fils, comme dans Pgraphics. |

### 4.4 Les erreurs et le journal

- Les bibliothèques utilisent des erreurs typées (`thiserror`) ; l'application les présente à
  l'utilisateur (`anyhow` + message en français). Aucun `unwrap()` dans les chemins de production :
  la règle clippy est activée.
- Une erreur ne doit **jamais vider l'écran de l'assemblée** : un afficheur garde la dernière image
  valide.
- Journal tournant dans `data/logs`, rapports de plantage (minidump + pile) et export d'un
  diagnostic, repris de Pgraphics.

### 4.5 Les données

- **La même base SQLite, sans conversion.** Les migrations sont versionnées par `user_version`
  (aujourd'hui 11) et seulement additives (de nouvelles tables pour les designs, par exemple). La
  version Python reste ainsi capable de lire la base jusqu'à la bascule.
- **Les réglages** : `po-settings` lit `settings.json` tel quel, avec des valeurs par défaut pour les
  champs absents, et garde les champs qu'il ne connaît pas. Les nouveaux réglages vont dans des
  sections nouvelles.
- **La bêta 3.0 travaille sur une copie** (`%APPDATA%\Project-On 3 (bêta)`, importée à son premier
  lancement). Les vraies données ne sont touchées qu'à la bascule.
- Aucun quick_check automatique de la base au démarrage (leçon de la 2.6).

---

## 5. La projection Web

**Le principe** : Project-On embarque un petit serveur Web local. Chaque écran (téléviseur,
vidéoprojecteur relié à un autre PC, OBS, vMix, Pgraphics, tablette de scène) ouvre une adresse dans
un navigateur, puis affiche ce que Rust lui envoie. **La page est en lecture seule** : elle ne peut
rien piloter, comme pour le serveur local de Pgraphics (ADR-0002).

| Élément | Choix |
|---|---|
| Serveur | `axum` + `tokio`, sur un port réglable (8080 par défaut, port suivant si occupé) |
| Écrans | Une liste d'écrans nommés, chacun avec son design. Préréglages : **Salle** (plein écran avec fond), **Diffusion** (lower third sur fond transparent, pour OBS, vMix ou Pgraphics), **Sous-titres** (transparent), **Retour scène** (texte en cours, suivant, horloge). On en ajoute autant qu'on veut. |
| Adresses | `/` liste les écrans, `/ecran/<nom>` ouvre un écran, `/ws` sert le WebSocket. L'ancienne adresse `/obs?scene=…` est redirigée vers l'écran correspondant. |
| Protocole | JSON versionné. Le serveur envoie `hello`, `frame` (liste d'affichage + transition + numéro de séquence), `clear` et `ping` ; le client envoie `hello` (taille de son écran, densité de pixels) et `pong`. La mise en page est calculée **pour la taille réelle de chaque écran**. |
| Fiabilité | Reconnexion automatique (de 0,5 à 5 s). À la reconnexion, le serveur renvoie l'état complet. Pendant une coupure, **la dernière image reste affichée** : jamais d'écran noir. Les polices et les médias sont servis par Project-On, avec des requêtes Range pour les vidéos. |
| Réseau | Par défaut, l'écoute est sur `127.0.0.1` (ce PC seulement). L'option « Écrans du réseau local » ouvre l'accès au réseau avec un **jeton dans l'adresse**, et un QR code permet d'ouvrir l'écran sur une télévision ou une tablette. |
| Supervision | La barre de commandes affiche « Web : 2 écrans connectés » ; un écran qui décroche passe à l'orange. |
| Tests | Tests d'intégration : un serveur lancé dans le test, des clients WebSocket automatiques, un contrôle des images reçues, une coupure suivie d'une reconnexion, plusieurs écrans en même temps. |

---

## 6. Lower thirds, sous-titres et bibliothèque de designs

### 6.1 Le modèle commun (`po-design`)

Un **design** possède un nom, une catégorie, un type (salle, lower third, sous-titres,
identification), un aperçu et une origine (intégré ou créé par l'utilisateur, avec le design de
départ éventuel). Il regroupe :

- **Texte** : police, taille, graisse, couleur, contour, ombre, espacement des lettres et des lignes,
  capitales.
- **Boîte** : aucune, unie, semi-transparente ou en dégradé ; coins arrondis, marges intérieures,
  ligne décorative (gauche, haut ou bas : épaisseur, couleur).
- **Position** : 9 ancrages, décalages, largeur en pourcentage, alignement.
- **Opacité, durée d'affichage** (0 = jusqu'au masquage), **animation** d'entrée et de sortie
  (fondu, glissement, révélation, mot à mot, aucune), avec sa durée et sa courbe.

### 6.2 Les lower thirds

Au moins 12 styles intégrés, tous personnalisables : minimaliste, moderne élégant, fond transparent,
texte seul, ligne décorative, bandeau semi-transparent, animé, prédication, nom de l'orateur, thème
du sermon, référence biblique, ainsi que **votre bandeau actuel (repris de la 2.x)**. Chacun propose
des champs adaptés : nom et fonction pour l'orateur, thème et série pour le sermon, référence et
version pour la Bible. On les affiche et on les masque à la main (touche L), ou automatiquement
avec le contenu du direct.

### 6.3 Les sous-titres

Plusieurs modèles : transparent, semi-transparent, contour, boîte par ligne. Polices, couleurs et
tailles au choix, position en bas, au centre ou en haut, de 1 à 3 lignes **équilibrées**. Les
sous-titres suivent le direct en temps réel : un paragraphe long est découpé en sous-titres que l'on
fait avancer avec ← et →. Touche S pour afficher ou masquer. Pour les vidéos projetées, un fichier
**SRT** peut être lu en synchronisation avec la vidéo (la 2.x exporte déjà des SRT).

### 6.4 La bibliothèque de designs

- Une grille d'aperçus réels, rendus par `po-render` avec le contenu en cours, et classés par
  catégorie : Louange, Prédication, Bible, Annonces, Diffusion, Sous-titres, Sobres.
- Un clic applique le design à **l'Aperçu** ; « Appliquer au direct » l'envoie avec un fondu. Le
  direct n'est jamais modifié par erreur.
- On peut dupliquer, personnaliser et enregistrer dans « Mes designs » (`data/designs/*.json`, un
  fichier par design, écriture atomique), ainsi qu'importer et exporter.

### 6.5 L'identification de Branham (couche 1)

- Le texte fixe est **« Reverend William Marrion Branham »**, comme vous l'avez écrit. La version
  « Révérend » ne demande de changer qu'une ligne.
- Il apparaît discrètement en bas, **uniquement** sur les **prédications, l'Exposé des Sept Âges et
  les brochures** (§ 9, décision 3). Les biographies et les autres livres en sont exclus. Plus de
  photo ni de nom dynamique : le badge « orateur du jour » quitte tous les slides (décision 4).
- Quatre styles : **typographie élégante** (petites capitales espacées avec un filet), **texte
  minimaliste**, **bandeau discret** (bande semi-transparente) et **identification transparente**
  (texte avec un halo léger).
- **Lisibilité** : la couleur et le halo s'adaptent à la luminosité du fond sous la zone. Le style
  bandeau garantit le contraste sur n'importe quel fond.

---

## 7. L'interface

Une disposition inspirée de Pgraphics : palette ardoise, accent ambre, **vert pour l'Aperçu et
rouge pour le Direct**, interface à plat, police Inter, icônes Lucide.

```
┌──────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◉ Project-On   [ Rechercher partout   Ctrl+K ]          ● Salle  ● Web 2  ○ NDI  ○ HDMI    ⚙   │
├────┬──────────────────────────┬────────────────────────────┬───────────────────────────────────┤
│ ☰  │ BIBLIOTHÈQUE             │ PLAYLIST · Culte du 9 nov. │ APERÇU                            │
│ 📖 │ Bible  Cantiques  Prédi- │ ▾ Louange                  │ ┌───────────────────────────────┐ │
│ ♪  │ cations  Exposé  Livres  │   ♪ 12  Grâce infinie      │ │                               │ │
│ 🎙 │ Médias                   │   ♪ 45  …                  │ └───────────────────────────────┘ │
│ 📚 │ [ filtrer…            ]  │ ▾ Prédication              │      [ F2 · Envoyer au direct ]   │
│ 🖼 │ liste (virtualisée)      │   🎙 63-0317  ¶ 12-14      │ DIRECT                            │
│ ◧  │                          │   📖 Jean 3:16             │ ┌───────────────────────────────┐ │
│ ⛪ │ détail : versets,        │ + section   + élément      │ │                               │ │
│ ⚙  │ strophes, paragraphes    │                            │ └───────────────────────────────┘ │
│    │                          │                            │  ◀  ▶   Masquer (B)   Noir        │
├────┴──────────────────────────┴────────────────────────────┴───────────────────────────────────┤
│ DESIGNS  Salle : Classique ▾   Diffusion : Ligne ambre ▾   Sous-titres : Contour ▾   [Bibliothèque] │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Le rail latéral** (repliable) : Bibliothèque, Playlist et déroulé, Designs, Écrans et sorties,
  Église, Historique, Réglages.
- **Travailler sans interrompre la projection** : tout se prépare dans l'Aperçu. Modifier une
  playlist, un cantique ou un design ne touche jamais le Direct avant F2.
- **Les raccourcis** : tous ceux de la 2.x sont gardés (F2, PgUp / PgDn, ← / →, B, F5, F8, Ctrl+K,
  Ctrl+F, Ctrl+G, Ctrl+H, Ctrl+Z, F1…). Nouveaux : Ctrl+1 à 6 pour les onglets de la bibliothèque,
  Ctrl+D pour les designs, L pour le lower third, S pour les sous-titres. Ils restent configurables
  (télécommande, Stream Deck).
- **Les petits écrans** : en dessous de 1 366 px, le rail passe en icônes ; en dessous de 1 100 px,
  la bibliothèque et la playlist passent en onglets et les moniteurs s'empilent.
- **Les animations** restent discrètes (150 à 200 ms) et sont coupées en mode PC modeste.

---

## 8. Le plan de migration

Chaque phase suit le même rythme : `cargo fmt`, `clippy -D warnings`, tests, commit, résumé, puis
**j'attends votre feu vert** avant la suivante. La version Python (2.8.x) reste celle qu'on livre
jusqu'à la phase 8 et ne reçoit aucune nouvelle fonction (décision 2). Seul son module Rust est
rebranché sur `po-text` en phase 1, sans changement de comportement, ce que ses tests vérifient.

| Phase | Contenu | Livrable vérifiable | Taille |
|---|---|---|---|
| **0. Validation technique** | `project-on-rs/` minimal. En Rust : lecture d'une **copie** de la vraie base (liste des sermons, recherche sans accents) ; mise en page d'un paragraphe qui remplit l'écran, rendue en PNG ; serveur Web avec un client WebSocket automatique ; une fenêtre egui avec le thème, rendue hors écran. | Mesures comparées à la 2.8 et **critères de go / no-go fixés d'avance** : recherche au moins aussi rapide qu'en 2.8, mise en page sous 10 ms, latence Web locale sous 50 ms, démarrage sous 3 s (hors base). Aucune fenêtre ne s'ouvre sur votre écran. | S |
| **1. Fondations** | `po-core`, `po-text`, `po-db`, `po-settings`. `project_on_core` devient l'enveloppe de `po-text`. | **Tests dorés** : le code Python produit des résultats de référence sur la vraie base (recherches, découpages, références bibliques, aller-retour des réglages), et le Rust doit donner les mêmes. | M |
| **2. Moteur de projection + couche 1** | `po-design` (style actuel), `po-layout` (parité avec le remplissage de la 2.8 : zone de sécurité 5 %, vers non coupés, référence épinglée), `po-render`, transitions. **Identification de Branham** (4 styles, contraste adapté au fond), sans badge d'orateur. | Captures de référence comparées, dans des tests sans fenêtre, pour chaque style d'identification sur fonds clairs, sombres et photos. | L |
| **3. Coque et bibliothèque** | Système de design repris de Pgraphics, rail, Bible / Cantiques / Prédications / Exposé / Livres, Aperçu / Direct, projection native multi-écrans, recherche globale, raccourcis. | **Première bêta utilisable**, installée à côté de la 2.8, sur une copie des données. | L |
| **4. Playlist et déroulé** | Parité avec la 2.8 : sections repliables, glisser-déposer, sélection multiple, copier / déplacer, Ctrl+Z, paragraphe entier. | Tests du modèle + essai guidé. | M |
| **5. Projection Web** | `po-web`, écrans multiples, reconnexion, compatibilité `/obs`, état des écrans dans la barre. | Tests d'intégration avec plusieurs clients, coupure et reprise. | M |
| **6. Designs, lower thirds, sous-titres** | Bibliothèque, éditeur, aperçus, Mes designs ; reprise des réglages 2.x en designs ; NDI et HDMI branchés sur `po-render`. | Captures de chaque style intégré, tests des animations et des sous-titres (lignes, SRT). | L |
| **7. Parité du reste** | Médias et vidéos, PowerPoint, réglages, Église (accueil, réseaux, écran de l'orateur, citations, galerie de photos), éditeur de cantiques, historique et exports (rapport, tableur, SRT, images), imports PDF et Bibles, sauvegardes, mise à jour, contrôle avant culte, reprise après coupure, mode PC modeste, pilotage d'OBS. **Sans les miniatures YouTube** (couche 1). | Une liste de parité fonction par fonction, cochée avec vous. | XL |
| **8. Bascule 3.0** | L'installeur remplace la 2.x en gardant la base, les playlists et les réglages ; essai complet sur un vrai vidéoprojecteur ; retrait du code Python (étiquette `v2.8.x`) ; publication. | Project-On 3.0 publié. | M |

---

## 9. Décisions prises le 9 novembre 2026

1. **Code de Pgraphics : il est repris** (thème, widgets, icônes, projecteur, rendu du texte,
   journal) et publié sous MIT dans Project-On.
2. **Couche 1 : seulement dans la version Rust.** La 2.8 ne reçoit aucune nouvelle fonction. Les miniatures ne sont
   pas portées ; l'identification arrive en phase 2.
3. **L'identification de Branham** s'applique aux **prédications, à l'Exposé des Sept Âges et aux
   brochures**. Les biographies (« Un homme envoyé de Dieu », « Un prophète visite l'Afrique du
   Sud ») en sont exclues.
4. **Le badge « orateur du jour » quitte tous les slides.** L'écran plein « Orateur du jour »
   (Ctrl+Maj+P) reste disponible.

Choix proposés et non contestés à ce jour : egui + wgpu pour l'interface (§ 3), le pilotage d'OBS
gardé comme intégration facultative (§ 1.5), le texte « Reverend » sans accent, et la bêta
travaillant sur une copie des données.

---

## 10. Risques et parades

| Risque | Parade |
|---|---|
| **L'ampleur** : environ 48 000 lignes à réécrire, donc plusieurs semaines de travail. | Des phases livrables ; la 2.x reste la version livrée jusqu'à la parité, et une liste de parité est validée avec vous. |
| La fidélité de l'import PDF (des alinéas fidèles au PDF) | PDFium, avec des tests dorés comparés au parseur Python sur les vrais PDF. L'import est rare, puisque la base est fournie : il arrive en phase 7. |
| Un rendu différent entre l'écran local et le Web | Une seule mise en page en Rust ; le navigateur ne fait que dessiner des lignes déjà placées, avec les mêmes fichiers de police. |
| L'accès concurrent à la base pendant la transition | La bêta travaille sur une copie ; les migrations sont seulement additives. |
| Les performances sur Intel UHD 620 | Pgraphics y compose de la vidéo 1080p à 30 i/s ; des slides de texte sont bien plus légères. La phase 0 le mesure. |
| L'accessibilité et la saisie (accents, IME) | egui gère l'IME et AccessKit, et c'est vérifié en phase 3 avec un clavier français. |
| La licence (Pgraphics propriétaire, PyMuPDF AGPL) | Le code repris de Pgraphics passe sous MIT (décision 1) ; PDFium remplace PyMuPDF. |
| Le DLL NDI parfois absent de `ndi/` | Chargement dynamique : sans le DLL, la sortie NDI est simplement indisponible et le reste fonctionne. |
| La signature de code (clé du certificat inutilisable) | Sans rapport avec la migration, mais à régler avant la 3.0. |
