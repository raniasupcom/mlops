<<<<<<< HEAD
# 🚀 ML Experiment Platform with GitOps

Stack : **MLflow + PostgreSQL + MinIO + Kubernetes + Helm + ArgoCD + Docker**

---

## 📁 Structure

```
mlops-project/
├── ml-app/                         # Repo 1 — ML App
│   ├── train.py
│   ├── Dockerfile
│   └── .github/workflows/
│       └── build-push.yml          # CI → Docker Hub
│
├── mlflow-gitops/                  # Repo 2 — GitOps
│   ├── helm-values/mlflow/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       ├── deployment.yaml
│   │       ├── service.yaml
│   │       └── ingress.yaml
│   ├── environments/
│   │   ├── dev.yaml
│   │   └── prod.yaml
│   └── argocd/
│       └── application.yaml
│
└── docker-compose.yml              # Test local SANS Kubernetes
```

---

## ✅ ÉTAPE 1 — Test local rapide (Docker Compose)

> **Prérequis** : Docker Desktop installé et lancé

```bash
# Dans le dossier mlops-project/
docker compose up --build
```

### Ce qui se passe :
| Service | URL | Rôle |
|---------|-----|------|
| MLflow UI | http://localhost:5000 | Voir les runs |
| MinIO Console | http://localhost:9001 | Voir les artifacts |
| ml-trainer | — | Lance train.py une fois |

### Vérifier que ça marche :
1. Ouvrir http://localhost:5000 → voir l'expérience `iris-classification`
2. Ouvrir http://localhost:9001 (user: `minioadmin` / pass: `minioadmin123`) → voir le bucket `mlflow`

```bash
# Stopper tout
docker compose down -v
```

---

## ✅ ÉTAPE 2 — Déploiement Kubernetes avec Helm

> **Prérequis** : `kubectl`, `helm`, cluster K8s (Docker Desktop K8s ou minikube)

### 2.1 — Activer Kubernetes dans Docker Desktop
Settings → Kubernetes → Enable Kubernetes → Apply

### 2.2 — Ajouter les repos Helm Bitnami
```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

### 2.3 — Installer les dépendances du chart
```bash
cd mlflow-gitops/helm-values/mlflow
helm dependency update
```

### 2.4 — Déployer MLflow dans K8s
```bash
kubectl create namespace mlflow

helm install mlflow . \
  --namespace mlflow \
  -f values.yaml \
  -f ../../environments/dev.yaml
```

### 2.5 — Vérifier le déploiement
```bash
kubectl get pods -n mlflow
kubectl get svc -n mlflow

# Port-forward pour accéder à l'UI
kubectl port-forward svc/mlflow-mlflow 5000:5000 -n mlflow
```
→ Ouvrir http://localhost:5000

### 2.6 — Mise à jour (GitOps-style manuel)
```bash
# Modifier environments/dev.yaml puis :
helm upgrade mlflow . \
  --namespace mlflow \
  -f values.yaml \
  -f ../../environments/dev.yaml
```

---

## ✅ ÉTAPE 3 — GitOps avec ArgoCD (automatisation complète)

### 3.1 — Installer ArgoCD
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Attendre que les pods soient Ready
kubectl wait --for=condition=Ready pods --all -n argocd --timeout=120s
```

### 3.2 — Accéder à l'UI ArgoCD
```bash
# Récupérer le mot de passe admin
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo

# Port-forward
kubectl port-forward svc/argocd-server -n argocd 8080:443
```
→ Ouvrir https://localhost:8080 (user: `admin`, pass: résultat ci-dessus)

### 3.3 — Configurer le repo GitOps
```bash
# Remplacer TON_USERNAME dans argocd/application.yaml
# puis appliquer :
kubectl apply -f mlflow-gitops/argocd/application.yaml
```

### 3.4 — Tester le flux GitOps 🎯
```bash
# 1. Modifier environments/dev.yaml (ex: replicaCount: 2)
# 2. git add . && git commit -m "scale up" && git push
# 3. Dans l'UI ArgoCD → voir la sync automatique
# 4. kubectl get pods -n mlflow → voir 2 pods
```

---

## ✅ ÉTAPE 4 — CI/CD Docker Hub (GitHub Actions)

### 4.1 — Créer les secrets GitHub
Dans ton repo `ml-app` → Settings → Secrets → Actions :
- `DOCKERHUB_USERNAME` = ton username Docker Hub
- `DOCKERHUB_TOKEN` = ton token Docker Hub (hub.docker.com → Account Settings → Security)

