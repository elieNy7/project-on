# Project-On 2.6.1

**Correctif du démarrage** 🚀 — après l'installation de la 2.6.0 par-dessus une version existante, Project-On pouvait rester figé sur l'écran de démarrage (« Ne répond pas »), puis se fermer, et recommencer au lancement suivant.

## Corrections

- **Démarrage débloqué** : la mise à jour du contenu (sermons SHP, livres) appliquée à la base existante utilisait un contrôle de doublons extrêmement lent — plus de dix minutes sur une base complète, si bien qu'elle n'aboutissait jamais. Elle prend désormais **moins d'une minute**, une seule fois, et n'est plus refaite ensuite.
- **Plus de « Ne répond pas »** : cette mise à jour et les vérifications de la base tournent en arrière-plan ; l'écran de démarrage reste animé et indique « Mise à jour du contenu (environ une minute)… ».
- **Disque préservé** : chaque tentative interrompue laissait une copie complète de la base (≈ 400 Mo) dans le dossier de données. Ces copies sont supprimées ; seule la sauvegarde de la dernière mise à jour est gardée.
- La base de contenu fournie avec l'application est lue sans écrire de fichiers dans le dossier d'installation.

## Installation

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
