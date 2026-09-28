# Project-On 2.7.0

**Une régie professionnelle** ⛪ — Bibles libres intégrées, déroulé du culte avec avance/retard, fonds animés, éditeur de cantiques, historique et export pour le montage vidéo, reprise après coupure de courant, mise à jour intégrée… et une sortie HDMI en **sous-titre OBS**.

## Nouveautés du culte

- **7 Bibles libres fournies** 📖 : Martin 1744, Crampon 1923, Perret-Gentil, Bovet-Bonnet, King James, Berean Standard Bible et Reina-Valera 1909, installées automatiquement (sans Internet). **Réglages → Bibles** : 15 autres Bibles du domaine public à télécharger (Darby, Synodale, Oltramare, Stapfer, ASV, créole haïtien, malgache…), et **import d'un fichier** (Zefania XML, XML « Beblia », JSON) pour une version dont l'église a les droits — lingala, swahili, tshiluba… Retirer une Bible est possible à tout moment.
- **Déroulé du culte** ⏱️ : sous les slides d'une playlist, des sections (Louange, Annonces, Prédication…) avec leur durée, l'heure de début prévue et les heures de chaque section. Pendant le culte : section en cours, temps restant, **avance ou retard** en direct, fin estimée. Une section liée à un slide démarre toute seule quand ce slide passe en direct.
- **Fonds animés** 🎞️ : une vidéo courte jouée en boucle, sans son, derrière les paroles et les versets (Réglages → Projection locale → Type de fond → Vidéo en boucle), ou un fond vidéo propre à un slide de playlist.
- **Éditeur de cantiques** ✏️ : bouton crayon de l'onglet Cantiques → Nouveau / Modifier. Strophes séparées par une ligne vide, refrain marqué d'un clic, aperçu du découpage.
- **Refrain répété automatiquement** : projeter tout le cantique donne strophe 1 → refrain → strophe 2 → refrain… (désactivable).
- **Import OpenLyrics, OpenSong et CCLI SongSelect** 🎵 : Cantiques → Importer, plusieurs fichiers à la fois, refrains reconnus, doublons ignorés.
- **Historique du culte** 🗒️ (Ctrl+H ou bouton « Historique » du déroulé) : tout ce qui est passé en direct, heure par heure. Exports : rapport de culte (.txt), tableur (.csv), **sous-titres .srt** calés sur l'heure de début de la vidéo, et **images transparentes** au style OBS + minutage pour DaVinci Resolve, Premiere ou CapCut.
- **Profil de l'église** 🏛️ : nom, titre d'accueil, devise, horaires des cultes, logo, couleurs et police. **Écran d'accueil** projeté avant le culte (Ctrl+Shift+W) et **images de citations** à partager (carré, story, paysage) par clic droit sur un verset ou un paragraphe (Ctrl+Shift+I pour le slide en direct).
- **Réseaux sociaux de l'église** 📱 : Facebook, YouTube, Instagram, WhatsApp, TikTok, X, Telegram, site web, e-mail et téléphone. Ils s'affichent sur l'écran d'accueil et les images de citations (au choix), et sur un nouvel **écran « Réseaux sociaux »** de fin de culte (Ctrl+Shift+R), avec un **QR code** à scanner vers le compte choisi. Chaque réseau apparaît avec son **vrai logo** aux couleurs officielles (Facebook, YouTube, Instagram, WhatsApp, TikTok, X, Telegram), aussi au centre du QR code.
- **Personnalisation des visuels** 🎨 : fond en dégradé, couleur unie ou **photo de l'église** assombrie à volonté ; style des citations classique, minimal ou encadré ; aperçu en direct ; export des visuels en PNG (accueil, réseaux sociaux paysage et carré) pour publier ou imprimer.
- **Raccourcis configurables** ⌨️ (Réglages → Raccourcis) : une touche par action, conflits signalés. **Télécommande de présentation** reconnue (Page suivante / Page précédente) et **Stream Deck** via l'action « Raccourci clavier ».

## Fiabilité

- **Reprise après coupure de courant** 🔌 : si Project-On s'arrête brutalement, il propose au redémarrage de reprendre exactement le programme et la slide où vous étiez.
- **Contrôle avant culte automatique** au démarrage : base, disque, écrans, OBS, NDI et HDMI ; un message discret n'apparaît qu'en cas de problème.
- **Mode PC modeste** (Réglages → Apparence) : sans transitions, animation mot à mot, zoom lent, fond vidéo, flou ni effet Mica — fluide sur un petit ordinateur.
- **Mise à jour intégrée** (Réglages → Mise à jour) : la nouvelle version est détectée quand Internet est disponible, téléchargée depuis GitHub (taille et empreinte vérifiées) puis installée en gardant vos données.

