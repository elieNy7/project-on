# Project-On 1.10.1

**Grande passe de fiabilité** 🛠️ — deux bugs de fond corrigés (import de cantiques qui perdait des versets, index de recherche corrompu après un « Vider les cantiques »), le cache PowerPoint devient sûr, et une série d'améliorations de l'interface et des paramètres.

## Corrections

- **Import de cantiques PDF** : dans les cantiques à versets numérotés (1. 2. 3.), un verset sur deux pouvait disparaître à l'import. Tous les versets sont désormais conservés.
- **Après « Vider les cantiques »** : le ré-import d'un PDF pouvait échouer en silence (ancien index de recherche jamais purgé). L'index est reconstruit proprement à chaque suppression.
- **PowerPoint : cache sûr** — une présentation dont le rendu a été interrompu n'est plus projetée à moitié ; le rendu reprend automatiquement. Le cache se met aussi à jour si le fichier .pptx est modifié.
- **Playlists PowerPoint** : le double-clic sur un slide précis démarre bien la projection sur ce slide (et plus au premier).
- **Fermeture propre** : quitter l'application pendant une projection ne laisse plus d'écran figé en plein écran.
- **Ctrl+F** fonctionne de nouveau dans l'onglet Exposés.
- **Réglages OBS** : la fenêtre n'interroge plus l'état du serveur en continu après sa fermeture.
- **Suppression d'un média** : une confirmation est demandée, comme pour les cantiques et les playlists.
- Le bouton « Copier » des prédications ne reste plus bloqué sur « Copié ! » en cas de double-clic rapide.

## Améliorations

