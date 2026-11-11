# Phase 8 : la bascule vers Project-On 3.0

**Date** : 11 novembre 2026. **État** : la bascule est **prête à être construite, pas faite**.
L'installateur qui remplace la 2.x existe. Il n'a été ni lancé sur votre poste, ni publié, et le
code de la 2.8 est toujours dans le dépôt. Ces trois gestes vous appartiennent (voir la fin).

- **Vérifié** : la version « bascule » compile sans avertissement. Son installateur a été construit
  une fois par Inno Setup, dans un dossier temporaire, pour vérifier le script, puis **supprimé**.
  Aucun fichier capable de remplacer votre 2.8 ne traîne sur le poste.
- **À essayer maintenant** : la **bêta 4** (`installer\Output\Project-On_3.0.0-beta.4_Setup.exe`). Elle
  apporte tout ce qui a été fait depuis la bêta 3 :
  - phase 5 : les écrans Web ;
  - phase 6 : les designs, les lower thirds, les sous-titres, NDI et HDMI ;
  - phase 7 : l'entretien et les réglages.

  Elle s'installe toujours à côté de la 2.8, sur une copie des données.

## Ce que fait la version « bascule »

Elle se construit avec `construire-beta.ps1 -Bascule`. C'est la même régie que la bêta, avec quatre
différences :

| | Bêta | Bascule |
|---|---|---|
| Données | Une **copie** dans `%APPDATA%\Project-On 3 (bêta)` | **Directement** celles de la 2.x, `%APPDATA%\Project-On` (base, playlists, réglages) : rien à copier, rien de perdu |
| Écrans Web | Port 8090 | Port **8080**, celui de la 2.x : les sources OBS réglées sur `http://127.0.0.1:8080/obs` restent bonnes |
| Installation | À côté de la 2.8 (« Project-On 3 beta ») | **À la place** de la 2.x : même identifiant d'application, même dossier, même verrou d'instance (`ProjectOnMutex`) |
| Nom | Project-On 3.0 bêta | Project-On 3.0 |

**Ce qui protège vos données** :
- L'installateur retire les fichiers du **programme** 2.x (Python) mais ne touche jamais à
  `%APPDATA%`. Comme celui de la 2.x, il ne lance jamais l'ancien désinstallateur, qui effaçait la
  base.
- La 3.0 n'applique à la base que des migrations **additives**, et seulement si elle est plus
  ancienne. La 2.8 peut donc la relire si l'on revient en arrière.
- Les réglages s'écrivent comme dans la 2.x (d'un coup, avec une copie `.bak`). Les réglages
  propres à la 3.0 sont dans une section que la 2.x ignore.
- Avant la bascule : « Réglages → Sauvegarder maintenant » dans la bêta, ou une sauvegarde de la
  2.8.

**Revenir en arrière** : réinstaller la 2.8 (`ProjectOn_2.8.0_Setup.exe`), qui reprend la même place
et les mêmes données.

## Avant de basculer : ce qui manque encore

La [liste de parité](../phase7/PARITE.md) compte 16 fonctions de la 2.8 pas encore dans la 3.0. Les
plus visibles dans un culte :
- les **images et vidéos** de la playlist ;
- les **PowerPoint** ;
- les **écrans de l'Église** (accueil, orateur, réseaux, citation, galerie) ;
- l'**éditeur de cantiques** ;
- les **imports** (PDF, Bibles) ;
- le **pilotage d'OBS**.

**Recommandation** : ne basculer qu'une fois ces fonctions faites, ou pour une église qui n'en a pas
besoin. D'ici là, la bêta 4 s'installe à côté de la 2.8 et permet d'essayer tout le reste en vrai.

## L'essai sur le vrai vidéoprojecteur

À faire ensemble, sur la bêta 4 (ou l'installateur de la bascule sur un poste d'essai) :

