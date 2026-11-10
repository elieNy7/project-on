# Phase 2 : rapport du moteur de projection et de la couche 1

**Date** : 10 novembre 2026. **Résultat** : la 3.0 met en page la projection **comme la 2.8**. Sur
2 208 slides comparés au vrai `SlideCanvas` de la 2.8, la taille, les coupures de lignes, la place
du texte, la référence et le filet sont identiques dans 100 % des cas (écart de position maximal :
1 px). L'identification de Branham existe en 4 styles, lisible sur tous les fonds essayés
(contraste ≥ 4,5 pour 1), et le badge d'orateur n'existe plus. Le livrable fixé par l'audit (§ 8,
phase 2) est tenu : des captures de référence comparées dans des tests sans fenêtre, pour chaque
style, sur fonds clairs, sombres et photos.

## Ce qui a été construit

| Crate | Contenu |
|---|---|
| `po-design` (nouvelle) | Le modèle du style de la salle (`RoomDesign`) : texte, référence, ombre, alignement, fond (couleur, dégradé, image, « look » cinéma / net / partagé, voile), animation, identification. Il se lit depuis les réglages « Projection » de la 2.x, avec les mêmes bornes. Les couleurs (`Rgba`, contraste WCAG), et le genre d'un slide (Bible, cantique, prédication, Exposé, brochure, livre, texte libre). |
| `po-layout` (refaite) | La mise en page plein écran de la 2.8 : zone de sécurité de 5 %, recherche de la plus grande taille qui tient, lignes équilibrées, vers jamais coupés, référence épinglée en haut ou en bas, filet de couleur. Le fond (image « couvrir / contenir », voiles, vignette). L'identification de Branham. Les transitions. Le résultat est toujours une **liste d'affichage** en trois couches : fond, contenu, surcouche. |
| `po-render` (complétée) | Le dessin d'une liste d'affichage : dégradés, images, ombres et halos floutés, groupes animés (opacité, déplacement, zoom, flou, découpe). Le fond est gardé en cache : les slides suivants le recopient. La luminosité du fond sous une zone, pour l'identification. |
| `po-web` (complété) | Les écrans Web reçoivent la même liste d'affichage, avec les images de fond, et la dessinent en SVG. |
| `project-on` (coque) | Les moniteurs Aperçu / Direct utilisent le nouveau moteur avec **votre** style de projection, lu sans écrire dans `%APPDATA%\Project-On\data\settings.json`. |
| `po-parite`, `po-mesures` | `po-parite projection` (tests dorés de la mise en page), `po-mesures captures` (planches de référence), la mesure du rendu avec les réglages par défaut et des aperçus successifs. |

Environ 3 800 lignes ajoutées et 77 tests dans l'espace de travail, tous sans fenêtre.

## La parité avec la 2.8

`outils/references_projection_28.py` fait tourner **le vrai `SlideCanvas` de la 2.8** (Python 3.14,
PySide6) sur une copie de la base. Le canevas n'est jamais affiché : il est mis en page en mémoire,
sur la vraie plateforme Windows de Qt, pour que les polices soient mesurées comme dans la 2.8
installée. Pour chaque slide, le script note la taille retenue, les lignes, la place du texte, de la
référence et du filet. `po-parite projection` refait la même mise en page en Rust et compare.

| Réglages (écran 1920 × 1080) | Prédications | Cantiques | Versets | Textes courts | Identiques |
|---|---:|---:|---:|---:|---:|
| Les vôtres (`settings.json`, fond uni) | 285 | 275 | 172 | 4 | 100 % |
| Référence en bas, ombre portée de 18 px | 285 | 275 | 172 | 4 | 100 % |
| Poppins gras 56, aligné à gauche, interligne 1,12, marge 80 | 285 | 275 | 172 | 4 | 100 % |
| **Total : 2 208 slides** | | | | | **100 %** |

« Identique » veut dire : même taille de police, mêmes lignes, même ligne de base (tolérance 2 px,
écart maximal mesuré 1 px), même référence (taille et place) et même filet (place et largeur). Le
détail est dans [`projection-parite.json`](projection-parite.json), sans aucun texte de la base.

