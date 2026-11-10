# Phase 1 : rapport des fondations

**Dates** : 9 et 10 novembre 2026. **Résultat** : les fondations de la 3.0 sont écrites en Rust et
donnent **exactement** les résultats de la 2.8. Sur 1 131 437 cas comparés au vrai code de la 2.8,
il y a 0 différence. Le livrable fixé par l'audit (§ 8, phase 1 : « tests dorés ») est tenu.

## Ce qui a été construit

| Crate | Contenu |
|---|---|
| `po-core` (nouvelle) | Les dossiers de données de la 2.x (registre, `%APPDATA%`, `%LOCALAPPDATA%`) et de la bêta 3.0 (`%APPDATA%\Project-On 3 (bêta)`). Le journal repris de Pgraphics : 5 Mo, 5 archives, 20 Mo au plus par lancement. Les conversions « à la Python » qui servent à relire les fichiers de la 2.x. |
| `po-text` (complétée) | Le nettoyage HTML (`html.unescape`, table des 2 231 entités tirée de Python) et les clés et requêtes de recherche. Le découpage des textes longs en parties équilibrées et des strophes en groupes de vers. Les étiquettes de refrains, les références bibliques tapées, la casse des titres imprimés, le titre commun des traductions, les repères de paragraphes et les chapitres de l'Exposé. |
| `po-settings` (nouvelle) | `settings.json` lu avec les règles exactes de la 2.8 pour les sections dont la 3.0 se sert déjà : projection, apparence, découpage, HDMI. Les autres sections sont gardées telles quelles. L'écriture est atomique avec `.bak`, et un fichier illisible est relu depuis la sauvegarde puis mis de côté. |
| `po-db` (complétée) | Le schéma et les migrations 1 à 11 (texte SQL identique à celui de la 2.8), puis la maintenance : titres communs, repères, index de recherche, import des Bibles JSON, compactage. La lecture et l'écriture de toutes les parties : Bible, cantiques, prédications, livres, Exposé, playlists (réorganiser, copier, déplacer, annuler), déroulé du culte et médias. La copie cohérente d'une base ouverte (API de sauvegarde de SQLite). |
| `po-parite` (nouvelle, jamais livrée) | Les tests dorés : la 3.0 rejoue les références de la 2.8 et compare tout. |
| `rust/project_on_core` (2.8) | Le module natif de la 2.8 n'est plus qu'une enveloppe de `po-text` : la 2.8 et la 3.0 partagent le même code de pliage sans accents. |

Environ 7 100 lignes de Rust, plus 61 tests unitaires dont chaque valeur attendue a été relevée sur
la 2.8.

## Les tests dorés

`outils/references_28.py` fait tourner **le vrai code de la 2.8** (Python 3.14, avec son module
natif) sur une copie de la base et enregistre ce qu'il rend. `po-parite` refait ensuite les mêmes
appels en Rust et compare chaque résultat.

| Partie | Ce qui est comparé | Cas | Différences |
|---|---|---:|---:|
| Textes | 24 fonctions sur tous les titres, lieux, strophes, un paragraphe sur 400, les 60 plus longs, des versets, 43 cas limites écrits à la main ; 9 000 découpages de textes et 44 000 découpages de strophes | 262 063 | 0 |
| Références bibliques | 25 saisies types et 4 par livre, dans les 11 traductions installées | 3 179 | 0 |
| Requêtes | 29 fonctions de lecture sur votre base (sermons, recherches, livres, Exposé, Bible, cantiques, playlists, médias) | 2 225 | 0 |
| Maintenance | Les titres communs, clés, repères (568 000 paragraphes) et étiquettes recalculés par la 2.8 et par la 3.0, puis les deux bases comparées ligne à ligne | 677 141 | 0 |
| Base neuve | Une base créée de zéro par chacune : schéma (texte SQL compris), démonstration, 3 Bibles importées | 93 355 | 0 |
| Opérations | 56 écritures (playlists, annulation, déroulé, médias, éditeur de cantiques) : valeurs rendues, puis bases comparées | 93 424 | 0 |
| Réglages | Votre `settings.json`, celui du dépôt et 8 fichiers piégés (mauvais types, valeurs hors bornes, fichier illisible) | 50 | 0 |
| **Total** | | **1 131 437** | **0** |