| | Faire | Attendu |
|---|---|---|
| ☐ | Brancher le vidéoprojecteur, lancer, F5 | La projection s'ouvre sur l'écran de la salle, plein écran, sans curseur |
| ☐ | Un sermon, F2, Page suivante (télécommande) | Texte net, transitions fluides ; l'identification de Branham est lisible |
| ☐ | B (masquer), puis B | Le texte disparaît en fondu, le fond reste ; il revient |
| ☐ | Clic droit sur « Projection » → un 2ᵉ écran → « Diffusion » | Le bandeau sur la couleur de clé, prêt pour le mélangeur ; F8 : la mire |
| ☐ | OBS : une source navigateur sur `/obs` (8090 en bêta, 8080 après la bascule) | Le bandeau sur fond transparent ; L : le lower third entre et sort |
| ☐ | Designs → « Source NDI » | La source « Project-On Diffusion » apparaît dans vMix ou OBS (plugin NDI), avec transparence |
| ☐ | S, puis → sur un long paragraphe | Les sous-titres avancent, la salle garde le paragraphe entier |
| ☐ | Une tablette : Web → « Ouvrir aux appareils du réseau », scanner le QR code, « Retour scène » | Le slide, le suivant, l'heure ; accepter le pare-feu de Windows (réseau privé) |
| ☐ | Débrancher le câble réseau de la tablette, puis le rebrancher | Le point orange dans la régie, puis l'écran revient seul |
| ☐ | Fermer Project-On par le gestionnaire des tâches pendant le direct, relancer | « Reprendre le direct » remet le même slide |
| ☐ | Ctrl+Shift+D | Le contrôle avant culte est tout vert |

## Les deux décisions qui vous reviennent

1. **Retirer le code Python de la 2.8 du dépôt**, après une étiquette `v2.8.x` qui le garde dans
   l'historique Git. C'est réversible par Git, mais cela change ce que voient les autres
   développeurs. À faire seulement une fois la bascule décidée.
2. **Publier Project-On 3.0** : l'installateur de la bascule sur la page de téléchargement, ou les
   mises à jour. C'est visible des églises qui utilisent Project-On.

Rien de cela n'a été fait.

## L'installateur définitif (11 novembre 2026, soir)

À votre demande, l'installateur **définitif** de Project-On 3.0 (pas une bêta) est construit :
`installer\Output\ProjectOn_3.0.0_Setup.exe`, par `construire-beta.ps1 -Bascule`, version
`3.0.0`. Il n'a **pas** été lancé ni publié, et le code de la 2.8 reste dans le dépôt.

**Attention : lancer ce fichier remplace la 2.8 sur le poste** (même place, mêmes données). Retour
à la 2.8 : réinstaller `ProjectOn_2.8.0_Setup.exe`.

**Mis à jour le 11 novembre 2026 (nuit)** : les 8 fonctions qui restaient sont faites (image de citation,
galerie, PowerPoint, imports PDF et Bibles, restauration d'une sauvegarde, pilotage d'OBS, réglages
détaillés du bandeau et du HDMI, mise à jour), et l'installateur est reconstruit avec elles. Reste,
hors de cette liste : le fond vidéo et l'effet Ken Burns (voir la
[liste de parité](../phase7/PARITE.md)). Ce qui n'a pas pu être essayé sur ce poste : les moteurs
PowerPoint et LibreOffice (aucun des deux n'y est installé), une vraie connexion à OBS, une vraie
mise à jour (rien n'est publié).

Ce qu'il apporte de plus que la bêta 6 :
- **un seul design pour les sorties** : choisi dans la page Designs (« Utiliser pour Web, NDI,
  HDMI »), il habille l'écran Web Diffusion, la source NDI et les sorties HDMI ; la projection de la
  salle garde le sien ;
- la **source NDI** prend n'importe quel design (bandeau, ou texte d'un design de slide), toujours
  sur fond transparent, avec le lower third ;
- le bouton **Web** : « Copier » marche (le presse-papiers manquait dans la construction), les
  adresses se sélectionnent, « Ouvrir » les ouvre dans le navigateur ;
- les **écrans Web** ouverts dans une fenêtre encore cachée (source OBS pas encore affichée,
  téléviseur qui démarre) ne restent plus illisibles ;
- l'installation pour tous les utilisateurs autorise Project-On dans le **pare-feu** (réseaux
  privés), pour les tablettes, les téléviseurs et NDI ;
- plus aucune mention « bêta » dans la fenêtre.

FFmpeg (vidéos) n'est pas livré avec : sur un autre poste, les vidéos de la playlist demandent
FFmpeg installé (il l'est sur celui-ci).

**Votre décision (11 novembre 2026)** : garder la 2.8, son code comme son installation, et ne rien
publier tant que les 16 fonctions restantes de la [liste de parité](../phase7/PARITE.md) ne sont pas
faites. La question vous sera reposée à ce moment-là.
