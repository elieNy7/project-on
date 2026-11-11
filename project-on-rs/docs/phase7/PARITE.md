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
| Projection plein écran, choix de l'écran, plusieurs écrans | ✅ | Phase 3, sur la carte graphique ; **plein écran comme PowerPoint même avec un seul écran** (→ ← Espace, B, Échap ou F5 pour revenir à la régie) |
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
| Images et vidéos dans une playlist | ✅ | Images en entier sur du noir ; **vidéos** lues par FFmpeg (repris de Pgraphics) dans la régie et la projection, avec le son : pause, recommencer, boucle, volume (identique à la 2.8 : 30 playlists, 0 différence). Pas encore sur les écrans Web, NDI ni HDMI ; FFmpeg à livrer avec l'installateur à la publication |
| PowerPoint dans une playlist | ✅ | 3.0 : chaque slide devient une image 1920 × 1080, projetée à sa place dans la playlist ; rendu par Microsoft PowerPoint s'il est installé, sinon LibreOffice (PDF, dont Windows rend les pages), comme la 2.8. Rendu en arrière-plan dès que la playlist s'affiche (« PowerPoint · 12 slides », « préparation… ») ; le cache est celui de la 2.8 : une présentation déjà rendue par la 2.8 se projette aussitôt. Ce poste n'a ni PowerPoint ni LibreOffice : vérifiés ici le cache, la playlist et le rendu des pages PDF par Windows, pas les deux moteurs eux-mêmes |
| Import / export d'une playlist (fichier) | ✅ | Au format de la 2.8 (archive avec `manifest.json` et les images, ancien JSON lu aussi), dans « Documents\Project-On playlists » |
| Diaporama d'un dossier d'images | ✅ | Page Médias (un dossier, ses images et vidéos dans l'ordre des noms) ou bouton « Diaporama » d'une playlist ; une vidéo donne le tempo (on passe au suivant à sa fin), une image dure sa durée (8 s par défaut) ; en boucle ; à l'arrêt le direct d'avant revient, une flèche rend la main comme dans la 2.8. Les PowerPoint attendent |
| Historique du culte (Ctrl+H), tableur, SRT | ✅ | Phase 7 : un fichier par jour, exports CSV et SRT dans « Documents\Project-On exports » ; le rapport imprimable de la 2.8 reste à faire |

## Diffusion

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Page OBS `/obs` (bandeau sur fond transparent) | ✅ | Phase 5, et l'adresse `/obs` est conservée |
| Réglages du bandeau OBS (position, police, filet, animation, dispositions) | ✅ | Phases 5 et 6, lus depuis vos réglages ; 3.0 : tous réglables dans Designs → un bandeau de « Mes designs » → Personnaliser → « Réglages détaillés » (graisse, taille minimale, espacement, interligne, lignes, ombre, référence et filet, bande, arrondi, marges, largeur, position, zone de sécurité, décalages, transition) |
| Sortie NDI du bandeau | ✅ | Phase 6, avec le lower third et la transparence ; depuis la 3.0, **n'importe quel design** de la page Designs : un bandeau, ou un design de slide dont le texte est posé sur un fond transparent |
| Un seul design pour les sorties | ✅ | 3.0 : « Utiliser pour Web, NDI, HDMI » dans la page Designs habille l'écran Web Diffusion (et `/obs`), la source NDI et les sorties HDMI ; un design de slide habille aussi les écrans Web Salle. La projection de la salle garde son propre design. Le choix (avec le lower third et les sous-titres) est gardé d'un lancement à l'autre |
| Sortie HDMI vers un mélangeur (couleur de clé) | ✅ | Phase 6, et 3.0 : Réglages → Diffusion : marges 16:9 (letterbox) à la couleur de clé, taille du texte (60 à 180 %), décalage vertical, réouverture au démarrage sur l'écran choisi. Le style propre au HDMI de la 2.8 est remplacé par le design unique des sorties (page Designs) |
| Mire HDMI (F8) | ✅ | Phase 6 |
| Pilotage d'OBS (WebSocket : scènes, enregistrement) | ✅ | 3.0 : Réglages → Pilotage d'OBS (obs-websocket 5, comme la 2.8) : adresse, port, mot de passe chiffré par Windows (celui de la 2.8 est relu), scène du direct et scène du texte masqué choisies dans la liste des scènes d'OBS, « Créer dans OBS » la source navigateur Project-On (écran Diffusion) ; reconnexion toutes les 10 s. La 3.0 ne change de scène que quand la scène voulue change. La 2.8 ne pilotait pas l'enregistrement |

## L'Église

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Écran d'accueil (Ctrl+Shift+W) | ✅ | Logo, nom, devise, horaires, orateur du jour, réseaux, QR code ; le haut se resserre pour ne jamais toucher les réseaux ; projeté comme une image, comme la 2.8 (Web, NDI, HDMI compris) |
| Écran de l'orateur du jour (Ctrl+Shift+P) | ✅ | Le pasteur, ou l'invité du jour (le pasteur en médaillon) ; photo, titre, nom, message |
| Écran « Réseaux sociaux » (Ctrl+Shift+R) | ✅ | Chaque compte en grand avec sa pastille, QR code « Scannez » |
| Image de citation du direct (Ctrl+Shift+I) | ✅ | 3.0 : le slide au direct en image aux couleurs de l'église, les 8 modèles et 3 formats de la 2.8 (carré, story, paysage) ; aperçu qui suit la frappe, « Enregistrer l'image… » (Documents\Project-On images), « Copier l'image » (à coller dans WhatsApp), et en plus « Projeter » ; le modèle choisi reste celui du profil |
| Galerie de photos | ✅ | 3.0 : Réglages → Profil de l'église → « Photos de l'église » : vignettes (décodées sans figer la régie), « Ajouter des photos… » (copiées dans les données, sans doublon, comme la 2.8), ✕ pour retirer ; fond du modèle « Photo » des images de citation, et en plus « Projeter en diaporama » |
| Profil de l'église (nom, logo, réseaux) | ✅ | Réglages → Profil de l'église ; lu et réécrit au format de la 2.x (les champs que la 3.0 ne connaît pas sont gardés) |

## Données et entretien

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Base SQLite de la 2.x, sans conversion | ✅ | Phase 1 |
| Éditeur de cantiques | ✅ | Créer, modifier, supprimer (avec confirmation) dans la page Cantiques : titre, numéro, langue, paroles en une zone (une ligne vide entre les strophes), bouton « Refrain », découpage reconnu en direct ; mêmes règles que la 2.8, vérifiées sur ses propres résultats |
| Import de Bibles | ✅ | 3.0 : page Bible → « Gérer les Bibles… » : les traductions installées (et leur suppression, sans réinstallation automatique), les Bibles fournies (livrées avec l'installateur), le catalogue des Bibles du domaine public de la 2.8 à télécharger, et l'import d'un fichier XML (Zefania, Beblia) ou JSON (scrollmapper, Project-On), .gz compris ; installation d'un bloc, dans un fil à part |
| Import PDF (sermons, cantiques) | ✅ | 3.0 : Cantiques → « Importer un PDF… » : le recueil lu en Rust (crate po-pdf, colonnes et écarts entre strophes comme la 2.8), liste cochée, préfixe et numéro de départ, aperçu, sans doublon de titre. Les règles de la 2.8 sont reprises à l'identique (mêmes lignes → mêmes cantiques) ; sur les recueils du dépôt, 679 cantiques sur 695 identiques à ceux de la 2.8 (Pene Na Yo 150/150, Cantiques-Ins 300/304, Crois seulement 229/241, les écarts surtout dans les coupures de strophes). Non repris : la lecture des PDF scannés (OCR) et l'ancien lecteur de secours, qui ne lisaient pas mieux « Chants de Victoire » ni le recueil swahili. La 2.8 n'importait pas de sermons en PDF |
| Sauvegardes de la base | ✅ | Phase 7 : base et réglages, copie cohérente, les 10 dernières gardées. **Restauration** (3.0) : une sauvegarde de la liste, ou une archive complète de la 2.8 (`.zip` : base, médias, réglages, vérifiée comme la 2.8 le faisait : manifeste, tailles, empreintes) ; appliquée au démarrage suivant, après une sauvegarde de l'état actuel, donc réversible. Mieux que la 2.8, qui reconstruisait un profil à côté à rouvrir à la main. La création d'une archive complète avec médias reste à faire |
| Reprise après coupure (le direct survit à un arrêt brutal) | ✅ | Phase 7, avec le masquage |
| Contrôle avant culte (Ctrl+Shift+D) | ✅ | Phase 7 : base, écrans, polices, écrans Web, NDI, sauvegarde, fichiers de la playlist |
| Mise à jour de l'application | ✅ | 3.0 : Réglages → Mise à jour (comme la 2.8) : les versions publiées sur GitHub (paratech-web, `project-on-v…`), « Rechercher une mise à jour », recherche discrète au démarrage (réglage de la 2.x), téléchargement vérifié (HTTPS GitHub seulement, taille, SHA-256 des notes) puis « Installer maintenant ». La bêta n'installe jamais (elle ouvre la page de la version) : l'installateur remplacerait la 2.8. Rien n'est publié : la recherche ne trouve que la 2.8 |
| Mode PC modeste | ✅ | Phase 7 : sans transitions ni aperçus de designs |

## Réglages

| Fonction de la 2.8 | 3.0 | Où, ou ce qui manque |
|---|---|---|
| Lecture de `settings.json` de la 2.x, mêmes règles | ✅ | Phase 1 |
| Page Réglages (projection, apparence, raccourcis, découpage, OBS, HDMI, église) | ✅ | Phase 7 : projection (texte, fond, transitions, écran), identification, découpage, couleur de clé HDMI, raccourcis, mode PC modeste, entretien ; 3.0 : profil de l'église et ses photos, HDMI (letterbox, taille, décalage, réouverture), pilotage d'OBS ; le bandeau OBS se règle dans la page Designs |
| Raccourcis personnalisés de la 2.x | ✅ | Lus et appliqués (phase 3), réglables dans la page Réglages (phase 7) |