L'outil a été vérifié à l'envers. Trois valeurs modifiées volontairement dans une base donnent trois
différences, chacune trouvée à la bonne ligne. Le zéro n'est donc pas un faux positif.

En chemin, la comparaison a fait apparaître deux **particularités de la 2.8**, gardées telles
quelles :

- Le titre « ECOUTEZ-LE - DURBAN AFRIQUE » devient « Ecoutez » : le lieu retiré emporte aussi
  « -LE ».
- Sans repère enregistré, la 2.8 prend la référence brute comme repère (« BK 40-1 » au lieu de
  « 40-1 »).

## La recherche à froid (point laissé ouvert en phase 0)

Pour mesurer comme au premier lancement d'un culte sans redémarrer le poste, chaque version a reçu
sa propre copie de la base, écrite sans passer par le cache de Windows (`outils/copie_froide.py`).
Les mesures ont été faites en deux tours, en alternant l'ordre. Chaque fois, ce sont les 7 requêtes
de la phase 0, au premier appel.

| Requête (premier appel, à froid) | 2.8 tour A | 3.0 tour A | 2.8 tour B | 3.0 tour B |
|---|---:|---:|---:|---:|
| Liste des sermons | 216 ms | 49 ms | 86 ms | 57 ms |
| Titres « foi » | 10 ms | 6 ms | 10 ms | 8 ms |
| Plein texte « grâce » | 7 030 ms | 6 491 ms | 5 613 ms | 6 037 ms |
| Plein texte « ferme assurance » | 255 ms | 239 ms | 418 ms | 134 ms |
| Expression « colonne de feu » | 1 773 ms | 1 721 ms | 2 299 ms | 1 648 ms |
| Sous-chaîne « ernel Die » | 16 836 ms | 18 578 ms | 20 713 ms | 19 372 ms |
| Sous-chaîne absente | 2 627 ms | 2 312 ms | 2 610 ms | 2 259 ms |
| **Total** | **28,7 s** | **29,4 s** | **31,7 s** | **29,5 s** |

- **À froid, la 3.0 est au niveau de la 2.8.** C'est le disque (SSD SATA) qui limite, pas le
  langage. Les résultats sont identiques. Le critère « recherche au moins aussi rapide » est tenu,
  à l'écart de mesure près.
- **La première recherche après un démarrage est lente dans les deux versions** : environ 6 s pour
  « grâce » (0,1 s une fois la base en mémoire) et environ 18 s pour la première recherche par
  sous-chaîne.
- **Remède mesuré** : lire toute la base une fois au lancement (3,4 s sur ce poste) ramène ces
  premières recherches à 0,1 s et 3,3 s ([`froid-c-30.json`](froid-c-30.json)). Cette lecture
  devra se faire en arrière-plan, sans gêner l'interface. Je propose de l'ajouter en phase 3, au
  démarrage de l'application.

## L'index trigramme (essai, rien n'est changé dans la base)

La recherche par sous-chaîne parcourt les 568 000 paragraphes : 2 à 3 s même base en mémoire, en
2.8 comme en 3.0. L'essai : un index FTS5 `trigram` sur le texte plié comme `unaccent()`, construit
sur une copie (`po-mesures trigramme`).

| | Parcours (2.8 et 3.0) | Index trigramme |
|---|---:|---:|
| « ernel Die » | 3 404 ms | 19,5 ms |
| « ait là, d » | 2 452 ms | 55,4 ms |
| « esprit de dieu » | 2 922 ms | 103,2 ms |
| « seigneur jésus-christ » | 2 510 ms | 59,4 ms |
| « œuvre » | 2 163 ms | 3,1 ms |
| « l'Éternel » | 2 286 ms | 8,5 ms |
| Absente (« zzqxw ») | 2 092 ms | 0,2 ms |

- **Mêmes résultats.** Pour toutes ces recherches, l'ensemble complet des paragraphes trouvés est
  identique, au paragraphe près. Seule exception : `%` et `_`, que la 2.8 traite comme des jokers
  (« foi_ » y trouve 78 256 paragraphes) et que l'index cherche tels quels. C'est plus juste, mais
  c'est un changement de comportement.