## Sortie HDMI, textes et cantiques
- **Sortie HDMI en sous-titre OBS** 📺 : la sortie HDMI vers le mélangeur (ATEM, Roland…) affiche le texte en sous-titre, exactement comme le mode « Sous-titre » de la page OBS.
- **Disposition HDMI « Sous-titre OBS »** « Sous-titre OBS »** par défaut. Réglages → Sortie HDMI → **Disposition** permet aussi de suivre la disposition choisie pour OBS, ou d'imposer bandeau bas, panneau latéral ou carte focus. Police, couleurs, contour et animation restent ceux de la page OBS.
- **Style du texte propre à la sortie HDMI** 🎨 : décochez « Utiliser le style de la page OBS » pour régler le HDMI indépendamment d'OBS, avec les mêmes familles de réglages — **police** (famille, épaisseur, casse, espacement, hauteur de ligne), **tailles et référence** (taille du texte et de la référence, style de référence, ajustement automatique, lignes au maximum), **position** (bas, haut ou centre, alignement, marges, largeur), **arrière-plan** (bandeau, couleur, dégradé, coins arrondis), **couleurs et habillage** (texte, référence, barre d'accent, pastille de source, accent personnalisé), **effets** (ombre, contour des lettres) et **animation d'entrée** (style, mot à mot, direction, durée).
- **Préréglages retirés** : les boutons de préréglages disparaissent de toutes les sections des Réglages (dont « Modes & style OBS ») ; chaque réglage se fait directement, et « Réinitialiser » ramène les valeurs par défaut.
- **Cantiques deux lignes par slide** 🎵 : chaque strophe est projetée deux lignes à la fois (« Strophe 2 (1/3) », « (2/3) »…), sans jamais couper un vers ; les flèches avancent de deux lignes en deux lignes. Nombre de lignes par slide réglable (1 à 12, 2 par défaut).
- **Découpage des paragraphes longs amélioré** ✂️ : les alinéas et retours à la ligne sont conservés (ils étaient collés en un seul bloc) ; la coupure se fait d'abord entre alinéas, puis en fin de phrase — plus jamais après « M. », « St. » ou « v. » —, puis aux virgules ; toutes les parties ont une longueur proche.
- **Nouvelle section Réglages → Découpage des textes** : activer/désactiver pour les textes et pour les cantiques, longueur maximale d'une partie (120 à 800 caractères), lignes par slide des cantiques, couplets, numéro de partie « (1/2) » affiché ou non, avec un aperçu immédiat du découpage.
- **Aperçu HDMI fidèle** : l'aperçu des réglages utilise exactement la configuration de la sortie (il pouvait afficher le plein écran OBS alors que l'écran HDMI montrait un bandeau).

## Corrections

- **Sortie HDMI beaucoup plus rapide** : chaque changement de verset ou de strophe demandait plus d'une seconde de calcul du texte, pendant laquelle la régie ne répondait plus (et l'animation d'entrée saccadait). La composition prend maintenant quelques dizaines de millisecondes ; la sortie NDI en profite aussi.
- **Plus de « flash » du texte** : avec l'animation mot à mot, le texte complet apparaissait une fraction de seconde avant de s'animer.
- **Câble HDMI débranché puis rebranché** : la sortie retourne d'elle-même sur l'écran du mélangeur au lieu de rester sur l'écran de la régie.
- La sortie HDMI suit le Direct plus vite (vérification toutes les 100 ms au lieu de 250 ms).
- **Installeur** : installation en mode 64 bits (« Program Files » et non « Program Files (x86) » pour une installation pour tous les utilisateurs) et Windows 10 minimum vérifié dès le lancement. Une mise à niveau garde le dossier existant, la base, les playlists et les réglages.

## Installation

Téléchargez **`ProjectOn_2.7.0_Setup.exe`** et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

## Rappel : Project-On 2.6.1

**Correctif du démarrage** 🚀 — après l'installation de la 2.6.0 par-dessus une version existante, Project-On pouvait rester figé sur l'écran de démarrage (« Ne répond pas »), puis se fermer, et recommencer au lancement suivant.

### Corrections

- **Démarrage débloqué** : la mise à jour du contenu (sermons SHP, livres) appliquée à la base existante utilisait un contrôle de doublons extrêmement lent — plus de dix minutes sur une base complète, si bien qu'elle n'aboutissait jamais. Elle prend désormais **moins d'une minute**, une seule fois, et n'est plus refaite ensuite.
- **Plus de « Ne répond pas »** : cette mise à jour et les vérifications de la base tournent en arrière-plan ; l'écran de démarrage reste animé et indique « Mise à jour du contenu (environ une minute)… ».
- **Disque préservé** : chaque tentative interrompue laissait une copie complète de la base (≈ 400 Mo) dans le dossier de données. Ces copies sont supprimées ; seule la sauvegarde de la dernière mise à jour est gardée.
- La base de contenu fournie avec l'application est lue sans écrire de fichiers dans le dossier d'installation.

### Installation

