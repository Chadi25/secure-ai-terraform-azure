# Maîtrise des coûts

Un budget Azure est défini au niveau du groupe de ressources avec des alertes par e-mail à 50 %, 80 % et 100 % du montant prévu. Container Apps est configuré avec zéro réplica minimum afin de ne rien facturer en calcul quand l'application ne reçoit pas de trafic.

Après la démonstration, l'ensemble est détruit avec terraform destroy. Le Key Vault reste en état supprimé réversible pendant la durée de rétention à cause de la protection contre la purge, ce qui est voulu.
