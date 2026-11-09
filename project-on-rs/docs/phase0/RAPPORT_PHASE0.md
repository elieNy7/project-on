# Phase 0 : rapport de validation technique

**Date** : 9 novembre 2026. **Verdict : GO.** Les quatre critères fixés d'avance dans
[`AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md`](../../../AUDIT_ET_ARCHITECTURE_RUST_2026-11-09.md)
(§ 8, phase 0) sont tenus, avec de la marge. Rien de ce qu'on a mesuré n'impose de changer
l'architecture cible.

## Ce qui a été construit

Un prototype minimal dans `project-on-rs/`, entièrement en Rust :

- **`po-text`** : le pliage sans accents et les requêtes de recherche, avec les mêmes résultats
  que la 2.8 (valeurs attendues relevées sur l'implémentation Python).
- **`po-db`** : la base de la 2.8 telle quelle (schéma 11), ouverte en **lecture seule**. On y
  trouve la liste des sermons, la recherche FTS5 et la recherche par sous-chaîne sans accents.
- **`po-layout`** : le texte qui remplit l'écran, porté de `slide_canvas` (zone de sécurité de 5 %,
  plafond 4×, lignes équilibrées, ponctuation française collée). Il produit une **liste
  d'affichage**.
- **`po-render`** : le dessin d'une liste d'affichage en image (contours des glyphes dans
  tiny-skia).
- **`po-web`** : la projection Web, avec un serveur local axum en lecture seule, un WebSocket et
  un client navigateur en SVG. Chaque écran reçoit une mise en page à sa taille, le client se
  reconnecte tout seul et garde la dernière image pendant une coupure.
- **`project-on`** : une coque egui avec le thème repris de Pgraphics. On y trouve la bibliothèque
  des prédications, les paragraphes, l'Aperçu et le Direct (F2), ainsi que l'état de la projection
  Web.
- **`po-mesures`** : les mesures de ce rapport (jamais livré).

Toutes les mesures portent sur une **copie** de la vraie base (596 Mo, 2 815 sermons affichés).
Aucune fenêtre ne s'est ouverte : l'interface est rendue hors écran (egui_kittest + wgpu).

## Les critères

