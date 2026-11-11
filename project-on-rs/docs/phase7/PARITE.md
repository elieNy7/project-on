# Liste de parité 2.8 → 3.0, fonction par fonction

Le livrable de la phase 7 (audit, § 8) : chaque fonction de la 2.8, et où elle en est dans la 3.0.
À cocher avec vous avant la bascule (phase 8). État au 11 novembre 2026, après la phase 7.

**Légende** :
- ✅ dans la 3.0, vérifiée ;
- 🟡 dans la 3.0, en partie (ce qui manque est noté) ;
- ⏳ pas encore dans la 3.0 ;
- ✖ retirée volontairement (décision du 9 novembre).

## Bibliothèques et projection

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Bible : livres, chapitres, versets, plusieurs traductions, référence tapée (« Jean 3:16 ») | ✅ | Phases 1 et 3 |
| Cantiques : liste, strophes, refrain répété | ✅ | Phases 1 et 3 |
| Prédications : liste, filtres, paragraphes, recherche dans un sermon | ✅ | Phases 1 et 3 |
| Exposé des Sept Âges, livres et brochures | ✅ | Phase 3 |
| Recherche globale (Ctrl+K) | ✅ | Phase 3, plus rapide que la 2.8 |
| Aperçu / Direct, F2, slides suivant et précédent, Début / Fin | ✅ | Phase 3 |
| Masquer le texte (B) | ✅ | Phase 3 ; aussi sur les écrans Web (phase 5) |
| Projection plein écran, choix de l'écran, plusieurs écrans | ✅ | Phase 3, sur la carte graphique |
| Mise en page de la projection (taille, coupures, référence, filet) | ✅ | Phase 2 : identique à la 2.8 sur 2 208 slides |
| Transitions (fondu, glissement, zoom, flou, balayage) | ✅ | Phases 2 et 3 |
| Fond : couleur, dégradé, image, assombrissement | ✅ | Phase 2 |
| Fond vidéo, effet Ken Burns | ⏳ | Avec les vidéos |
| Identification de Branham (4 styles) | ✅ | Phase 2 (couche 1) |
| Badge « orateur du jour » sur les slides | ✖ | Retiré (décision 4) |
| Miniatures YouTube | ✖ | Retirées (couche 1) |

## Playlist et culte

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Playlists : créer, renommer, supprimer, ordonner, glisser-déposer, sélection multiple | ✅ | Phase 4 |
| Dupliquer, copier, déplacer vers une autre playlist ; Ctrl+Z | ✅ | Phase 4 |
| Ajouter un verset, une plage, un chapitre, un cantique, un paragraphe entier | ✅ | Phase 4 |
| Slide saisi | ✅ | Phase 4 |
| Déroulé du culte : sections, heures, avance / retard | ✅ | Phase 4 |
| Section suivante (Ctrl+Alt+N) | ✅ | Phase 7 |
| Images et vidéos dans une playlist | 🟡 | Les **images** se projettent à leur place, en entier sur du noir, et le fond propre d'un élément de texte le suit (identique à la 2.8 : 30 playlists, 0 différence) ; les **vidéos** restent à faire |
| PowerPoint dans une playlist | ⏳ | Médias |
| Import / export d'une playlist (fichier) | ⏳ | |
| Diaporama d'un dossier d'images | ⏳ | Médias |
| Historique du culte (Ctrl+H), tableur, SRT | ✅ | Phase 7 : un fichier par jour, exports CSV et SRT dans « Documents\Project-On exports » ; le rapport imprimable de la 2.8 reste à faire |

## Diffusion

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Page OBS `/obs` (bandeau sur fond transparent) | ✅ | Phase 5, et l'adresse `/obs` est conservée |
| Réglages du bandeau OBS (position, police, filet, animation, dispositions) | ✅ | Phases 5 et 6, lus depuis vos réglages |
| Sortie NDI du bandeau | ✅ | Phase 6, avec le lower third et la transparence |
| Sortie HDMI vers un mélangeur (couleur de clé) | 🟡 | Phase 6 ; letterbox, taille du texte et décalage avec les réglages |
| Mire HDMI (F8) | ✅ | Phase 6 |
| Pilotage d'OBS (WebSocket : scènes, enregistrement) | ⏳ | |

## L'Église

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Écran d'accueil (Ctrl+Shift+W) | ⏳ | |
| Écran de l'orateur du jour (Ctrl+Shift+P) | ⏳ | |
| Écran « Réseaux sociaux » (Ctrl+Shift+R) | ⏳ | |
| Image de citation du direct (Ctrl+Shift+I) | ⏳ | |
| Galerie de photos | ⏳ | |
| Profil de l'église (nom, logo, réseaux) | ⏳ | |

## Données et entretien

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Base SQLite de la 2.x, sans conversion | ✅ | Phase 1 |
| Éditeur de cantiques | ⏳ | |
| Import de Bibles | ⏳ | |
| Import PDF (sermons, cantiques) | ⏳ | |
| Sauvegardes de la base | 🟡 | Phase 7 : base et réglages, copie cohérente, les 10 dernières gardées ; la restauration et l'archive avec médias de la 2.8 restent à faire |
| Reprise après coupure (le direct survit à un arrêt brutal) | ✅ | Phase 7, avec le masquage |
| Contrôle avant culte (Ctrl+Shift+D) | ✅ | Phase 7 : base, écrans, polices, écrans Web, NDI, sauvegarde, fichiers de la playlist |
| Mise à jour de l'application | ⏳ | Avec l'installateur de la bascule |
| Mode PC modeste | ✅ | Phase 7 : sans transitions ni aperçus de designs |

## Réglages

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Lecture de `settings.json` de la 2.x, mêmes règles | ✅ | Phase 1 |
| Page Réglages (projection, apparence, raccourcis, découpage, OBS, HDMI, église) | 🟡 | Phase 7 : projection (texte, fond, transitions, écran), identification, découpage, couleur de clé HDMI, raccourcis, mode PC modeste, entretien. Restent : réglages détaillés du bandeau OBS (repris de la 2.x en attendant), HDMI (letterbox, taille), église |
| Raccourcis personnalisés de la 2.x | ✅ | Lus et appliqués (phase 3), réglables dans la page Réglages (phase 7) |