Téléchargez **`ProjectOn_2.6.1_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés. Si Project-On est resté ouvert et figé, fermez-le d'abord (Gestionnaire des tâches → Project-On → Fin de tâche).

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

## Rappel : nouveautés de la 2.6.0

**Une régie repensée, façon Windows 11** 🪟 — Project-On change de moteur (PySide6, Qt officiel) et d'allure : un menu latéral, une barre de commandes avec l'état de toutes les sorties, une **recherche globale** et, surtout, deux moniteurs côte à côte : l'**Aperçu**, où l'on prépare, et le **Direct**, ce que voit l'assemblée. Rien ne part plus en direct par erreur, et le double-clic garde ses habitudes.

### Nouveautés

- **Aperçu et Direct** 🎬 : un clic sur un verset, une strophe, un paragraphe, un média ou un élément de playlist le **prépare** dans l'Aperçu, avec le rendu exact de la projection. **F2** (ou « Envoyer au direct ») le projette — exactement ce qui a été préparé, même si vous avez changé de chapitre entre-temps. Le double-clic et Entrée projettent toujours immédiatement ; les flèches font avancer le Direct.
- **Voyant d'antenne** 🔴 : le moniteur Direct affiche **● EN DIRECT**, **MASQUÉ** ou **VIDE** selon ce qui part réellement vers la projection, OBS, le HDMI et le NDI.
- **Recherche globale** 🔎 : **Ctrl+K**, puis tapez « Jean 3:16 », « 1 co 13 », « Ps 23 » ou quelques mots (avec ou sans accents). Résultats groupés — Bible, prédications, exposés, médias, playlists — en moins de 0,2 s pour les premiers. Entrée ouvre le résultat dans son onglet ; un verset arrive prêt dans l'Aperçu.
- **Nouvelle interface Windows 11** 🪟 : menu latéral repliable, barre de commandes avec l'état de la projection, d'OBS, du HDMI et du NDI (un clic ouvre le réglage correspondant), police Segoe UI Variable, effet **Mica**, barre de titre sombre ou claire assortie au thème.
- **Une seule page Réglages** ⚙️ : les six fenêtres de réglages deviennent des sections d'une même page, à côté des moniteurs. Chaque changement s'applique et s'enregistre **aussitôt**, sans bouton. Tous les écrans ont été redessinés : plus de texte tronqué ni de défilement horizontal.
- **Échap protégé** 🛡️ : dans un champ de saisie (recherches, textes, nombres), Échap ne ferme plus la projection.
- **Sermons SHP fidèles au PDF** 📖 : les 1 209 sermons ont été réimportés depuis les recueils annuels. Chaque alinéa et chaque lecture biblique forment désormais leur propre ligne (plus de pavés de texte), tous rattachés au numéro du paragraphe (§12). Les paragraphes que la source avait collés au précédent (« …Je crois… 6. Quelqu'un m'a dit ») sont retrouvés.
- **Titre, lieu et date exacts** 🗓️ : le titre et le lieu gardent les mots du bandeau du PDF, avec une majuscule à chaque mot (« La Foi Est Une Ferme Assurance », « Oakland CA USA ») ; la date s'affiche telle qu'imprimée (« Sam 12.04.47 »). Les titres coupés par erreur (« Allumez » / « La Lumière ») sont corrigés.
- **Paragraphe entier ou alinéa seul** 🎯 : le double-clic projette tout le paragraphe (§12 et tous ses alinéas, un par ligne) ; clic droit → « Projeter cet alinéa seulement ».
- **Onglet « Livres »** 📚 : l'onglet Exposé devient « Livres ». La liste déroulante propose les deux Exposés (inchangés), *William Branham, un homme envoyé de Dieu* (introduction + 22 chapitres), *William Branham, un prophète visite l'Afrique du Sud* (préface + 5 chapitres) et 10 brochures (Au-delà du rideau du temps, La femme Jézabel, Le Messager, Le mystère de Dieu, Jésus-Christ est Dieu…). Même présentation que l'Exposé : chapitres, pages, paragraphes « page-n ». Les poèmes gardent leurs vers ; les sept brochures scannées ont été lues par l'OCR de Windows.
- **Recherche par expression exacte** 🔤 : entre guillemets, « ferme assurance » ne trouve que cette expression, dans l'ordre ; sans guillemets, tous les mots sont cherchés comme avant.
- **Nouveau logo** 🅿️ : un « P » sobre traversé d'un trait doré, comme un signal qui part à l'écran. Il habille l'icône de l'application, la barre des tâches, l'installeur et le site.
- **Nouvel écran de démarrage** ✨ : carte Windows 11 assortie au thème clair ou sombre, logo, étape de chargement en cours et barre de progression fluide.

### Changements

- **Thèmes de projection retirés** : un seul style de projection, celui de « Projection locale ». L'apparence actuelle est conservée ; les autres thèmes et les attributions par type de contenu disparaissent.
- **Les chapitres de l'Exposé n'apparaissent plus dans la liste des Sermons** (ils restent dans l'onglet Livres).
- **Cantiques hors de la recherche globale** (ils gardent leur propre recherche dans leur onglet).

### Fiabilité

- Correction d'un **plantage rare** lorsque plusieurs recherches se terminaient en même temps.
- Réglages de projection : la configuration OBS suit désormais chaque changement (cadrage des médias), sans attendre un redémarrage.
- Fermeture de l'application : les tâches en arrière-plan se terminent proprement.
- Qt for Python (PySide6, licence LGPL) remplace PyQt6.