La planche [`comparaison-28-30.jpg`](comparaison-28-30.jpg) montre 12 de ces slides côte à côte :
la capture de la 2.8 à gauche, le rendu de la 3.0 à droite, avec vos réglages. L'identification y
est désactivée, puisque la 2.8 n'en a pas.

### Ce qu'il a fallu reproduire

Atteindre 100 % a demandé d'imiter Qt jusque dans ses arrondis :

- **Hauteurs** : Qt convertit l'ascendante et la descendante de la police en virgule fixe 26.6 en
  tronquant, puis arrondit. Il lit les métriques « typo » si la police le demande (bit
  `USE_TYPO_METRICS`), sinon les métriques Windows, avec un interligne recalculé. L'ordre exact des
  opérations compte : un calcul dans un autre ordre donnait 1 px de trop pour Poppins 45.
- **Largeurs** : sous Windows, Qt prend les largeurs des lettres à DirectWrite en mode « GDI
  naturel », arrondies au pixel lettre par lettre, plus le crénage. Aux tailles moyennes (20 à
  60 px), le simple arrondi des largeurs de la police ne suffit pas : une ligne sur cinquante était
  coupée à un autre mot. La 3.0 appelle donc DirectWrite pour ces largeurs (module `dwrite.rs`, le
  seul code `unsafe` du projet, limité aux appels Windows) et les garde en cache.
