# Project-On 3.0.0

**Entièrement réécrit en Rust, avec un nouveau design** 🦀 — plus rapide, dessiné par la carte graphique, et un design choisi qui sert sur toutes les sorties. La 3.0 remplace la 2.x et reprend sa base, ses playlists et ses réglages.

## Nouveau design

- **Bleu nuit et or**, en relief doux : cartes posées sur un fond en dégradé, boutons qui s'éclairent au survol, Aperçu et Direct entourés d'une lueur verte et rouge.
- **Réglages refaits** : des rubriques (Projection, Slides, Église, Sorties HDMI, OBS, Raccourcis, Entretien, Général), un **aperçu en direct** de la projection avant même d'enregistrer, les **fonds fournis en vignettes** à cliquer, et une vraie sélection d'image (logo, photos, fonds) avec sa vignette.
- **Le logo de Project-On partout** : raccourci du Bureau, barre des tâches, fenêtres, pages Web.

## Projection et sorties

- **Un design pour toutes les sorties** : choisi dans la page Designs, il sert aux écrans Web, à NDI et au HDMI ; la projection de la salle garde le sien.
- **Écrans Web** : salle, diffusion transparente (source navigateur d'OBS), sous-titres, retour de scène ; adresse à copier et QR code.
- **NDI transparent**, **HDMI** sur fond de clé (vert, magenta, bleu) avec marges 16:9, taille et position du texte, mire F8.
- **Designs** : une bibliothèque de designs, lower thirds (L) et sous-titres (S) en direct, « Mes designs ».
- **Sous-titres entiers** : le sous-titre montre tout le texte du slide, comme les autres sorties ; un texte long prend des lignes de plus, puis rétrécit juste ce qu'il faut.
- **Pilotage d'OBS** (obs-websocket 5) : la scène change au direct et au masquage ; le mot de passe de la 2.x est repris.
- Transitions fondu, glissement, zoom, flou et balayage, dessinées par la carte graphique ; projection plein écran même avec un seul écran (Échap ou F5 pour revenir).

## Bibliothèques et culte

- **Bible** : « Gérer les Bibles… » pour installer, télécharger, importer (XML Zefania ou Beblia, JSON) ou supprimer une version.
- **Cantiques** : éditeur, et **import d'un recueil en PDF** (liste cochée, préfixe, aperçu, sans doublon).
- **Playlist** : PowerPoint (chaque slide en image), images, vidéos, sections du déroulé avec l'avance ou le retard en direct, import et export.
- **L'église** : écran d'accueil, orateur du jour, réseaux sociaux avec QR code, **images de citation** (Ctrl+Maj+I : enregistrer, copier pour WhatsApp, projeter), galerie de photos en diaporama.
- **Fiabilité** : reprise après une coupure de courant, contrôle avant culte, sauvegardes et **restauration** (y compris une archive de la 2.8), mise à jour intégrée.

## À savoir

- La 3.0 **remplace la 2.x** sur le poste et travaille sur ses données (base, playlists, réglages) ; faites une sauvegarde avant si vous le souhaitez.
- Pas encore dans la 3.0 : le **fond vidéo** et l'**effet Ken Burns** sur les fonds. Les **miniatures YouTube** sont retirées.
- Les **vidéos** de la playlist demandent FFmpeg installé sur l'ordinateur.

Windows peut afficher un avertissement SmartScreen : « Informations complémentaires », puis « Exécuter quand même ».

SHA-256 : 86f3bb35336f474c79b83146fa6ad3e8f975406d87f794ff8aacc7f4d440edfd
