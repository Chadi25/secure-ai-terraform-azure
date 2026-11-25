.PHONY: test policy run fmt validate checkov plan apply destroy image push

test:            ## tests application + vérificateur
	cd app && python3 -m unittest discover -s tests -v
	python3 -m unittest discover -s policy_check/tests -v

policy:          ## règles de sécurité maison sur infra/
	python3 policy_check/check.py infra

run:             ## lancer l'API en local (http://127.0.0.1:8080)
	cd app && python3 -m ragapp

fmt:
	terraform -chdir=infra fmt -recursive

validate:
	terraform -chdir=infra init -backend=false && terraform -chdir=infra validate

checkov:
	checkov --config-file .checkov.yaml

plan:
	terraform -chdir=infra plan -out=tfplan

apply:
	terraform -chdir=infra apply tfplan

destroy:
	terraform -chdir=infra destroy

image:
	docker build -t ragapp:local app

push:            ## ACR=acrsecaixxxxx make push
	az acr login --name $(ACR)
	docker build -t $(ACR).azurecr.io/ragapp:0.1.0 app
	docker push $(ACR).azurecr.io/ragapp:0.1.0