- **Paramètres** : nouvelle ligne « Taille de la base » dans Données & stockage, outil « Optimiser la base » plus robuste, aide des raccourcis complète (Ctrl+G, onglets 1 à 7).
- **Recherche Exposés** plus fluide : la requête est débouncée comme dans les autres onglets (plus d'une recherche par touche tapée).
- **Fiabilité** : les erreurs de base de données et de configuration sont maintenant journalisées au lieu d'être silencieuses ; la recherche d'extrait biblique de l'aperçu affiche le texte normalisé.
- **Nettoyage** : retrait de code mort dans toute l'application (base de données, parseurs, interface).

## Installation

Téléchargez **`ProjectOn_1.10.1_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.10.0

**PowerPoint et pages Web rejoignent les Médias** 🎞️🌐 — projetez vos présentations PowerPoint **avec leur design complet** (chaque slide rendue en image fidèle) et affichez des **pages web** plein écran, directement dans la fenêtre de projection ou via OBS.

## Nouveautés

- **Importer PowerPoint** (.pptx/.ppsx) : chaque slide est rendue en image haute résolution avec tout son design. Le rendu utilise Microsoft PowerPoint s'il est installé (fidélité parfaite) ou LibreOffice (gratuit) automatiquement. Les slides se naviguent avec suivant/précédent, comme le reste.
- **Ajouter un site web** : saisissez une URL (Bible en ligne, page de l'église…) — la page s'affiche **plein écran dans la projection** et peut être envoyée au navigateur OBS (iframe dédiée).
- **Dans les playlists** : un PowerPoint ajouté à une playlist développe toutes ses slides dans l'ordre ; les pages web se projettent d'un double-clic.
- **Médias** : boutons « Importer PowerPoint » et « Ajouter un site web » dans la galerie, miniatures dédiées (PPT ·, 🌐).

## Limites connues

- Le rendu PowerPoint exige Microsoft **PowerPoint** ou **LibreOffice** installés sur la machine (l'application détecte automatiquement l'un ou l'autre et vous guide sinon).
- Les animations et transitions PowerPoint ne sont pas rejouées : chaque slide est projetée comme une image figée haute résolution.
- Les pages web nécessitent une connexion internet (les adresses locales fonctionnent aussi).

## Installation

Téléchargez **`ProjectOn_1.10.0_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés. L'installeur est plus volumineux (~+180 Mo) car il embarque le moteur d'affichage web.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.9.1

**L'Aperçu montre la vidéo** : quand une vidéo est projetée, le panneau d'Aperçu affiche désormais le cadre vidéo réel (au format de la projection, letterbox), avec la lecture/pause synchronisée sur vos boutons — sans jamais prendre tout l'écran. Le son reste coupé dans l'aperçu : c'est l'écran projeté qui parle.

## Amélioration

- **Cadre vidéo dans l'Aperçu** : remplace le simple titre « 🎬 » — vous voyez la vidéo exactement comme elle sera projetée, au ratio conservé, pendant que vous pilotez Lecture / Pause / Stop.

## Installation

Téléchargez **`ProjectOn_1.9.1_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.9.0

**Project-On s'élargit : images et vidéos** 🎬 — un nouvel onglet **Médias** permet d'importer vos photos et vidéos, de les projeter plein écran, de les ajouter à vos playlists et de les envoyer vers OBS. Composez maintenant des cultes complets mêlant versets, cantiques, prédications, images d'annonce et clips vidéo.

## Nouveautés

- **Onglet « Médias »** dans la bibliothèque (Ctrl+5) : galerie de miniatures, import d'**images** (png, jpg, webp, bmp, gif) et de **vidéos** (mp4, webm, mov, mkv, avi) — les fichiers sont copiés dans la bibliothèque Project-On, plus besoin de refaire les imports.
- **Projection plein écran** : double-clic sur une image ou une vidéo pour la projeter. Les images s'affichent seules, sans voile.
- **Vidéo à contrôle manuel** : la vidéo s'affiche prête (en pause) et vous lancez la lecture quand vous voulez avec le bouton **Lecture / Pause** de l'Aperçu — **Stop** revient au début. Navigation suivant/précédent : la vidéo se coupe proprement.
- **Médias dans les playlists** : clic droit → « Ajouter à la playlist » ; dans une playlist, les vidéos se lancent à la main, les diapositives textuelles s'enchaînent normalement.
- **OBS** : les vidéos sont servies au navigateur OBS (`api/video`, lecture/pause pilotés depuis l'application).
- **Titre des Exposés dans les playlists** : les paragraphes d'Exposé ajoutés à une playlist portent désormais le titre de leur chapitre (plus de marqueurs bruts « 45-3 »).
- Raccourcis mis à jour : 7 onglets — **Ctrl+5 = Médias**, Ctrl+6 = Playlists, Ctrl+7 = Paramètres.

## Installation

Téléchargez **`ProjectOn_1.9.0_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.8.2

**Soutenez le projet ❤** — Project-On est et restera gratuit. Un nouveau bouton « Soutenir le projet » fait désormais le lien vers la page de dons, pour celles et ceux qui souhaitent aider le développement d'un coup de pouce libre.

## Nouveautés

- **Bouton « Soutenir le projet »** dans la barre latérale et dans la fenêtre « À propos » : ouvre la page de dons dans votre navigateur (aucune donnée n'est collectée, aucun paiement intégré — juste un lien).
- Le site web propose aussi le don depuis la page d'accueil.

## Installation

Téléchargez **`ProjectOn_1.8.2_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.8.1

**L'ajout à la playlist passe à la vitesse supérieure : en série.** Composez une playlist de culte en quelques clics — une plage de versets, une série de paragraphes, un cantique entier.

## Nouveautés

- **Bible — plages de versets** : clic droit dans la liste des versets → « **Ajouter une plage de versets…** » et indiquez « du 1 au 4 » : les versets demandés rejoignent la playlist en un seul ajout.
- **Prédications et Exposés — plages de paragraphes** : clic droit → « **Ajouter une plage de paragraphes…** » — « du 1 au 4 » ajoute la série complète, dans l'ordre.
- **Cantiques — toujours le cantique entier** : l'ajout à la playlist depuis un cantique ajoute désormais **toutes les strophes**, dans l'ordre du cantique — plus besoin de sélectionner.

## Installation

Téléchargez **`ProjectOn_1.8.1_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.8.0

**La passe « régie professionnelle »** : Project-On gagne les outils des régies de projection pro — aperçu du slide à venir, sauts rapides dans le programme, horloge à l'écran, playlists partageables entre ordinateurs. Basé sur vos retours : le chronomètre de culte n'a pas été ajouté et le bouton « Texte rapide » disparaît de la barre d'Aperçu pour laisser place nette.

## Nouveautés

- **Bandeau « SUIVANT »** sous l'Aperçu : pendant que le slide en cours est à l'écran, vous voyez en permanence le slide qui vient après (référence + début du texte). Fini les mauvaises surprises à la transition.
- **Sauts rapides dans le programme** : `Home` va au premier slide du programme en cours, `End` au dernier — pratique pour revenir au début d'un cantique ou sauter à la fin.
- **Horloge dans la barre d'état** : l'heure locale reste visible en permanence pendant le culte.
- **Raccourcis d'onglets corrigés** : 6 onglets, 6 raccourcis — `Ctrl+5` ouvre Playlists, `Ctrl+6` ouvre Paramètres (la liste F1 est à jour).
- **Référence des Exposés complète** : la référence projetée d'un paragraphe de l'Exposé affiche désormais le titre de l'ouvrage et du chapitre — ex. « **Exposé des Sept Âges — L'Âge de l'église de Sardes** » (et « Exposé SHP — … » pour la version Shekinah).
- **Playlists partageables** : clic droit sur une playlist → **« Exporter vers un fichier… »** (fichier `.json`) ; bouton **« Importer »** pour charger une playlist exportée sur un autre ordinateur. Idéal pour préparer le culte chez soi et le projeter à l'église.
- **Aperçu des playlists agrandi** : la zone d'aperçu du slide est désormais redimensionnable (tirez la séparation liste/aperçu) et plus haute par défaut.
- **Barre d'Aperçu épurée** : le bouton « Texte rapide » est retiré — la préparation de slides libres se fait depuis l'onglet Playlists.

## Installation

Téléchargez **`ProjectOn_1.8.0_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.6

**La section Playlists arrive** : préparez un culte entier à l'avance — annonces, versets, cantiques, extraits de prédications — regroupés en playlists, puis projetez-les en enchaînement. Rien d'autre ne change : toutes les fonctionnalités des versions précédentes sont conservées à l'identique.

## Nouveautés

- **Nouvel onglet « Playlists »** dans la bibliothèque, entre Exposés et Paramètres :
  - créez autant de **playlists** que besoin (ex. « Culte du dimanche », « Louange »), renommez-les ou supprimez-les ;
  - ajoutez des **slides** (titre + texte) à chaque playlist, modifiez-les, réordonnez-les d'un clic (↑ / ↓) ;
  - **double-clic sur un slide** (ou bouton « Projeter ») : la playlist est projetée **à partir de ce slide** — la navigation suivant/précédent enchaîne les slides suivants, avec le découpage automatique des textes longs ;
  - un aperçu du slide sélectionné reste visible pendant la préparation.
- **Liée à la bibliothèque — « Ajouter à la playlist »** dans les menus contextuels (clic droit) :
  - **Bible** : ajoutez le(s) verset(s) sélectionné(s) ou tout le chapitre ;
  - **Cantiques** : ajoutez la/les strophe(s) sélectionnée(s) ou tout le cantique ;
  - **Prédications** et **Exposés** : ajoutez le paragraphe choisi.
  - Un dialogue permet de choisir la playlist de destination ou d'en créer une à la volée.
- Les slides de playlist utilisent le même rendu que le reste de l'application : position de la référence (haut/bas), styles et transitions s'appliquent tels quels.

## Installation

Téléchargez **`ProjectOn_1.7.6_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists existantes, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.5

**La position de la référence se choisit en un clic** et l'onglet Exposé (VGR) gagne en confort de pilotage. Les nouveautés sont incluses dans l'installeur : une seule installation met à jour tout, sur le poste comme sur les nouveaux ordinateurs.

## Nouveautés

- **Position de la référence au choix** : un nouveau bouton dans la barre de l'Aperçu bascule la référence biblique **au-dessus** ou **en dessous** du texte, en direct, pendant la projection — sans ouvrir les paramètres. L'aperçu reflète immédiatement la position et le choix est mémorisé pour les prochaines sessions. (Le réglage complet reste disponible dans Paramètres → Affichage.)
- **Exposé VGR — écran plus propre** : la référence projetée d'un chapitre de l'Exposé affiche désormais **le titre du chapitre seul** (ex. « L'Église de Sardes ») au lieu de « titre - Page X-¶Y » : plus de bruit visuel pour l'assemblée.
- **Exposé VGR — suivi en direct** : pendant la navigation (suivant/précédent), le paragraphe en projection est **surligné automatiquement** dans la liste et la page correspondante s'active dans la barre de pages — l'opérateur ne perd jamais le fil.
- **Exposé VGR — projection ciblée** : un **clic droit** sur un paragraphe propose « Projeter ce paragraphe seulement » en plus du classique « Projeter le chapitre à partir d'ici ». Le bouton principal est renommé « Projeter le chapitre » pour lever toute ambiguïté.

## Installation

Téléchargez **`ProjectOn_1.7.5_Setup.exe`** ci-dessous et installez-le par-dessus la version existante : cantiques, playlists, réglages et base sont conservés.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.4

**Correction de l'Exposé appliquée automatiquement aux installations existantes** : la 1.7.3 incluait l'Exposé des Sept Âges corrigé (lectures bibliques fusionnées en un seul paragraphe, résidus de mise en page purgés) dans l'installeur, mais les ordinateurs qui avaient déjà Project-On gardaient leur ancien Exposé — la base utilisateur n'est jamais écrasée (cantiques, playlists et réglages préservés). Désormais, au premier démarrage, l'application applique le pack de données corrigé aux bases existantes.

## Corrections

- **Pack de données** : au premier démarrage, les chapitres de l'Exposé des Sept Âges (VGR) sont remplacés par la version corrigée — lectures bibliques d'ouverture en un seul paragraphe, plus aucun résidu de mise en page (« … aux Églises. SARDES » etc.). Les cantiques importés, playlists et réglages sont conservés.
- **Titres exacts garantis sur toutes les installations** (correctif 1.7.3 consolidé) : toute base dont les titres canoniques SHP diffèrent des titres des PDF est recalculée au démarrage.
- La base de données corrigée reste incluse dans l'installeur pour les installations fraîches.
- Installeur et application signés numériquement (éditeur « Elie Nyembo / Project-On », horodatage DigiCert).

## Installation

Téléchargez **`ProjectOn_1.7.4_Setup.exe`** ci-dessous et installez-le par-dessus la version existante, puis lancez Project-On une fois : la correction de l'Exposé et des titres s'applique au démarrage (le premier lancement peut prendre une minute de plus, le temps de resynchroniser l'index de recherche).

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.3

**Correctif important pour les mises à jour** : sur les ordinateurs où une ancienne version de Project-On était déjà installée, la 1.7.2 pouvait encore afficher les anciens titres de prédications. La cause est corrigée : la vérification « données prêtes » du démarrage détecte désormais une base dont les titres SHP diffèrent des titres des PDF et le recalcul s'applique alors automatiquement, sans ré-import ni réinstallation.

## Corrections

- **Titres exacts garantis sur toutes les installations** : au premier démarrage, une base existante dont les titres canoniques SHP diffèrent des titres source est recalculée automatiquement.
- La base de données corrigée reste incluse dans l'installeur (titres SHP exacts, Exposé VGR avec lectures bibliques fusionnées et résidus purgés, index resynchronisé).
- Installeur et application signés numériquement (éditeur « Elie Nyembo / Project-On », horodatage DigiCert).

## Installation

Téléchargez **`ProjectOn_1.7.3_Setup.exe`** ci-dessous et installez-le par-dessus la version existante, puis lancez Project-On une fois : les titres se mettent à jour au démarrage.

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.2

Cette version accompagne la grande mise à jour des données : **la base de données corrigée est incluse dans l'installeur**. À la première installation, les prédications et l'Exposé des Sept Âges sont déjà exacts, sans aucun ré-import manuel.

## Nouveautés de cette version

- **Base de données corrigée incluse** : titres de prédications SHP exacts comme imprimés dans les PDF (« LA COMMUNION », « EXPERIENCES 1 / 2 / 3 » distincts…), lieu réintégré dans la recherche, index de recherche resynchronisé (418 299 paragraphes).
- **Exposé des Sept Âges (VGR) corrigé** : la lecture biblique d'ouverture de chaque chapitre forme un seul paragraphe, et les résidus de mise en page des PDF (titres de section collés type « … aux Églises. SARDES ») sont purgés.
- **Mise à jour automatique des bases existantes** : au premier démarrage, l'application recalcule les titres canoniques des bases déjà présentes — les installations antérieures affichent les titres exacts sans ré-import.
- **Installeur signé numériquement** : éditeur « Elie Nyembo / Project-On » vérifié avec horodatage DigiCert.
- **Fiabilité** : 108 tests validés (interface, projection, scènes OBS, import SHP, fusion de lecture de l'Exposé).

## Installation

Téléchargez **`ProjectOn_1.7.2_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

# Project-On 1.7.1

Cette version est une passe complète de finition sur le poste opérateur : corrections de défauts d'interface accumulés, retour d'une fonction perdue et harmonisation visuelle. Aucune donnée n'est modifiée ; tous les réglages existants sont conservés.

## Nouveautés et corrections

- **Édition rapide de retour** : le bouton crayon dans la console de l'aperçu permet de corriger la référence ou le texte de la slide en direct (utile pour rectifier une faute pendant le culte). Le bouton n'est actif que lorsqu'une slide est chargée.
- **État vide du moniteur** : quand aucun programme n'est chargé, l'écran d'aperçu affiche une invite claire « Prêt à projeter » au lieu d'un cadre noir silencieux.
- **Badge LIVE réparé** : la taille de police du badge « LIVE / PREVIEW » était cassée par une erreur de feuille de style (texte brut au lieu d'une valeur) ; les couleurs passent désormais par la palette du thème (vert quand le direct est actif).
- **Touche Espace corrigée** : Espace masque/affiche la sortie uniquement lorsque le focus n'est pas sur un bouton, un champ ou une liste — les boutons reçoivent de nouveau leur Espace (activation au clavier possible).
- **Bouton « Texte rapide » complet** : le libellé n'est plus tronqué (« TEXTE RAPIDE » s'affiche en entier, largeur mesurée en majuscules).
- **Filtres Prédications** : retrait des emojis des listes « Toutes années / Sans date / Toutes traductions » qui s'affichaient en carrés et tronquaient les libellés.
- **Bibliothèque Bible** : l'intitulé de la liste affiche « Livres » (et non plus « Bible »), avec un texte d'aide dédié dans l'aperçu de verset.
- **Barre latérale** : suppression du double branding — l'en-tête porte la marque, le pied affiche la version réelle de l'application.
- **Barre d'état** : la pastille compteur « n / total » disparaît quand il n'y a rien à compter.
- **Titres de prédications exacts** : la traduction SHP affiche désormais le titre imprimé dans le bandeau du PDF, à la lettre (fin des titres fusionnés ou recasés comme « LA COMMUNION » devenu « Communion », ou « EXPERIENCES 1/2/3 » réduits à un seul titre). Le lieu est de nouveau pris en compte dans la recherche.
- **Exposé des Sept Âges (VGR)** : la lecture biblique d'ouverture de chaque chapitre (référence « Apocalypse x.y-z » + versets) forme un seul paragraphe, calculée sur trois signaux (référence, nombre de versets annoncé, longueur). Les résidus de mise en page sont purgés (« … aux Églises. SARDES » etc.) — 1 681 paragraphes revalidés en 1 616.
- **Import SHP en mode catalogue** : nouvelle option `--metadata-only` pour n'importer que le titre exact, la date et le lieu sans le texte.
- **Maintenance de la base** : nouvel outil `tools/rebuild_sermon_metadata.py` (titres canoniques, index de recherche, ANALYZE, compactage) ; correction de la resynchronisation de l'index après import (lignes orphelines détectées et éliminées — 418 299 paragraphes synchronisés).
- **Fiabilité** : suppression du doublon complet de la classe `LibraryPanel` (la seconde définition écrasait la première en silence), nettoyage du code mort hérité de l'ancienne UI à onglets et de la feuille de style `style.qss` jamais chargée.

## Installation

Téléchargez **`ProjectOn_1.7.1_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».

Windows 10 / 11 (64 bits) · fonctionne hors-ligne.

---

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