### 4.2 — Push et vérifier
```bash
git add . && git commit -m "feat: initial ml app" && git push
```
→ GitHub Actions → voir le workflow `Build & Push` passer ✅
→ Docker Hub → voir l'image `ton-username/ml-app:latest`

---

## 🏆 Flux complet (ce que tu montres sur le CV)

```
1. git push ml-app/         → GitHub Actions build & push Docker Hub
2. git push mlflow-gitops/  → ArgoCD détecte le changement
3. ArgoCD sync              → Helm upgrade automatique
4. Kubernetes               → Nouveau pod déployé
5. MLflow UI                → Accessible via port-forward ou Ingress
```

---

## ✅ ÉTAPE 5 — Model Registry, Webhook & Serving API

> Ajoute : un Model Registry MLflow (`iris-classifier`), un service de
> serving Flask qui charge le modèle `Production`, et un webhook qui
> redémarre le pod de serving quand un modèle passe Staging → Production.

### 5.1 — Comment ça s'articule

```
train.py            -> log + REGISTER le modèle "iris-classifier" (stage None)
scripts/promote_model.py  -> transitionne une version vers Staging puis Production
                              et notifie webhook-service/app.py
webhook-service/app.py    -> reçoit l'event, fait un `kubectl rollout restart`
                              sur le Deployment ml-app-serve
ml-app/serve.py            -> Flask API ; recharge le modèle "Production" au
                              démarrage du pod (donc au restart) via /health, /predict, /reload
```

⚠️ MLflow open-source n'a pas de vrais webhooks natifs (c'est une feature
Databricks). `scripts/promote_model.py` joue ce rôle : il fait la transition
de stage **puis** appelle lui-même `webhook-service`. En CI/CD, c'est cette
commande que tu lances comme step de déploiement.

### 5.2 — Construire et pousser les nouvelles images
```bash
docker build -t YOUR_DOCKERHUB_USERNAME/ml-app-serve:latest -f ml-app/Dockerfile.serve ml-app/
docker push YOUR_DOCKERHUB_USERNAME/ml-app-serve:latest

docker build -t YOUR_DOCKERHUB_USERNAME/mlflow-webhook-service:latest webhook-service/
docker push YOUR_DOCKERHUB_USERNAME/mlflow-webhook-service:latest
```
Remplace `YOUR_DOCKERHUB_USERNAME` dans `k8s/serve-deployment.yaml` et
`k8s/webhook-deployment.yaml`.

### 5.3 — Déployer dans le cluster
```bash
kubectl apply -f k8s/webhook-deployment.yaml
kubectl apply -f k8s/serve-deployment.yaml
kubectl get pods -n mlflow
```

### 5.4 — Entraîner et enregistrer un modèle
```bash
docker compose up --build ml-trainer
```
→ crée la version 1 de `iris-classifier` dans le Model Registry (stage `None`).

### 5.5 — Tester l'API de serving
```bash
kubectl port-forward svc/ml-app-serve 8000:8000 -n mlflow

curl http://localhost:8000/health

curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"data": [[5.1, 3.5, 1.4, 0.2]]}'
```

### 5.6 — Promouvoir une version en Production (déclenche le webhook + restart)
```bash
pip install -r scripts/requirements.txt

kubectl port-forward svc/webhook-service 8001:8001 -n mlflow &

MLFLOW_TRACKING_URI=http://localhost:5000 \
WEBHOOK_URL=http://localhost:8001/webhook/mlflow \
python scripts/promote_model.py --version 1 --to-stage Production --archive-existing
```
→ `webhook-service` reçoit l'event, patch le `Deployment ml-app-serve`
(annotation `kubectl.kubernetes.io/restartedAt`) → Kubernetes redémarre les
pods → `serve.py` recharge `models:/iris-classifier/Production` au démarrage.

```bash
kubectl get pods -n mlflow -w   # observer le restart des pods ml-app-serve
```

### 5.7 — Sécuriser le webhook (optionnel)
Définis `WEBHOOK_SECRET` côté `webhook-service` (via un Secret Kubernetes
`webhook-secret`) et côté `promote_model.py` (variable d'env `WEBHOOK_SECRET`)
pour que les requêtes soient signées en HMAC-SHA256 et vérifiées.

---

## 🔧 Commandes utiles

```bash
# Voir tous les pods du projet
kubectl get pods -n mlflow -n argocd

# Logs MLflow
kubectl logs -n mlflow deploy/mlflow-mlflow

# Désinstaller MLflow
helm uninstall mlflow -n mlflow

# Reset ArgoCD
kubectl delete -f mlflow-gitops/argocd/application.yaml
```
=======
# mlops
>>>>>>> d6365f6b43bd20e046ba156071b35ae36d938e37