- **Vitesse** : la largeur d'une ligne est la somme des largeurs des mots (gardées en cache) et des
  espaces, exactement comme dans Qt. Cela a divisé par cinq le temps de mise en page (1,2 ms en
  médiane aujourd'hui).

## L'identification de Branham (couche 1)

- **Le texte** : « Reverend William Marrion Branham », fixe, en bas de l'écran.
- **Où** : prédications, Exposé des Sept Âges (`BK-AGES`) et brochures (`TR-`). Les autres livres
  (`BK-`), dont les biographies, et les Bibles, cantiques et textes libres n'en ont pas.
- **Quatre styles** ([`identification-zoom.png`](identification-zoom.png), taille réelle) :
  - **élégante** : capitales espacées en Spectral, avec un filet fin au-dessus ;
  - **minimaliste** : Lato, sobre ;
  - **bandeau discret** : capitales Lato sur une bande sombre semi-transparente ;
  - **transparente** : Lato gras avec un halo léger.
- **Lisibilité** : la 3.0 mesure la luminosité du fond sous la zone (image, voile et dégradé
  compris), choisit l'encre claire ou sombre qui contraste le mieux, et ajoute un halo si le
  contraste reste sous 4,5 pour 1. Le bandeau garde un texte clair sur sa bande, quel que soit le
  fond.
- **Jamais sur le texte** : une hauteur de 58 px (à 1080 lignes) est réservée au-dessus de la marge
  de sécurité ; le texte et la référence ne la traversent pas (vérifié pour les 4 styles, référence
  en haut et en bas, sur 4 tailles d'écran).

Contraste mesuré sur l'image rendue (encre contre fond, halo compris), 960 × 540 :

| Fond (luminosité sous la zone) | Élégante | Minimaliste | Bandeau | Transparente |
|---|---:|---:|---:|---:|
| Sombre uni (0,00) | 16,6 | 15,6 | 18,0 | 17,9 |
| Clair uni (0,84) | 5,1 | 16,2 | 5,9 | 8,3 |
| Gris moyen (0,22), le cas le plus dur | 5,0 | 5,5 | 11,0 | 7,4 |
| Clair avec dégradé et voile (0,12) | 5,5 | 5,2 | 13,0 | 7,5 |
| Photo claire, sable (0,25) | 6,7 | 4,9 | 10,4 | 8,0 |
| Photo, montagnes à l'aube (0,01) | 16,2 | 15,3 | 17,9 | 17,7 |

Le minimum demandé est 4,5 pour 1 (WCAG AA). Le test `identification_is_readable_on_every_background`
échoue sous ce seuil. La planche [`identification.png`](identification.png) montre les 16
combinaisons sur un vrai paragraphe en 1920 × 1080 : 4 fonds de haut en bas, 4 styles de gauche à
droite.

**Le badge « orateur du jour »** n'existe pas dans la 3.0 : la liste d'affichage n'a aucun élément
pour lui. L'écran plein « Orateur du jour » arrivera avec la parité du reste (phase 7).

## Les transitions

Fondu, glissement, zoom, flou et balayage, avec la courbe de la 2.8 (`InOutCubic` de Qt, puis
`smootherstep`). Une image de transition est une liste d'affichage comme les autres : le fond du
nouveau slide reste fixe, l'ancien et le nouveau contenu passent dans deux groupes animés. Les
écrans Web les reçoivent donc aussi. Planche : [`transitions.jpg`](transitions.jpg) (5 transitions,
5 instants chacune).

**Une amélioration** : dans le balayage de la 2.8, l'ancien texte restait visible sous le nouveau
jusqu'à la fin. Dans la 3.0, il s'efface au fur et à mesure que le nouveau apparaît.

## Les écrans Web

Le client du navigateur dessine la même liste d'affichage en SVG : fond (image servie par le
serveur, dégradés, voile), texte avec les polices de l'application, ombres, filet, identification,
transitions. Il a été vérifié dans un navigateur avec une image de fond : image, filet doré et
identification présents.

## Performances

Mesurées sur ce poste (i5-8350U), base copiée, avec `po-mesures tout`. Détail :
[`mesures.json`](mesures.json).

| Mesure | Phase 0 | Phase 2 | Critère |
|---|---:|---:|---|
| Mise en page d'un slide 1080p (médiane / p95 / max) | 0,57 / 0,73 / 1,8 ms | 1,2 / 3,7 / 18,7 ms | < 10 ms : tenu |
| Rendu 1920 × 1080, fond uni sans ombre (médiane) | 11,8 ms | 15,2 ms | |
| Rendu 1920 × 1080, réglages par défaut de la 2.x : ombre, dégradé, voile (médiane / p95) | — | 38 / 47 ms | |
| Rendu d'un moniteur 960 × 540 (médiane) | 5,4 ms | 6,7 ms | |
| Latence Web, 3 écrans (médiane / p95) | 2,5 / 6,2 ms | 4,0 / 8,9 ms | < 50 ms : tenu |
| Première image de l'interface | 545 ms | 600 à 860 ms | < 3 s : tenu |
| Clic sur un paragraphe jusqu'à l'Aperçu (premier / suivants) | 9 ms | 108 / 80 ms | |

Le moteur fait bien plus qu'en phase 0 (vraie recherche de taille, DirectWrite, fond, ombre,
identification). Le dernier chiffre concerne de longs paragraphes (jusqu'à 3 000 caractères) avec
l'ombre portée, le tout dessiné par le processeur. Le rendu par la carte graphique arrive en
phase 3.

**Deux défauts trouvés et corrigés en mesurant** :

- **L'ombre portée était lente** : jusqu'à 0,4 s pour un long paragraphe dans l'Aperçu. Chaque
  ligne avait son propre calque de la taille de l'écran, flouté sur ses quatre canaux, et le texte
  était dessiné deux fois. La 3.0 calcule maintenant la forme des lettres une seule fois pour tout
  le bloc. Elle floute seulement l'opacité, l'ombre n'ayant qu'une couleur, sur la zone utile, puis
  pose le texte avec la même forme. Le rendu 1080p avec les réglages par défaut est passé de 169 ms
  à 38 ms (médiane). Pour une ligne seule, l'écart avec l'ancienne méthode est d'au plus 2 niveaux
  sur 255, et un test le vérifie. C'est aussi plus fidèle : comme `ShadowTextLabel` de la 2.8,
  l'ombre est floutée pour tout le bloc, donc l'ombre d'une ligne ne passe plus sur la ligne
  au-dessus.
- **L'Aperçu ne montrait pas exactement la salle.** La coque mettait le slide en page à la taille
  du moniteur (960 × 540) : les longs paragraphes y tombaient à la taille minimale et coupaient
  leurs lignes ailleurs que sur le projecteur. Comme dans la 2.8, la 3.0 met maintenant le slide en
  page à la taille de l'écran de projection (1920 × 1080), puis le montre réduit.

## Particularités de la 2.8 trouvées en chemin

- **La 2.8 plante en plein écran quand la référence est masquée** (`show_reference: false`) : la
  hauteur disponible n'est jamais calculée (`_apply_layout_metrics`). La 3.0 donne alors toute la
  scène au texte. Ce réglage n'a donc pas pu être comparé.
- **Le balayage** laissait l'ancien texte visible (voir plus haut).

## Ce que ces résultats ne couvrent pas

- **Une seule taille d'écran comparée à la 2.8** (1920 × 1080). Les autres tailles sont couvertes
  par les tests de la 3.0 (zone de sécurité, identification), pas par une comparaison.
- **Les autres modes de mise en page** de la 2.8 (bandeau bas, panneau latéral, sous-titres, carte
  centrée) arrivent avec les designs, en phase 6.
- **Les fonds vidéo, l'effet Ken Burns et les médias** : phase 7.
- **Les transitions sont dessinées par le processeur, trop lentement pour la salle** : une image de
  transition 1080p prend 80 à 100 ms (270 ms pour le flou), soit une dizaine d'images par seconde.
  Elles sont justes (même liste d'affichage, testées image par image), mais leur fluidité attend la
  projection native de la phase 3, dessinée par la carte graphique.
- **Les largeurs DirectWrite** n'existent que sous Windows. Ailleurs, la 3.0 utilise les largeurs
  de la police, arrondies : la mise en page reste juste, mais n'est plus garantie identique au
  pixel.
- **Le client Web** dessine le texte avec le moteur du navigateur et les mêmes fichiers de police.
  Les largeurs peuvent différer d'un pixel ; les coupures de lignes, elles, viennent du serveur.
- **Pas encore relevé** : le test de la 2.8 sur la version du site (`docs/index.html` pointe encore
  vers la 2.7.0), signalé en phase 1, est toujours en échec. Il ne concerne pas la refonte.

## Incidents et solutions

- **Les premières références de la 2.8 étaient fausses.** Faites avec la plateforme Qt
  « offscreen », elles mesuraient le texte avec FreeType et non avec DirectWrite. Elles ont été
  refaites avec la vraie plateforme Windows, toujours sans afficher de fenêtre : le canevas est
  mis en page par un rendu en mémoire.
- **Un premier relevé des performances a été fait pendant qu'autre chose occupait le poste** (tout
  y était 5 à 10 fois plus lent, jusqu'à l'ouverture de la base). Il a été refait au calme. C'est
  en le comparant à la phase 0 que les deux défauts ci-dessus sont apparus.
- **Contraste insuffisant sur un fond gris moyen** (3,6 pour 1 au premier essai) : l'encre est
  maintenant choisie selon le meilleur contraste, et le halo est plus net.

## Refaire les vérifications

```powershell
cd project-on-rs
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
# depuis la racine du dépôt, sur une COPIE de la base (Python avec PySide6 : py -3.14) :
py -3.14 project-on-rs\outils\references_projection_28.py <copie\project_on.db> project-on-rs\target\phase2\ref28
cd project-on-rs
cargo run --release -p po-parite -- projection target\phase2\ref28
cargo run --release -p po-mesures -- captures target\phase2\ref28 target\phase2\captures
cargo run --release -p po-mesures -- tout <copie\project_on.db> target\phase2\mesures
```

Les références contiennent des textes de la base : elles restent dans `target\` (non versionné).

## Suite proposée : la phase 3 (coque et bibliothèque)

- Le système de design repris de Pgraphics, le rail, et les bibliothèques Bible, Cantiques,
  Prédications, Exposé et Livres.
- Aperçu et Direct, la **projection native** sur plusieurs écrans (rendue par la carte graphique,
  transitions comprises) et la recherche globale.
- Les raccourcis, avec un essai au clavier français (accents).
- La lecture de la base en arrière-plan au lancement, qui rend la première recherche rapide
  (mesurée en phase 1).
- Livrable : **la première bêta utilisable**, installée à côté de la 2.8, sur une copie des
  données.
