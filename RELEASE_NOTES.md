# Project-On 1.5.2

Cette mise à jour professionnalise la préparation et le déploiement de Project-On. Elle protège les données pendant les mises à niveau, fiabilise les sauvegardes SQLite et ajoute un contrôle complet avant le direct.

## Nouveautés de cette version

- **Contrôle avant service** : vérification en arrière-plan de l'intégrité de la base, des contenus, du stockage, de l'espace disque, des fichiers de projection, des écrans et de la sortie OBS/NDI.
- **Rapport support exportable** : le diagnostic peut être copié ou enregistré en texte pour accélérer l'assistance technique.
- **Sauvegarde SQLite cohérente** : la copie utilise l'API transactionnelle SQLite, inclut les transactions WAL et passe un contrôle d'intégrité avant d'être publiée.
- **Mise à niveau sans perte de données** : l'installeur ne lance plus l'ancien désinstalleur et ne supprime plus la base, les playlists ou les réglages dans AppData.
- **Désinstallation prudente** : les données utilisateur restent disponibles pour une réinstallation ou une récupération manuelle.
- **Accessibilité et feedback** : navigation clavier sur les outils de paramètres, focus visible, actions de fond désactivées pendant le traitement et états sans icônes emoji.
- **Validation renforcée** : 77 tests automatisés couvrent désormais aussi la sauvegarde, le diagnostic et la sécurité de l'installateur.

## Installation

Téléchargez **`ProjectOn_1.5.2_Setup.exe`** ci-dessous et lancez-le.
Si Windows affiche **SmartScreen** : « Informations complémentaires » → « Exécuter quand même ».
Si l'installeur est bloqué (erreur 4551), utilisez **`ProjectOn_1.5.2_Portable.zip`** : décompressez et lancez `Project-On.exe`.

Windows 10 / 11 (64 bits) · ~500 Mo · fonctionne hors-ligne.

## Crédits

Silhouettes aigle / lion / agneau : game-icons.net (Lorc, Delapouite) — CC BY 3.0.