| Critère (fixé d'avance) | Seuil | Mesuré | |
|---|---|---|---|
| Recherche | au moins aussi rapide qu'en 2.8 | plus rapide sur les 7 requêtes, résultats identiques | ✅ |
| Mise en page d'un slide 1080p | < 10 ms | médiane **0,57 ms**, max 1,79 ms | ✅ |
| Latence de la projection Web locale | < 50 ms | médiane **2,5 ms**, max 9,8 ms | ✅ |
| Démarrage (hors base) | < 3 s | **0,68 à 0,70 s** jusqu'à la première image | ✅ |

### Recherche : 2.8 (Python + module natif livré) contre 3.0 (Rust)

Ce sont les mêmes requêtes sur la même copie, avec le meilleur de 3 essais (cache disque chaud).
Le nombre de résultats et le premier résultat sont identiques pour chaque requête.

| Requête | 2.8 | 3.0 | Résultats |
|---|---:|---:|---|
| Liste des sermons | 22,1 ms | 5,9 ms | 2 815 |
| Titres contenant « foi » | 7,8 ms | 2,9 ms | 111 |
| Plein texte « grâce » | 101,6 ms | 84,3 ms | 100 (61-0827 §165) |
| Plein texte « ferme assurance » | 18,6 ms | 14,5 ms | 100 (47-0412 §50) |
| Expression « colonne de feu » | 76,0 ms | 51,4 ms | 100 (53-0509 §53) |
| Sous-chaîne « ernel Die » | 2 838 ms | 2 580 ms | 100 (47-1123 E-76) |
| Sous-chaîne absente | 2 013 ms | 1 891 ms | 0 |

La 2.8 a été mesurée avec son module natif (`unaccent` en extension SQLite). C'est ce que
l'utilisateur a installé. Sans ce module, la 2.8 met 60 à 75 s par recherche par sous-chaîne ;
le JSON de référence le vérifie (`"native": true`).

### Mise en page et rendu (1 347 paragraphes réels)

Les paragraphes viennent d'un sermon sur 25 (les 12 premiers paragraphes de chacun). Le style est
celui de l'utilisateur (Passion One, majuscules, référence en haut).

| | Médiane | p95 | Max |
|---|---:|---:|---:|
| Mise en page 1920 × 1080 | 0,57 ms | 0,73 ms | 1,79 ms |
| Rendu en image 1920 × 1080 (CPU) | 11,8 ms | 12,6 ms | 13,4 ms |
| Rendu d'un moniteur 960 × 540 (CPU) | 5,4 ms | 6,1 ms | 7,7 ms |

### Projection Web

Trois écrans étaient connectés en même temps et 100 changements du Direct ont été envoyés, soit
300 images reçues sur 300. La latence est mesurée de la prise au Direct jusqu'à la réception par
chaque écran, mise en page à sa taille comprise.

- Latence : médiane 2,5 ms, p95 6,2 ms, max 9,8 ms (à cache chaud : 1,8 / 3,9 / 4,9 ms).
- Reconnexion d'un écran jusqu'à l'image du Direct : 1,9 ms.

Le client a aussi été vérifié dans un vrai navigateur ([`ecran-web.jpg`](ecran-web.jpg)) : le rendu,
les polices servies par Project-On, la nouvelle mise en page quand l'onglet change de taille, la
dernière image gardée pendant une coupure et la reconnexion automatique.

### Démarrage

Le processus complet, mesuré de l'extérieur sur 3 essais, met **688, 678 et 701 ms**. Cela couvre
l'ouverture de la base, la liste des 2 815 sermons, le chargement des polices, l'initialisation du
GPU et la première image de l'interface. L'exécutable en version optimisée pèse 17,7 Mo.

## Images de référence

- [`interface.png`](interface.png) : la coque, 1500 × 900, avec un paragraphe à l'Aperçu et au
  Direct.
- [`slide-long.png`](slide-long.png), [`slide-court.png`](slide-court.png),
  [`slide-verset.png`](slide-verset.png) : des slides 1920 × 1080 rendus par `po-render`.
- [`ecran-web.jpg`](ecran-web.jpg) : l'écran Web dans un navigateur.

## Ce que ces chiffres ne disent pas

- **La toute première requête, à froid, n'est pas comparée.** Elle dépend surtout du cache disque
  de Windows, que rien ne contrôle ici. Selon l'état de ce cache, la même requête « grâce » a pris
  4,6 s en Rust juste après une compilation, puis 75 ms à l'essai suivant. En 2.8, elle a pris
  1,2 s au premier essai. Une comparaison à froid contrôlée reste à faire en phase 1 : vider le
  cache, puis lancer la 2.8 et la 3.0 dans les mêmes conditions.
- **La recherche par sous-chaîne reste lente : 2 à 3 s**, en Rust comme en 2.8. Elle parcourt les
  568 000 paragraphes. La piste pour la phase 1 est un index FTS5 trigramme, ajouté à côté de
  l'index actuel sans rien changer aux données. À mesurer avant de décider.
- **Le temps d'une image à l'écran n'est pas mesuré**, puisqu'aucune fenêtre ne doit s'ouvrir.
  Le travail d'egui par image prend 0,44 ms (médiane). Le « rendu GPU et lecture » de 234 ms est
  le coût de la capture hors écran (copie du GPU vers la mémoire), pas celui d'une image affichée.
  Il faudra le vérifier sur le poste Intel UHD 620 avec une vraie fenêtre, quand vous le voudrez.
- **Le texte du slide long est coupé à 280 caractères** pour la mesure (d'où « SES É » à la fin
  de [`slide-long.png`](slide-long.png)). Le moteur, lui, ne coupe rien.
- **Le Web est mesuré en local** (127.0.0.1). Sur le réseau de la salle, il faut ajouter la
  latence du Wi-Fi ou du câble.

## Problèmes rencontrés et solutions retenues

- **SQLite et `cl.exe` (D8050).** Lancé par Cargo, le compilateur C de Visual Studio 2026 échoue
  sur ce poste quand il doit écrire les informations de débogage. Elles sont désactivées pour
  `libsqlite3-sys` seulement, dans le `Cargo.toml` de l'espace de travail.
- **Le module natif absent du dossier installé.** Le `project_on_core` de la version installée
  n'a pas de `__init__.py`. Il a fallu extraire le paquet
  `build/native/project_on_core-*.whl` pour mesurer la 2.8 dans ses vraies conditions. Ce
  problème concerne l'installation de la 2.8 ; il n'a pas été corrigé ici (la 2.8 ne reçoit plus
  d'évolutions).
- **egui 0.37** : les panneaux s'écrivent `egui::Panel::top/left/right(…)` et non plus
  `TopBottomPanel`/`SidePanel`.

## Refaire les mesures

Toujours sur une **copie** de la base :

```powershell
cd project-on-rs
cargo build --release -p po-mesures
.\target\release\po-mesures.exe tout <copie\project_on.db> target\phase0
.\target\release\po-mesures.exe demarrage <copie\project_on.db>
```

Pour la 2.8 (depuis la racine du dépôt, avec le paquet du module natif extrait dans un dossier) :

```powershell
python project-on-rs\docs\phase0\bench_py.py <copie\project_on.db> sortie.json <dossier du module natif>
```

Les chiffres bruts sont dans [`mesures.json`](mesures.json) (mesure de référence),
[`mesures-cache-chaud.json`](mesures-cache-chaud.json) (la même mesure, relancée) et
[`mesures-python-2.8.json`](mesures-python-2.8.json).

## Suite proposée : la phase 1 (fondations)

Elle crée les crates `po-core` et `po-settings` et complète `po-text` et `po-db`. Le module
`project_on_core` de la 2.8 devient une simple enveloppe de `po-text`. Elle est vérifiée par des
**tests dorés** : la 2.8 produit des résultats de référence sur la vraie base (recherches,
découpages, références bibliques, aller-retour des réglages), et le Rust doit donner les mêmes.
S'y ajoutent les deux points laissés ouverts ici : la comparaison de la recherche à froid et
l'évaluation de l'index trigramme. Le détail est au § 8 de l'audit.
