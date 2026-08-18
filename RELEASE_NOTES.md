# Project-On 1.7.0

Cette mise à jour simplifie radicalement le poste opérateur : la playlist disparaît au profit d'une **projection directe depuis la bibliothèque**. L'interface passe à trois sections (Bibliothèque, Aperçu, barre d'état) et chaque élément d'une liste — verset, strophe, paragraphe de sermon ou d'exposé — se projette immédiatement, en gardant le découpage des textes longs en plusieurs parties navigables.

## Nouveautés de cette version

- **Interface à 3 sections** : Bibliothèque et Aperçu côte à côte, plus de panneau playlist — l'écran est plus large pour les listes et l'aperçu gagne en place.
- **Projection directe** : double-clic, touche Entrée ou bouton « Projeter » sur un verset / paragraphe / strophe — la slide passe immédiatement en direct.
- **Programme de lecture intelligent** : projeter un paragraphe de sermon charge tout le sermon (les flèches suivent le déroulé complet) ; un verset charge le chapitre ; une strophe charge le cantique ; un paragraphe d'exposé charge le chapitre entier. La sélection multiple projette uniquement la sélection.
- **Découpage conservé** : les textes longs restent divisés en slides équilibrées « référence (2/4) », navigables pendant la projection avec les flèches ou les boutons de l'aperçu.
- **Recherche globale projetable** : double-clic sur un résultat de recherche de paragraphe → le sermon d'origine complet est rechargé et démarre au bon paragraphe.
- **Titre du programme en direct** : l'aperçu affiche le nom du sermon/chapitre/cantique en lecture, avec compteur « n / total ».
- **Texte rapide** : un bouton dans l'aperçu permet de projeter immédiatement une annonce ou un texte libre (avec ou sans découpage).
- **Raccourcis épurés** : suppression des raccourcis playlist (Suppr, Ctrl+Z, Ctrl+↑/↓, Ctrl+D) ; documentation mise à jour.
- **Données préservées** : la base de données et les anciennes playlists ne sont ni modifiées ni supprimées.

## Installation

Téléchargez **`ProjectOn_1.7.0_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».
Si l'installeur est bloqué (erreur 4551), utilisez **`ProjectOn_1.7.0_Portable.zip`** : décompressez et lancez `Project-On.exe`.

Windows 10 / 11 (64 bits) · ~500 Mo · fonctionne hors-ligne.

## Crédits

Silhouettes aigle / lion / agneau : game-icons.net (Lorc, Delapouite) — CC BY 3.0.

---

# Project-On 1.6.0

Cette mise à jour fait passer la diffusion OBS de Project-On au niveau professionnel : habillage TV repensé, animation du texte mot à mot, styles indépendants par scène OBS et pilotage de OBS depuis le poste opérateur via WebSocket. Les versions précédentes restent compatible : vos réglages existants sont conservés tels quels.

## Nouveautés de cette version

- **Révélation du texte mot à mot** : nouveau style d'animation « broadcast » où les mots apparaissent en cascade, comme sur les habillages TV. Réglable dans Style OBS → Effets → « Révélation du texte », mis en valeur par les préréglages *Lower Third TV* et *Louange — Impact*.
- **Entrée de bandeau chorégraphiée** : à l'apparition du bandeau, la barre d'accent balaie l'écran, puis le badge source, le texte et la référence arrivent en cascade.
- **Design affiné** : liseré lumineux sur le haut du bandeau, barre d'accent en dégradé deux tons avec halo doux, badge source avec anneau interne, badge référence épuré, reflets et orbes plus discrets.
- **Styles par scène OBS** : créez des styles indépendants (ex. *Louange* plein écran, *Prédication* en lower third discret) dans Style OBS, chacun avec son URL dédiée `?scene=…` à coller dans une source Navigateur. Ajout, renommage, duplication et suppression directement dans le dialogue, avec aperçu en direct par scène.
- **Contrôle OBS (WebSocket)** : Project-On se connecte à OBS (obs-websocket 5.x, aucun réglage OBS requis si sans mot de passe) et peut basculer automatiquement de scène quand vous projetez ou masquez, charger la liste des scènes et créer la source Navigateur Project-On en 1920 × 1080 en un clic. Reconnexion automatique si OBS redémarre.
- **Compatibilité et robustesse** : les anciens fichiers de réglages chargent sans perte ; 91 tests automatisés couvrent l'application, dont les scènes, le protocole WebSocket et la diffusion serveur.

## Installation

Téléchargez **`ProjectOn_1.6.0_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».
Si l'installeur est bloqué (erreur 4551), utilisez **`ProjectOn_1.6.0_Portable.zip`** : décompressez et lancez `Project-On.exe`.

Windows 10 / 11 (64 bits) · ~500 Mo · fonctionne hors-ligne.

## Crédits

Silhouettes aigle / lion / agneau : game-icons.net (Lorc, Delapouite) — CC BY 3.0.

---

# Project-On 1.5.3

Cette mise à jour harmonise toute la typographie de Project-On afin de rendre le poste opérateur plus lisible, plus rapide à parcourir et plus cohérent pendant un service. Elle améliore également la playlist et les principaux dialogues sans modifier la navigation existante ni la taille configurée du texte projeté.

## Nouveautés de cette version

- **Échelle typographique professionnelle** : rôles communs pour les titres, sections, labels, contenus, contrôles, filtres, métadonnées et numéros.
- **Lecture plus confortable** : textes et labels principaux à 14 px, titres de sections à 15 px et titres majeurs à 18–20 px.
- **Informations secondaires compactes** : filtres à 12 px, métadonnées à 11 px et numéros ou badges à 10 px.
- **Tous les onglets harmonisés** : Bible, Cantiques, Prédications, Exposé et Paramètres partagent désormais la même hiérarchie visuelle.
- **Playlist améliorée** : cartes plus lisibles, références mieux séparées, dossiers renforcés et compteurs plus discrets.
- **Dialogues mieux dimensionnés** : projection locale, OBS, import, prévol et À propos profitent de labels cohérents et d'une meilleure utilisation de l'espace.
- **Thèmes clair et sombre contrôlés** : contraste, densité et absence de coupure vérifiés sur les deux apparences.
- **Validation renforcée** : 80 tests automatisés couvrent l'application, la projection, les données, la typographie et la sécurité de l'installateur.

## Installation

Téléchargez **`ProjectOn_1.5.3_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».
Si l'installeur est bloqué (erreur 4551), utilisez **`ProjectOn_1.5.3_Portable.zip`** : décompressez et lancez `Project-On.exe`.

Windows 10 / 11 (64 bits) · ~500 Mo · fonctionne hors-ligne.

## Crédits

Silhouettes aigle / lion / agneau : game-icons.net (Lorc, Delapouite) — CC BY 3.0.