- **Moins de deux lettres** : l'index ne sert pas, le parcours reste.
- **Le prix** : +714 Mo sur le disque (la base passe de 596 Mo à 1,3 Go) et 98 s de construction,
  une seule fois.
- Les temps ci-dessus viennent du premier passage. Un second passage, sur un poste plus chargé, a
  été environ deux fois plus lent pour les deux méthodes ; ses résultats sont dans
  [`trigramme.json`](trigramme.json).
- **Décision à prendre (rien n'est fait)** : l'index divise par 20 à 1 000 la recherche par
  sous-chaîne, mais double la taille des données. Il peut arriver comme une migration additive (une
  table de plus, que la 2.8 ignore) quand vous le déciderez.

## Le module natif de la 2.8

- Le module est recompilé sur `po-text`. Ses tests Rust passent, et ses fonctions donnent les mêmes
  résultats depuis Python : pliage, liste, extension SQLite.
- **Suite de tests de la 2.8 avec ce module : 599 réussis, 1 échec, 1 ignoré.** L'échec
  (`test_release_version_is_consistent_across_product_surfaces`) n'a rien à voir avec la phase 1.
  Le site (`docs/index.html`) pointe encore vers l'installeur 2.7.0 alors que la version est la
  2.8.0. Ce fichier n'a pas été modifié par la refonte.
- Le module recompilé pèse 5,3 Mo contre 2,8 Mo pour celui de l'installation. Les expressions
  régulières et la table HTML de `po-text` n'y sont pas (vérifié) : l'écart vient de la façon de
  compiler (maturin pour l'installeur, Cargo ici). À regarder seulement si une 2.8.x devait être
  republiée.

## Ce que ces résultats ne couvrent pas

- **La mise à jour du « pack de données »** (`upgrade_data_pack` de la 2.8 : remplacement des
  livres et des sermons SHP par ceux de l'installeur) n'est pas portée. Elle appartient à
  l'installeur (phase 8).
- **Les réglages** `obs`, `shortcuts`, `church` et `thumbnail_models` sont gardés tels quels, sans
  être interprétés. Ils seront typés dans la phase qui s'en sert : Web en 5, designs en 6, Église
  en 7. Les miniatures YouTube ne seront pas reprises (couche 1).
- **Les valeurs non finies** (`NaN`, `Infinity`) d'un `settings.json` écrit à la main, que Python
  accepte, et les chiffres non ASCII (« ٣ ») dans une référence biblique ne sont pas reproduits.
  Aucun fichier réel n'en contient.
- **La copie d'une base** (`copy_database`) abandonne désormais après 60 s sans progrès. La 2.8
  réessayait indéfiniment, et l'application restait figée.

## Incidents et solutions

- **Le dossier temporaire de Windows est fermé en écriture aux programmes Rust sur ce poste.** Les
  tests écrivent donc dans `target/tmp`. Une copie de base lue dans un tel dossier ne progressait
  plus : c'est ce qui a révélé la copie sans fin (corrigée).
- **Le premier Python du poste n'a pas PySide6.** La suite de la 2.8 tourne avec `py -3.14`.
- **Les égalités de tri.** Les traductions d'un sermon partagent leur date et leurs numéros de
  paragraphe. La limite de 100 résultats peut donc garder l'une ou l'autre selon le plan de SQLite.
  Les comparaisons se font sur les ensembles complets.

## Refaire les vérifications

```powershell
cd project-on-rs
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
# depuis la racine du dépôt, sur une COPIE de la base :
python project-on-rs\outils\references_28.py <copie\project_on.db> project-on-rs\target\parite <module natif>
cargo run --release -p po-parite -- target\parite
```

Fichiers bruts : [`parite.json`](parite.json) (décompte par fonction, sans aucun texte de la base),
`froid-*.json`, [`trigramme.json`](trigramme.json).

## Suite proposée : la phase 2 (moteur de projection et couche 1)

- `po-design` reprendra le style actuel, et `po-layout` sera au niveau du remplissage de la 2.8.
- Les transitions entre les slides.
- **L'identification de Branham** (4 styles, contraste adapté au fond), sans badge d'orateur.
- Des captures de référence comparées dans des tests sans fenêtre.
